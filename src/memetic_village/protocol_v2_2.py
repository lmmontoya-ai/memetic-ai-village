from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import PROCESSED, REPORTS, ROOT
from .util import sha256_file, stable_id

ANNOTATIONS = ROOT / "annotations" / "v2_2"
V21_ANNOTATIONS = ROOT / "annotations" / "v2_1"
SPEC = ROOT / "research_spec_v2.2.md"
HOLDOUT_PLAN = ROOT / "docs" / "holdout_sampling_plan_v2.2.json"

CLAIM_FIELDS = [
    "blind_unit_id",
    "annotator_id",
    "claim_slot",
    "message_role",
    "event_id",
    "exact_claim_span",
    "atomic_proposition",
    "referent",
    "polarity",
    "modality",
    "attribution",
    "claim_type",
    "speech_act_type",
    "confidence_1_to_5",
    "notes",
]
MESSAGE_FIELDS = [
    "blind_unit_id",
    "annotator_id",
    "message_role",
    "event_id",
    "claim_presence",
    "nonclaim_speech_act",
    "notes",
]
REQUIRED_CLAIM_FIELDS = {
    "blind_unit_id",
    "claim_slot",
    "message_role",
    "event_id",
    "exact_claim_span",
    "atomic_proposition",
    "referent",
    "polarity",
    "claim_type",
}
SEMANTIC_CLAIM_FIELDS = {
    "exact_claim_span",
    "atomic_proposition",
    "referent",
    "polarity",
    "claim_type",
}
ABSTENTIONS = {"", "unknown", "unclear", "indeterminate", "insufficient_trace", "abstain"}
TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(TOKEN_RE.findall(text))


def _tokens(value: str | None) -> set[str]:
    return set(_normalized(value).split())


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


def _same_or_unspecified(left: str | None, right: str | None) -> bool:
    a, b = _normalized(left), _normalized(right)
    return a == b or not a or not b or a in {"unknown", "unclear"} or b in {"unknown", "unclear"}


def claims_are_near_duplicates(left: dict[str, str], right: dict[str, str]) -> bool:
    """Frozen development rule; only claims from the same source/response message can merge."""
    if (left["blind_unit_id"], left["message_role"], left["event_id"]) != (
        right["blind_unit_id"],
        right["message_role"],
        right["event_id"],
    ):
        return False
    same_type = _normalized(left.get("claim_type")) == _normalized(right.get("claim_type"))
    same_polarity = _normalized(left.get("polarity")) == _normalized(right.get("polarity"))
    if (
        not same_type
        or not same_polarity
        or not _same_or_unspecified(left.get("modality"), right.get("modality"))
    ):
        return False
    referent_match = _normalized(left.get("referent")) == _normalized(right.get("referent"))
    referent_match = (
        referent_match
        or _jaccard(_tokens(left.get("referent")), _tokens(right.get("referent"))) >= 0.90
    )
    proposition_match = (
        _jaccard(_tokens(left.get("atomic_proposition")), _tokens(right.get("atomic_proposition")))
        >= 0.85
    )
    return referent_match and proposition_match


def claims_share_referent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = _normalized(left.get("referent")), _normalized(right.get("referent"))
    return bool(a and b and (a == b or _jaccard(set(a.split()), set(b.split())) >= 0.80))


def _claim_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path)
    complete: list[dict[str, str]] = []
    for row in rows:
        semantic_populated = {
            field for field in SEMANTIC_CLAIM_FIELDS if (row.get(field) or "").strip()
        }
        # Reserved template slots retain unit, role, event, and slot IDs.  A slot
        # is unused when every semantic claim field is blank, not when the whole
        # CSV row is blank.
        if not semantic_populated:
            continue
        populated = {field for field in REQUIRED_CLAIM_FIELDS if (row.get(field) or "").strip()}
        missing = REQUIRED_CLAIM_FIELDS - populated
        if missing:
            raise ValueError(f"Partially completed claim row in {path}: missing {sorted(missing)}")
        complete.append(row)
    return complete


