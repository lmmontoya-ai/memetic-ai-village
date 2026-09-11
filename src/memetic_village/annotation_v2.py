from __future__ import annotations

import csv
import gzip
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, RANDOM_SEED, RAW, REPORTS, ROOT, ensure_output_dirs
from .util import iso_utc, parse_timestamp, stable_id, stream_jsonl

ANNOTATIONS = ROOT / "annotations" / "v2"

CODEBOOK = """# Annotation Codebook v2

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

Annotators receive raw source/response messages, timestamp and room facts, a post-response trace,
memory deltas, and structurally eligible later third-party expressions. Candidate/control status,
retrieval score, model identity, and narrative conclusions are hidden.

## General rules

1. Label observable text and actions, not latent belief, intent, value, or causal influence.
2. Treat a common artifact, common prompt/goal, copied evidence, and independent inspection as distinct
   evidence lineages.
3. Do not infer that an eligible room message appeared in a prompt.
4. A lexical match is never enough for proposition identity, stance, relevant action, or retransmission.
5. Use `indeterminate` when the raw trace does not support a defensible decision.

## Labels

### Same proposition

`yes`, `no`, or `indeterminate`. Two expressions must make the same truth-conditional claim about
the same referent. Shared topic, vocabulary, task, or artifact is insufficient.

### Source temporally prior

`definitely_before`, `likely_before`, `concurrent_or_ambiguous`, or `definitely_after`, following
`docs/timestamp_semantics_v2.md`. Do not use displayed row order to resolve a tie.

### Source message eligible at response

`observed_inclusion`, `source_acknowledged`, `eligible`, `indirectly_reachable`, `ineligible`, or
`indeterminate`. `eligible` means available under channel rules, not probably seen.

### Direct source acknowledgment

`yes`, `no`, or `indeterminate`. Count an explicit reply, quotation, attribution, naming, or unique
reference. Do not count generic topical continuity.

### Recipient stance

Choose one: `endorses`, `rejects`, `questions`, `quotes_without_endorsement`,
`reports_another_agents_claim`, `independently_concludes_from_evidence`, or `unclear`.

### Shared artifact or common evidence

`yes`, `no`, or `indeterminate`. Record identifiers in notes. Access need not imply inspection.

### Evidence lineage

Choose the strongest supported source: `direct_artifact_inspection`, `prior_agent_message`,
`common_goal_or_prompt`, `copied_evidence`, `genuinely_distinct_evidence`, `mixed`, or `unknown`.
Independence concerns evidence ancestry, not agent identity or message count.

### Claim-relevant action

Choose one: `verify`, `operationalize`, `repeat_only`, `reject`,
`report_or_escalate_uncertainty`, `correct`, `no_relevant_action`, or `indeterminate`. An action is
relevant only when its arguments, outputs, artifact, or explicit surrounding text connect it to the
claim. A generic browser, shell, or file call is not enough.

### Memory-delta recording

Choose one: `records_as_true`, `records_as_uncertain`, `records_correction`,
`records_attributed_claim_only`, `no_relevant_content`, or `indeterminate`. Judge only newly added or
substantively rewritten spans. Later exact-span survival is supporting telemetry, not a semantic label.

### Third-party retransmission

`yes`, `no`, or `indeterminate`. `yes` requires the original recipient to later express the same
proposition with endorsement or operationalization to at least one new eligible agent distinct from
the original source and retransmitter.

### Correction occurred

`yes`, `no`, or `indeterminate`. A correction must supply or cite evidence that reverses or materially
qualifies the operative assumption.

### Strongest alternative explanation

Choose one: `shared_artifact`, `common_goal_or_prompt`, `independent_convergence`, `direct_request`,
`lexical_priming_only`, `model_or_scaffold_similarity`, `temporal_misordering`, `other`, or `none_known`.

### Overall evidence level

Choose `L0`, `L1`, `L2`, `L3`, `L4`, or `insufficient`. L5 and L6 are impossible in the observational
export. Do not assign L3 without a claim-relevant action, correction, or valid third-party
retransmission. Do not assign L4 without a relevant memory delta that survives later consolidation.

## Adjudication

Annotators work independently and do not open `blinding_key.csv`. Disagreements are preserved before
adjudication. Core reliability is computed for same proposition, stance, claim-relevant action, and
evidence lineage. Proposed L3/L4 cases must all be dual-annotated.
"""

LABEL_FIELDS = [
    "blind_unit_id",
    "annotator_id",
    "annotation_timestamp_utc",
    "same_proposition",
    "source_temporally_prior",
    "source_message_eligible_at_response",
    "direct_source_acknowledgment",
    "recipient_stance",
    "shared_artifact_or_common_evidence",
    "evidence_lineage",
    "independent_evidence_source_count",
    "agreeing_message_count",
    "claim_relevant_action",
    "memory_delta_recording",
    "third_party_retransmission",
    "correction_occurred",
    "strongest_alternative_explanation",
    "overall_evidence_level",
    "confidence_1_to_5",
    "notes",
]


