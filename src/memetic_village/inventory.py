from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import CORE_TABLES, RANDOM_SEED, RAW, REPORTS, ROOT, ensure_output_dirs
from .util import flatten_fields, iso_utc, parse_timestamp, stream_jsonl, type_name


@dataclass
class FieldStats:
    present: int = 0
    nulls: int = 0
    types: Counter[str] = field(default_factory=Counter)


@dataclass
class TableStats:
    name: str
    rows: int = 0
    duplicate_ids: int = 0
    missing_ids: int = 0
    timestamp_parse_failures: int = 0
    impossible_timestamps: int = 0
    created_after_updated: int = 0
    fields: dict[str, FieldStats] = field(default_factory=lambda: defaultdict(FieldStats))
    min_time: datetime | None = None
    max_time: datetime | None = None
    ids: set[str] = field(default_factory=set)
    samples: list[dict[str, Any]] = field(default_factory=list)


def _reservoir_add(
    sample: list[dict[str, Any]], record: dict[str, Any], count: int, rng: random.Random
) -> None:
    compact = {
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "agent_id": record.get("agent_id") or record.get("agent_speaker_id"),
        "room_id": record.get("room_id"),
        "event_index": record.get("event_index"),
        "action_type": (record.get("data") or {}).get("actionType")
        if isinstance(record.get("data"), dict)
        else None,
        "non_null_fields": sorted(key for key, value in record.items() if value is not None),
    }
    if len(sample) < 20:
        sample.append(compact)
    else:
        index = rng.randrange(count)
        if index < 20:
            sample[index] = compact


def scan_table(name: str) -> TableStats:
    path = RAW / f"{name}.jsonl.gz"
    if not path.exists():
        raise FileNotFoundError(f"Missing required snapshot table: {path}")
    stats = TableStats(name=name)
    rng = random.Random(f"{RANDOM_SEED}:{name}")
    for record in stream_jsonl(path):
        stats.rows += 1
        record_id = record.get("id")
        if not record_id:
            stats.missing_ids += 1
        elif record_id in stats.ids:
            stats.duplicate_ids += 1
        else:
            stats.ids.add(record_id)
        _reservoir_add(stats.samples, record, stats.rows, rng)
        created = parse_timestamp(record.get("created_at"))
        updated = parse_timestamp(record.get("updated_at"))
        for key, value in record.items():
            if (
                key.endswith(("_at", "_time"))
                and value is not None
                and parse_timestamp(value) is None
            ):
                stats.timestamp_parse_failures += 1
        for timestamp in (created, updated):
            if timestamp:
                if timestamp.year < 2025 or timestamp > datetime.now(UTC):
                    stats.impossible_timestamps += 1
                stats.min_time = (
                    timestamp if stats.min_time is None else min(stats.min_time, timestamp)
                )
                stats.max_time = (
                    timestamp if stats.max_time is None else max(stats.max_time, timestamp)
                )
        if created and updated and created > updated:
            stats.created_after_updated += 1
        for field_name, value in flatten_fields(record):
            item = stats.fields[field_name]
            item.present += 1
            item.types[type_name(value)] += 1
            if value is None:
                item.nulls += 1
    if name not in {"agents", "chat_rooms", "chat_messages", "computer_use_sessions"}:
        stats.ids.clear()
    return stats


def _load_id_map(table: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {column: record.get(column) for column in columns}
        for record in stream_jsonl(RAW / f"{table}.jsonl.gz")
    ]


