import csv
from pathlib import Path

from memetic_village.protocol_v2_2 import (
    CLAIM_FIELDS,
    _claim_rows,
    ascertainable_rate,
    claims_are_near_duplicates,
    classify_stage_a_units,
    deduplicate_claims,
    gate_1a_label,
    generate_stage_b_pairs,
    select_full_trace_audits,
)


def claim(
    *,
    blind: str = "u1",
    role: str,
    slot: str,
    proposition: str,
    referent: str,
    annotator: str = "a1",
    polarity: str = "affirmed",
    claim_type: str = "fact",
) -> dict[str, str]:
    return {
        "blind_unit_id": blind,
        "annotator_id": annotator,
        "claim_slot": slot,
        "message_role": role,
        "event_id": f"{blind}-{role}",
        "exact_claim_span": proposition,
        "atomic_proposition": proposition,
        "referent": referent,
        "polarity": polarity,
        "modality": "asserted",
        "attribution": "",
        "claim_type": claim_type,
        "speech_act_type": "factual_claim",
        "confidence_1_to_5": "5",
        "notes": "",
    }


def test_near_duplicate_rule_merges_only_same_message_and_atomic_claim() -> None:
    left = claim(
        role="source",
        slot="1",
        proposition="File X has 93 valid addresses confirmed by deterministic spreadsheet inspection",
        referent="File X",
    )
    right = claim(
        role="source",
        slot="1",
        proposition="Deterministic spreadsheet inspection confirmed File X has 93 valid addresses",
        referent="File X",
        annotator="a2",
    )
    assert claims_are_near_duplicates(left, right)
    assert len(deduplicate_claims([left, right])) == 1
    different_event = right | {"event_id": "another-event"}
    assert not claims_are_near_duplicates(left, different_event)


def test_stage_b_generates_every_referent_compatible_cross_product() -> None:
    rows = [
        claim(role="source", slot="1", proposition="X exists", referent="artifact X"),
        claim(role="source", slot="2", proposition="X is empty", referent="artifact X"),
        claim(role="response", slot="1", proposition="X has data", referent="artifact X"),
        claim(role="response", slot="2", proposition="Y has data", referent="artifact Y"),
    ]
    pairs = generate_stage_b_pairs(deduplicate_claims(rows))
    assert len(pairs) == 2
    assert {row["response_atomic_proposition"] for row in pairs} == {"X has data"}


def test_no_best_pair_selection_and_polarity_not_deduplicated() -> None:
    positive = claim(
        role="source", slot="1", proposition="service is available", referent="service"
    )
    negative = claim(
        role="source",
        slot="2",
        proposition="service is not available",
        referent="service",
        polarity="negated",
    )
    response = claim(
        role="response", slot="1", proposition="service is available", referent="service"
    )
    pairs = generate_stage_b_pairs(deduplicate_claims([positive, negative, response]))
    assert len(pairs) == 2


def test_claim_and_pair_ids_are_globally_unique_across_units() -> None:
    rows = []
    for blind in ("u1", "u2"):
        rows.extend(
            [
                claim(
                    blind=blind,
                    role="source",
                    slot="1",
                    proposition="X exists",
                    referent="artifact X",
                ),
                claim(
                    blind=blind,
                    role="response",
                    slot="1",
                    proposition="X exists",
                    referent="artifact X",
                ),
            ]
        )
    deduplicated = deduplicate_claims(rows)
    pairs = generate_stage_b_pairs(deduplicated)
    assert len({row["deduplicated_claim_id"] for row in deduplicated}) == 4
    assert len({row["claim_pair_id"] for row in pairs}) == 2


def test_stage_a_no_claim_is_not_a_negative_proposition_match() -> None:
    messages = []
    for reviewer in ("a1", "a2"):
        for role in ("source", "response"):
            messages.append(
                {
                    "blind_unit_id": "u1",
                    "annotator_id": reviewer,
                    "message_role": role,
                    "event_id": f"u1-{role}",
                    "claim_presence": "nonclaim",
                    "nonclaim_speech_act": "directive_request",
                }
            )
    outcomes = classify_stage_a_units([], [], messages)
    assert outcomes == {
        "u1": {
            "claim_extraction_pattern": "neither_annotator_extracts_a_claim",
            "referent_pairing_outcome": "claim_absent_on_one_or_both_message_roles",
            "nonclaim_speech_acts": "directive_request",
        }
    }


def test_claim_reader_ignores_reserved_blank_slots_with_identifiers(tmp_path: Path) -> None:
    populated = claim(role="source", slot="1", proposition="X exists", referent="artifact X")
    reserved = {field: "" for field in CLAIM_FIELDS}
    reserved.update(
        {
            "blind_unit_id": "u1",
            "annotator_id": "a1",
            "claim_slot": "2",
            "message_role": "source",
            "event_id": "u1-source",
        }
    )
    path = tmp_path / "claims.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLAIM_FIELDS)
        writer.writeheader()
        writer.writerows([populated, reserved])
    assert _claim_rows(path) == [populated]


def test_abstentions_remain_separate_and_bound_rate() -> None:
    result = ascertainable_rate(["yes", "no", "unknown", "insufficient_trace"], {"yes"})
    assert result["positive_count"] == 1
    assert result["abstention_count"] == 2
    assert result["ascertainability_rate"] == 0.5
    assert result["conditional_positive_rate"] == 0.5
    assert result["lower_bound"] == 0.25
    assert result["upper_bound"] == 0.75


def test_gate_1a_is_per_label_and_uses_frozen_point_and_interval_rules() -> None:
    assert gate_1a_label(0.76, 0.62, 0.88) == "strong_pass"
    assert gate_1a_label(0.72, 0.40, 0.83) == "pass"
    assert gate_1a_label(0.69, 0.65, 0.90) == "qualitative_only"
    assert gate_1a_label(0.75, 0.20, 0.90) == "qualitative_only"


def test_full_trace_audit_includes_positive_extremes_and_both_negative_strata() -> None:
    rows = []
    for index in range(60):
        rows.append(
            {
                "blind_unit_id": f"u{index:02d}",
                "action_level": "A0" if index < 20 else ("A2" if index < 50 else "A5"),
                "evidence_level": "L3b" if index == 55 else "L1",
                "featured_incident": index == 59,
                "memory_recording": "no" if index % 2 == 0 else "yes",
            }
        )
    selected = select_full_trace_audits(rows)
    assert len(selected["a0_stable_sample_up_to_12"]) == 12
    assert len(selected["a1_to_a3_stable_25_percent_minimum_10"]) == 10
    assert len(selected["memory_negative_stable_20_percent_minimum_10"]) == 10
    assert {f"u{index:02d}" for index in range(50, 60)} <= set(selected["union"])
