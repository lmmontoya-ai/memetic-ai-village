"""Run blinded v2.2 Stage-D memory/re-expression annotation with Fable 5 high."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_d" / "audit_packets"
OUTPUT_DIR = ROOT / "annotations" / "v2_2" / "machine" / "fable_high" / "stage_d"

MEMORY_MEANING = {
    "records_true",
    "records_uncertain",
    "records_correction",
    "attributes_claim_only",
    "no_relevant_content",
    "unknown",
}
YES_NO_UNKNOWN = {"yes", "no", "unknown"}
WRITER = {"agent_written", "automatic", "mixed", "unknown"}
TRACE_LABEL = {"yes", "no", "unclear", "insufficient_trace"}
THIRD_PARTY_STANCE = {
    "endorses",
    "operationalizes",
    "rejects",
    "questions",
    "quotes_without_endorsement",
    "reports_another_agents_claim",
    "unclear",
    "no_candidate",
    "insufficient_trace",
}

FIELDS = [
    "blind_unit_id",
    "annotator_id",
    "fixed_claim_id",
    "memory_meaning",
    "memory_supporting_span",
    "memory_absent_before",
    "memory_relocation_or_rephrasing",
    "memory_writer_mechanism",
    "memory_survives_consolidation",
    "later_behavioral_use",
    "later_use_event_ids",
    "third_party_restatement",
    "third_party_stance",
    "third_party_supporting_event_ids",
    "new_recipient_event_ids",
    "confidence_1_to_5",
    "notes",
]

SYSTEM_PROMPT = (
    "You are an independent blinded research annotator. Perform only the supplied "
    "Stage-D memory and third-party-expression task. Do not use tools, files, web "
    "access, outside knowledge, truth judgments, or candidate/control inference. "
    "Emit only schema-valid structured output."
)

TASK_INSTRUCTIONS = r"""
You are annotator `fable_high` performing Stage D of a blinded study. Judge EVERY fixed
claim pair and do not select a favorable pair. Truth is not part of this task.

For memory:
- `memory_meaning`: records_true means the memory records the proposition as true (not
  that the proposition is objectively true); records_uncertain; records_correction;
  attributes_claim_only; no_relevant_content; or unknown.
- Copy a verbatim `memory_supporting_span` from the displayed delta when relevant.
- Assess whether the content was absent before, could merely be relocation/rephrasing,
  and whether the writer mechanism is agent_written, automatic, mixed, or unknown.
- `memory_survives_consolidation` requires semantic survival, not merely a mechanical
  overlap flag. Compare the exact later snapshot contents supplied in the packet.
- `later_behavioral_use` is yes only for a later action demonstrably relying on the
  recorded claim. Use the supplied claim-frozen operational trace; if it does not
  establish reliance, use insufficient_trace rather than assuming it.

For third-party expression, `yes` requires all of the following: the original response
agent later expresses the same proposition; it endorses or operationalizes rather than
rejecting/quoting it; at least one new agent could receive the later message; and the new
recipient differs from source and retransmitter. Lexical overlap alone is insufficient.
Use only displayed `later_event_id` values as supporting/new-recipient event IDs.