def _audit_foreign_keys(table_stats: dict[str, TableStats]) -> list[dict[str, Any]]:
    agent_ids = table_stats["agents"].ids
    room_ids = table_stats["chat_rooms"].ids
    message_ids = table_stats["chat_messages"].ids
    session_ids = table_stats["computer_use_sessions"].ids
    agent_created = {
        row["id"]: parse_timestamp(row["created_at"])
        for row in _load_id_map("agents", ("id", "created_at"))
    }
    room_created = {
        row["id"]: parse_timestamp(row["created_at"])
        for row in _load_id_map("chat_rooms", ("id", "created_at"))
    }
    checks: Counter[tuple[str, str]] = Counter()
    for key in (
        ("broken_agent_reference", "chat_messages.agent_speaker_id"),
        ("broken_room_reference", "chat_messages.room_id"),
        ("message_before_agent_created", "chat_messages"),
        ("message_before_room_created", "chat_messages"),
        ("record_before_agent_created", "agent_memories"),
        ("record_before_agent_created", "computer_use_sessions"),
        ("record_before_agent_created", "agent_goals"),
        ("record_before_agent_created", "claude_code_sessions"),
        ("record_before_agent_created", "claude_code_messages"),
        ("broken_session_reference", "computer_use_turns.session_id"),
        ("broken_message_reference", "events.data.messageId"),
        ("broken_room_reference", "events.data.roomId"),
        ("broken_session_reference", "events.data.computerUseSessionId"),
        ("broken_agent_reference", "events.data.actor"),
        ("chat_message_without_event", "chat_messages.id"),
    ):
        checks[key] = 0

    for row in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        agent_id = row.get("agent_speaker_id")
        room_id = row.get("room_id")
        if agent_id and agent_id not in agent_ids:
            checks[("broken_agent_reference", "chat_messages.agent_speaker_id")] += 1
        if room_id and room_id not in room_ids:
            checks[("broken_room_reference", "chat_messages.room_id")] += 1
        if (
            agent_id
            and timestamp
            and agent_created.get(agent_id)
            and timestamp < agent_created[agent_id]
        ):
            checks[("message_before_agent_created", "chat_messages")] += 1
        if (
            room_id
            and timestamp
            and room_created.get(room_id)
            and timestamp < room_created[room_id]
        ):
            checks[("message_before_room_created", "chat_messages")] += 1

    for table, field_name in (
        ("agent_memories", "agent_id"),
        ("computer_use_sessions", "agent_id"),
        ("agent_goals", "agent_id"),
        ("claude_code_sessions", "agent_id"),
        ("claude_code_messages", "agent_id"),
    ):
        for row in stream_jsonl(RAW / f"{table}.jsonl.gz"):
            value = row.get(field_name)
            if value and value not in agent_ids:
                checks[("broken_agent_reference", f"{table}.{field_name}")] += 1
            timestamp = parse_timestamp(row.get("created_at"))
            if (
                value
                and timestamp
                and agent_created.get(value)
                and timestamp < agent_created[value]
            ):
                checks[("record_before_agent_created", table)] += 1

    null_model_turns = 0
    for row in stream_jsonl(RAW / "computer_use_turns.jsonl.gz"):
        if row.get("session_id") not in session_ids:
            checks[("broken_session_reference", "computer_use_turns.session_id")] += 1
        if row.get("agent_messages") is None:
            null_model_turns += 1
    checks[("turn_without_model_response", "computer_use_turns.agent_messages")] = null_model_turns

    linked_messages: set[str] = set()
    event_actor_missing = 0
    for row in stream_jsonl(RAW / "events.jsonl.gz"):
        data = row.get("data") or {}
        message_id = data.get("messageId")
        if message_id:
            linked_messages.add(message_id)
            if message_id not in message_ids:
                checks[("broken_message_reference", "events.data.messageId")] += 1
        actor = (
            data.get("speakerId") if data.get("actionType") == "AGENT_TALK" else data.get("agentId")
        )
        if actor and actor not in agent_ids:
            event_actor_missing += 1
        room = data.get("roomId")
        if room and room not in room_ids:
            checks[("broken_room_reference", "events.data.roomId")] += 1
        session = data.get("computerUseSessionId")
        if session and session not in session_ids:
            checks[("broken_session_reference", "events.data.computerUseSessionId")] += 1
    checks[("broken_agent_reference", "events.data.actor")] = event_actor_missing
    checks[("chat_message_without_event", "chat_messages.id")] = len(message_ids - linked_messages)

    return [
        {"check": check, "scope": scope, "count": count}
        for (check, scope), count in sorted(checks.items())
    ]


