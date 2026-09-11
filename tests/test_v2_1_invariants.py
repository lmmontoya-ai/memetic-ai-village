from __future__ import annotations

import csv
import gzip
import json
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest

from memetic_village.amendments_v2_1 import bootstrap_cluster_agreement
from memetic_village.config import EPISODES, PROCESSED, RAW, REPORTS, ROOT
from memetic_village.eligibility_v2 import (
    classify_information_eligibility,
    room_transition_between,
)
from memetic_village.outcomes_v2 import _sender_room_at_message
from memetic_village.util import parse_timestamp, stream_jsonl


def _classification(**overrides: object) -> tuple[bool | None, str, str]:
    values = {
        "temporal_relation": "likely_before",
        "exact_retrieval": False,
        "direct_reference": False,
        "direct_reference_rule": "none",
        "same_room": True,
        "global_at_response": False,
        "history_search_available": False,
        "shared_artifact_available": False,
    }
    values.update(overrides)
    return classify_information_eligibility(**values)  # type: ignore[arg-type]


def test_response_eligibility_rules_out_future_source() -> None:
    assert _classification(temporal_relation="definitely_after")[:2] == (False, "ineligible")


def test_unknown_room_state_is_indeterminate() -> None:
    assert _classification(same_room=None)[:2] == (None, "indeterminate")


def test_different_room_excludes_direct_message_path() -> None:
    assert _classification(same_room=False)[:2] == (False, "ineligible")


def test_different_room_can_leave_indirect_history_path() -> None:
    assert _classification(same_room=False, history_search_available=True)[:2] == (
        False,
        "indirectly_reachable",
    )


def test_global_channel_boundary_allows_direct_path() -> None:
    assert _classification(same_room=False, global_at_response=True)[:2] == (True, "eligible")


def test_observed_history_retrieval_outranks_room_uncertainty() -> None:
    assert _classification(same_room=None, exact_retrieval=True)[:2] == (
        True,
        "observed_inclusion",
    )


def test_room_transition_interval_boundaries() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    moves = [(start + timedelta(minutes=5), "room-b")]
    assert room_transition_between(start, start + timedelta(minutes=10), moves)
    assert not room_transition_between(start, start + timedelta(minutes=4), moves)


def test_cluster_bootstrap_primary_statistic_is_ac1() -> None:
    rows = [
        ("cluster-a", "yes", "yes"),
        ("cluster-a", "no", "no"),
        ("cluster-b", "yes", "yes"),
    ]
    result = bootstrap_cluster_agreement(rows, iterations=100, seed=1)
    assert result["primary_statistic"] == "gwet_ac1"
    assert result["gwet_ac1"] == 1.0
    assert result["cluster_count"] == 2


@pytest.mark.data
def test_author_diagnostic_is_excluded_from_gate_1() -> None:
    report = json.loads(
        (REPORTS / "author_autocorrelation_diagnostic_v2_1.json").read_text(encoding="utf-8")
    )
    assert report["diagnostic_name"] == "author_autocorrelation_diagnostic"
    assert report["valid_social_influence_null"] is False
    assert report["included_in_gate_1"] is False


@pytest.mark.data
def test_fixed_author_comparisons_preserve_identity_and_cluster() -> None:
    rows = pq.read_table(
        PROCESSED / "fixed_author_local_source_comparisons_v2_1.parquet"
    ).to_pylist()
    assert rows
    assert all(not row["author_sequence_modified"] for row in rows)
    assert all(row["source_agent_id"] != row["response_agent_id"] for row in rows)
    assert all(row["episode_cluster_id"] for row in rows)


@pytest.mark.data
def test_v2_1_development_set_prioritizes_available_hard_controls() -> None:
    report = json.loads((REPORTS / "development_set_v2_1.json").read_text(encoding="utf-8"))
    assert (report["candidate_count"], report["control_count"], report["placebo_count"]) == (
        30,
        20,
        10,
    )
    assert report["hard_control_count"] == report["hard_control_candidate_coverage"] == 7
    assert report["candidate_without_available_hard_control_count"] == 23


@pytest.mark.data
def test_source_linked_channel_preserves_unopened_holdout() -> None:
    rows = pq.read_table(PROCESSED / "source_linked_candidates_v2_1.parquet").to_pylist()
    assert sum(row["selected_for_development_sample"] for row in rows) == 60
    assert all(not row["holdout_semantic_content_opened"] for row in rows)