Preserve unknown/unclear/insufficient_trace rather than guessing. Do not assign a final
L0-L4 evidence level; that is computed across frozen stages. Return each fixed claim pair
exactly once.
""".strip()

LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fixed_claim_id": {"type": "string"},
        "memory_meaning": {"type": "string", "enum": sorted(MEMORY_MEANING)},
        "memory_supporting_span": {"type": "string"},
        "memory_absent_before": {"type": "string", "enum": sorted(YES_NO_UNKNOWN)},
        "memory_relocation_or_rephrasing": {"type": "string", "enum": sorted(YES_NO_UNKNOWN)},
        "memory_writer_mechanism": {"type": "string", "enum": sorted(WRITER)},
        "memory_survives_consolidation": {"type": "string", "enum": sorted(YES_NO_UNKNOWN)},
        "later_behavioral_use": {"type": "string", "enum": sorted(TRACE_LABEL)},
        "later_use_event_ids": {"type": "array", "items": {"type": "string"}},
        "third_party_restatement": {"type": "string", "enum": sorted(TRACE_LABEL)},
        "third_party_stance": {"type": "string", "enum": sorted(THIRD_PARTY_STANCE)},
        "third_party_supporting_event_ids": {"type": "array", "items": {"type": "string"}},
        "new_recipient_event_ids": {"type": "array", "items": {"type": "string"}},
        "confidence_1_to_5": {"type": "integer", "minimum": 1, "maximum": 5},
        "notes": {"type": "string"},
    },
    "required": [field for field in FIELDS if field not in {"blind_unit_id", "annotator_id"}],
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
                    "labels": {"type": "array", "items": LABEL_SCHEMA},
                },
                "required": ["blind_unit_id", "labels"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["units"],
    "additionalProperties": False,
}

PUNCTUATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_packet(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        packet = json.load(handle)
    if packet.get("stage") != "D_v2_2_exact_memory_audit_all_valid_pair_units":
        raise ValueError(f"Unexpected stage in {path}")
    if packet.get("stage_b_semantic_labels_used") is not False:
        raise ValueError(f"Stage-B labels affected packet {path}")
    return packet


def payload(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "blind_unit_id": packet["blind_unit_id"],
        "fixed_claim_pairs": packet["fixed_claim_pairs"],
        "memory_delta": packet["memory_delta"],
        "memory_trace_limitations": packet["memory_trace_limitations"],
        "exact_memory_snapshots": packet["exact_memory_snapshots"],
        "claim_frozen_operational_trace": packet["claim_frozen_operational_trace"],
        "third_party_expression_candidates": packet["third_party_expression_candidates"],
    }


def restore_memory_span(span: str, memory_text: str) -> tuple[str, bool]:
    if not span or span in memory_text:
        return span, False
    folded_span, folded_text = span.translate(PUNCTUATION), memory_text.translate(PUNCTUATION)
    starts, offset = [], 0
    while True:
        start = folded_text.find(folded_span, offset)
        if start < 0:
            break
        starts.append(start)
        offset = start + 1
    if len(starts) != 1:
        return span, False
    restored = memory_text[starts[0] : starts[0] + len(span)]
    return (restored, True) if restored.translate(PUNCTUATION) == folded_span else (span, False)


def validate_batch(structured: dict[str, Any], packets: list[dict[str, Any]]) -> None:
    expected = {
        packet["blind_unit_id"]: {row["claim_pair_id"] for row in packet["fixed_claim_pairs"]}
        for packet in packets
    }
    valid_later = {
        packet["blind_unit_id"]: {
            row["later_event_id"] for row in packet["third_party_expression_candidates"]
        }
        for packet in packets
    }
    valid_action_events = {
        packet["blind_unit_id"]: {
            row["event_id"] for row in packet["claim_frozen_operational_trace"]
        }
        for packet in packets
    }
    memory_texts = {}
    for packet in packets:
        delta = packet["memory_delta"]
        delta_spans = [
            *json.loads(delta.get("added_spans") or "[]"),
            *json.loads(delta.get("removed_or_rewritten_spans") or "[]"),
        ]
        snapshot_contents = [row.get("content") or "" for row in packet["exact_memory_snapshots"]]
        memory_texts[packet["blind_unit_id"]] = "\n".join([*delta_spans, *snapshot_contents])
    units = structured.get("units")
    if (
        not isinstance(units, list)
        or len(units) != len(expected)
        or {row.get("blind_unit_id") for row in units} != set(expected)
    ):
        raise ValueError("Stage-D unit IDs/count do not match packet batch")
    for unit in units:
        blind_id, labels = unit["blind_unit_id"], unit.get("labels")
        if not isinstance(labels, list):
            raise TypeError(f"{blind_id}: labels not an array")
        ids = [row.get("fixed_claim_id") for row in labels]
        if len(ids) != len(set(ids)) or set(ids) != expected[blind_id]:
            raise ValueError(f"{blind_id}: fixed claim IDs do not exactly match")
        for row in labels:
            if row.get("memory_meaning") not in MEMORY_MEANING:
                raise ValueError(f"{blind_id}: invalid memory meaning")
            for key in (
                "memory_absent_before",
                "memory_relocation_or_rephrasing",
                "memory_survives_consolidation",
            ):
                if row.get(key) not in YES_NO_UNKNOWN:
                    raise ValueError(f"{blind_id}: invalid {key}")
            if row.get("memory_writer_mechanism") not in WRITER:
                raise ValueError(f"{blind_id}: invalid writer mechanism")
            if (
                row.get("later_behavioral_use") not in TRACE_LABEL
                or row.get("third_party_restatement") not in TRACE_LABEL
            ):
                raise ValueError(f"{blind_id}: invalid trace label")
            if row.get("third_party_stance") not in THIRD_PARTY_STANCE:
                raise ValueError(f"{blind_id}: invalid third-party stance")
            later_use = row.get("later_use_event_ids")
            if not isinstance(later_use, list) or any(
                value not in valid_action_events[blind_id] for value in later_use
            ):
                raise ValueError(f"{blind_id}: unsupported event ID in later_use_event_ids")
            for key in ("third_party_supporting_event_ids", "new_recipient_event_ids"):
                values = row.get(key)
                if not isinstance(values, list) or any(
                    value not in valid_later[blind_id] for value in values
                ):
                    raise ValueError(f"{blind_id}: unsupported event ID in {key}")
            span = row.get("memory_supporting_span", "")
            restored, repaired = restore_memory_span(span, memory_texts[blind_id])
            if repaired:
                row["memory_supporting_span"] = restored
                row["notes"] = "; ".join(
                    filter(
                        None,
                        [row.get("notes", ""), "memory_span_punctuation_restored_by_validator"],
                    )
                )
                span = restored
            if span and span not in memory_texts[blind_id]:
                raise ValueError(f"{blind_id}: memory span is not verbatim from displayed delta")
            confidence = row.get("confidence_1_to_5")
            if not isinstance(confidence, int) or not 1 <= confidence <= 5:
                raise ValueError(f"{blind_id}: invalid confidence")


def run_batch(
    index: int, packets: list[dict[str, Any]], raw_dir: Path, structured_dir: Path, retries: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    response_path, structured_path = (
        raw_dir / f"batch_{index:03d}_response.json",
        structured_dir / f"batch_{index:03d}.json",
    )
    if response_path.exists() and structured_path.exists():
        wrapper = json.loads(response_path.read_text(encoding="utf-8"))
        structured = json.loads(structured_path.read_text(encoding="utf-8"))
        validate_batch(structured, packets)
        return wrapper, structured
    for failure_path in sorted(
        raw_dir.glob(f"batch_{index:03d}_attempt_*_failure.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            wrapper = json.loads(failure["stdout"])
            structured = wrapper.get("structured_output")
            if not isinstance(structured, dict):
                structured = json.loads(wrapper["result"])
            validate_batch(structured, packets)
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
        {"instructions": TASK_INSTRUCTIONS, "packets": [payload(row) for row in packets]},
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
            timeout=900,
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
            validate_batch(structured, packets)
            response_path.write_text(
                json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            structured_path.write_text(
                json.dumps(structured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            return wrapper, structured
        except Exception as exc:  # noqa: BLE001  # preserve invalid attempts for audit
            last_error = exc
            (raw_dir / f"batch_{index:03d}_attempt_{attempt}_failure.json").write_text(
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
    raise RuntimeError(f"Stage-D batch {index} failed: {last_error}")


def batch_packets(
    packets: list[dict[str, Any]], max_units: int, max_chars: int
) -> list[list[dict[str, Any]]]:
    batches, current, chars = [], [], 0
    for packet in packets:
        size = len(json.dumps(payload(packet), ensure_ascii=False))
        if current and (len(current) >= max_units or chars + size > max_chars):
            batches.append(current)
            current, chars = [], 0
        current.append(packet)
        chars += size
    if current:
        batches.append(current)
    return batches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-units", type=int, default=5)
    parser.add_argument("--max-prompt-chars", type=int, default=400_000)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    paths = sorted(PACKET_DIR.glob("*.json.gz"))
    packets = [read_packet(path) for path in paths]
    if not packets:
        raise SystemExit("No compiled Stage-D packets found")
    batches = batch_packets(packets, args.batch_units, args.max_prompt_chars)
    raw_dir, structured_dir = OUTPUT_DIR / "raw", OUTPUT_DIR / "structured"
    raw_dir.mkdir(parents=True, exist_ok=True)
    structured_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, batch in enumerate(batches, 1):
        print(f"Fable Stage D batch {index}/{len(batches)} ({len(batch)} units)", flush=True)
        results.append(run_batch(index, batch, raw_dir, structured_dir, args.retries))
    labels, wrappers = {}, []
    for wrapper, structured in results:
        wrappers.append(wrapper)
        for unit in structured["units"]:
            for row in unit["labels"]:
                labels[(unit["blind_unit_id"], row["fixed_claim_id"])] = row
    expected = {
        (packet["blind_unit_id"], pair["claim_pair_id"])
        for packet in packets
        for pair in packet["fixed_claim_pairs"]
    }
    if set(labels) != expected:
        raise ValueError("Compiled Stage-D labels do not cover every pair")
    rows = []
    array_fields = {
        "later_use_event_ids",
        "third_party_supporting_event_ids",
        "new_recipient_event_ids",
    }
    for blind_id, fixed_id in sorted(expected):
        label = labels[(blind_id, fixed_id)]
        rows.append(
            {
                "blind_unit_id": blind_id,
                "annotator_id": "fable_high",
                **{
                    key: (";".join(value) if key in array_fields else value)
                    for key, value in label.items()
                },
            }
        )
    with (OUTPUT_DIR / "memory_restatement.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "annotator_id": "fable_high",
        "requested_model_alias": "fable",
        "observed_cli_model_usage": {
            model: {
                "input_tokens": sum(
                    int(((w.get("modelUsage") or {}).get(model) or {}).get("inputTokens") or 0)
                    for w in wrappers
                ),
                "output_tokens": sum(
                    int(((w.get("modelUsage") or {}).get(model) or {}).get("outputTokens") or 0)
                    for w in wrappers
                ),
                "cost_usd": round(
                    sum(
                        float(((w.get("modelUsage") or {}).get(model) or {}).get("costUSD") or 0)
                        for w in wrappers
                    ),
                    6,
                ),
            }
            for model in sorted({name for w in wrappers for name in (w.get("modelUsage") or {})})
        },
        "effort": "high",
        "stage": "D_v2_2_exact_memory_audit_all_valid_pair_units",
        "machine_annotation_not_human_ground_truth": True,
        "unit_count": len(packets),
        "fixed_claim_pair_count": len(expected),
        "all_valid_claim_pair_units_exact_memory_audited": True,
        "batch_count": len(results),
        "total_cost_usd_reported_by_cli": round(
            sum(float(w.get("total_cost_usd") or 0) for w in wrappers), 6
        ),
        "task_instructions_sha256": sha256_bytes(TASK_INSTRUCTIONS.encode()),
        "validation": "passed",
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
