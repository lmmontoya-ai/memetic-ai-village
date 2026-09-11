"""Full-trace audit of every claim-frozen Stage-C development unit with Fable.

All 11 valid-claim-pair units are audited, a conservative superset of the frozen
label-stratified audit requirement. Selection therefore does not depend on a
provisional positive or negative machine label.
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import run_fable_stage_c as compact

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_c" / "packets"
OUTPUT_DIR = ROOT / "annotations" / "v2_2" / "machine" / "fable_high" / "stage_c_full_audit"

TASK_INSTRUCTIONS = r"""
You are annotator `fable_high` performing the mandatory full-trace audit for Stage C.
Every valid-claim-pair development unit is included regardless of its compact-trace
label. Judge EVERY fixed pair and do not select a favorable pair.

The packet contains the marked source/response, followed by the entire preserved action
window. Reassess semantic relevance, claim consistency, claim dependency, action type,
execution level, direct verification, and correction. A generic later browser, shell,
memory, or tool event is not claim-dependent merely because it follows the response or
mentions the same artifact. Claim dependency requires a defensible presupposition or
explicit link. Use the highest supported execution level: A0 none; A1 discussed/repeated;
A2 verification attempted; A3 claim-dependent action proposed; A4 attempted; A5
completed; A6 collective/external state changed. Verification is not operational
acceptance. Preserve unclear/insufficient_trace rather than guessing.

