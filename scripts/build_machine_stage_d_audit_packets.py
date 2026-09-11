"""Augment every claim-frozen Stage-D packet with exact memory snapshots.

All 11 valid-claim-pair development units are included, independent of semantic
labels.  This exceeds the frozen minimum negative audit and ensures any proposed
L4 result can be checked for semantic absence, relocation, and persistence.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_d"
PACKET_DIR = BASE_DIR / "packets"
SNAPSHOT_PATH = BASE_DIR / "referenced_memory_snapshots.json.gz"
STAGE_C_DIR = ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_c" / "packets"
OUTPUT_DIR = BASE_DIR / "audit_packets"


def read_gzip(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_gzip(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def main() -> None:
    extracted = read_gzip(SNAPSHOT_PATH)
    snapshots = extracted["snapshots_by_id"]
    packet_count = 0
    snapshot_references = 0
    for path in sorted(PACKET_DIR.glob("*.json.gz")):
        packet = read_gzip(path)
        blind_id = packet["blind_unit_id"]
        delta = packet["memory_delta"]
        before_id = delta.get("memory_before_id")
        after_id = delta.get("memory_after_id")
        later_ids = json.loads(delta.get("later_memory_ids") or "[]")
        ordered = [
            ("before", before_id),
            ("after", after_id),
            *[(f"later_{index}", value) for index, value in enumerate(later_ids, 1)],
        ]
        exact = []
        for role, memory_id in ordered:
            if not memory_id:
                continue
            if memory_id not in snapshots:
                raise ValueError(f"{blind_id}: missing extracted memory {memory_id}")
            row = snapshots[memory_id]
            exact.append(
                {
                    "snapshot_role": role,
                    "memory_id": memory_id,
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "content": row.get("content") or "",
                }
            )
        stage_c = read_gzip(STAGE_C_DIR / path.name)
        audit = {
            **packet,
            "stage": "D_v2_2_exact_memory_audit_all_valid_pair_units",
            "exact_memory_snapshots": exact,
            "claim_frozen_operational_trace": stage_c["compact_trace"],
            "operational_complete_trace_path": stage_c["complete_trace_path"],
            "audit_scope": (
                "All valid-claim-pair development units, selected without semantic labels; "
                "model identity may be incidentally visible inside raw memory prose."
            ),
        }
        write_gzip(OUTPUT_DIR / path.name, audit)
        packet_count += 1
        snapshot_references += len(exact)
    manifest = {
        "stage": "D_v2_2_exact_memory_audit_packet_build",
        "packet_count": packet_count,
        "fixed_claim_pair_count": sum(
            len(read_gzip(path)["fixed_claim_pairs"])
            for path in sorted(OUTPUT_DIR.glob("*.json.gz"))
        ),
        "exact_snapshot_reference_count": snapshot_references,
        "selection_used_semantic_labels": False,
        "all_valid_claim_pair_units_audited": True,
        "memory_model_identity_blinding_limitation_disclosed": True,
        "status": "complete",
    }
    (BASE_DIR / "audit_packet_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
