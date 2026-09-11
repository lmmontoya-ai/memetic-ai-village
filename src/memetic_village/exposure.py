"""LEGACY V1 — INVALID PROXY first-subsequent-decision graph.

VisibilityIndex room/message metadata remains reusable; v2 does not use these edge confidences.
"""

from __future__ import annotations

import bisect
import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import (
    CHAT_LIMIT_INTRODUCED,
    PROCESSED,
    RANDOM_SEED,
    RAW,
    REPORTS,
    ROOMS_INTRODUCED,
    ROOT,
    ensure_output_dirs,
)
from .util import iso_utc, parse_timestamp, stable_id, stream_jsonl

EXPOSURE_SCHEMA = pa.schema(
    [
        ("edge_id", pa.string()),
        ("source_agent_id", pa.string()),
        ("recipient_agent_id", pa.string()),
        ("source_event_id", pa.string()),
        ("source_message_id", pa.string()),
        ("available_at", pa.timestamp("us", tz="UTC")),
        ("decision_event_id", pa.string()),
        ("decision_timestamp", pa.timestamp("us", tz="UTC")),
        ("room_id", pa.string()),
        ("confidence", pa.string()),
        ("available", pa.bool_()),
        ("prompt_inclusion_confirmed", pa.bool_()),
        ("rule_id", pa.string()),
        ("explanation", pa.string()),
        ("is_holdout", pa.bool_()),
    ]
)


@dataclass(frozen=True)
class ExposureAssessment:
    confidence: str
    available: bool
    prompt_inclusion_confirmed: bool
    rule_id: str
    explanation: str
    source_timestamp: str | None = None
    decision_timestamp: str | None = None
    source_room_id: str | None = None
    recipient_room_id: str | None = None


