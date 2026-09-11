"""Export aggregate results without labels, excerpts, private keys, or model responses.

Run after analyze_machine_annotations_v2_2.py in a data-equipped checkout.
Only the explicitly named numeric and boolean fields below can enter the export.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "machine_annotation_preliminary_v2_2.json"
OUTPUT = ROOT / "reports" / "public_results_v2_2.json"
GROUPS = (
    "broad_candidates",
    "all_controls",
    "hard_controls",
    "ordinary_local_controls",
    "source_identity_placebos",
    "temporal_placebos",
)
STATUSES = (
    "positive",
    "negative",
    "abstention_or_disagreement",
    "ineligible_no_valid_claim_pair",
)
PAIRING_OUTCOMES = (
    "claim_absent_on_one_or_both_message_roles",
    "claims_no_compatible_referent",
    "valid_claim_pair_available",
)
RATE_FIELDS = (
    "selected_unit_count",
    "valid_claim_pair_yield",
    "valid_claim_pair_unit_count",
    "ascertainability_among_valid_pairs",
    "positive_rate_conditional_on_ascertainability",
    "positive_lower_bound_among_valid_pairs",
    "positive_upper_bound_among_valid_pairs",
    "strict_consensus_positive_fraction_of_all_selected_units",
    "unique_episode_cluster_count",
)
LEVELS = (
    "L1_proposition_recurrence",
    "L2_source_linked_recurrence",
    "L3a_operational_convergence",
    "L3b_source_linked_operational_cascade",
    "L4a_persistent_recorded_claim",
    "L4b_persistent_operational_assumption",
)
RELIABILITY_LABELS = (
    "stage_b.proposition_equivalence",
    "stage_b.recipient_stance",
    "stage_b.explicit_source_link",
    "stage_b.evidence_lineage_class",
    "stage_c_full.claim_dependency",
    "stage_c_full.execution_level",
    "stage_d.memory_meaning",
    "stage_d.third_party_restatement",
)


def numeric_fields(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    result = {}
    for key in keys:
        item = value[key]
        if item is not None and type(item) not in (int, float, bool):
            raise ValueError(f"Expected a numeric or boolean aggregate for {key}")
        result[key] = item
    return result


def counts(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, int]:
    result = {key: value.get(key, 0) for key in keys}
    if any(type(item) is not int or item < 0 for item in result.values()):
        raise ValueError("Aggregate counts must be nonnegative integers")
    return result


def public_summary(source: dict[str, Any]) -> dict[str, Any]:
    retrieval = {}
    for group in GROUPS:
        value = source["retrieval_results"][group]
        retrieval[group] = {
            **numeric_fields(value, RATE_FIELDS),
            "status_counts": counts(value["status_counts"], STATUSES),
            "pairing_outcome_counts": counts(value["pairing_outcome_counts"], PAIRING_OUTCOMES),
        }
    reliability = {}
    for label in RELIABILITY_LABELS:
        value = source["reliability_diagnostics"][label]
        reliability[label] = {
            **numeric_fields(value, ("n", "cluster_count", "raw_agreement", "gwet_ac1")),
            "ac1_cluster_bootstrap_95_ci": numeric_fields(
                value["bootstrap_95_ci"]["gwet_ac1"], ("lower", "upper")
            ),
        }
    return {
        "schema_version": 1,
        "status": "preliminary_machine_development_annotation",
        "scope": numeric_fields(
            source["scope"],
            (
                "development_units",
                "development_episode_clusters",
                "unique_source_agents",
                "unique_response_agents",
                "holdout_semantics_opened",
                "source_linked_channel_development_sample_annotated",
                "machine_annotation_not_human_ground_truth",
                "known_public_incidents_in_primary_sample",
            ),
        ),
        "stage_a": {
            **numeric_fields(
                source["stage_a"],
                (
                    "marked_messages_per_judge",
                    "maximum_claims_per_marked_message",
                    "exhaustive_extraction_under_v2_2_contract",
                ),
            ),
            "atomic_claim_counts": counts(
                source["stage_a"]["atomic_claim_counts"], ("fable_high", "sol_max")
            ),
            "template_slot_counts": counts(
                source["stage_a"]["template_slot_counts"], ("fable_high", "sol_max")
            ),
        },
        "stage_a_to_b": {
            **numeric_fields(
                source["stage_a_to_b"],
                (
                    "valid_pair_units",
                    "valid_pair_episode_clusters",
                    "fixed_claim_pairs",
                ),
            ),
            "pairing_outcome_counts": counts(
                source["stage_a_to_b"]["pairing_outcome_counts"], PAIRING_OUTCOMES
            ),
        },
        "retrieval_results": retrieval,
        "evidence_ladder": numeric_fields(
            source["strict_two_judge_evidence_ladder"],
            tuple(f"{level}_episode_count" for level in LEVELS)
            + ("L1_pair_count_inside_positive_episodes",),
        ),
        "reliability_diagnostics": reliability,
        "human_gate_1_passed": False,
        "causal_peer_influence_tested": False,
        "limitations": [
            "Development sample with machine judgments; independent human validation is pending.",
            "Extraction was capped at three claims per message, contrary to exhaustive v2.2 extraction.",
            "Fable High is a run label with multiple observed model identifiers in its Stage-A manifest.",
            "Sol Max used an interactive agent workflow; no standalone replay runner is included.",
            "Only one hard control had a compatible claim pair; detector validity is unestablished.",
            "The recipient was already inspecting the shared artifact before the source message.",
            "Exact recipient prompts are absent; chronology and attribution do not identify causality.",
        ],
    }


def main() -> None:
    summary = public_summary(json.loads(SOURCE.read_text(encoding="utf-8")))
    manifest = json.loads((ROOT / "data/raw_manifest/dataset_manifest.json").read_text())
    summary["dataset"] = {
        "repository": "aidigestorg/ai-village",
        "revision": manifest["revision"],
    }
    inputs = [SOURCE]
    machine = ROOT / "annotations/v2_2/machine"
    for judge in ("fable_high", "sol_max"):
        for relative in (
            "stage_a/claims.csv",
            "stage_a/message_classification.csv",
            "stage_b/comparisons.csv",
            "stage_c_full_audit/actions_full_trace_audit.csv",
            "stage_d/memory_restatement.csv",
        ):
            inputs.append(machine / judge / relative)
    inputs.extend(
        [
            machine / "combined/stage_b/stage_a_pairing_outcomes.csv",
            ROOT / "annotations/v2_1/private/blinding_and_structural_key.csv",
            ROOT / "episodes/development_units_v2_1.csv",
            ROOT / "scripts/analyze_machine_annotations_v2_2.py",
            ROOT / "scripts/export_public_results.py",
        ]
    )
    summary["local_input_sha256"] = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in inputs
    }
    OUTPUT.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote aggregate export: {OUTPUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
