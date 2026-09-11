"""Protect completed annotations from commands that regenerate blank templates."""

from __future__ import annotations

import csv
from pathlib import Path

LABEL_FIELDS = {
    "atomic_proposition",
    "exact_claim_span",
    "claim_presence",
    "same_proposition",
    "proposition_match",
    "proposition_equivalence",
    "recipient_stance",
    "explicit_source_link",
    "claim_dependency",
    "execution_level",
    "memory_meaning",
    "third_party_restatement",
    "source_pointer_round_trip",
    "timestamp_reconstruction_correct",
    "signed_at",
}
REBUILD_COMMANDS = {
    "all",
    "v2-all",
    "v2-annotations",
    "v2-1-all",
    "v2-1-annotations",
    "v2-2-freeze",
}


def protect_annotations(root: Path, command: str) -> None:
    if command == "v2-2-compile-stage-b":
        directories = [root / "annotations/v2_2/stage_b"]
    elif command in REBUILD_COMMANDS:
        directories = [root / "annotations"]
    else:
        return
    for directory in directories:
        for path in sorted(directory.rglob("*.csv")):
            if any(part in {"machine", "private", "packets", "full_traces"} for part in path.parts):
                continue
            with path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    if any(row.get(field, "").strip() for field in LABEL_FIELDS):
                        relative = path.relative_to(root).as_posix()
                        raise ValueError(
                            f"{command} would overwrite or invalidate completed annotations in "
                            f"{relative}. Rebuild in a separate checkout; preserve signed inputs."
                        )
