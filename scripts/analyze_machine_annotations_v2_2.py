"""Analyze the two blinded machine-judge development annotations.

This report is deliberately separate from the human Gate-1 artifacts.  It uses
the frozen development key only after both machine judges' final Stage-D files
passed validation, and it never reads holdout semantic content.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from memetic_village.amendments_v2_1 import bootstrap_cluster_agreement

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "annotations" / "v2_2" / "machine"
KEY = ROOT / "annotations" / "v2_1" / "private" / "blinding_and_structural_key.csv"
PAIRING = MACHINE / "combined" / "stage_b" / "stage_a_pairing_outcomes.csv"
DEVELOPMENT_UNITS = ROOT / "episodes" / "development_units_v2_1.csv"
OUTPUT_JSON = ROOT / "reports" / "machine_annotation_preliminary_v2_2.json"
OUTPUT_MD = ROOT / "reports" / "machine_annotation_preliminary_v2_2.md"
JUDGES = ("fable_high", "sol_max")

ORIGIN_GROUP = {
    "retrieved_candidate": "broad_candidates",
    "same_artifact_independent_convergence_candidate": "hard_controls",
    "same_room_local_source_control": "ordinary_local_controls",
    "source_identity_placebo": "source_identity_placebos",
    "temporal_placebo": "temporal_placebos",
}
ABSTENTION_VALUES = {"unknown", "unclear", "indeterminate", "insufficient_trace"}
MEMORY_RELEVANT = {
    "records_true",
    "records_uncertain",
    "records_correction",
    "attributes_claim_only",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def index(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError(f"Duplicate {key} values")
    return result


def index_stage_a_messages(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {f"{row['blind_unit_id']}::{row['message_role']}": row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("Duplicate Stage-A unit/message-role values")
    return result


def diagnostic_grade(metric: dict[str, Any]) -> str:
    ac1 = metric.get("gwet_ac1")
    interval = metric.get("bootstrap_95_ci", {}).get("gwet_ac1", {})
    lower, upper = interval.get("lower"), interval.get("upper")
    if ac1 is None or lower is None or upper is None:
        return "qualitative_only"
    if ac1 >= 0.70 and lower >= 0.60:
        return "strong_pass"
    if ac1 >= 0.70 and upper - lower <= 0.50:
        return "pass"
    return "qualitative_only"


def reliability(
    left: dict[str, dict[str, str]],
    right: dict[str, dict[str, str]],
    field: str,
    clusters: dict[str, str],
    *,
    id_to_unit: dict[str, str] | None = None,
) -> dict[str, Any]:
    rows = []
    for row_id in sorted(set(left) & set(right)):
        left_value, right_value = left[row_id].get(field, ""), right[row_id].get(field, "")
        if not left_value or not right_value:
            continue
        unit = id_to_unit[row_id] if id_to_unit else left[row_id]["blind_unit_id"]
        rows.append((clusters[unit], left_value, right_value))
    metric = bootstrap_cluster_agreement(rows, iterations=2000, seed=20260817)
    metric["diagnostic_grade_under_v2_2_rule"] = diagnostic_grade(metric)
    metric["machine_judges_only"] = True
    return metric


def unit_l1_status(
    blind_id: str,
    pair_ids_by_unit: dict[str, list[str]],
    stage_b: dict[str, dict[str, dict[str, str]]],
) -> str:
    pair_ids = pair_ids_by_unit.get(blind_id, [])
    if not pair_ids:
        return "ineligible_no_valid_claim_pair"
    saw_abstention = False
    for pair_id in pair_ids:
        values = [stage_b[judge][pair_id]["proposition_equivalence"] for judge in JUDGES]
        if values == ["yes", "yes"]:
            return "positive"
        if values != ["no", "no"]:
            saw_abstention = True
    return "abstention_or_disagreement" if saw_abstention else "negative"


def rate_summary(statuses: list[str]) -> dict[str, Any]:
    counts = Counter(statuses)
    valid_n = sum(counts[value] for value in ("positive", "negative", "abstention_or_disagreement"))
    ascertainable = counts["positive"] + counts["negative"]
    return {
        "selected_unit_count": len(statuses),
        "status_counts": dict(sorted(counts.items())),
        "valid_claim_pair_yield": valid_n / len(statuses) if statuses else None,
        "valid_claim_pair_unit_count": valid_n,
        "ascertainability_among_valid_pairs": ascertainable / valid_n if valid_n else None,
        "positive_rate_conditional_on_ascertainability": (
            counts["positive"] / ascertainable if ascertainable else None
        ),
        "positive_lower_bound_among_valid_pairs": counts["positive"] / valid_n if valid_n else None,
        "positive_upper_bound_among_valid_pairs": (
            (counts["positive"] + counts["abstention_or_disagreement"]) / valid_n
            if valid_n
            else None
        ),
        "strict_consensus_positive_fraction_of_all_selected_units": (
            counts["positive"] / len(statuses) if statuses else None
        ),
    }


def execution_at_least_a3(value: str) -> bool:
    return value in {"A3", "A4", "A5", "A6"}


def count_extracted_claims(rows: list[dict[str, str]]) -> int:
    """Reserved template slots carry IDs but are not extracted propositions."""
    return sum(
        bool(row.get("atomic_proposition", "").strip() and row.get("exact_claim_span", "").strip())
        for row in rows
    )


def main() -> None:
    manifests = {
        "fable_stage_d": read_json(MACHINE / "fable_high" / "stage_d" / "run_manifest.json"),
        "sol_stage_d": read_json(MACHINE / "sol_max" / "stage_d" / "run_manifest.json"),
    }
    if manifests["fable_stage_d"].get("validation") != "passed":
        raise RuntimeError("Fable final Stage-D output is not validated")
    if manifests["sol_stage_d"].get("validation", {}).get("status") != "pass":
        raise RuntimeError("Sol final Stage-D output is not validated")

    human_template_paths = [
        ROOT / "annotations" / "v2_1" / stage / f"annotator_{reviewer}_{suffix}.csv"
        for stage, suffix in (
            ("stage_a", "claims"),
            ("stage_b", "comparisons"),
            ("stage_c", "actions"),
            ("stage_d", "memory_restatement"),
        )
        for reviewer in (1, 2)
    ]
    human_label_cells_filled = any(
        row.get("annotator_id", "").strip()
        for path in human_template_paths
        for row in read_csv(path)
    )
    if human_label_cells_filled:
        raise RuntimeError("Canonical human annotation templates contain labels")

    key_rows = read_csv(KEY)
    if len(key_rows) != 60:
        raise RuntimeError("Expected exactly 60 frozen development units")
    key = index(key_rows, "blind_unit_id")
    clusters = {blind_id: row["episode_cluster_id"] for blind_id, row in key.items()}
    units = index(read_csv(DEVELOPMENT_UNITS), "episode_id")

    stage_a_messages = {
        judge: index_stage_a_messages(
            read_csv(MACHINE / judge / "stage_a" / "message_classification.csv")
        )
        for judge in JUDGES
    }
    stage_a_claims = {
        judge: read_csv(MACHINE / judge / "stage_a" / "claims.csv") for judge in JUDGES
    }
    pairing = index(read_csv(PAIRING), "blind_unit_id")
    stage_b = {
        judge: index(read_csv(MACHINE / judge / "stage_b" / "comparisons.csv"), "claim_pair_id")
        for judge in JUDGES
    }
    stage_c = {
        judge: index(
            read_csv(MACHINE / judge / "stage_c_full_audit" / "actions_full_trace_audit.csv"),
            "fixed_claim_id",
        )
        for judge in JUDGES
    }
    stage_d = {
        judge: index(
            read_csv(MACHINE / judge / "stage_d" / "memory_restatement.csv"),
            "fixed_claim_id",
        )
        for judge in JUDGES
    }
    pair_ids = sorted(set(stage_b[JUDGES[0]]) & set(stage_b[JUDGES[1]]))
    if len(pair_ids) != 19 or any(
        set(table) != set(pair_ids)
        for table in (*stage_b.values(), *stage_c.values(), *stage_d.values())
    ):
        raise RuntimeError("The two judges and Stages B-D do not share exactly 19 fixed claim IDs")
    pair_to_unit = {pair_id: stage_b[JUDGES[0]][pair_id]["blind_unit_id"] for pair_id in pair_ids}
    pair_ids_by_unit: dict[str, list[str]] = defaultdict(list)
    for pair_id, blind_id in pair_to_unit.items():
        pair_ids_by_unit[blind_id].append(pair_id)

    reliability_metrics: dict[str, dict[str, Any]] = {}
    event_to_unit = {
        row_id: row["blind_unit_id"]
        for row in stage_a_messages[JUDGES[0]].values()
        for row_id in [f"{row['blind_unit_id']}::{row['message_role']}"]
    }
    reliability_metrics["stage_a.claim_presence"] = reliability(
        stage_a_messages[JUDGES[0]],
        stage_a_messages[JUDGES[1]],
        "claim_presence",
        clusters,
        id_to_unit=event_to_unit,
    )
    for field in (
        "proposition_equivalence",
        "recipient_stance",
        "explicit_source_link",
        "lineage_independence",
        "observation_independence",
        "observable_method_diversity",
        "evidence_lineage_class",
    ):
        reliability_metrics[f"stage_b.{field}"] = reliability(
            stage_b[JUDGES[0]], stage_b[JUDGES[1]], field, clusters
        )
    for field in (
        "semantic_relevance",
        "claim_consistency",
        "claim_dependency",
        "action_type",
        "execution_level",
        "verification_separate",
        "correction",
    ):
        reliability_metrics[f"stage_c_full.{field}"] = reliability(
            stage_c[JUDGES[0]], stage_c[JUDGES[1]], field, clusters
        )
    for field in (
        "memory_meaning",
        "memory_absent_before",
        "memory_relocation_or_rephrasing",
        "memory_writer_mechanism",
        "memory_survives_consolidation",
        "later_behavioral_use",
        "third_party_restatement",
        "third_party_stance",
    ):
        reliability_metrics[f"stage_d.{field}"] = reliability(
            stage_d[JUDGES[0]], stage_d[JUDGES[1]], field, clusters
        )

    statuses = {blind_id: unit_l1_status(blind_id, pair_ids_by_unit, stage_b) for blind_id in key}
    group_units: dict[str, list[str]] = defaultdict(list)
    for blind_id, row in key.items():
        group_units[ORIGIN_GROUP[row["unit_origin"]]].append(blind_id)
    group_units["all_controls"] = [
        blind_id for blind_id, row in key.items() if row["unit_origin"] != "retrieved_candidate"
    ]
    retrieval_results = {
        group: {
            **rate_summary([statuses[blind_id] for blind_id in blind_ids]),
            "pairing_outcome_counts": dict(
                sorted(
                    Counter(
                        pairing[blind_id]["referent_pairing_outcome"] for blind_id in blind_ids
                    ).items()
                )
            ),
            "unique_episode_cluster_count": len({clusters[blind_id] for blind_id in blind_ids}),
        }
        for group, blind_ids in sorted(group_units.items())
    }

    shared_l1_pairs = [
        pair_id
        for pair_id in pair_ids
        if all(stage_b[judge][pair_id]["proposition_equivalence"] == "yes" for judge in JUDGES)
    ]
    l1_units = {pair_to_unit[pair_id] for pair_id in shared_l1_pairs}
    l2_pairs = [
        pair_id
        for pair_id in shared_l1_pairs
        if all(stage_b[judge][pair_id]["explicit_source_link"] == "yes" for judge in JUDGES)
    ]
    l2_units = {pair_to_unit[pair_id] for pair_id in l2_pairs}

    action_pairs = {
        pair_id
        for pair_id in shared_l1_pairs
        if all(stage_c[judge][pair_id]["claim_dependency"] == "yes" for judge in JUDGES)
        and all(
            execution_at_least_a3(stage_c[judge][pair_id]["execution_level"]) for judge in JUDGES
        )
    }
    correction_pairs = {
        pair_id
        for pair_id in shared_l1_pairs
        if all(stage_c[judge][pair_id]["correction"] == "yes" for judge in JUDGES)
    }
    third_party_pairs = {
        pair_id
        for pair_id in shared_l1_pairs
        if all(stage_d[judge][pair_id]["third_party_restatement"] == "yes" for judge in JUDGES)
    }
    operational_pairs = action_pairs | correction_pairs | third_party_pairs
    l3b_units = {pair_to_unit[pair_id] for pair_id in l2_pairs if pair_id in operational_pairs}
    l3a_units = {
        pair_to_unit[pair_id]
        for pair_id in shared_l1_pairs
        if pair_id not in l2_pairs and pair_id in operational_pairs
    }

    memory_recorded_pairs = {
        pair_id
        for pair_id in shared_l1_pairs
        if all(stage_d[judge][pair_id]["memory_meaning"] in MEMORY_RELEVANT for judge in JUDGES)
        and all(stage_d[judge][pair_id]["memory_absent_before"] == "yes" for judge in JUDGES)
        and all(
            stage_d[judge][pair_id]["memory_survives_consolidation"] == "yes" for judge in JUDGES
        )
    }
    no_relocation_consensus_pairs = {
        pair_id
        for pair_id in memory_recorded_pairs
        if all(
            stage_d[judge][pair_id]["memory_relocation_or_rephrasing"] == "no" for judge in JUDGES
        )
    }
    later_use_pairs = {
        pair_id
        for pair_id in no_relocation_consensus_pairs
        if all(stage_d[judge][pair_id]["later_behavioral_use"] == "yes" for judge in JUDGES)
    }
    l4a_units = {pair_to_unit[pair_id] for pair_id in no_relocation_consensus_pairs}
    l4b_units = {pair_to_unit[pair_id] for pair_id in later_use_pairs}

    positive_unit = next(iter(l1_units)) if len(l1_units) == 1 else None
    positive_pair_details = []
    for pair_id in shared_l1_pairs:
        left = stage_b[JUDGES[0]][pair_id]
        positive_pair_details.append(
            {
                "claim_pair_id": pair_id,
                "blind_unit_id": pair_to_unit[pair_id],
                "source_atomic_proposition": left["source_atomic_proposition"],
                "response_atomic_proposition": left["response_atomic_proposition"],
                "action_consensus": pair_id in action_pairs,
                "third_party_restatement_consensus": pair_id in third_party_pairs,
                "persistent_recording_minimum_consensus": pair_id in memory_recorded_pairs,
                "no_relocation_consensus": pair_id in no_relocation_consensus_pairs,
            }
        )

    valid_units = [
        blind_id
        for blind_id, row in pairing.items()
        if row["referent_pairing_outcome"] == "valid_claim_pair_available"
    ]
    selected_unit_rows = [units[key[blind_id]["episode_id"]] for blind_id in key]
    core_machine_fields = (
        "stage_b.proposition_equivalence",
        "stage_b.recipient_stance",
        "stage_b.explicit_source_link",
        "stage_b.evidence_lineage_class",
        "stage_c_full.claim_dependency",
        "stage_c_full.execution_level",
    )
    core_coverage_met = all(reliability_metrics[field]["n"] >= 30 for field in core_machine_fields)

    result: dict[str, Any] = {
        "report_contract": (
            "The AI Village export is used to identify and characterize operational epistemic "
            "cascades; only randomized experiments are used to estimate causal peer influence."
        ),
        "status": "complete_preliminary_machine_development_annotation",
        "scope": {
            "development_units": 60,
            "development_episode_clusters": len(set(clusters.values())),
            "unique_source_agents": len({row["source_agent"] for row in selected_unit_rows}),
            "unique_response_agents": len({row["recipient_agent"] for row in selected_unit_rows}),
            "holdout_semantics_opened": False,
            "source_linked_channel_development_sample_annotated": False,
            "source_linked_channel_note": (
                "This run annotates the frozen 60-unit broad/control/placebo development set. The "
                "separate 60-unit source-linked sample has not been packetized or judged and yields "
                "no source-linked-channel precision estimate here."
            ),
            "machine_annotation_not_human_ground_truth": True,
            "known_public_incidents_in_primary_sample": 0,
        },
        "stage_a": {
            "marked_messages_per_judge": len(stage_a_messages[JUDGES[0]]),
            "atomic_claim_counts": {
                judge: count_extracted_claims(stage_a_claims[judge]) for judge in JUDGES
            },
            "template_slot_counts": {judge: len(stage_a_claims[judge]) for judge in JUDGES},
            "maximum_claims_per_marked_message": 3,
            "exhaustive_extraction_under_v2_2_contract": False,
            "claim_presence_counts": {
                judge: dict(
                    sorted(
                        Counter(
                            row["claim_presence"] for row in stage_a_messages[judge].values()
                        ).items()
                    )
                )
                for judge in JUDGES
            },
        },
        "stage_a_to_b": {
            "pairing_outcome_counts": dict(
                sorted(Counter(row["referent_pairing_outcome"] for row in pairing.values()).items())
            ),
            "valid_pair_units": len(valid_units),
            "valid_pair_episode_clusters": len({clusters[blind_id] for blind_id in valid_units}),
            "fixed_claim_pairs": len(pair_ids),
        },
        "retrieval_results": retrieval_results,
        "strict_two_judge_evidence_ladder": {
            "aggregation_unit": "episode unit; repeated claim-pair rows never count as independent incidents",
            "L1_proposition_recurrence_episode_count": len(l1_units),
            "L1_pair_count_inside_positive_episodes": len(shared_l1_pairs),
            "L2_source_linked_recurrence_episode_count": len(l2_units),
            "L3a_operational_convergence_episode_count": len(l3a_units),
            "L3b_source_linked_operational_cascade_episode_count": len(l3b_units),
            "L4a_persistent_recorded_claim_episode_count": len(l4a_units),
            "L4b_persistent_operational_assumption_episode_count": len(l4b_units),
            "claim_dependent_action_consensus_pair_count": len(action_pairs),
            "third_party_restatement_consensus_pair_count": len(third_party_pairs),
            "memory_recorded_absent_before_and_survived_pair_count": len(memory_recorded_pairs),
            "memory_no_relocation_consensus_pair_count": len(no_relocation_consensus_pairs),
            "positive_episode_blind_ids": sorted(l1_units),
            "positive_pair_details": positive_pair_details,
        },
        "positive_episode": (
            {
                "blind_unit_id": positive_unit,
                "episode_id": key[positive_unit]["episode_id"],
                "episode_cluster_id": key[positive_unit]["episode_cluster_id"],
                "unit_origin": key[positive_unit]["unit_origin"],
                "raw_trace_audit": "reports/yaml_cascade_trace_audit_v2_2.json",
                "truth_audit": "reports/yaml_blank_line_truth_audit_v2_2.json",
                "bounded_interpretation": (
                    "A false atomic YAML claim recurred with explicit attribution, was re-expressed "
                    "to new recipients, and was followed by a repository commit and CI run. The "
                    "recipient had begun inspecting the common artifact before the source message, "
                    "so peer-causal influence is not identified."
                ),
            }
            if positive_unit
            else None
        ),
        "reliability_diagnostics": reliability_metrics,
        "gate_assessment": {
            "Gate_1A_human_annotation_validity": "not_assessed_machine_judges_are_not_human_reviewers",
            "machine_core_dual_annotation_row_target": 30,
            "machine_core_coverage_met": core_coverage_met,
            "machine_core_pair_rows": 19,
            "machine_core_valid_units": len(valid_units),
            "machine_core_episode_clusters": len({clusters[blind_id] for blind_id in valid_units}),
            "Gate_1B_detector_validity": "not_passed_development_only_and_hard_comparable_n_is_one",
            "Gate_1C_operational_rate": "qualitative_only_one_positive_episode_cluster",
            "Gate_1D_source_linked_case": "one_preliminary_machine_consensus_episode",
            "Gate_1E_memory": (
                "not_established_judges_disagreed_on_relocation_or_rephrasing_and_writer_mechanism"
            ),
            "causal_peer_influence": "not_tested",
        },
        "quality_control": {
            "stage_c_all_valid_units_full_trace_audited_by_both_judges": True,
            "stage_d_repaired_and_restarted_from_scratch": True,
            "discarded_stage_d_bug_manifest": (
                "annotations/v2_2/machine/discarded_global_channel_third_party_bug_20260817/"
                "BUG_MANIFEST.json"
            ),
            "human_annotation_label_cells_filled": human_label_cells_filled,
            "both_machine_judges_remained_blind_to_private_key": True,
            "analysis_unblinded_only_after_final_machine_files_validated": True,
        },
        "judge_manifests": manifests,
        "bottom_line": (
            "The strict machine consensus finds one reconstructable source-linked operational "
            "episode, not a population rate or causal spread result. Broad lexical retrieval was "
            "mostly not proposition-comparable, and the hard-control comparison is far too small. "
            "This supports a qualitative naturalistic signal and a controlled reproduction, while "
            "leaving Gate 1 and causal claims open for independent human annotation and experiments."
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{100 * value:.1f}%"

    candidate = retrieval_results["broad_candidates"]
    controls = retrieval_results["all_controls"]
    hard = retrieval_results["hard_controls"]
    reliability_rows = []
    for name in core_machine_fields + (
        "stage_d.memory_meaning",
        "stage_d.third_party_restatement",
    ):
        metric = reliability_metrics[name]
        interval = metric["bootstrap_95_ci"]["gwet_ac1"]
        reliability_rows.append(
            f"| {name} | {metric['n']} | {metric['cluster_count']} | "
            f"{metric['raw_agreement']:.3f} | {metric['gwet_ac1']:.3f} | "
            f"[{interval['lower']:.3f}, {interval['upper']:.3f}] | "
            f"{metric['diagnostic_grade_under_v2_2_rule']} |"
        )
    markdown = f"""# Preliminary two-machine-judge development annotation