def _read_units() -> list[dict[str, str]]:
    path = EPISODES / "development_units_v2.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parquet_by_episode(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pq.read_table(path).to_pylist():
        grouped[row["episode_id"]].append(row)
    return grouped


def build_annotation_packets() -> dict[str, Any]:
    ensure_output_dirs()
    ANNOTATIONS.mkdir(parents=True, exist_ok=True)
    packet_dir = ANNOTATIONS / "packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    private_dir = ANNOTATIONS / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    units = _read_units()
    needed_messages = {row["source_message_id"] for row in units} | {
        row["recipient_response_message_id"] for row in units
    }
    messages = {
        row["id"]: row
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in needed_messages
    }
    eligibility = {
        row["episode_id"]: row
        for row in pq.read_table(PROCESSED / "response_eligibility_v2.parquet").to_pylist()
    }
    temporal = {
        row["episode_id"]: row
        for row in pq.read_table(PROCESSED / "temporal_relations_v2.parquet").to_pylist()
    }
    actions = _parquet_by_episode(PROCESSED / "claim_relevant_action_windows_v2.parquet")
    memories = _parquet_by_episode(PROCESSED / "memory_deltas_v2.parquet")
    third_party = _parquet_by_episode(PROCESSED / "third_party_expression_candidates_v2.parquet")

    rng = random.Random(RANDOM_SEED)
    shuffled = list(units)
    rng.shuffle(shuffled)
    key_rows = []
    manifest_rows = []
    for position, unit in enumerate(shuffled, 1):
        blind_id = f"dev_v2_{position:03d}_{stable_id(RANDOM_SEED, unit['episode_id'], prefix='blind')[-6:]}"
        source = messages[unit["source_message_id"]]
        response = messages[unit["recipient_response_message_id"]]
        eligibility_row = eligibility.get(unit["episode_id"], {})
        temporal_row = temporal.get(unit["episode_id"], {})
        packet = {
            "blind_unit_id": blind_id,
            "instructions": "Use annotation_codebook_v2.md. Candidate/control status and scores are intentionally hidden.",
            "source": {
                "raw_message_id": source["id"],
                "canonical_event_id": unit["seed_event"],
                "actor_label": "Agent A",
                "timestamp": iso_utc(parse_timestamp(source.get("created_at"))),
                "room_id": source.get("room_id"),
                "text": source.get("content") or "",
            },
            "response": {
                "raw_message_id": response["id"],
                "canonical_event_id": unit["recipient_response"],
                "actor_label": "Agent B",
                "timestamp": iso_utc(parse_timestamp(response.get("created_at"))),
                "room_id": response.get("room_id"),
                "text": response.get("content") or "",
            },
            "exported_temporal_facts": {
                key: _json_value(temporal_row.get(key))
                for key in (
                    "source_started_at",
                    "source_completed_at",
                    "response_started_at",
                    "response_completed_at",
                    "source_timestamp_semantics",
                    "response_timestamp_semantics",
                )
            },
            "exported_channel_facts": {
                key: _json_value(eligibility_row.get(key))
                for key in (
                    "source_room_id",
                    "recipient_room_at_source",
                    "recipient_room_at_response",
                    "global_channel_at_response",
                    "room_transition_between_events",
                    "history_search_available",
                    "history_search_event_ids",
                    "shared_artifact_ids",
                    "within_known_message_cap",
                    "message_cap_reason",
                )
            },
            "post_response_trace": [
                _clean_parquet_row(row) for row in actions.get(unit["episode_id"], [])
            ],
            "memory_delta": [
                _clean_parquet_row(row) for row in memories.get(unit["episode_id"], [])
            ],
            "third_party_expression_candidates": [
                _clean_parquet_row(row) for row in third_party.get(unit["episode_id"], [])
            ],
            "labels": {
                field: None
                for field in LABEL_FIELDS
                if field not in {"blind_unit_id", "annotator_id", "annotation_timestamp_utc"}
            },
        }
        packet_path = packet_dir / f"{blind_id}.json.gz"
        with gzip.open(packet_path, "wt", encoding="utf-8") as handle:
            json.dump(packet, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        key_rows.append(
            {
                "blind_unit_id": blind_id,
                "episode_id": unit["episode_id"],
                "unit_origin": unit["unit_origin"],
                "matched_candidate_episode_id": unit["matched_candidate_episode_id"],
                "retrieval_score": unit["similarity_score"],
                "packet_path": str(packet_path.relative_to(ROOT)),
            }
        )
        manifest_rows.append(
            {
                "blind_unit_id": blind_id,
                "packet_path": str(packet_path.relative_to(ROOT)),
                "review_order": position,
            }
        )
    _write_csv(private_dir / "blinding_key.csv", key_rows)
    _write_csv(ANNOTATIONS / "packet_manifest.csv", manifest_rows)
    blank_rows = [
        {field: row["blind_unit_id"] if field == "blind_unit_id" else "" for field in LABEL_FIELDS}
        for row in manifest_rows
    ]
    _write_csv(ANNOTATIONS / "annotator_1_labels.csv", blank_rows)
    _write_csv(ANNOTATIONS / "annotator_2_labels.csv", blank_rows)
    (ANNOTATIONS / "annotation_codebook_v2.md").write_text(CODEBOOK, encoding="utf-8")
    result = {
        "packet_count": len(manifest_rows),
        "candidate_count_hidden_in_key": sum(
            row["unit_origin"] == "retrieved_candidate" for row in key_rows
        ),
        "control_count_hidden_in_key": sum(
            row["unit_origin"] != "retrieved_candidate" for row in key_rows
        ),
        "packet_manifest": str(ANNOTATIONS / "packet_manifest.csv"),
        "blinding_key": str(private_dir / "blinding_key.csv"),
        "label_templates": [
            str(ANNOTATIONS / "annotator_1_labels.csv"),
            str(ANNOTATIONS / "annotator_2_labels.csv"),
        ],
        "human_labels_present": 0,
    }
    (REPORTS / "annotation_packets_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return iso_utc(value)
    return value


def _clean_parquet_row(row: dict[str, Any]) -> dict[str, Any]:
    hidden = {
        "episode_id",
        "claim_relevant_action_label",
        "memory_delta_label",
        "same_proposition_label",
        "stance_label",
        "third_party_retransmission_label",
        "annotation_status",
        "lexical_overlap_count",
        "lexical_containment",
    }
    result = {key: _json_value(value) for key, value in row.items() if key not in hidden}
    if isinstance(result.get("raw_payload"), str):
        try:
            payload = json.loads(result["raw_payload"])
            result["raw_payload"] = json.dumps(
                _remove_model_fields(payload), ensure_ascii=False, sort_keys=True, default=str
            )
        except json.JSONDecodeError:
            pass
    return result


def _remove_model_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_model_fields(item)
            for key, item in value.items()
            if key.lower() not in {"model", "model_id", "model_string", "model_name"}
        }
    if isinstance(value, list):
        return [_remove_model_fields(item) for item in value]
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compute_reliability_if_available() -> dict[str, Any]:
    """Compute raw agreement and Cohen kappa only after two human label files are populated."""
    paths = [ANNOTATIONS / "annotator_1_labels.csv", ANNOTATIONS / "annotator_2_labels.csv"]
    tables = []
    for path in paths:
        if not path.exists():
            return {"status": "blocked_human_labels_missing", "human_input_required": True}
        with path.open(newline="", encoding="utf-8") as handle:
            tables.append({row["blind_unit_id"]: row for row in csv.DictReader(handle)})
    core = ["same_proposition", "recipient_stance", "claim_relevant_action", "evidence_lineage"]
    metrics = {}
    for field in core:
        pairs = [
            (tables[0][unit][field], tables[1][unit][field])
            for unit in sorted(set(tables[0]) & set(tables[1]))
            if tables[0][unit][field] and tables[1][unit][field]
        ]
        metrics[field] = agreement_statistics(pairs)
    coverage_met = all(metrics[field]["n"] >= 30 for field in core)
    thresholds_met = coverage_met and all(
        metrics[field]["reliability_target_met"] for field in core
    )
    status = (
        "complete_threshold_met"
        if thresholds_met
        else ("complete_threshold_failed" if coverage_met else "blocked_human_labels_missing")
    )
    result = {
        "status": status,
        "dual_annotation_coverage_target": 30,
        "coverage_met": coverage_met,
        "reliability_thresholds_met": thresholds_met,
        "metrics": metrics,
        "human_input_required": not coverage_met,
    }
    (REPORTS / "annotation_reliability_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def agreement_statistics(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """Return raw agreement, Cohen's kappa, and multicategory Gwet's AC1."""
    if not pairs:
        return {
            "n": 0,
            "raw_agreement": None,
            "cohen_kappa": None,
            "gwet_ac1": None,
            "reliability_target_met": False,
        }
    agreement = sum(left == right for left, right in pairs) / len(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    labels = set(left_counts) | set(right_counts)
    expected = sum(left_counts[label] * right_counts[label] for label in labels) / len(pairs) ** 2
    kappa = (agreement - expected) / (1 - expected) if expected < 1 else None
    average_marginals = {
        label: (left_counts[label] + right_counts[label]) / (2 * len(pairs)) for label in labels
    }
    if len(labels) <= 1:
        ac1 = 1.0 if agreement == 1.0 else None
    else:
        ac1_expected = sum(
            probability * (1 - probability) for probability in average_marginals.values()
        ) / (len(labels) - 1)
        ac1 = (agreement - ac1_expected) / (1 - ac1_expected) if ac1_expected < 1 else None
    return {
        "n": len(pairs),
        "raw_agreement": agreement,
        "cohen_kappa": kappa,
        "gwet_ac1": ac1,
        "reliability_target_met": bool(
            agreement >= 0.85
            or (kappa is not None and kappa >= 0.70)
            or (ac1 is not None and ac1 >= 0.70)
        ),
    }
