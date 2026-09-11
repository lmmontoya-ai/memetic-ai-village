"""Extract exact memory snapshots needed by the claim-frozen Stage-D packets.

The raw export is a large gzip JSONL file, so this performs one streaming pass and
writes only the explicitly referenced before/after/later records.  It does not
inspect holdout material or select snapshots using semantic labels.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_d" / "packets"
RAW = ROOT / "data" / "raw_manifest" / "snapshot" / "agent_memories.jsonl.gz"
OUTPUT = (
    ROOT
    / "annotations"
    / "v2_2"
    / "machine"
    / "combined"
    / "stage_d"
    / "referenced_memory_snapshots.json.gz"
)
MANIFEST = OUTPUT.with_suffix("").with_suffix(".manifest.json")


def read_packet(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    references: dict[str, set[str]] = {}
    wanted: set[str] = set()
    for path in sorted(PACKET_DIR.glob("*.json.gz")):
        packet = read_packet(path)
        delta = packet["memory_delta"]
        ids = {
            str(value)
            for value in (
                delta.get("memory_before_id"),
                delta.get("memory_after_id"),
                *json.loads(delta.get("later_memory_ids") or "[]"),
            )
            if value
        }
        references[packet["blind_unit_id"]] = ids
        wanted.update(ids)
    if not wanted:
        raise SystemExit("No memory snapshot IDs referenced by Stage-D packets")

    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    with gzip.open(RAW, "rt", encoding="utf-8") as handle:
        for line in handle:
            scanned += 1
            row = json.loads(line)
            row_id = str(row.get("id") or "")
            if row_id in wanted:
                found[row_id] = row
                if len(found) == len(wanted):
                    break
            if scanned % 100_000 == 0:
                print(
                    f"memory snapshot scan: {scanned:,} rows; found {len(found)}/{len(wanted)}",
                    flush=True,
                )

    missing = sorted(wanted - set(found))
    output = {
        "stage": "D_v2_2_exact_referenced_memory_snapshots",
        "selection_used_semantic_labels": False,
        "references_by_blind_unit": {
            blind_id: sorted(ids) for blind_id, ids in sorted(references.items())
        },
        "snapshots_by_id": found,
        "missing_ids": missing,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    manifest = {
        "raw_path": str(RAW.relative_to(ROOT)),
        "raw_size_bytes": RAW.stat().st_size,
        "dataset_revision": "504ae8dc5fd254917c4ccbb071d932ad93b3584c",
        "raw_rows_scanned": scanned,
        "target_id_count": len(wanted),
        "found_id_count": len(found),
        "missing_id_count": len(missing),
        "output_path": str(OUTPUT.relative_to(ROOT)),
        "selection_used_semantic_labels": False,
        "status": "complete" if not missing else "incomplete_missing_referenced_ids",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    if missing:
        raise SystemExit(f"Missing {len(missing)} referenced memory snapshots")


if __name__ == "__main__":
    main()