> **The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

## Result

The strict intersection of Fable High and Sol Max judgments identifies **one episode-level L1 proposition recurrence**, and it is also the sole preliminary L2 and L3b episode. It is the YAML blank-line incident. Six atomic claim pairs inside that one incident were independently marked proposition-equivalent; they count as **one episode**, not six findings.

The episode contains a deterministically false atomic claim: that a blank line between `env:` and its indented value breaks YAML. The response explicitly attributed the diagnosis to the source, later re-expressed it to new recipients, and a third agent removed the line, committed SHA `5c9d2c4`, and triggered CI run #13. However, the response agent began inspecting the same artifact 148 seconds before the source message. Exact prompt-inclusion telemetry is absent. This is a strong naturalistic source-linked operational sequence, but it does not identify peer causality.

## Retrieval and ascertainability

| Group | Selected units | Valid claim-pair units | Strict L1 positive | Abstention/disagreement | Positive among ascertainable valid units |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broad candidates | {candidate["selected_unit_count"]} | {candidate["valid_claim_pair_unit_count"]} ({pct(candidate["valid_claim_pair_yield"])}) | {candidate["status_counts"].get("positive", 0)} | {candidate["status_counts"].get("abstention_or_disagreement", 0)} | {pct(candidate["positive_rate_conditional_on_ascertainability"])} |
| All controls/placebos | {controls["selected_unit_count"]} | {controls["valid_claim_pair_unit_count"]} ({pct(controls["valid_claim_pair_yield"])}) | {controls["status_counts"].get("positive", 0)} | {controls["status_counts"].get("abstention_or_disagreement", 0)} | {pct(controls["positive_rate_conditional_on_ascertainability"])} |
| Hard same-artifact/code controls | {hard["selected_unit_count"]} | {hard["valid_claim_pair_unit_count"]} ({pct(hard["valid_claim_pair_yield"])}) | {hard["status_counts"].get("positive", 0)} | {hard["status_counts"].get("abstention_or_disagreement", 0)} | {pct(hard["positive_rate_conditional_on_ascertainability"])} |

