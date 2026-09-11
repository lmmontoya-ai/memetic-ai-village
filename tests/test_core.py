from __future__ import annotations

from datetime import UTC, datetime

from memetic_village.annotation_v2 import agreement_statistics
from memetic_village.eligibility_v2 import artifact_identifiers
from memetic_village.temporal_v2 import EventInterval, assess_temporal_relation
from memetic_village.timeline import scaffold_version
from memetic_village.util import parse_timestamp, stable_id


def test_stable_id_is_deterministic_and_namespaced() -> None:
    first = stable_id("events", "abc", "message_sent")
    assert first == stable_id("events", "abc", "message_sent")
    assert first != stable_id("chat_messages", "abc", "message_sent")
    assert first.startswith("ev_")


def test_parse_naive_upstream_timestamp_as_utc() -> None:
    assert parse_timestamp("2025-04-02 17:00:00.123456") == datetime(
        2025, 4, 2, 17, 0, 0, 123456, tzinfo=UTC
    )


def test_scaffold_boundaries() -> None:
    assert scaffold_version(datetime(2025, 4, 2, tzinfo=UTC), None) == "launch-scaffold"
    assert scaffold_version(datetime(2026, 3, 25, tzinfo=UTC), "gpt") == "perma-computer-rooms-v1"
    assert (
        scaffold_version(datetime(2026, 1, 30, tzinfo=UTC), "claude-code::opus")
        == "claude-code-agent-sdk"
    )


def _interval(
    event_id: str,
    start: datetime | None,
    completion: datetime | None,
) -> EventInterval:
    return EventInterval(
        event_id=event_id,
        event_started_at=start,
        event_completed_at=completion,
        point_timestamp=completion or start,
        timestamp_semantics="synthetic_test_interval",
        timestamp_provenance="synthetic",
    )


def test_same_timestamp_source_response_is_ambiguous() -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relation = assess_temporal_relation(
        _interval("source", None, timestamp), _interval("response", None, timestamp)
    )
    assert relation.relation == "concurrent_or_ambiguous"


def test_source_sent_during_recipient_generation_is_ambiguous() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relation = assess_temporal_relation(
        _interval("source", start.replace(minute=5), start.replace(minute=5)),
        _interval("response", start, start.replace(minute=10)),
    )
    assert relation.relation == "concurrent_or_ambiguous"


def test_source_completed_before_prompt_assembly_is_definitely_before() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relation = assess_temporal_relation(
        _interval("source", start, start.replace(minute=1)),
        _interval("response", start.replace(minute=2), start.replace(minute=3)),
    )
    assert relation.relation == "definitely_before"


def test_canonical_id_tie_break_cannot_resolve_equal_timestamps() -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    # Deliberately reverse lexical ID order; IDs must not affect the relation.
    relation = assess_temporal_relation(
        _interval("z_source", None, timestamp), _interval("a_response", None, timestamp)
    )
    assert relation.relation == "concurrent_or_ambiguous"


def test_source_after_model_start_before_completion_is_ambiguous() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relation = assess_temporal_relation(
        _interval("source", start.replace(second=30), start.replace(second=31)),
        _interval("response", start, start.replace(minute=1)),
    )
    assert relation.relation == "concurrent_or_ambiguous"


def test_source_emitted_after_response_is_definitely_after() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    relation = assess_temporal_relation(
        _interval("source", None, start.replace(minute=2)),
        _interval("response", None, start.replace(minute=1)),
    )
    assert relation.relation == "definitely_after"


def test_artifact_identifier_extraction_is_case_normalized() -> None:
    assert "pr #70" in artifact_identifiers("Please inspect PR #70 before acting.")


def test_reliability_statistics_perfect_multiclass_agreement() -> None:
    metrics = agreement_statistics([("yes", "yes"), ("no", "no"), ("yes", "yes")])
    assert metrics["raw_agreement"] == 1.0
    assert metrics["cohen_kappa"] == 1.0
    assert metrics["gwet_ac1"] == 1.0
    assert metrics["reliability_target_met"] is True


def test_reliability_statistics_empty_is_not_complete() -> None:
    metrics = agreement_statistics([])
    assert metrics["n"] == 0
    assert metrics["reliability_target_met"] is False