def build_inventory() -> dict[str, Any]:
    ensure_output_dirs()
    table_stats = {name: scan_table(name) for name in CORE_TABLES}
    checks = _audit_foreign_keys(table_stats)

    csv_path = ROOT / "data_inventory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "table",
                "field",
                "rows",
                "present",
                "missing",
                "null",
                "types",
                "primary_key",
                "interpretation",
            ),
        )
        writer.writeheader()
        for name, stats in table_stats.items():
            for field_name, item in sorted(stats.fields.items()):
                writer.writerow(
                    {
                        "table": name,
                        "field": field_name,
                        "rows": stats.rows,
                        "present": item.present,
                        "missing": stats.rows - item.present,
                        "null": item.nulls,
                        "types": "|".join(sorted(item.types)),
                        "primary_key": field_name == "id",
                        "interpretation": "See pinned SCHEMA.md; nested/provider fields remain unresolved"
                        if "." in field_name
                        else "See pinned SCHEMA.md",
                    }
                )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "tables": {
            name: {
                "rows": stats.rows,
                "fields": len(stats.fields),
                "duplicate_ids": stats.duplicate_ids,
                "missing_ids": stats.missing_ids,
                "min_timestamp": iso_utc(stats.min_time),
                "max_timestamp": iso_utc(stats.max_time),
                "timestamp_parse_failures": stats.timestamp_parse_failures,
                "impossible_timestamps": stats.impossible_timestamps,
                "created_after_updated": stats.created_after_updated,
            }
            for name, stats in table_stats.items()
        },
        "checks": checks,
    }
    (REPORTS / "data_quality.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS / "manual_sample.json").write_text(
        json.dumps({name: stats.samples for name, stats in table_stats.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_inventory_markdown(summary)
    return summary


def _write_inventory_markdown(summary: dict[str, Any]) -> None:
    lines = [
        "# AI Village data inventory",
        "",
        "Generated from the pinned local snapshot. UTC timestamps are normalized internally; raw",
        "timestamps are UTC without suffix, per the upstream schema. `data_inventory.csv` contains",
        "one row per observed field, including nested event fields.",
        "",
        "| Table | Rows | Fields | Time range | Duplicate IDs |",
        "|---|---:|---:|---|---:|",
    ]
    for name, item in summary["tables"].items():
        lines.append(
            f"| `{name}` | {item['rows']:,} | {item['fields']} | "
            f"{item['min_timestamp']} – {item['max_timestamp']} | {item['duplicate_ids']} |"
        )
    lines.extend(
        [
            "",
            "## Automated integrity checks",
            "",
            "| Check | Scope | Count |",
            "|---|---|---:|",
        ]
    )
    for check in summary["checks"]:
        lines.append(f"| {check['check']} | `{check['scope']}` | {check['count']:,} |")
    lines.extend(
        [
            "",
            "## Interpretation and known uncertainty",
            "",
            "Primary keys are table `id` columns; `events.event_index` is the authoritative raw event",
            "ordering. Foreign-key coverage is quantified above. Provider-shaped response fields are",
            "heterogeneous and intentionally left as nested data. Exact prompts, raw call logs, historic",
            "room snapshots before recorded moves, screenshot pixels, and private scaffold code are not in",
            "this snapshot. Generated summaries are secondary evidence. See `visibility_rules.md` for the",
            "consequences for exposure claims.",
            "",
            "A deterministic 20-record structural sample per table is stored in",
            "`reports/manual_sample.json`; it contains identifiers and field-presence metadata, not bulk",
            "restricted text.",
        ]
    )
    (ROOT / "data_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