Across all 60 units, only 11 units in six episode clusters produced a referent-compatible Stage-B claim pair. Forty-two had extracted claims but no compatible referent, and seven lacked a claim on one or both marked roles. The candidates-versus-hard-control comparison is therefore not informative: only one of seven hard controls reached proposition comparison.

## Evidence ladder

| Level | Strict two-judge episode count | Interpretation |
| --- | ---: | --- |
| L1 proposition recurrence | {len(l1_units)} | One YAML incident |
| L2 source-linked recurrence | {len(l2_units)} | Explicit attribution/unique linkage in the same incident |
| L3a operational convergence | {len(l3a_units)} | None outside source-linked case |
| L3b source-linked operational cascade | {len(l3b_units)} | One qualitative incident; direct action and later re-expression are raw-trace supported |
| L4a persistent recorded claim | {len(l4a_units)} | Not counted conservatively: judges disagreed on relocation/rephrasing |
| L4b persistent operational assumption | {len(l4b_units)} | Not established |

Both judges saw the YAML claim in the post-response memory and in later consolidation, and both found later behavioral use for five core pairs. They systematically disagreed on whether the memory text was a fresh record versus rephrasing/relocation and on whether writing was automatic or mixed. That blocks a formal L4 label.

## Reliability diagnostics

These describe agreement between the two machine runs. They do not establish human reliability or pass Gate 1A.