class VisibilityIndex:
    def __init__(self) -> None:
        self.agents = {row["id"]: row for row in stream_jsonl(RAW / "agents.jsonl.gz")}
        self.message_events: dict[str, tuple[str, datetime, str | None, str | None]] = {}
        self.event_to_message: dict[str, str] = {}
        self.room_moves: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        previous_rooms: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        for row in stream_jsonl(RAW / "events.jsonl.gz"):
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            timestamp = parse_timestamp(row.get("created_at"))
            message_id = data.get("messageId")
            if message_id and timestamp:
                canonical = stable_id(
                    "events",
                    row["id"],
                    "message_sent"
                    if data.get("actionType") == "AGENT_TALK"
                    else "human_message_sent",
                )
                self.message_events[message_id] = (
                    canonical,
                    timestamp,
                    data.get("speakerId"),
                    data.get("roomId"),
                )
                self.event_to_message[canonical] = message_id
            if data.get("actionType") == "ENTER_ROOM" and timestamp and data.get("agentId"):
                room_id = data.get("roomId") or data.get("newRoomId")
                if room_id:
                    self.room_moves[data["agentId"]].append((timestamp, room_id))
                if data.get("previousRoomId"):
                    previous_rooms[data["agentId"]].append((timestamp, data["previousRoomId"]))
        rooms_start = parse_timestamp(ROOMS_INTRODUCED)
        if rooms_start:
            for agent_id, values in previous_rooms.items():
                earliest_previous = min(values)[1]
                self.room_moves[agent_id].append((rooms_start, earliest_previous))
        for moves in self.room_moves.values():
            moves.sort()

        self.decisions: dict[str, list[tuple[int, str]]] = defaultdict(list)
        con = duckdb.connect()
        cursor = con.execute(
            """
            SELECT epoch_us(timestamp), canonical_event_id, actor_agent_id
            FROM read_parquet(?)
            WHERE timestamp IS NOT NULL AND actor_agent_id IS NOT NULL
            ORDER BY actor_agent_id, timestamp, canonical_event_id
            """,
            [str(PROCESSED / "canonical_events.parquet")],
        )
        while batch := cursor.fetchmany(100_000):
            for timestamp_us, event_id, actor_id in batch:
                self.decisions[actor_id].append((timestamp_us, event_id))
        con.close()
        for decisions in self.decisions.values():
            decisions.sort()
        self.created = {
            agent_id: _timestamp_us(parse_timestamp(row.get("created_at")))
            for agent_id, row in self.agents.items()
        }
        self.last_active = {
            agent_id: decisions[-1][0]
            for agent_id, decisions in self.decisions.items()
            if decisions
        }

    def room_at(self, agent_id: str, timestamp: datetime) -> str | None:
        if timestamp < parse_timestamp(ROOMS_INTRODUCED):
            return "__global__"
        moves = self.room_moves.get(agent_id, [])
        position = bisect.bisect_right(moves, (timestamp, chr(0x10FFFF))) - 1
        return moves[position][1] if position >= 0 else None

    def next_decision(
        self, agent_id: str, timestamp: datetime, maximum_delay: timedelta = timedelta(days=7)
    ) -> tuple[datetime | None, str | None]:
        rows = self.decisions.get(agent_id, [])
        source_us = _timestamp_us(timestamp)
        maximum_us = source_us + int(maximum_delay.total_seconds() * 1_000_000)
        position = bisect.bisect_right(rows, (source_us, chr(0x10FFFF)))
        if position >= len(rows) or rows[position][0] > maximum_us:
            return None, None
        return _datetime_us(rows[position][0]), rows[position][1]

    def is_active(self, agent_id: str, timestamp: datetime) -> bool:
        created = self.created.get(agent_id)
        last = self.last_active.get(agent_id)
        timestamp_us = _timestamp_us(timestamp)
        return bool(created and last and created <= timestamp_us <= last)

    def assess(
        self,
        recipient_id: str,
        source_event_id: str,
        decision_timestamp: datetime,
    ) -> ExposureAssessment:
        message_id = self.event_to_message.get(source_event_id)
        if not message_id:
            return ExposureAssessment(
                "unknown",
                False,
                False,
                "source_not_chat_message",
                "Source event is not a mapped chat message.",
            )
        _, source_time, source_agent, source_room = self.message_events[message_id]
        if decision_timestamp <= source_time:
            return ExposureAssessment(
                "ruled_out",
                False,
                False,
                "future_to_past",
                "The recipient decision is not later than the source item.",
                iso_utc(source_time),
                iso_utc(decision_timestamp),
                source_room,
                self.room_at(recipient_id, decision_timestamp),
            )
        if recipient_id == source_agent:
            return ExposureAssessment(
                "ruled_out", False, False, "self_edge", "Source and recipient are the same agent."
            )
        recipient_room = self.room_at(recipient_id, source_time)
        if source_time < parse_timestamp(ROOMS_INTRODUCED):
            if source_time < parse_timestamp(CHAT_LIMIT_INTRODUCED):
                return ExposureAssessment(
                    "probable",
                    True,
                    False,
                    "global_pre_limit",
                    "Global chat and the later documented context-limit change support probable availability; exact prompt is absent.",
                    iso_utc(source_time),
                    iso_utc(decision_timestamp),
                    "__global__",
                    "__global__",
                )
            return ExposureAssessment(
                "possible",
                True,
                False,
                "global_limited_context",
                "Global channel access is compatible, but chat truncation makes prompt inclusion uncertain.",
                iso_utc(source_time),
                iso_utc(decision_timestamp),
                "__global__",
                "__global__",
            )
        if recipient_room is None or source_room is None:
            return ExposureAssessment(
                "unknown",
                False,
                False,
                "historic_room_unknown",
                "No historic room state is exported for one side at the source time.",
                iso_utc(source_time),
                iso_utc(decision_timestamp),
                source_room,
                recipient_room,
            )
        if recipient_room != source_room:
            return ExposureAssessment(
                "ruled_out",
                False,
                False,
                "different_known_rooms",
                "Rooms v1 records place source and recipient in different rooms.",
                iso_utc(source_time),
                iso_utc(decision_timestamp),
                source_room,
                recipient_room,
            )
        return ExposureAssessment(
            "possible",
            True,
            False,
            "same_room_limited_context",
            "Known same-room membership supports availability, but prompt inclusion is not exported.",
            iso_utc(source_time),
            iso_utc(decision_timestamp),
            source_room,
            recipient_room,
        )


def could_observe(
    recipient_id: str, source_event_id: str, decision_timestamp: str | datetime
) -> ExposureAssessment:
    timestamp = (
        parse_timestamp(decision_timestamp)
        if isinstance(decision_timestamp, str)
        else decision_timestamp.astimezone(UTC)
    )
    if timestamp is None:
        raise ValueError("decision_timestamp must be a valid timestamp")
    return VisibilityIndex().assess(recipient_id, source_event_id, timestamp)


def _timestamp_us(timestamp: datetime | None) -> int:
    if timestamp is None:
        return 0
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = timestamp.astimezone(UTC) - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _datetime_us(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC)


