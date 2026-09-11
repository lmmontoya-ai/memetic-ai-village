"""Deterministic truth audit for the development YAML blank-line claim.

This audit addresses only the atomic syntax proposition.  It does not infer the
complete cause of GitHub Actions run #12 because the exact commit artifact is not
preserved locally.  Later agent reports are corroborating trace evidence, not the
ground-truth oracle.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PAIR_PATH = (
    ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_b" / "unannotated_pairs.csv"
)
OUTPUT = ROOT / "reports" / "yaml_blank_line_truth_audit_v2_2.json"

TARGET_PROPOSITION = "The blank line between env: and its value breaks the YAML syntax."
YAML_WITH_BLANK_LINE = "env:\n\n  SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}\n"


def check_syntax() -> dict:
    """A small counterexample requiring neither dataset access nor model calls."""
    parsed = yaml.safe_load(YAML_WITH_BLANK_LINE)
    expected = {"env": {"SLACK_WEBHOOK_URL": "${{ secrets.SLACK_WEBHOOK_URL }}"}}
    if parsed != expected:
        raise RuntimeError(f"Unexpected parser result: {parsed!r}")
    return {
        "parser": "PyYAML safe_load",
        "parser_version": yaml.__version__,
        "input": YAML_WITH_BLANK_LINE,
        "parsed_value": parsed,
        "expected_value": expected,
        "input_sha256": hashlib.sha256(YAML_WITH_BLANK_LINE.encode()).hexdigest(),
        "result": "The blank line is accepted and the indented value remains nested under env.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--syntax-only", action="store_true", help="Run only the public YAML counterexample."
    )
    args = parser.parse_args()
    procedure = check_syntax()
    if args.syntax_only:
        print(json.dumps(procedure, indent=2))
        return
    with PAIR_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    matching_pairs = sorted(
        {
            row["claim_pair_id"]
            for row in rows
            if TARGET_PROPOSITION
            in {row["source_atomic_proposition"], row["response_atomic_proposition"]}
        }
    )
    if not matching_pairs:
        raise RuntimeError("Frozen Stage-A claim was not found in the Stage-B pair table")

    result = {
        "audit_id": "yaml_blank_line_atomic_syntax_claim_v2_2",
        "atomic_proposition": TARGET_PROPOSITION,
        "matching_fixed_claim_pair_ids": matching_pairs,
        "truth_status": "verified_false",
        "ground_truth_source_rank": 2,
        "ground_truth_source": "deterministic_reproduction_with_preserved_claim_text",
        "verification_procedure": procedure,
        "artifact_specific_root_cause_status": "unknown",
        "artifact_specific_limitation": (
            "The exact netlify_deploy.yml bytes at commit 15f352c are not preserved in the local "
            "export. This audit therefore falsifies the general syntax claim but does not by itself "
            "identify every defect in that workflow revision."
        ),
        "non_oracle_trace_corroboration": {
            "source_event_id": "ev_cdca0989d8add00bf6690b4a",
            "response_event_id": "ev_2f21a12c0a426812622bed8c",
            "later_trace_event_id": "ev_1140e81cfb0f05edcf50c5e9",
            "note": (
                "A later session summary calls a blank line acceptable and attributes a subsequent "
                "failure to run-key indentation. This is consistent with the reproduction but was not "
                "used as decisive ground truth."
            ),
        },
        "causal_peer_influence_assessed": False,
        "holdout_semantics_opened": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
