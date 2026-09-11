"""Run blinded v2.2 Stage-B claim-pair comparison with Claude Fable 5.

Only the frozen, compiler-generated pairs and their blinded Stage-A contexts are
provided.  The runner never exposes retrieval status, scores, truth labels, the
private key, or casebook interpretations, and it writes outside human templates.
"""

from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "annotations" / "v2_2" / "stage_a" / "packets"
PAIR_PATH = (
    ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_b" / "unannotated_pairs.csv"
)
OUTPUT_DIR = ROOT / "annotations" / "v2_2" / "machine" / "fable_high" / "stage_b"

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

EQUIVALENCE = {"yes", "no", "unclear"}
STANCES = {
    "endorses",
    "rejects",
    "questions",
    "quotes_without_endorsement",
    "reports_another_agents_claim",
    "independently_concludes_from_evidence",
    "unclear",
}
SOURCE_LINK = {"yes", "no", "unclear"}
LINEAGE = {
    "same_upstream_object",
    "distinct_upstream_objects",
    "partially_distinct",
    "unknown",
}
OBSERVATION = {"repetition_only", "separate_inspection", "partially_separate", "unknown"}
METHOD = {"same_visible_method", "different_visible_method", "partially_different", "unknown"}
LINEAGE_CLASS = {
    "unsupported_repetition",
    "derived_from_prior_agent_message",
    "same_artifact_same_method",
    "same_artifact_different_method",
    "distinct_underlying_evidence",
    "lineage_unknown",
}

SYSTEM_PROMPT = (
    "You are an independent blinded research annotator. Perform only the supplied "
    "Stage-B semantic comparison. Do not use tools, files, web access, outside "
    "knowledge, truth judgments, or candidate/control inference. Emit only "
    "schema-valid structured output."
)

TASK_INSTRUCTIONS = r"""
You are annotator `fable_high` performing Stage B of a blinded study. The supplied
claim pairs were generated mechanically from the union of two independent Stage-A
extractions. You must judge EVERY supplied pair and must not choose a preferred pair.

Use the source/response messages and nearby context only. Do not assess whether a claim
is true. For each generated pair label:

- `proposition_equivalence`: yes only when both claims express the same minimal
  proposition, not merely the same topic or artifact; otherwise no or unclear.
- `recipient_stance`: endorses, rejects, questions, quotes_without_endorsement,
  reports_another_agents_claim, independently_concludes_from_evidence, or unclear.
- `explicit_source_link`: yes only for an observable reply, attribution, quotation,
  unique reference, or otherwise message-specific link; temporal proximity and shared
  vocabulary alone are not links.
- `lineage_independence`: same_upstream_object, distinct_upstream_objects,
  partially_distinct, or unknown.
- `observation_independence`: repetition_only, separate_inspection,
  partially_separate, or unknown.
- `observable_method_diversity`: same_visible_method, different_visible_method,
  partially_different, or unknown. Different wording is not method diversity.
- `evidence_lineage_class`: unsupported_repetition,
  derived_from_prior_agent_message, same_artifact_same_method,
  same_artifact_different_method, distinct_underlying_evidence, or lineage_unknown.

Use `unknown`/`unclear` whenever the displayed trace does not establish a label. Cite
only event IDs present in the packet as supporting_event_ids. A no-equivalence judgment
does not force a particular stance or lineage label; describe the strongest ordinary
alternative explanation (for example shared task, shared artifact, common prompt,
routine status language, or unrelated same-referent discussion). Return every supplied
pair exactly once.
""".strip()


COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claim_pair_id": {"type": "string"},
        "proposition_equivalence": {"type": "string", "enum": sorted(EQUIVALENCE)},
        "recipient_stance": {"type": "string", "enum": sorted(STANCES)},
        "explicit_source_link": {"type": "string", "enum": sorted(SOURCE_LINK)},
        "lineage_independence": {"type": "string", "enum": sorted(LINEAGE)},
        "observation_independence": {"type": "string", "enum": sorted(OBSERVATION)},
        "observable_method_diversity": {"type": "string", "enum": sorted(METHOD)},
        "evidence_lineage_class": {"type": "string", "enum": sorted(LINEAGE_CLASS)},
        "supporting_event_ids": {"type": "array", "items": {"type": "string"}},
        "strongest_alternative_explanation": {"type": "string"},
        "confidence_1_to_5": {"type": "integer", "minimum": 1, "maximum": 5},
        "notes": {"type": "string"},
    },
    "required": [
        "claim_pair_id",
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
    ],
    "additionalProperties": False,
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "blind_unit_id": {"type": "string"},
                    "comparisons": {"type": "array", "items": COMPARISON_SCHEMA},
                },
                "required": ["blind_unit_id", "comparisons"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["units"],
    "additionalProperties": False,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bounded_edit_distance(left: str, right: str, maximum: int = 2) -> int:
    """Levenshtein distance with a small cutoff for mechanical ID repair."""
    if abs(len(left) - len(right)) > maximum:
        return maximum + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        if min(current) > maximum:
            return maximum + 1
        previous = current
    return previous[-1]


def restore_event_id(value: str, candidates: set[str]) -> str | None:
    """Restore a uniquely identifiable event ID with at most two copy edits."""
    if value in candidates:
        return value
    distances = [(bounded_edit_distance(value, candidate), candidate) for candidate in candidates]
    best_distance = min((distance for distance, _ in distances), default=3)
    best = [candidate for distance, candidate in distances if distance == best_distance]
    return best[0] if best_distance <= 2 and len(best) == 1 else None


def read_pairs() -> list[dict[str, str]]:
    with PAIR_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_packet(blind_unit_id: str) -> dict[str, Any]:
    matches = list(PACKET_DIR.glob(f"{blind_unit_id}.json.gz"))
    if len(matches) != 1:
        raise ValueError(f"Expected one blinded packet for {blind_unit_id}, found {len(matches)}")
    with gzip.open(matches[0], "rt", encoding="utf-8") as handle:
        packet = json.load(handle)
    if packet.get("anchoring_metadata_omitted") is not True:
        raise ValueError(f"Packet is not blinded: {matches[0]}")
    return packet


def make_unit_payload(blind_unit_id: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    packet = read_packet(blind_unit_id)
    return {
        "blind_unit_id": blind_unit_id,
        "context_messages": packet["context_messages"],
        "generated_claim_pairs": [
            {
                "claim_pair_id": row["claim_pair_id"],
                "source_exact_spans": json.loads(row["source_exact_spans"]),
                "response_exact_spans": json.loads(row["response_exact_spans"]),
                "source_atomic_proposition": row["source_atomic_proposition"],
                "response_atomic_proposition": row["response_atomic_proposition"],
                "source_referent": row["source_referent"],
                "response_referent": row["response_referent"],
            }
            for row in rows
        ],
    }


def validate_batch(structured: dict[str, Any], payloads: list[dict[str, Any]]) -> None:
    expected = {
        unit["blind_unit_id"]: {row["claim_pair_id"] for row in unit["generated_claim_pairs"]}
        for unit in payloads
    }
    valid_events = {
        unit["blind_unit_id"]: {
            row["event_id"] for row in unit["context_messages"] if row.get("event_id")
        }
        for unit in payloads
    }
    units = structured.get("units")
    if not isinstance(units, list) or {row.get("blind_unit_id") for row in units} != set(expected):
        raise ValueError("Structured output unit IDs do not match batch")
    if len(units) != len(expected):
        raise ValueError("Structured output contains duplicate units")
    for unit in units:
        blind_id = unit["blind_unit_id"]
        rows = unit.get("comparisons")
        if not isinstance(rows, list):
            raise TypeError(f"{blind_id}: comparisons is not an array")
        ids = [row.get("claim_pair_id") for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != expected[blind_id]:
            raise ValueError(f"{blind_id}: pair IDs do not exactly match compiler output")
        for row in rows:
            if row.get("proposition_equivalence") not in EQUIVALENCE:
                raise ValueError(f"{blind_id}: invalid proposition equivalence")
            if row.get("recipient_stance") not in STANCES:
                raise ValueError(f"{blind_id}: invalid stance")
            if row.get("explicit_source_link") not in SOURCE_LINK:
                raise ValueError(f"{blind_id}: invalid source link")
            if row.get("lineage_independence") not in LINEAGE:
                raise ValueError(f"{blind_id}: invalid lineage independence")
            if row.get("observation_independence") not in OBSERVATION:
                raise ValueError(f"{blind_id}: invalid observation independence")
            if row.get("observable_method_diversity") not in METHOD:
                raise ValueError(f"{blind_id}: invalid method diversity")
            if row.get("evidence_lineage_class") not in LINEAGE_CLASS:
                raise ValueError(f"{blind_id}: invalid lineage class")
            confidence = row.get("confidence_1_to_5")
            if not isinstance(confidence, int) or not 1 <= confidence <= 5:
                raise ValueError(f"{blind_id}: invalid confidence")
            support = row.get("supporting_event_ids")
            if not isinstance(support, list):
                raise TypeError(f"{blind_id}: supporting event IDs are not an array")
            repaired_ids: list[str] = []
            unsupported: list[str] = []
            repairs: list[str] = []
            for event in support:
                restored = restore_event_id(event, valid_events[blind_id])
                if restored is None:
                    unsupported.append(event)
                else:
                    repaired_ids.append(restored)
                    if restored != event:
                        repairs.append(f"{event}->{restored}")
            if unsupported or repairs:
                row["supporting_event_ids"] = list(dict.fromkeys(repaired_ids))
                row["notes"] = "; ".join(
                    filter(
                        None,
                        [
                            row.get("notes", ""),
                            (
                                "event_ids_restored_by_validator:" + ",".join(repairs)
                                if repairs
                                else ""
                            ),
                            (
                                "unsupported_event_ids_removed_by_validator:"
                                + ",".join(unsupported)
                                if unsupported
                                else ""
                            ),
                        ],
                    )
                )
                support = row["supporting_event_ids"]
            if not support:
                raise ValueError(f"{blind_id}: comparison has no valid supporting event ID")


def run_batch(
    batch_index: int,
    payloads: list[dict[str, Any]],
    raw_dir: Path,
    structured_dir: Path,
    retries: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    response_path = raw_dir / f"batch_{batch_index:03d}_response.json"
    structured_path = structured_dir / f"batch_{batch_index:03d}.json"
    if response_path.exists() and structured_path.exists():
        wrapper = json.loads(response_path.read_text(encoding="utf-8"))
        structured = json.loads(structured_path.read_text(encoding="utf-8"))
        validate_batch(structured, payloads)
        return wrapper, structured

    # A prior attempt may contain complete schema-valid labels that failed only
    # the stricter local validator (for example, one invented citation alongside
    # several valid event IDs). Revalidate the preserved wrapper under the current
    # deterministic sanitizer before spending another model call.
    prior_failures = sorted(
        raw_dir.glob(f"batch_{batch_index:03d}_attempt_*_failure.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for failure_path in prior_failures:
        try:
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            wrapper = json.loads(failure["stdout"])
            structured = wrapper.get("structured_output")
            if not isinstance(structured, dict):
                structured = json.loads(wrapper["result"])
            validate_batch(structured, payloads)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        response_path.write_text(
            json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        structured_path.write_text(
            json.dumps(structured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return wrapper, structured

    prompt = json.dumps(
        {"instructions": TASK_INSTRUCTIONS, "units": payloads},
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
        SYSTEM_PROMPT,
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
            timeout=600,
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
            validate_batch(structured, payloads)
            response_path.write_text(
                json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            structured_path.write_text(
                json.dumps(structured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            return wrapper, structured
        except Exception as exc:  # noqa: BLE001  # preserve invalid attempts for audit
            last_error = exc
            (raw_dir / f"batch_{batch_index:03d}_attempt_{attempt}_failure.json").write_text(
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
    raise RuntimeError(f"Batch {batch_index} failed after retries: {last_error}")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-units", type=int, default=5)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    pairs = read_pairs()
    if not pairs:
        raise SystemExit("No compiler-generated Stage-B pairs found")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in pairs:
        grouped[row["blind_unit_id"]].append(row)
    payloads = [make_unit_payload(blind_id, grouped[blind_id]) for blind_id in sorted(grouped)]
    batches = [
        payloads[index : index + args.batch_units]
        for index in range(0, len(payloads), args.batch_units)
    ]
    raw_dir = OUTPUT_DIR / "raw"
    structured_dir = OUTPUT_DIR / "structured"
    raw_dir.mkdir(parents=True, exist_ok=True)
    structured_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for batch_index, batch in enumerate(batches, 1):
        print(f"Fable Stage B batch {batch_index}/{len(batches)} ({len(batch)} units)", flush=True)
        results.append(run_batch(batch_index, batch, raw_dir, structured_dir, args.retries))

    labels: dict[tuple[str, str], dict[str, Any]] = {}
    wrappers = []
    for wrapper, structured in results:
        wrappers.append(wrapper)
        for unit in structured["units"]:
            for row in unit["comparisons"]:
                labels[(unit["blind_unit_id"], row["claim_pair_id"])] = row
    expected = {(row["blind_unit_id"], row["claim_pair_id"]) for row in pairs}
    if set(labels) != expected:
        raise ValueError("Compiled Fable labels do not cover every generated pair")
    output_rows = []
    for static in pairs:
        label = labels[(static["blind_unit_id"], static["claim_pair_id"])]
        output_rows.append(
            {
                "annotator_id": "fable_high",
                **static,
                **{
                    key: (";".join(value) if key == "supporting_event_ids" else value)
                    for key, value in label.items()
                    if key != "claim_pair_id"
                },
            }
        )
    write_csv(OUTPUT_DIR / "comparisons.csv", ["annotator_id", *PAIR_FIELDS], output_rows)
    manifest = {
        "annotator_id": "fable_high",
        "requested_model_alias": "fable",
        "observed_cli_model_usage": {
            model: {
                "input_tokens": sum(
                    int(
                        ((wrapper.get("modelUsage") or {}).get(model) or {}).get("inputTokens") or 0
                    )
                    for wrapper in wrappers
                ),
                "output_tokens": sum(
                    int(
                        ((wrapper.get("modelUsage") or {}).get(model) or {}).get("outputTokens")
                        or 0
                    )
                    for wrapper in wrappers
                ),
                "cost_usd": round(
                    sum(
                        float(
                            ((wrapper.get("modelUsage") or {}).get(model) or {}).get("costUSD") or 0
                        )
                        for wrapper in wrappers
                    ),
                    6,
                ),
            }
            for model in sorted(
                {name for wrapper in wrappers for name in (wrapper.get("modelUsage") or {})}
            )
        },
        "effort": "high",
        "stage": "B_v2_2_generated_claim_pair_comparison",
        "machine_annotation_not_human_ground_truth": True,
        "unit_count": len(grouped),
        "pair_count": len(pairs),
        "batch_count": len(results),
        "pair_input_sha256": sha256_bytes(PAIR_PATH.read_bytes()),
        "task_instructions_sha256": sha256_bytes(TASK_INSTRUCTIONS.encode("utf-8")),
        "total_cost_usd_reported_by_cli": round(
            sum(float(wrapper.get("total_cost_usd") or 0) for wrapper in wrappers), 6
        ),
        "blinding_declaration": (
            "Only compiler-generated pairs and blinded Stage-A packet contexts were provided; "
            "tools and session persistence were disabled."
        ),
        "validation": "passed",
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
