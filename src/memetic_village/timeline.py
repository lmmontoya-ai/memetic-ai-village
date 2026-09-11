from __future__ import annotations

import bisect
import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import INTERIM, PROCESSED, RAW, ROOT, ensure_output_dirs
from .util import iso_utc, json_text, parse_timestamp, stable_id, stream_jsonl

EVENT_SCHEMA = pa.schema(
    [
        ("canonical_event_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("event_type", pa.string()),
        ("actor_agent_id", pa.string()),
        ("recipient_agent_ids", pa.string()),
        ("room_or_channel_id", pa.string()),
        ("goal_id", pa.string()),
        ("model_id", pa.string()),
        ("scaffold_version", pa.string()),
        ("source_table", pa.string()),
        ("source_record_id", pa.string()),
        ("parent_event_id", pa.string()),
        ("content_reference", pa.string()),
        ("artifact_reference", pa.string()),
        ("memory_version_before", pa.string()),
        ("memory_version_after", pa.string()),
        ("visibility_metadata", pa.string()),
        ("source_order", pa.int64()),
        ("ordering_priority", pa.int16()),
        ("is_holdout", pa.bool_()),
    ]
)

ACTION_TYPES = {
    "AGENT_TALK": "message_sent",
    "USER_TALK": "human_message_sent",
    "START_USING_COMPUTER": "computer_session_started",
    "STOP_USING_COMPUTER": "computer_session_stopped",
    "CONSOLIDATE": "memory_consolidation",
    "WAIT": "wait",
    "PAUSE": "pause",
    "SEARCH_HISTORY": "history_search",
    "ENTER_ROOM": "room_joined",
    "REQUEST_HUMAN_HELPER": "human_intervention_requested",
    "CANCEL_REQUEST_FOR_HUMAN_HELPER": "human_intervention_cancelled",
    "STOP_HUMAN_USE_SESSION": "human_intervention_stopped",
    "OUTREACH_APPROVAL_REQUEST": "outreach_approval_requested",
    "OUTREACH_APPROVAL_RESPONSE": "outreach_approval_decided",
    "REQUEST_GOOGLE_SIGN_IN": "human_intervention_requested",
    "RESTARTING_AFTER_GOOGLE_SIGN_IN": "human_intervention_completed",
}


def scaffold_version(timestamp: datetime | None, model_id: str | None) -> str | None:
    if timestamp is None:
        return None
    if model_id and model_id.startswith("claude-code::"):
        return "claude-code-agent-sdk"
    if timestamp >= datetime(2026, 6, 11, tzinfo=UTC):
        return "perma-computer-rooms-unseen-cap-200"
    if timestamp >= datetime(2026, 3, 24, tzinfo=UTC):
        return "perma-computer-rooms-v1"
    if timestamp >= datetime(2026, 2, 25, tzinfo=UTC):
        return "session-computer-rooms-v1"
    if timestamp >= datetime(2025, 8, 20, tzinfo=UTC):
        return "session-computer-limited-chat-context"
    if timestamp >= datetime(2025, 5, 2, tzinfo=UTC):
        return "session-computer-interleaved-chat"
    return "launch-scaffold"


class GoalLookup:
    def __init__(self) -> None:
        self.by_agent: dict[str, list[tuple[datetime, datetime | None, str]]] = defaultdict(list)
        for row in stream_jsonl(RAW / "agent_goals.jsonl.gz"):
            start = parse_timestamp(row.get("start_time")) or parse_timestamp(row.get("created_at"))
            end = parse_timestamp(row.get("end_time"))
            if start and row.get("agent_id"):
                self.by_agent[row["agent_id"]].append((start, end, row.get("id")))
        for intervals in self.by_agent.values():
            intervals.sort()

    def at(self, timestamp: datetime | None, agent_id: str | None = None) -> str | None:
        intervals = self.by_agent.get(agent_id or "", [])
        if timestamp is None or not intervals:
            return None
        starts = [item[0] for item in intervals]
        position = bisect.bisect_right(starts, timestamp) - 1
        if position < 0:
            return None
        start, end, goal_id = intervals[position]
        return goal_id if timestamp >= start and (end is None or timestamp <= end) else None


class EventWriter:
    def __init__(self, path: Path, batch_size: int = 25_000) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = pq.ParquetWriter(path, EVENT_SCHEMA, compression="zstd")
        self.batch_size = batch_size
        self.rows: list[dict[str, Any]] = []
        self.counts: dict[str, int] = defaultdict(int)

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        self.counts[row["source_table"]] += 1
        if len(self.rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if self.rows:
            self.writer.write_table(pa.Table.from_pylist(self.rows, schema=EVENT_SCHEMA))
            self.rows.clear()

    def close(self) -> None:
        self.flush()
        self.writer.close()


def _event_time_bounds() -> tuple[datetime, datetime, datetime]:
    minimum: datetime | None = None
    maximum: datetime | None = None
    for row in stream_jsonl(RAW / "events.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        if timestamp:
            minimum = timestamp if minimum is None else min(minimum, timestamp)
            maximum = timestamp if maximum is None else max(maximum, timestamp)
    if minimum is None or maximum is None:
        raise ValueError("events table contains no valid timestamp")
    cutoff = minimum + (maximum - minimum) * 0.8
    return minimum, maximum, cutoff


def _base_row(
    *,
    source_table: str,
    source_record_id: str,
    timestamp: datetime | None,
    event_type: str,
    holdout_cutoff: datetime,
    actor: str | None = None,
    recipients: list[str] | None = None,
    room: str | None = None,
    goal: str | None = None,
    model: str | None = None,
    parent: str | None = None,
    content: str | None = None,
    artifact: str | None = None,
    memory_before: str | None = None,
    memory_after: str | None = None,
    visibility: dict[str, Any] | None = None,
    source_order: int | None = None,
    priority: int = 50,
) -> dict[str, Any]:
    return {
        "canonical_event_id": stable_id(source_table, source_record_id, event_type),
        "timestamp": timestamp,
        "event_type": event_type,
        "actor_agent_id": actor,
        "recipient_agent_ids": json_text(recipients or []),
        "room_or_channel_id": room,
        "goal_id": goal,
        "model_id": model,
        "scaffold_version": scaffold_version(timestamp, model),
        "source_table": source_table,
        "source_record_id": source_record_id,
        "parent_event_id": parent,
        "content_reference": content,
        "artifact_reference": artifact,
        "memory_version_before": memory_before,
        "memory_version_after": memory_after,
        "visibility_metadata": json_text(visibility or {}),
        "source_order": source_order,
        "ordering_priority": priority,
        "is_holdout": bool(timestamp and timestamp >= holdout_cutoff),
    }


def build_timeline() -> dict[str, Any]:
    ensure_output_dirs()
    minimum, maximum, cutoff = _event_time_bounds()
    agents = {row["id"]: row for row in stream_jsonl(RAW / "agents.jsonl.gz")}
    sessions = {
        row["id"]: row.get("agent_id")
        for row in stream_jsonl(RAW / "computer_use_sessions.jsonl.gz")
    }
    goals = GoalLookup()
    linked_message_ids: set[str] = set()
    unsorted_path = INTERIM / "canonical_events_unsorted.parquet"
    writer = EventWriter(unsorted_path)

    for row in stream_jsonl(RAW / "events.jsonl.gz"):
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        action_type = data.get("actionType") or "UNKNOWN"
        event_type = ACTION_TYPES.get(action_type, action_type.lower())
        timestamp = parse_timestamp(row.get("created_at"))
        actor = data.get("speakerId") if action_type == "AGENT_TALK" else data.get("agentId")
        model = agents.get(actor, {}).get("model_string") if actor else None
        message_id = data.get("messageId")
        if message_id:
            linked_message_ids.add(message_id)
        session_id = data.get("computerUseSessionId")
        parent = (
            stable_id("computer_use_sessions", session_id, "computer_session_recorded")
            if session_id
            else None
        )
        content = f"raw://chat_messages/{message_id}#content" if message_id else None
        if action_type == "SEARCH_HISTORY":
            content = f"raw://events/{row['id']}#data.answerToQuery"
        writer.add(
            _base_row(
                source_table="events",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type=event_type,
                holdout_cutoff=cutoff,
                actor=actor,
                room=data.get("roomId"),
                goal=goals.at(timestamp, actor),
                model=model,
                parent=parent,
                content=content,
                visibility={
                    "raw_action_type": action_type,
                    "prompt_inclusion_exported": False,
                },
                source_order=row.get("event_index"),
                priority=20,
            )
        )

    for row in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        if row["id"] in linked_message_ids:
            continue
        timestamp = parse_timestamp(row.get("created_at"))
        actor = row.get("agent_speaker_id")
        event_type = "message_sent" if actor else "human_message_sent"
        writer.add(
            _base_row(
                source_table="chat_messages",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type=event_type,
                holdout_cutoff=cutoff,
                actor=actor,
                room=row.get("room_id"),
                goal=goals.at(timestamp, actor),
                model=agents.get(actor, {}).get("model_string") if actor else None,
                content=f"raw://chat_messages/{row['id']}#content",
                visibility={"event_link_missing": True, "prompt_inclusion_exported": False},
                priority=21,
            )
        )

    for row in stream_jsonl(RAW / "computer_use_sessions.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        actor = row.get("agent_id")
        writer.add(
            _base_row(
                source_table="computer_use_sessions",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type="computer_session_recorded",
                holdout_cutoff=cutoff,
                actor=actor,
                goal=goals.at(timestamp, actor),
                model=agents.get(actor, {}).get("model_string"),
                content=f"raw://computer_use_sessions/{row['id']}#session_goal",
                priority=30,
            )
        )

    for row in stream_jsonl(RAW / "computer_use_turns.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        actor = sessions.get(row.get("session_id"))
        action = row.get("agent_action")
        if action is not None:
            event_type = "tool_call"
        elif row.get("output") is not None or row.get("error") is not None:
            event_type = "tool_result"
        else:
            event_type = "model_response"
        writer.add(
            _base_row(
                source_table="computer_use_turns",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type=event_type,
                holdout_cutoff=cutoff,
                actor=actor,
                goal=goals.at(timestamp, actor),
                model=agents.get(actor, {}).get("model_string") if actor else None,
                parent=stable_id(
                    "computer_use_sessions", row.get("session_id"), "computer_session_recorded"
                ),
                content=f"raw://computer_use_turns/{row['id']}#agent_messages",
                artifact=f"raw://computer_use_turns/{row['id']}#agent_action"
                if action is not None
                else None,
                visibility={"screenshot_redacted": row.get("screenshot_is_redacted")},
                priority=40,
            )
        )

    memories: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for row in stream_jsonl(RAW / "agent_memories.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        if timestamp and row.get("agent_id"):
            memories[row["agent_id"]].append((timestamp, row["id"]))
    for actor, versions in memories.items():
        versions.sort()
        previous = None
        for timestamp, memory_id in versions:
            writer.add(
                _base_row(
                    source_table="agent_memories",
                    source_record_id=memory_id,
                    timestamp=timestamp,
                    event_type="memory_updated",
                    holdout_cutoff=cutoff,
                    actor=actor,
                    goal=goals.at(timestamp, actor),
                    model=agents.get(actor, {}).get("model_string"),
                    content=f"raw://agent_memories/{memory_id}#content",
                    memory_before=previous,
                    memory_after=memory_id,
                    priority=45,
                )
            )
            previous = memory_id

    for table in ("agent_goals",):
        for row in stream_jsonl(RAW / f"{table}.jsonl.gz"):
            timestamp = parse_timestamp(row.get("start_time")) or parse_timestamp(
                row.get("created_at")
            )
            actor = row.get("agent_id")
            writer.add(
                _base_row(
                    source_table=table,
                    source_record_id=row["id"],
                    timestamp=timestamp,
                    event_type="goal_assigned",
                    holdout_cutoff=cutoff,
                    actor=actor,
                    goal=row["id"],
                    model=agents.get(actor, {}).get("model_string") if actor else None,
                    content=f"raw://{table}/{row['id']}#goal",
                    priority=10,
                )
            )

    for row in agents.values():
        timestamp = parse_timestamp(row.get("created_at"))
        writer.add(
            _base_row(
                source_table="agents",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type="model_or_scaffold_change",
                holdout_cutoff=cutoff,
                actor=row["id"],
                model=row.get("model_string"),
                content=f"raw://agents/{row['id']}#model_string",
                priority=5,
            )
        )

    for row in stream_jsonl(RAW / "claude_code_sessions.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        actor = row.get("agent_id")
        writer.add(
            _base_row(
                source_table="claude_code_sessions",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type="computer_session_recorded",
                holdout_cutoff=cutoff,
                actor=actor,
                model=agents.get(actor, {}).get("model_string"),
                priority=30,
            )
        )
    for row in stream_jsonl(RAW / "claude_code_messages.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        actor = row.get("agent_id")
        message_type = row.get("message_type")
        event_type = {
            "assistant": "model_response",
            "user": "tool_result",
            "system": "scaffold_message",
            "result": "tool_result",
        }.get(message_type, "claude_code_message")
        writer.add(
            _base_row(
                source_table="claude_code_messages",
                source_record_id=row["id"],
                timestamp=timestamp,
                event_type=event_type,
                holdout_cutoff=cutoff,
                actor=actor,
                model=agents.get(actor, {}).get("model_string"),
                parent=stable_id("claude_code_sdk", row.get("sdk_session_id"), "session"),
                content=f"raw://claude_code_messages/{row['id']}#content",
                priority=41,
            )
        )

    _add_changelog_events(writer, cutoff)
    writer.close()

    return finalize_timeline(
        unsorted_path=unsorted_path,
        minimum=minimum,
        maximum=maximum,
        cutoff=cutoff,
        source_counts=dict(writer.counts),
    )


def finalize_timeline(
    *,
    unsorted_path: Path | None = None,
    minimum: datetime | None = None,
    maximum: datetime | None = None,
    cutoff: datetime | None = None,
    source_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    unsorted_path = unsorted_path or (INTERIM / "canonical_events_unsorted.parquet")
    if minimum is None or maximum is None or cutoff is None:
        minimum, maximum, cutoff = _event_time_bounds()

    target = PROCESSED / "canonical_events.parquet"
    target.unlink(missing_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET TimeZone='UTC'")
    source_sql = str(unsorted_path.resolve()).replace("'", "''").replace("\\", "/")
    target_sql = str(target.resolve()).replace("'", "''").replace("\\", "/")
    boundary = con.execute(
        f"""
        SELECT min(timestamp)::VARCHAR, max(timestamp)::VARCHAR,
               quantile_disc(timestamp, 0.8)::VARCHAR
        FROM read_parquet('{source_sql}')
        WHERE timestamp IS NOT NULL
        """
    ).fetchone()
    minimum = parse_timestamp(boundary[0])
    maximum = parse_timestamp(boundary[1])
    cutoff = parse_timestamp(boundary[2])
    con.execute(
        f"""
        COPY (
          WITH source AS (
            SELECT * EXCLUDE (is_holdout),
                   timestamp >= TIMESTAMPTZ '{iso_utc(cutoff)}' AS is_holdout
            FROM read_parquet('{source_sql}')
          )
          SELECT row_number() OVER (
                     ORDER BY timestamp NULLS LAST, ordering_priority,
                              source_order NULLS LAST, canonical_event_id
                 ) AS event_order,
                 *
          FROM source
        ) TO '{target_sql}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
        """
    )
    validation = con.execute(
        """
        SELECT count(*) AS rows,
               count(DISTINCT canonical_event_id) AS unique_ids,
               sum(is_holdout::INTEGER) AS holdout_rows,
               min(timestamp)::VARCHAR, max(timestamp)::VARCHAR
        FROM read_parquet(?)
        """,
        [str(target)],
    ).fetchone()
    if source_counts is None:
        source_counts = dict(
            con.execute(
                "SELECT source_table, count(*) FROM read_parquet(?) GROUP BY source_table",
                [str(target)],
            ).fetchall()
        )
    con.close()
    holdout = {
        "policy": "first 80% of chronologically ordered canonical event records is discovery; final 20% is holdout",
        "minimum": iso_utc(minimum),
        "maximum": iso_utc(maximum),
        "cutoff": iso_utc(cutoff),
        "content_inspected_to_choose_cutoff": False,
        "canonical_rows": validation[0],
        "holdout_rows": validation[2],
    }
    (ROOT / "data" / "raw_manifest" / "holdout.json").write_text(
        json.dumps(holdout, indent=2) + "\n", encoding="utf-8"
    )
    result = {
        "path": str(target.relative_to(ROOT)),
        "rows": validation[0],
        "unique_ids": validation[1],
        "holdout_rows": validation[2],
        "minimum": str(validation[3]),
        "maximum": str(validation[4]),
        "source_counts": source_counts,
    }
    (ROOT / "reports" / "timeline_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _add_changelog_events(writer: EventWriter, cutoff: datetime) -> None:
    pattern = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?:\b| to )")
    for line_number, line in enumerate(
        (RAW / "CHANGELOG.md").read_text(encoding="utf-8").splitlines(), 1
    ):
        match = pattern.match(line)
        if not match:
            continue
        timestamp = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
        record_id = f"line-{line_number}-{match.group(1)}"
        writer.add(
            _base_row(
                source_table="CHANGELOG.md",
                source_record_id=record_id,
                timestamp=timestamp,
                event_type="scaffold_change",
                holdout_cutoff=cutoff,
                content=f"raw://CHANGELOG.md#L{line_number}",
                priority=1,
            )
        )


def retrieve_history(
    *,
    agent_id: str | None = None,
    goal_id: str | None = None,
    event_id: str | None = None,
    hours: int = 24,
    limit: int = 500,
) -> list[dict[str, Any]]:
    path = PROCESSED / "canonical_events.parquet"
    con = duckdb.connect()
    if event_id:
        center = con.execute(
            "SELECT timestamp FROM read_parquet(?) WHERE canonical_event_id = ?",
            [str(path), event_id],
        ).fetchone()
        if not center:
            raise KeyError(f"Unknown canonical event: {event_id}")
        start, end = center[0] - timedelta(hours=hours), center[0] + timedelta(hours=hours)
        query = """
            SELECT * FROM read_parquet(?)
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY event_order LIMIT ?
        """
        params: list[Any] = [str(path), start, end, limit]
    elif agent_id:
        query = """
            SELECT * FROM read_parquet(?)
            WHERE actor_agent_id = ? ORDER BY event_order LIMIT ?
        """
        params = [str(path), agent_id, limit]
    elif goal_id:
        query = """
            SELECT * FROM read_parquet(?)
            WHERE goal_id = ? ORDER BY event_order LIMIT ?
        """
        params = [str(path), goal_id, limit]
    else:
        raise ValueError("Specify agent_id, goal_id, or event_id")
    cursor = con.execute(query, params)
    columns = [item[0] for item in cursor.description]
    result = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    con.close()
    return result
