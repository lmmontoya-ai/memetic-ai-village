from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, REPORTS, ensure_output_dirs
from .util import iso_utc

TemporalRelation = Literal[
    "definitely_before",
    "likely_before",
    "concurrent_or_ambiguous",
    "definitely_after",
]


@dataclass(frozen=True)
class EventInterval:
    event_id: str
    event_started_at: datetime | None
    event_completed_at: datetime | None
    point_timestamp: datetime | None
    timestamp_semantics: str
    timestamp_provenance: str


@dataclass(frozen=True)
class TemporalAssessment:
    relation: TemporalRelation
    reason: str


def assess_temporal_relation(source: EventInterval, response: EventInterval) -> TemporalAssessment:
    """Relate source to response without using deterministic storage tie-breakers."""
    if (
        source.event_completed_at is not None
        and response.event_started_at is not None
        and source.event_completed_at <= response.event_started_at
    ):
        return TemporalAssessment(
            "definitely_before", "source_completion_no_later_than_response_start"
        )
    if (
        source.event_started_at is not None
        and response.event_completed_at is not None
        and source.event_started_at > response.event_completed_at
    ):
        return TemporalAssessment("definitely_after", "source_started_after_response_completed")
    if all(
        value is not None
        for value in (
            source.event_started_at,
            source.event_completed_at,
            response.event_started_at,
            response.event_completed_at,
        )
    ):
        assert source.event_started_at is not None
        assert source.event_completed_at is not None
        assert response.event_started_at is not None
        assert response.event_completed_at is not None
        if (
            source.event_started_at <= response.event_completed_at
            and response.event_started_at <= source.event_completed_at
        ):
            return TemporalAssessment("concurrent_or_ambiguous", "exported_intervals_overlap")

    source_point = source.event_completed_at or source.point_timestamp
    response_point = response.event_completed_at or response.point_timestamp
    if source_point is None or response_point is None:
        return TemporalAssessment("concurrent_or_ambiguous", "required_timestamp_missing")
    if source_point == response_point:
        return TemporalAssessment(
            "concurrent_or_ambiguous", "equal_point_timestamps_no_runtime_boundaries"
        )
    if source_point > response_point:
        return TemporalAssessment(
            "definitely_after", "source_emission_or_insertion_after_response_emission"
        )
    return TemporalAssessment(
        "likely_before", "source_precedes_response_but_response_start_is_unavailable"
    )


def emitted_message_interval(
    event_id: str,
    timestamp: datetime | None,
    provenance: str = "canonical.timestamp<-chat_or_event_created_at",
) -> EventInterval:
    return EventInterval(
        event_id=event_id,
        event_started_at=None,
        event_completed_at=timestamp,
        point_timestamp=timestamp,
        timestamp_semantics="response_emission_or_row_insertion",
        timestamp_provenance=provenance,
    )


TEMPORAL_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("source_event_id", pa.string()),
        ("response_event_id", pa.string()),
        ("source_started_at", pa.timestamp("us", tz="UTC")),
        ("source_completed_at", pa.timestamp("us", tz="UTC")),
        ("response_started_at", pa.timestamp("us", tz="UTC")),
        ("response_completed_at", pa.timestamp("us", tz="UTC")),
        ("source_timestamp_semantics", pa.string()),
        ("response_timestamp_semantics", pa.string()),
        ("source_timestamp_provenance", pa.string()),
        ("response_timestamp_provenance", pa.string()),
        ("temporal_relation", pa.string()),
        ("ordering_uncertainty_reason", pa.string()),
        ("event_order_used_as_causal_evidence", pa.bool_()),
    ]
)


def build_temporal_relations(
    registry_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, object]:
    ensure_output_dirs()
    registry_path = registry_path or (
        EPISODES / "development_units_v2.csv"
        if (EPISODES / "development_units_v2.csv").exists()
        else EPISODES / "candidate_registry.csv"
    )
    output_path = output_path or PROCESSED / "temporal_relations_v2.parquet"
    report_path = report_path or REPORTS / "temporal_relations_v2.json"
    with registry_path.open(newline="", encoding="utf-8") as handle:
        registry = list(csv.DictReader(handle))
    ids = sorted(
        {row["seed_event"] for row in registry} | {row["recipient_response"] for row in registry}
    )
    con = duckdb.connect()
    metadata = {
        event_id: (timestamp, source_table)
        for event_id, timestamp, source_table in con.execute(
            """
            SELECT canonical_event_id, timestamp, source_table
            FROM read_parquet(?)
            WHERE canonical_event_id IN (SELECT unnest(?))
            """,
            [str(PROCESSED / "canonical_events.parquet"), ids],
        ).fetchall()
    }
    con.close()
    rows: list[dict[str, object]] = []
    for item in registry:
        source_time, source_table = metadata.get(item["seed_event"], (None, "unknown"))
        response_time, response_table = metadata.get(item["recipient_response"], (None, "unknown"))
        source = emitted_message_interval(
            item["seed_event"], source_time, f"{source_table}.created_at/upstream_database"
        )
        response = emitted_message_interval(
            item["recipient_response"],
            response_time,
            f"{response_table}.created_at/upstream_database",
        )
        assessment = assess_temporal_relation(source, response)
        rows.append(
            {
                "episode_id": item["episode_id"],
                "source_event_id": source.event_id,
                "response_event_id": response.event_id,
                "source_started_at": source.event_started_at,
                "source_completed_at": source.event_completed_at,
                "response_started_at": response.event_started_at,
                "response_completed_at": response.event_completed_at,
                "source_timestamp_semantics": source.timestamp_semantics,
                "response_timestamp_semantics": response.timestamp_semantics,
                "source_timestamp_provenance": source.timestamp_provenance,
                "response_timestamp_provenance": response.timestamp_provenance,
                "temporal_relation": assessment.relation,
                "ordering_uncertainty_reason": assessment.reason,
                "event_order_used_as_causal_evidence": False,
            }
        )
    pq.write_table(
        pa.Table.from_pylist(rows, schema=TEMPORAL_SCHEMA), output_path, compression="zstd"
    )
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["temporal_relation"])
        counts[key] = counts.get(key, 0) + 1
    result = {
        "artifact": str(output_path),
        "row_count": len(rows),
        "relation_counts": counts,
        "event_order_used_as_causal_evidence": False,
        "generated_at_note": "Deterministic build; event_order and tie-break priority excluded.",
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def interval_to_json(interval: EventInterval) -> dict[str, str | None]:
    return {
        "event_id": interval.event_id,
        "event_started_at": iso_utc(interval.event_started_at),
        "event_completed_at": iso_utc(interval.event_completed_at),
        "point_timestamp": iso_utc(interval.point_timestamp),
        "timestamp_semantics": interval.timestamp_semantics,
        "timestamp_provenance": interval.timestamp_provenance,
    }
