"""Compile blinded machine Stage-A labels into frozen v2.2 Stage-B pairs."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from memetic_village.protocol_v2_2 import (
    _read_csv,
    classify_stage_a_units,
    deduplicate_claims,
    generate_stage_b_pairs,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "annotations" / "v2_2" / "machine"
JUDGES = ("fable_high", "sol_max")
COMBINED = MACHINE / "combined" / "stage_b"

PAIR_FIELDS = [
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

SEMANTIC_CLAIM_FIELDS = {
    "exact_claim_span",
    "atomic_proposition",
    "referent",
    "polarity",
    "claim_type",
}


def populated_claim_rows(path: Path) -> list[dict[str, str]]:
    """Accept fully blank reserved slots and reject partial semantic claims.

    The canonical template always populates unit/role/event identifiers, including
    for unused slots, so those identifiers cannot be used to detect whether a
    semantic claim was entered.
    """
    result = []
    for row in _read_csv(path):
        populated = {field for field in SEMANTIC_CLAIM_FIELDS if (row.get(field) or "").strip()}
        if not populated:
            continue
        missing = SEMANTIC_CLAIM_FIELDS - populated
        if missing:
            raise ValueError(f"Partially completed claim row in {path}: missing {sorted(missing)}")
        result.append(row)
    return result


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    claim_paths = {judge: MACHINE / judge / "stage_a" / "claims.csv" for judge in JUDGES}
    message_paths = {
        judge: MACHINE / judge / "stage_a" / "message_classification.csv" for judge in JUDGES
    }
    missing = [
        str(path) for path in (*claim_paths.values(), *message_paths.values()) if not path.exists()
    ]
    if missing:
        raise SystemExit(f"Machine Stage A is incomplete; missing: {missing}")

    messages = []
    claims = []
    for judge in JUDGES:
        judge_messages = _read_csv(message_paths[judge])
        if len(judge_messages) != 120 or any(
            row.get("annotator_id") != judge or not row.get("claim_presence", "").strip()
            for row in judge_messages
        ):
            raise ValueError(f"{judge}: invalid or incomplete message classification file")
        judge_claims = populated_claim_rows(claim_paths[judge])
        if any(row.get("annotator_id") != judge for row in judge_claims):
            raise ValueError(f"{judge}: annotator ID mismatch in claim file")
        messages.extend(judge_messages)
        claims.extend(judge_claims)

    deduplicated = deduplicate_claims(claims)
    pairs = generate_stage_b_pairs(deduplicated)
    claim_ids = [row["deduplicated_claim_id"] for row in deduplicated]
    pair_ids = [row["claim_pair_id"] for row in pairs]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("Deduplicated claim IDs are not globally unique")
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("Stage-B pair IDs are not globally unique")
    outcomes = classify_stage_a_units(claims, pairs, messages)

    COMBINED.mkdir(parents=True, exist_ok=True)
    dedup_fields = sorted({key for row in deduplicated for key in row})
    write_csv(COMBINED / "deduplicated_claim_union.csv", dedup_fields, deduplicated)
    write_csv(COMBINED / "unannotated_pairs.csv", PAIR_FIELDS, pairs)
    outcome_rows = [
        {"blind_unit_id": blind_id, **outcome} for blind_id, outcome in sorted(outcomes.items())
    ]
    write_csv(
        COMBINED / "stage_a_pairing_outcomes.csv",
        [
            "blind_unit_id",
            "claim_extraction_pattern",
            "referent_pairing_outcome",
            "nonclaim_speech_acts",
        ],
        outcome_rows,
    )
    for judge in JUDGES:
        rows = [{**row, "annotator_id": judge} for row in pairs]
        write_csv(
            MACHINE / judge / "stage_b" / "comparisons.csv", ["annotator_id", *PAIR_FIELDS], rows
        )

    extraction_counts = Counter(row["claim_extraction_pattern"] for row in outcome_rows)
    pairing_counts = Counter(row["referent_pairing_outcome"] for row in outcome_rows)
    manifest = {
        "stage": "B_v2_2_generated_claim_pair_comparison",
        "machine_annotation_not_human_ground_truth": True,
        "judges": list(JUDGES),
        "input_populated_claim_count": len(claims),
        "deduplicated_claim_count": len(deduplicated),
        "referent_compatible_pair_count": len(pairs),
        "globally_unique_claim_ids": True,
        "globally_unique_pair_ids": True,
        "unit_count": len(outcomes),
        "claim_extraction_pattern_counts": dict(extraction_counts),
        "referent_pairing_outcome_counts": dict(pairing_counts),
        "best_pair_selection_permitted": False,
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (*claim_paths.values(), *message_paths.values())
        },
        "status": "complete",
    }
    (COMBINED / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