def deduplicate_claims(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Union exact/near duplicates and preserve every original extraction and span."""
    ordered = sorted(
        rows,
        key=lambda row: (
            row["blind_unit_id"],
            row["message_role"],
            row["event_id"],
            row.get("annotator_id", ""),
            int(row["claim_slot"]),
        ),
    )
    parent = list(range(len(ordered)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for i, left in enumerate(ordered):
        for j in range(i + 1, len(ordered)):
            right = ordered[j]
            if (left["blind_unit_id"], left["message_role"], left["event_id"]) != (
                right["blind_unit_id"],
                right["message_role"],
                right["event_id"],
            ):
                continue
            exact = all(
                _normalized(left.get(field)) == _normalized(right.get(field))
                for field in (
                    "atomic_proposition",
                    "referent",
                    "polarity",
                    "modality",
                    "claim_type",
                )
            )
            if exact or claims_are_near_duplicates(left, right):
                union(i, j)
    groups: dict[int, list[dict[str, str]]] = defaultdict(list)
    for i, row in enumerate(ordered):
        groups[find(i)].append(row)
    result = []
    for members in groups.values():
        representative = min(
            members,
            key=lambda row: (
                len(_normalized(row["atomic_proposition"])),
                _normalized(row["atomic_proposition"]),
            ),
        )
        source_ids = sorted(
            f"{row.get('annotator_id', '')}:{row['message_role']}:{row['claim_slot']}"
            for row in members
        )
        message_identity = (
            representative["blind_unit_id"],
            representative["message_role"],
            representative["event_id"],
        )
        result.append(
            {
                **representative,
                "deduplicated_claim_id": stable_id(
                    *message_identity, *source_ids, prefix="claim_v2_2"
                ),
                "extractor_count": len({row.get("annotator_id", "") for row in members}),
                "original_extraction_ids": json.dumps(source_ids),
                "all_exact_spans": json.dumps(sorted({row["exact_claim_span"] for row in members})),
            }
        )
    return sorted(result, key=lambda row: row["deduplicated_claim_id"])


def generate_stage_b_pairs(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate every referent-compatible source x response pair; never select a best pair."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"source": [], "response": []}
    )
    for claim in claims:
        grouped[claim["blind_unit_id"]][claim["message_role"]].append(claim)
    pairs = []
    for blind_id, roles in sorted(grouped.items()):
        for source in roles["source"]:
            for response in roles["response"]:
                if not claims_share_referent(source, response):
                    continue
                pair_id = stable_id(
                    source["deduplicated_claim_id"],
                    response["deduplicated_claim_id"],
                    prefix="pair_v2_2",
                )
                pairs.append(
                    {
                        "blind_unit_id": blind_id,
                        "claim_pair_id": pair_id,
                        "source_claim_id": source["deduplicated_claim_id"],
                        "response_claim_id": response["deduplicated_claim_id"],
                        "source_exact_spans": source["all_exact_spans"],
                        "response_exact_spans": response["all_exact_spans"],
                        "source_atomic_proposition": source["atomic_proposition"],
                        "response_atomic_proposition": response["atomic_proposition"],
                        "source_referent": source["referent"],
                        "response_referent": response["referent"],
                        "proposition_equivalence": "",
                        "recipient_stance": "",
                        "explicit_source_link": "",
                        "lineage_independence": "",
                        "observation_independence": "",
                        "observable_method_diversity": "",
                        "evidence_lineage_class": "",
                        "supporting_event_ids": "",
                        "strongest_alternative_explanation": "",
                        "confidence_1_to_5": "",
                        "notes": "",
                    }
                )
    return sorted(pairs, key=lambda row: (row["blind_unit_id"], row["claim_pair_id"]))


def classify_stage_a_units(
    claims: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    message_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Classify claim-pair availability without converting no-claim cases into negatives."""
    units = sorted({row["blind_unit_id"] for row in message_rows})
    paired = {row["blind_unit_id"] for row in pairs}
    claims_by_unit_reviewer: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in claims:
        claims_by_unit_reviewer[row["blind_unit_id"]][row.get("annotator_id", "")].append(row)
    speech_acts: dict[str, set[str]] = defaultdict(set)
    for row in message_rows:
        if _normalized(row.get("claim_presence")) == "nonclaim":
            speech_acts[row["blind_unit_id"]].add(_normalized(row.get("nonclaim_speech_act")))
    outcomes: dict[str, dict[str, str]] = {}
    for blind_id in units:
        reviewer_claims = claims_by_unit_reviewer[blind_id]
        reviewers_with_claims = sum(bool(rows) for rows in reviewer_claims.values())
        all_claims = [row for rows in reviewer_claims.values() for row in rows]
        has_source = any(row["message_role"] == "source" for row in all_claims)
        has_response = any(row["message_role"] == "response" for row in all_claims)
        if reviewers_with_claims == 0:
            extraction_pattern = "neither_annotator_extracts_a_claim"
        elif reviewers_with_claims == 1:
            extraction_pattern = "only_one_annotator_extracts_any_claim"
        else:
            extraction_pattern = "both_annotators_extract_one_or_more_claims"
        if blind_id in paired:
            pairing_outcome = "valid_claim_pair_available"
        elif has_source and has_response:
            pairing_outcome = "claims_no_compatible_referent"
        else:
            pairing_outcome = "claim_absent_on_one_or_both_message_roles"
        outcomes[blind_id] = {
            "claim_extraction_pattern": extraction_pattern,
            "referent_pairing_outcome": pairing_outcome,
            "nonclaim_speech_acts": ";".join(sorted(speech_acts[blind_id])),
        }
    return outcomes


def ascertainable_rate(labels: list[str], positives: set[str]) -> dict[str, float | int | None]:
    normalized = [_normalized(label) for label in labels]
    positive_count = sum(label in positives for label in normalized)
    unknown_count = sum(label in ABSTENTIONS for label in normalized)
    negative_count = len(labels) - positive_count - unknown_count
    adjudicable = positive_count + negative_count
    return {
        "n": len(labels),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "abstention_count": unknown_count,
        "ascertainability_rate": adjudicable / len(labels) if labels else None,
        "conditional_positive_rate": positive_count / adjudicable if adjudicable else None,
        "lower_bound": positive_count / len(labels) if labels else None,
        "upper_bound": (positive_count + unknown_count) / len(labels) if labels else None,
    }


def gate_1a_label(ac1: float | None, lower: float | None, upper: float | None) -> str:
    if ac1 is None or lower is None or upper is None:
        return "qualitative_only"
    if ac1 >= 0.70 and lower >= 0.60:
        return "strong_pass"
    if ac1 >= 0.70 and upper - lower <= 0.50:
        return "pass"
    return "qualitative_only"


def select_full_trace_audits(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Deterministic, label-stratified audit selection after frozen semantic labels exist."""
    by_id = {str(row["blind_unit_id"]): row for row in rows}
    featured = {key for key, row in by_id.items() if row.get("featured_incident") is True}
    positive = {
        key
        for key, row in by_id.items()
        if row.get("action_level") in {"A4", "A5", "A6"} or row.get("evidence_level") == "L3b"
    }
    a0 = sorted(
        (key for key, row in by_id.items() if row.get("action_level") == "A0"),
        key=lambda key: hashlib.sha256(f"v2.2-a0:{key}".encode()).hexdigest(),
    )[:12]
    middle = sorted(
        (key for key, row in by_id.items() if row.get("action_level") in {"A1", "A2", "A3"}),
        key=lambda key: hashlib.sha256(f"v2.2-middle:{key}".encode()).hexdigest(),
    )
    middle_n = min(len(middle), max(10, (len(middle) + 3) // 4)) if middle else 0
    memory_negative = sorted(
        (key for key, row in by_id.items() if row.get("memory_recording") == "no"),
        key=lambda key: hashlib.sha256(f"v2.2-memory:{key}".encode()).hexdigest(),
    )
    memory_n = (
        min(len(memory_negative), max(10, (len(memory_negative) + 4) // 5))
        if memory_negative
        else 0
    )
    return {
        "featured_incidents": sorted(featured),
        "all_a4_to_a6_and_l3b": sorted(positive),
        "a0_stable_sample_up_to_12": a0,
        "a1_to_a3_stable_25_percent_minimum_10": middle[:middle_n],
        "memory_negative_stable_20_percent_minimum_10": memory_negative[:memory_n],
        "union": sorted(
            featured | positive | set(a0) | set(middle[:middle_n]) | set(memory_negative[:memory_n])
        ),
    }


def _blank_stage_a_templates() -> dict[str, Any]:
    source = V21_ANNOTATIONS / "stage_a" / "annotator_1_claims.csv"
    if any(row.get("atomic_proposition", "").strip() for row in _read_csv(source)):
        raise RuntimeError(
            "v2.1 Stage A contains human input; migration requires an explicit audit"
        )
    existing_claims = [
        ANNOTATIONS / "stage_a" / f"annotator_{reviewer}_claims.csv" for reviewer in (1, 2)
    ]
    existing_messages = [
        ANNOTATIONS / "stage_a" / f"annotator_{reviewer}_message_classification.csv"
        for reviewer in (1, 2)
    ]
    if any(
        path.exists() and any(row.get("atomic_proposition", "").strip() for row in _read_csv(path))
        for path in existing_claims
    ) or any(
        path.exists() and any(row.get("claim_presence", "").strip() for row in _read_csv(path))
        for path in existing_messages
    ):
        raise RuntimeError("Refusing to overwrite entered v2.2 Stage A reviewer data")
    original = _read_csv(source)
    packet_source = V21_ANNOTATIONS / "stage_a" / "packets"
    event_ids: dict[tuple[str, str], str] = {}
    for source_path in sorted(packet_source.glob("*.json.gz")):
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            packet = json.load(handle)
        event_ids[(packet["blind_unit_id"], "source")] = packet["source_event_id"]
        event_ids[(packet["blind_unit_id"], "response")] = packet["response_event_id"]
    claim_rows = []
    for original_row in original:
        row = {field: original_row.get(field, "") for field in CLAIM_FIELDS}
        row["event_id"] = event_ids[(row["blind_unit_id"], row["message_role"])]
        claim_rows.append(row)
    messages = {}
    for row in claim_rows:
        key = (row["blind_unit_id"], row["message_role"], row["event_id"])
        messages[key] = {
            "blind_unit_id": row["blind_unit_id"],
            "annotator_id": "",
            "message_role": row["message_role"],
            "event_id": row["event_id"],
            "claim_presence": "",
            "nonclaim_speech_act": "",
            "notes": "",
        }
    for reviewer in (1, 2):
        reviewer_id = f"reviewer_{reviewer}"
        _write_csv(
            ANNOTATIONS / "stage_a" / f"annotator_{reviewer}_claims.csv",
            [row | {"annotator_id": reviewer_id} for row in claim_rows],
            CLAIM_FIELDS,
        )
        _write_csv(
            ANNOTATIONS / "stage_a" / f"annotator_{reviewer}_message_classification.csv",
            [row | {"annotator_id": reviewer_id} for row in messages.values()],
            MESSAGE_FIELDS,
        )
    packet_target = ANNOTATIONS / "stage_a" / "packets"
    packet_target.mkdir(parents=True, exist_ok=True)
    for stale in packet_target.glob("*.json.gz"):
        stale.unlink()
    packet_count = 0
    for source_path in sorted(packet_source.glob("*.json.gz")):
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            packet = json.load(handle)
        packet["stage"] = "A_v2_2_independent_atomic_claim_extraction"
        packet["truth_assessment"] = "not_assessed_by_semantic_reviewer"
        packet["required_companion_file"] = "message_classification"
        with gzip.open(packet_target / source_path.name, "wt", encoding="utf-8") as handle:
            json.dump(packet, handle, ensure_ascii=False, indent=2)
        packet_count += 1
    return {
        "claim_slots_per_reviewer": len(claim_rows),
        "messages_per_reviewer": len(messages),
        "blind_stage_a_packet_count": packet_count,
    }


def _source_linked_strata() -> dict[str, Any]:
    path = PROCESSED / "source_linked_candidates_v2_1.parquet"
    rows = [
        row for row in pq.read_table(path).to_pylist() if row["selected_for_development_sample"]
    ]
    mapping = {
        "source_agent_named": "possible_source_linked_claim_uptake",
        "explicit_discourse_reference_with_source_phrase": "possible_message_specific_claim_uptake",
        "direct_request_names_recipient": "directive_compliance_or_refusal",
        "explicit_artifact_handoff": "artifact_information_transfer_or_coordination",
    }
    counts = Counter(mapping[row["link_rule"]] for row in rows)
    result = {
        "development_sample_n": len(rows),
        "construct_counts": dict(sorted(counts.items())),
        "epistemic_entry_rule": (
            "Only claim-bearing attribution/reference strata may enter L2; direct requests and "
            "artifact handoffs remain separate auxiliary constructs."
        ),
        "subtypes_reported_separately": True,
    }
    (REPORTS / "source_linked_strata_v2_2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def freeze_annotation_protocol_v2_2() -> dict[str, Any]:
    ANNOTATIONS.mkdir(parents=True, exist_ok=True)
    templates = _blank_stage_a_templates()
    independence_rows = [
        {
            "reviewer_id": f"reviewer_{i}",
            "reviewer_role": "semantic_annotator",
            "pipeline_builder": "",
            "casebook_author": "",
            "seen_candidate_assignments": "",
            "seen_retrieval_scores": "",
            "seen_provisional_interpretations": "",
            "independent_of_retrieval_construction": "",
            "conflict_notes": "",
            "signed_at": "",
        }
        for i in (1, 2)
    ]
    independence_fields = list(independence_rows[0])
    _write_csv(
        ANNOTATIONS / "annotator_independence_declarations.csv",
        independence_rows,
        independence_fields,
    )
    strata = _source_linked_strata()
    frozen_files = [
        SPEC,
        HOLDOUT_PLAN,
        ANNOTATIONS / "annotation_codebook_v2.2.md",
        Path(__file__),
    ]
    missing = [str(path) for path in frozen_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Protocol files missing: {missing}")
    result = {
        "status": "frozen_before_stage_a",
        "v2_1_human_labels_detected": 0,
        "holdout_semantic_content_opened": False,
        "templates": templates,
        "source_linked_strata": strata,
        "frozen_file_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in frozen_files
        },
        "stage_b_release": "blocked_until_both_stage_a_reviewers_are_frozen",
    }
    (REPORTS / "pre_annotation_freeze_v2_2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    completion = {
        "status": "complete_ready_for_development_stage_a",
        "holdout_semantic_content_opened": False,
        "decisions_frozen": {
            "01_stage_a_to_b": "union, frozen near-deduplication, every referent-compatible pair",
            "02_annotator_independence": "one genuinely independent reviewer minimum; blinded declarations required",
            "03_channel_separation": "claim references, directives, and artifact handoffs reported separately",
            "04_no_claim": "ineligible for proposition comparison and separately reported",
            "05_truth": "removed from semantic interface; independent audit only",
            "06_unknowns": "abstentions with ascertainability and lower/upper bounds",
            "07_precision_targets": "broad L1; source-linked L2; L3a/L3b secondary",
            "08_gate_1a": "per-label AC1 point and cluster-bootstrap interval rule",
            "09_gate_1b": "all, hard, ordinary, and placebo comparisons separate",
            "10_holdout_sampling": "exact K, caps, priority, deduplication, and shortfall policy frozen",
            "11_source_linked_holdout": "own untouched evaluation, subtype-separated",
            "12_trace_audit": "A0, A1-A3, all A4-A6/L3b, featured, and memory-negative strata",
            "13_compact_trace": "claim-frozen deterministic anchors, corrections, neighbors, and final states",
            "14_method_diversity": "observable_method_diversity; internal inference not inferred",
            "15_memory": "manual positive review plus deterministic negative audit",
            "16_truth_hierarchy": "artifact, reproduction, logs, screenshots, later reports, unresolved",
            "17_structural_audit": "all high-level positives, hard controls, impossible orderings, and sampled negatives",
            "18_holdout_discipline": "one-shot; failures cannot tune the spent holdout",
        },
        "human_input_next": "two independent Stage A files and signed independence declarations",
    }
    (REPORTS / "completion_audit_v2_2.json").write_text(
        json.dumps(completion, indent=2) + "\n", encoding="utf-8"
    )
    return result


def compile_stage_b_v2_2() -> dict[str, Any]:
    claim_paths = [ANNOTATIONS / "stage_a" / f"annotator_{i}_claims.csv" for i in (1, 2)]
    message_paths = [
        ANNOTATIONS / "stage_a" / f"annotator_{i}_message_classification.csv" for i in (1, 2)
    ]
    incomplete_messages = [
        row
        for path in message_paths
        for row in _read_csv(path)
        if not row.get("claim_presence", "").strip()
    ]
    if incomplete_messages:
        result = {
            "status": "blocked_stage_a_incomplete",
            "incomplete_message_classifications": len(incomplete_messages),
            "stage_b_rows_written": 0,
        }
        (REPORTS / "stage_a_to_b_compilation_v2_2.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result
    declarations = _read_csv(ANNOTATIONS / "annotator_independence_declarations.csv")
    no_exposure = all(
        _normalized(row.get(field)) in {"no", "false"}
        for row in declarations
        for field in (
            "seen_candidate_assignments",
            "seen_retrieval_scores",
            "seen_provisional_interpretations",
        )
    )
    independent_reviewer = any(
        _normalized(row.get("independent_of_retrieval_construction")) in {"yes", "true"}
        for row in declarations
    )
    declarations_signed = len(declarations) >= 2 and all(
        row.get("signed_at", "").strip() for row in declarations
    )
    if not (no_exposure and independent_reviewer and declarations_signed):
        result = {
            "status": "blocked_annotator_independence_declarations",
            "no_prohibited_exposure_declared": no_exposure,
            "independent_reviewer_declared": independent_reviewer,
            "both_declarations_signed": declarations_signed,
            "stage_b_rows_written": 0,
        }
        (REPORTS / "stage_a_to_b_compilation_v2_2.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result
    raw_claims = [row for path in claim_paths for row in _claim_rows(path)]
    claims = deduplicate_claims(raw_claims)
    pairs = generate_stage_b_pairs(claims)
    fields = (
        list(pairs[0])
        if pairs
        else [
            "blind_unit_id",
            "claim_pair_id",
            "source_claim_id",
            "response_claim_id",
            "source_exact_spans",
            "response_exact_spans",
            "source_atomic_proposition",
            "response_atomic_proposition",
            "source_referent",
            "response_referent",
            "proposition_equivalence",
            "recipient_stance",
            "explicit_source_link",
            "lineage_independence",
            "observation_independence",
            "observable_method_diversity",
            "evidence_lineage_class",
            "supporting_event_ids",
            "strongest_alternative_explanation",
            "confidence_1_to_5",
            "notes",
        ]
    )
    for reviewer in (1, 2):
        _write_csv(ANNOTATIONS / "stage_b" / f"annotator_{reviewer}_comparisons.csv", pairs, fields)
    unit_outcomes = classify_stage_a_units(
        raw_claims, pairs, [row for path in message_paths for row in _read_csv(path)]
    )
    extraction_statuses = Counter(row["claim_extraction_pattern"] for row in unit_outcomes.values())
    pairing_statuses = Counter(row["referent_pairing_outcome"] for row in unit_outcomes.values())
    outcome_rows = [
        {"blind_unit_id": blind_id, **outcome}
        for blind_id, outcome in sorted(unit_outcomes.items())
    ]
    _write_csv(
        ANNOTATIONS / "stage_b" / "stage_a_pairing_outcomes.csv",
        outcome_rows,
        [
            "blind_unit_id",
            "claim_extraction_pattern",
            "referent_pairing_outcome",
            "nonclaim_speech_acts",
        ],
    )
    result = {
        "status": "complete",
        "deduplicated_claim_count": len(claims),
        "all_referent_compatible_pair_count": len(pairs),
        "claim_extraction_pattern_counts": dict(extraction_statuses),
        "referent_pairing_outcome_counts": dict(pairing_statuses),
        "episode_aggregation_rule": "L1 positive iff at least one generated pair is judged equivalent",
        "best_pair_selection_permitted": False,
    }
    (REPORTS / "stage_a_to_b_compilation_v2_2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def verify_v2_2() -> dict[str, Any]:
    freeze = json.loads((REPORTS / "pre_annotation_freeze_v2_2.json").read_text(encoding="utf-8"))
    hashes_match = all(
        (ROOT / relative).exists() and sha256_file(ROOT / relative) == expected
        for relative, expected in freeze["frozen_file_hashes"].items()
    )
    checks = {
        "spec_exists": SPEC.exists(),
        "holdout_plan_exists": HOLDOUT_PLAN.exists(),
        "codebook_exists": (ANNOTATIONS / "annotation_codebook_v2.2.md").exists(),
        "stage_a_packet_count_is_60": len(
            list((ANNOTATIONS / "stage_a" / "packets").glob("*.json.gz"))
        )
        == 60,
        "freeze_record_exists": (REPORTS / "pre_annotation_freeze_v2_2.json").exists(),
        "frozen_hashes_match": hashes_match,
        "truth_absent_from_stage_a": all(
            "truth" not in field
            for field in _read_csv(ANNOTATIONS / "stage_a" / "annotator_1_claims.csv")[0]
        ),
        "stage_a_still_blank": not any(
            row.get("atomic_proposition", "").strip()
            for row in _read_csv(ANNOTATIONS / "stage_a" / "annotator_1_claims.csv")
            + _read_csv(ANNOTATIONS / "stage_a" / "annotator_2_claims.csv")
        ),
        "stage_a_event_ids_complete": all(
            row.get("event_id", "").strip()
            for row in _read_csv(ANNOTATIONS / "stage_a" / "annotator_1_claims.csv")
            + _read_csv(ANNOTATIONS / "stage_a" / "annotator_2_claims.csv")
            + _read_csv(ANNOTATIONS / "stage_a" / "annotator_1_message_classification.csv")
            + _read_csv(ANNOTATIONS / "stage_a" / "annotator_2_message_classification.csv")
        ),
        "observable_method_diversity_used": "observable_method_diversity"
        in (ANNOTATIONS / "annotation_codebook_v2.2.md").read_text(encoding="utf-8"),
        "holdout_unopened": json.loads(HOLDOUT_PLAN.read_text(encoding="utf-8"))[
            "holdout_semantic_content_opened"
        ]
        is False,
    }
    result = {"status": "pass" if all(checks.values()) else "fail", "checks": checks}
    (REPORTS / "verification_v2_2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result