Cite only event IDs displayed in this packet and set `full_trace_consulted` to true.
Truth, candidate/control status, and causal influence are not assessed. Return every
fixed claim pair exactly once.
""".strip()

OUTPUT_SCHEMA = copy.deepcopy(compact.OUTPUT_SCHEMA)
OUTPUT_SCHEMA["properties"]["units"]["items"]["properties"]["labels"]["items"]["properties"][
    "full_trace_consulted"
]["enum"] = [True]

AUDIT_FIELDS = [*compact.FIELDS, "changed_fields_from_compact"]


def read_gzip(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def payload(packet: dict[str, Any]) -> dict[str, Any]:
    full = read_gzip(ROOT / packet["complete_trace_path"])
    marked = [
        event
        for event in packet["compact_trace"]
        if str(event.get("event_type") or "").startswith("marked_")
    ]
    return {
        "blind_unit_id": packet["blind_unit_id"],
        "fixed_claim_pairs": packet["fixed_claim_pairs"],
        "marked_messages": marked,
        "complete_action_window": full["events"],
        "full_trace_event_count": len(full["events"]),
    }


def validate(structured: dict[str, Any], packet: dict[str, Any], supplied: dict[str, Any]) -> None:
    blind_id = packet["blind_unit_id"]
    expected = {row["claim_pair_id"] for row in packet["fixed_claim_pairs"]}
    valid_events = {
        row["event_id"]
        for row in [*supplied["marked_messages"], *supplied["complete_action_window"]]
    }
    units = structured.get("units")
    if not isinstance(units, list) or len(units) != 1 or units[0].get("blind_unit_id") != blind_id:
        raise ValueError(f"{blind_id}: full-audit unit identity mismatch")
    labels = units[0].get("labels")
    if not isinstance(labels, list):
        raise TypeError(f"{blind_id}: labels not an array")
    ids = [row.get("fixed_claim_id") for row in labels]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError(f"{blind_id}: full-audit fixed claim IDs mismatch")
    for row in labels:
        if row.get("semantic_relevance") not in compact.SEMANTIC_RELEVANCE:
            raise ValueError(f"{blind_id}: invalid semantic relevance")
        if row.get("claim_consistency") not in compact.CLAIM_CONSISTENCY:
            raise ValueError(f"{blind_id}: invalid claim consistency")
        if row.get("claim_dependency") not in compact.CLAIM_DEPENDENCY:
            raise ValueError(f"{blind_id}: invalid claim dependency")
        if row.get("action_type") not in compact.ACTION_TYPES:
            raise ValueError(f"{blind_id}: invalid action type")
        if row.get("execution_level") not in compact.EXECUTION_LEVELS:
            raise ValueError(f"{blind_id}: invalid execution level")
        if row.get("verification_separate") not in compact.TERNARY_TRACE:
            raise ValueError(f"{blind_id}: invalid verification")
        if row.get("correction") not in compact.TERNARY_TRACE:
            raise ValueError(f"{blind_id}: invalid correction")
        if row.get("full_trace_consulted") is not True:
            raise ValueError(f"{blind_id}: full trace not acknowledged")
        support = row.get("supporting_event_ids")
        if not isinstance(support, list):
            raise TypeError(f"{blind_id}: support IDs not an array")
        unsupported = [value for value in support if value not in valid_events]
        if unsupported:
            row["supporting_event_ids"] = [value for value in support if value in valid_events]
            row["notes"] = "; ".join(
                filter(
                    None,
                    [
                        row.get("notes", ""),
                        "unsupported_event_ids_removed_by_validator:" + ",".join(unsupported),
                    ],
                )
            )
            support = row["supporting_event_ids"]
        if not support:
            raise ValueError(f"{blind_id}: no valid full-trace support ID")
        confidence = row.get("confidence_1_to_5")
        if not isinstance(confidence, int) or not 1 <= confidence <= 5:
            raise ValueError(f"{blind_id}: invalid confidence")


def run_one(
    index: int, packet: dict[str, Any], retries: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_dir, structured_dir = OUTPUT_DIR / "raw", OUTPUT_DIR / "structured"
    raw_dir.mkdir(parents=True, exist_ok=True)
    structured_dir.mkdir(parents=True, exist_ok=True)
    response_path = raw_dir / f"unit_{index:03d}_response.json"
    structured_path = structured_dir / f"unit_{index:03d}.json"
    supplied = payload(packet)
    if response_path.exists() and structured_path.exists():
        wrapper = json.loads(response_path.read_text(encoding="utf-8"))
        structured = json.loads(structured_path.read_text(encoding="utf-8"))
        validate(structured, packet, supplied)
        return wrapper, structured
    prompt = json.dumps(
        {"instructions": TASK_INSTRUCTIONS, "packet": supplied},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    command = [
        "claude",
        "-p",
        "--model",
        "fable",
        "--effort",
        "high",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(OUTPUT_SCHEMA, separators=(",", ":")),
        "--no-session-persistence",
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--system-prompt",
        compact.SYSTEM_PROMPT,
        "--exclude-dynamic-system-prompt-sections",
    ]
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            timeout=1200,
            check=False,
        )
        try:
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Claude exited {completed.returncode}: {completed.stderr[-2000:]}"
                )
            wrapper = json.loads(completed.stdout)
            if wrapper.get("is_error") or wrapper.get("subtype") != "success":
                raise RuntimeError("Claude wrapper reports failure")
            structured = wrapper.get("structured_output")
            if not isinstance(structured, dict):
                structured = json.loads(wrapper["result"])
            validate(structured, packet, supplied)
            response_path.write_text(
                json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            structured_path.write_text(
                json.dumps(structured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            return wrapper, structured
        except Exception as exc:  # noqa: BLE001  # preserve invalid attempts for audit
            last_error = exc
            (raw_dir / f"unit_{index:03d}_attempt_{attempt}_failure.json").write_text(
                json.dumps(
                    {
                        "error": str(exc),
                        "returncode": completed.returncode,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            if attempt <= retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Full-audit unit {index} failed: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    packets = [compact.read_packet(path) for path in sorted(PACKET_DIR.glob("*.json.gz"))]
    if len(packets) != 11:
        raise SystemExit(f"Expected 11 claim-pair packets, found {len(packets)}")
    compact_rows = {}
    with (ROOT / "annotations/v2_2/machine/fable_high/stage_c/actions.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            compact_rows[(row["blind_unit_id"], row["fixed_claim_id"])] = row
    results = []
    for index, packet in enumerate(packets, 1):
        print(
            f"Fable full-trace audit {index}/{len(packets)}: {packet['blind_unit_id']}", flush=True
        )
        results.append((packet, *run_one(index, packet, args.retries)))
    rows, wrappers = [], []
    compared_fields = [
        "semantic_relevance",
        "claim_consistency",
        "claim_dependency",
        "action_type",
        "execution_level",
        "verification_separate",
        "correction",
    ]
    for packet, wrapper, structured in results:
        wrappers.append(wrapper)
        blind_id = packet["blind_unit_id"]
        for label in structured["units"][0]["labels"]:
            previous = compact_rows[(blind_id, label["fixed_claim_id"])]
            changed = [field for field in compared_fields if previous[field] != str(label[field])]
            rows.append(
                {
                    "blind_unit_id": blind_id,
                    "annotator_id": "fable_high",
                    **{
                        key: (";".join(value) if key == "supporting_event_ids" else value)
                        for key, value in label.items()
                    },
                    "changed_fields_from_compact": ";".join(changed),
                }
            )
    rows.sort(key=lambda row: (row["blind_unit_id"], row["fixed_claim_id"]))
    with (OUTPUT_DIR / "actions_full_trace_audit.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    observed_usage: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    for wrapper in wrappers:
        for model, usage in (wrapper.get("modelUsage") or {}).items():
            observed_usage[model]["input_tokens"] += int(usage.get("inputTokens") or 0)
            observed_usage[model]["output_tokens"] += int(usage.get("outputTokens") or 0)
            observed_usage[model]["cost_usd"] += float(usage.get("costUSD") or 0)
    manifest = {
        "annotator_id": "fable_high",
        "requested_model_alias": "fable",
        "observed_cli_model_usage": {
            model: {
                **usage,
                "cost_usd": round(float(usage["cost_usd"]), 6),
            }
            for model, usage in sorted(observed_usage.items())
        },
        "effort": "high",
        "stage": "C_v2_2_full_trace_audit_all_valid_pair_units",
        "machine_annotation_not_human_ground_truth": True,
        "unit_count": len(packets),
        "fixed_claim_pair_count": len(rows),
        "all_valid_claim_pair_units_full_audited": True,
        "selection_used_compact_semantic_labels": False,
        "rows_with_any_label_change": sum(bool(row["changed_fields_from_compact"]) for row in rows),
        "total_cost_usd_reported_by_cli": round(
            sum(float(w.get("total_cost_usd") or 0) for w in wrappers), 6
        ),
        "task_instructions_sha256": hashlib.sha256(TASK_INSTRUCTIONS.encode()).hexdigest(),
        "validation": "passed",
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