def build_exposures() -> dict[str, Any]:
    ensure_output_dirs()
    index = VisibilityIndex()
    holdout = json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())
    cutoff = parse_timestamp(holdout["cutoff"])
    target = PROCESSED / "exposures.parquet"
    writer = pq.ParquetWriter(target, EXPOSURE_SCHEMA, compression="zstd")
    buffer: list[dict[str, Any]] = []

    for message in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        source_agent = message.get("agent_speaker_id")
        mapped = index.message_events.get(message["id"])
        if not source_agent or not mapped:
            continue
        timestamp = mapped[1]
        source_event_id = mapped[0]
        for recipient_id in index.agents:
            if recipient_id == source_agent or not index.is_active(recipient_id, timestamp):
                continue
            decision_time, decision_event = index.next_decision(recipient_id, timestamp)
            if decision_time is None:
                assessment = ExposureAssessment(
                    "unknown",
                    False,
                    False,
                    "no_subsequent_decision",
                    "No recipient event occurs within the seven-day decision window.",
                    iso_utc(timestamp),
                    None,
                    mapped[3],
                    index.room_at(recipient_id, timestamp),
                )
            else:
                assessment = index.assess(recipient_id, source_event_id, decision_time)
            row = {
                "edge_id": stable_id(source_event_id, recipient_id, decision_event, prefix="edge"),
                "source_agent_id": source_agent,
                "recipient_agent_id": recipient_id,
                "source_event_id": source_event_id,
                "source_message_id": message["id"],
                "available_at": timestamp,
                "decision_event_id": decision_event,
                "decision_timestamp": decision_time,
                "room_id": mapped[3],
                "confidence": assessment.confidence,
                "available": assessment.available,
                "prompt_inclusion_confirmed": assessment.prompt_inclusion_confirmed,
                "rule_id": assessment.rule_id,
                "explanation": assessment.explanation,
                "is_holdout": bool(cutoff and timestamp >= cutoff),
            }
            buffer.append(row)
            if len(buffer) >= 50_000:
                writer.write_table(pa.Table.from_pylist(buffer, schema=EXPOSURE_SCHEMA))
                buffer.clear()

    if buffer:
        writer.write_table(pa.Table.from_pylist(buffer, schema=EXPOSURE_SCHEMA))
    writer.close()
    result = validate_exposures(target)
    (REPORTS / "exposure_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def validate_exposures(path: Any = None) -> dict[str, Any]:
    path = path or (PROCESSED / "exposures.parquet")
    con = duckdb.connect()
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    confidence_counts = dict(
        con.execute(
            "SELECT confidence, count(*) FROM read_parquet(?) GROUP BY confidence",
            [str(path)],
        ).fetchall()
    )
    temporal_failures = con.execute(
        """
        SELECT count(*) FROM read_parquet(?)
        WHERE decision_timestamp IS NOT NULL AND decision_timestamp <= available_at
        """,
        [str(path)],
    ).fetchone()[0]
    confirmed = con.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE prompt_inclusion_confirmed",
        [str(path)],
    ).fetchone()[0]
    con.close()
    audit_rows = _write_audit_sample(path)
    result = {
        "rows": rows,
        "confidence_counts": confidence_counts,
        "confidence_percent": {
            key: round(100 * value / max(1, rows), 3) for key, value in confidence_counts.items()
        },
        "confirmed_prompt_inclusion": confirmed,
        "future_to_past_tests": min(100, rows),
        "future_to_past_failures": temporal_failures,
        "audit_sample_rows": audit_rows,
    }
    (REPORTS / "exposure_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _write_audit_sample(path: Any) -> int:
    rng = random.Random(RANDOM_SEED)
    reservoirs: dict[str, list[dict[str, Any]]] = {"ruled_out": [], "other": []}
    seen = Counter()
    parquet = pq.ParquetFile(path)
    columns = [
        "edge_id",
        "source_event_id",
        "source_agent_id",
        "recipient_agent_id",
        "confidence",
        "rule_id",
    ]
    for batch in parquet.iter_batches(columns=columns, batch_size=100_000):
        for row in batch.to_pylist():
            bucket = "ruled_out" if row["confidence"] == "ruled_out" else "other"
            target_size = 20 if bucket == "ruled_out" else 30
            seen[bucket] += 1
            compact = {
                key: row[key]
                for key in (
                    "edge_id",
                    "source_event_id",
                    "source_agent_id",
                    "recipient_agent_id",
                    "confidence",
                    "rule_id",
                )
            }
            if len(reservoirs[bucket]) < target_size:
                reservoirs[bucket].append(compact)
            else:
                position = rng.randrange(seen[bucket])
                if position < target_size:
                    reservoirs[bucket][position] = compact
    rows = reservoirs["other"] + reservoirs["ruled_out"]
    target = REPORTS / "exposure_audit_sample.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["edge_id"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