@pytest.mark.data
def test_stage_a_packets_do_not_contain_anchoring_fields() -> None:
    prohibited = (
        "retrieved_candidate",
        "dev_candidate_",
        "dev_control_",
        "normalized_proposition",
        "known_incident",
        "retrieval_score",
        "similarity_score",
        "model_id",
        "model_name",
    )
    packets = sorted((ROOT / "annotations" / "v2_1" / "stage_a" / "packets").glob("*.gz"))
    assert len(packets) == 60
    for packet in packets:
        with gzip.open(packet, "rt", encoding="utf-8") as handle:
            text = handle.read().lower()
        assert not any(term in text for term in prohibited)


@pytest.mark.data
def test_holdout_washout_endpoint_and_cluster_leakage_invariants() -> None:
    rows = pq.read_table(PROCESSED / "holdout_episode_clusters_v2.parquet").to_pylist()
    cutoff = parse_timestamp(
        json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())["cutoff"]
    )
    assert cutoff is not None
    for row in rows:
        if row["after_48h_washout"]:
            assert row["episode_started_at"] >= cutoff + timedelta(hours=48)
        if row["crosses_old_cutoff"]:
            assert row["episode_started_at"] < cutoff <= row["episode_ended_at"]
        assert row["semantic_content_opened"] is False


@pytest.mark.data
def test_memory_pairing_and_intervening_counts_are_coherent() -> None:
    rows = pq.read_table(PROCESSED / "memory_annotation_units_v2_1.parquet").to_pylist()
    assert len(rows) == 60
    for row in rows:
        assert row["memory_after_timestamp"] >= row["response_timestamp"]
        assert row["response_to_memory_seconds"] >= 0
        assert row["intervening_event_count"] >= 0
        assert row["memory_writer_mechanism"] == "unknown_agent_scaffold_or_mixed"


@pytest.mark.data
def test_third_party_recipient_is_distinct() -> None:
    rows = pq.read_table(PROCESSED / "third_party_expression_candidates_v2_1.parquet").to_pylist()
    for row in rows:
        recipients = set(json.loads(row["new_recipient_agent_ids"]))
        assert recipients
        assert row["original_source_agent_id"] not in recipients
        assert row["candidate_reexpressing_agent_id"] not in recipients


def test_third_party_legacy_room_id_is_normalized_to_global_channel() -> None:
    class StubVisibility:
        def room_at(self, _agent_id: str, _timestamp: datetime) -> str:
            return "__global__"

    before_rooms = datetime(2025, 11, 25, tzinfo=UTC)
    assert (
        _sender_room_at_message(
            StubVisibility(),  # type: ignore[arg-type]
            "agent-a",
            before_rooms,
            "legacy-exported-room-id",
        )
        == "__global__"
    )


@pytest.mark.data
def test_truth_audit_uses_atomic_unadjudicated_claims_and_versions() -> None:
    with (EPISODES / "claim_truth_audit_v2_1.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 14
    assert all(row["truth_status"] == "pending_independent_truth_review" for row in rows)
    egg_rows = [row for row in rows if row["case_id"] == "known_03_whitespace_egg"]
    assert len(egg_rows) == 6
    assert all(row["artifact_version"] == "ad4f148" for row in egg_rows)


@pytest.mark.data
def test_raw_message_pointer_round_trip_for_atomic_units() -> None:
    units = pq.read_table(PROCESSED / "atomic_claim_extraction_units_v2_1.parquet").to_pylist()
    expected_ids = {row["raw_message_id"] for row in units}
    found_ids = {
        row["id"]
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in expected_ids
    }
    assert found_ids == expected_ids


@pytest.mark.data
def test_action_scale_and_cluster_ids_are_present() -> None:
    table = pq.read_table(PROCESSED / "action_annotation_units_v2_1.parquet")
    assert table.num_rows == 60
    assert table["episode_cluster_id"].null_count == 0
    specification = (ROOT / "research_spec_v2.1.md").read_text(encoding="utf-8")
    assert "A0_no_relevant_action" in specification
    assert "A6_collective_or_external_state_changed" in specification