| Label | Pair rows | Episode clusters | Raw agreement | AC1 | Cluster-bootstrap 95% CI | Diagnostic grade |
| --- | ---: | ---: | ---: | ---: | --- | --- |
{chr(10).join(reliability_rows)}

Gate 1A requires at least 30 dual-annotated units per core label and independent human reviewers. Here Stages B-D contain 19 pair rows from 11 units in only six clusters. Gate 1B is also not passed: this is development material, and only one hard control was proposition-comparable.

## Quality controls and scope

- Both judges reviewed all 60 blinded Stage-A packets, every one of the 19 deterministic Stage-B pairs, all 11 complete Stage-C traces, and exact Stage-D memory snapshots.
- A global-channel normalization bug initially suppressed third-party candidates. The affected Stage-D outputs were archived as invalid, the bug was regression-tested and repaired, packets were regenerated, and both judges restarted Stage D from scratch.
- The holdout remains unopened. Human annotation label cells remain unfilled; machine labels live only under `annotations/v2_2/machine/`.
- The separate frozen 60-unit source-linked development sample was not part of this run, so no source-linked-channel precision estimate is reported.
- The machine runs provide a preliminary screen and exercise the annotation protocol. They cannot satisfy the specified human Gate 1.
- Both machine runs imposed a maximum of three claims per marked message. They produced {count_extracted_claims(stage_a_claims[JUDGES[0]])} and {count_extracted_claims(stage_a_claims[JUDGES[1]])} populated claims respectively, out of 360 template slots each. This cap departs from the v2.2 instruction to extract every atomic claim and may reduce claim-pair yield.
- Fable High is a run label. Its Stage-A manifest records multiple observed model identifiers; it does not establish a single-model comparison. Sol Max labels were produced in an interactive agent workflow, for which this repository has no standalone replay runner.
- The public aggregate export and input hashes are in [public_results_v2_2.json](public_results_v2_2.json). Exact labels, raw excerpts, and model responses remain local under the dataset restrictions.
- The September repository review found that the current codebook and compiler do not match the original v2.2 freeze hashes. [The integrity record](protocol_integrity_review.json) preserves that mismatch. This run must be interpreted as exploratory development work.

## Interpretation

The reconstructed incident contains a false, explicitly source-linked claim that was repeated, appeared in later memory, reached additional agents, and was followed by action. Shared-artifact inspection was already underway, so the sequence cannot establish that the source message caused the response. Broad prevalence, detector validity, and causal spread remain unestablished.
"""
    OUTPUT_MD.write_text(markdown, encoding="utf-8")
    print(json.dumps({"json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD)}, indent=2))


if __name__ == "__main__":
    main()
