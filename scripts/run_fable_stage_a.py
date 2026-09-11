"""Run blinded v2.2 Stage-A development annotation with Claude Fable 5.

The runner deliberately supplies only the frozen Stage-A instructions and blinded
packet contents.  It writes machine annotations outside the canonical human
templates so exploratory model labels cannot be mistaken for human ground truth.
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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "annotations" / "v2_2" / "stage_a" / "packets"
OUTPUT_DIR = ROOT / "annotations" / "v2_2" / "machine" / "fable_high" / "stage_a"

MESSAGE_FIELDS = [
    "blind_unit_id",
    "annotator_id",
    "message_role",
    "event_id",
    "claim_presence",
    "nonclaim_speech_act",
    "notes",
]
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

CLAIM_PRESENCE = {"claim_bearing", "nonclaim", "uncertain"}
NONCLAIM_ACTS = {"", "directive_request", "status_update", "social_act", "other"}
POLARITIES = {"affirmed", "negated", "mixed", "unclear"}
MODALITIES = {"asserted", "probable", "possible", "conditional", "unclear"}
CLAIM_TYPES = {"fact", "intent", "recommended_action", "operational_status", "other"}
SPEECH_ACTS = {
    "factual_claim",
    "operational_status",
    "directive_request",
    "recommendation",
    "social_act",
    "other",
}

# Claude occasionally normalizes typographic punctuation while copying a span
# (for example, ``I’m`` becomes ``I'm``).  The frozen protocol requires the CSV
# span itself to be verbatim.  Restore only unambiguous, one-character
# punctuation substitutions; do not fuzzy-match words or silently rewrite the
# semantic content of an extraction.
SPAN_PUNCTUATION_TRANSLATION = str.maketrans(
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

SYSTEM_PROMPT = (
    "You are an independent blinded research annotator. Perform only the supplied "
    "Stage-A semantic extraction task. Do not use tools, files, web access, outside "
    "knowledge, or truth judgments. Emit only schema-valid structured output."
)

TASK_INSTRUCTIONS = r"""
You are annotator `fable_high` performing Stage A of a blinded study. Candidate/control
status, retrieval scores, model identity, known-incident status, provisional claims, and
truth labels are intentionally unavailable. Do not infer or assess truth.

For every supplied unit, annotate ONLY the marked `source` and `response` messages;
surrounding `context` messages may be used solely to interpret them.

First classify each marked message:
- `claim_bearing`: it contains at least one minimal truth-apt or operational proposition.
- `nonclaim`: it contains no extractable proposition.
- `uncertain`: the presence of an extractable proposition cannot be determined.

For `nonclaim`, classify the dominant speech act as `directive_request`, `status_update`,
`social_act`, or `other`. Otherwise set `nonclaim_speech_act` to the empty string.

Then extract each minimal proposition separately, in textual order, up to the three slots
supported by the frozen schema. Split facts, intent, recommended action, and operational
status when they have different truth conditions. Copy `exact_claim_span` verbatim as a
single contiguous substring of the marked message. Do not extract politeness, generic
waiting, or a bare directive unless it also asserts a proposition. If more than three
material atomic propositions exist, select the three most central and put
`schema_limit_overflow` in the message notes.

For every claim provide:
- a concise atomic proposition;
- a concise referent naming the object, artifact, event, condition, or proposed action;
- polarity: affirmed, negated, mixed, or unclear;
- modality: asserted, probable, possible, conditional, or unclear;
- attribution: the explicitly named/quoted source, otherwise empty;
- claim type: fact, intent, recommended_action, operational_status, or other;
- speech act: factual_claim, operational_status, directive_request, recommendation,
  social_act, or other;
- confidence from 1 (very uncertain extraction) to 5 (unambiguous extraction).

Preserve ambiguity rather than guessing. Do not compare source and response claims and do
not decide whether either claim is correct. Return every supplied blind unit exactly once,
with exactly one source and one response annotation.
""".strip()


CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "exact_claim_span": {"type": "string"},
        "atomic_proposition": {"type": "string"},
        "referent": {"type": "string"},
        "polarity": {"type": "string", "enum": sorted(POLARITIES)},
        "modality": {"type": "string", "enum": sorted(MODALITIES)},
        "attribution": {"type": "string"},
        "claim_type": {"type": "string", "enum": sorted(CLAIM_TYPES)},
        "speech_act_type": {"type": "string", "enum": sorted(SPEECH_ACTS)},
        "confidence_1_to_5": {"type": "integer", "minimum": 1, "maximum": 5},
        "notes": {"type": "string"},
    },
    "required": [
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
    ],
    "additionalProperties": False,
}

MESSAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message_role": {"type": "string", "enum": ["source", "response"]},
        "event_id": {"type": "string"},
        "claim_presence": {"type": "string", "enum": sorted(CLAIM_PRESENCE)},
        "nonclaim_speech_act": {"type": "string", "enum": sorted(NONCLAIM_ACTS)},
        "notes": {"type": "string"},
        "claims": {"type": "array", "items": CLAIM_SCHEMA, "maxItems": 3},
    },
    "required": [
        "message_role",
        "event_id",
        "claim_presence",
        "nonclaim_speech_act",
        "notes",
        "claims",
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
                    "messages": {
                        "type": "array",
                        "items": MESSAGE_SCHEMA,
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
                "required": ["blind_unit_id", "messages"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["units"],
    "additionalProperties": False,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_packet(path: Path) -> tuple[dict[str, Any], str]:
    compressed = path.read_bytes()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        packet = json.load(handle)
    if packet.get("stage") != "A_v2_2_independent_atomic_claim_extraction":
        raise ValueError(f"Unexpected stage in {path}")
    if packet.get("anchoring_metadata_omitted") is not True:
        raise ValueError(f"Packet is not marked blinded: {path}")
    return packet, sha256_bytes(compressed)


def marked_messages(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {
        item["role"]: item
        for item in packet["context_messages"]
        if item.get("role") in {"source", "response"}
    }
    if set(result) != {"source", "response"}:
        raise ValueError(f"Packet {packet['blind_unit_id']} lacks one marked message")
    return result


def restore_verbatim_span(span: str, text: str) -> tuple[str, bool]:
    """Return an exact source substring after a narrow punctuation-only repair."""
    if span in text:
        return span, False
    folded_span = span.translate(SPAN_PUNCTUATION_TRANSLATION)
    folded_text = text.translate(SPAN_PUNCTUATION_TRANSLATION)
    starts: list[int] = []
    offset = 0
    while True:
        start = folded_text.find(folded_span, offset)
        if start < 0:
            break
        starts.append(start)
        offset = start + 1
    if len(starts) != 1:
        return span, False
    start = starts[0]
    restored = text[start : start + len(span)]
    if restored.translate(SPAN_PUNCTUATION_TRANSLATION) != folded_span:
        return span, False
    return restored, True


def validate_batch(structured: dict[str, Any], packets: list[dict[str, Any]]) -> None:
    expected = {packet["blind_unit_id"]: packet for packet in packets}
    units = structured.get("units")
    if not isinstance(units, list) or len(units) != len(expected):
        raise ValueError("Structured output has the wrong unit count")
    observed_ids = [unit.get("blind_unit_id") for unit in units]
    if len(set(observed_ids)) != len(observed_ids) or set(observed_ids) != set(expected):
        raise ValueError("Structured output unit IDs do not match the batch")

    for unit in units:
        packet = expected[unit["blind_unit_id"]]
        marked = marked_messages(packet)
        messages = unit.get("messages")
        if not isinstance(messages, list) or len(messages) != 2:
            raise ValueError(f"{unit['blind_unit_id']}: expected two message annotations")
        roles = [message.get("message_role") for message in messages]
        if len(set(roles)) != 2 or set(roles) != {"source", "response"}:
            raise ValueError(f"{unit['blind_unit_id']}: source/response roles invalid")
        for message in messages:
            role = message["message_role"]
            expected_event = marked[role]["event_id"]
            if message.get("event_id") != expected_event:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: event ID mismatch")
            presence = message.get("claim_presence")
            if presence not in CLAIM_PRESENCE:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid claim presence")
            nonclaim = message.get("nonclaim_speech_act")
            if nonclaim not in NONCLAIM_ACTS:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid nonclaim act")
            if presence != "nonclaim" and nonclaim:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: nonclaim act on claim message")
            claims = message.get("claims")
            if not isinstance(claims, list) or len(claims) > 3:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid claims array")
            if presence == "claim_bearing" and not claims:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: claim-bearing but no claims")
            if presence == "nonclaim" and claims:
                raise ValueError(f"{unit['blind_unit_id']}:{role}: nonclaim has claims")
            text = marked[role]["text"]
            for claim in claims:
                span = claim.get("exact_claim_span", "")
                restored_span, repaired = restore_verbatim_span(span, text)
                if repaired:
                    claim["exact_claim_span"] = restored_span
                    repair_note = "exact_span_punctuation_restored_by_validator"
                    claim["notes"] = "; ".join(
                        item for item in (claim.get("notes", ""), repair_note) if item
                    )
                    span = restored_span
                if not span or span not in text:
                    raise ValueError(
                        f"{unit['blind_unit_id']}:{role}: exact span is not a verbatim substring"
                    )
                if not claim.get("atomic_proposition") or not claim.get("referent"):
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: empty proposition/referent")
                if claim.get("polarity") not in POLARITIES:
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid polarity")
                if claim.get("modality") not in MODALITIES:
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid modality")
                if claim.get("claim_type") not in CLAIM_TYPES:
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid claim type")
                if claim.get("speech_act_type") not in SPEECH_ACTS:
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid speech act")
                confidence = claim.get("confidence_1_to_5")
                if not isinstance(confidence, int) or not 1 <= confidence <= 5:
                    raise ValueError(f"{unit['blind_unit_id']}:{role}: invalid confidence")


def run_batch(
    batch_index: int,
    packet_paths: list[Path],
    raw_dir: Path,
    structured_dir: Path,
    retries: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    response_path = raw_dir / f"batch_{batch_index:03d}_response.json"
    structured_path = structured_dir / f"batch_{batch_index:03d}.json"
    packets_and_hashes = [read_packet(path) for path in packet_paths]
    packets = [item[0] for item in packets_and_hashes]

    if response_path.exists() and structured_path.exists():
        wrapper = json.loads(response_path.read_text(encoding="utf-8"))
        structured = json.loads(structured_path.read_text(encoding="utf-8"))
        validate_batch(structured, packets)
        return wrapper, structured, packets

    prompt_payload = {
        "instructions": TASK_INSTRUCTIONS,
        "packets": packets,
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"))
    schema = json.dumps(OUTPUT_SCHEMA, separators=(",", ":"))
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
        schema,
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
                raise RuntimeError(f"Claude wrapper reports failure: {wrapper}")
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
            return wrapper, structured, packets
        except Exception as exc:  # noqa: BLE001  # preserve invalid attempts for audit
            last_error = exc
            failure_path = raw_dir / f"batch_{batch_index:03d}_attempt_{attempt}_failure.json"
            failure_path.write_text(
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


def compile_outputs(
    results: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]],
    packet_paths: list[Path],
) -> dict[str, Any]:
    message_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    wrappers: list[dict[str, Any]] = []

    for wrapper, structured, packets in results:
        wrappers.append(wrapper)
        packet_map = {packet["blind_unit_id"]: packet for packet in packets}
        for unit in structured["units"]:
            packet = packet_map[unit["blind_unit_id"]]
            marked = marked_messages(packet)
            by_role = {message["message_role"]: message for message in unit["messages"]}
            for role in ("source", "response"):
                message = by_role[role]
                message_rows.append(
                    {
                        "blind_unit_id": unit["blind_unit_id"],
                        "annotator_id": "fable_high",
                        "message_role": role,
                        "event_id": marked[role]["event_id"],
                        "claim_presence": message["claim_presence"],
                        "nonclaim_speech_act": message["nonclaim_speech_act"],
                        "notes": message["notes"],
                    }
                )
                claims = message["claims"]
                for slot in range(1, 4):
                    base: dict[str, Any] = {
                        "blind_unit_id": unit["blind_unit_id"],
                        "annotator_id": "fable_high",
                        "claim_slot": slot,
                        "message_role": role,
                        "event_id": marked[role]["event_id"],
                    }
                    if slot <= len(claims):
                        base.update(claims[slot - 1])
                    else:
                        base.update({field: "" for field in CLAIM_FIELDS if field not in base})
                    claim_rows.append(base)

    message_rows.sort(key=lambda row: (row["blind_unit_id"], row["message_role"] != "source"))
    claim_rows.sort(
        key=lambda row: (
            row["blind_unit_id"],
            row["message_role"] != "source",
            int(row["claim_slot"]),
        )
    )
    if len(message_rows) != 120 or len(claim_rows) != 360:
        raise ValueError(
            f"Compiled row counts invalid: messages={len(message_rows)}, claims={len(claim_rows)}"
        )

    write_csv(OUTPUT_DIR / "message_classification.csv", MESSAGE_FIELDS, message_rows)
    write_csv(OUTPUT_DIR / "claims.csv", CLAIM_FIELDS, claim_rows)

    costs = [float(wrapper.get("total_cost_usd") or 0.0) for wrapper in wrappers]
    observed_model_usage: dict[str, dict[str, float | int]] = {}
    for wrapper in wrappers:
        for model, values in (wrapper.get("modelUsage") or {}).items():
            aggregate = observed_model_usage.setdefault(
                model, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            )
            aggregate["input_tokens"] += int(values.get("inputTokens") or 0)
            aggregate["output_tokens"] += int(values.get("outputTokens") or 0)
            aggregate["cost_usd"] += float(values.get("costUSD") or 0.0)
    usage = {
        "input_tokens": sum(
            int((wrapper.get("usage") or {}).get("input_tokens") or 0) for wrapper in wrappers
        ),
        "cache_creation_input_tokens": sum(
            int((wrapper.get("usage") or {}).get("cache_creation_input_tokens") or 0)
            for wrapper in wrappers
        ),
        "cache_read_input_tokens": sum(
            int((wrapper.get("usage") or {}).get("cache_read_input_tokens") or 0)
            for wrapper in wrappers
        ),
        "output_tokens": sum(
            int((wrapper.get("usage") or {}).get("output_tokens") or 0) for wrapper in wrappers
        ),
    }
    manifest = {
        "annotator_id": "fable_high",
        "requested_model_alias": "fable",
        "observed_cli_model_usage": observed_model_usage,
        "effort": "high",
        "stage": "A_v2_2_independent_atomic_claim_extraction",
        "machine_annotation_not_human_ground_truth": True,
        "packet_count": len(packet_paths),
        "message_row_count": len(message_rows),
        "claim_template_row_count": len(claim_rows),
        "populated_claim_count": sum(bool(row["atomic_proposition"]) for row in claim_rows),
        "batch_count": len(results),
        "total_cost_usd_reported_by_cli": round(sum(costs), 6),
        "usage": usage,
        "packet_sha256": {path.name: sha256_bytes(path.read_bytes()) for path in packet_paths},
        "task_instructions_sha256": sha256_bytes(TASK_INSTRUCTIONS.encode("utf-8")),
        "output_schema_sha256": sha256_bytes(
            json.dumps(OUTPUT_SCHEMA, sort_keys=True).encode("utf-8")
        ),
        "blinding_declaration": (
            "Only the embedded frozen Stage-A instructions and blinded packet contents were "
            "provided; tools and session persistence were disabled."
        ),
        "schema_limit": "At most three atomic claims per marked message.",
        "validation": "passed",
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    packet_paths = sorted(PACKET_DIR.glob("*.json.gz"))
    if len(packet_paths) != 60:
        raise SystemExit(f"Expected 60 blinded packets, found {len(packet_paths)}")
    raw_dir = OUTPUT_DIR / "raw"
    structured_dir = OUTPUT_DIR / "structured"
    raw_dir.mkdir(parents=True, exist_ok=True)
    structured_dir.mkdir(parents=True, exist_ok=True)

    results = []
    batches = [
        packet_paths[index : index + args.batch_size]
        for index in range(0, len(packet_paths), args.batch_size)
    ]
    for batch_index, paths in enumerate(batches, start=1):
        print(
            f"Fable Stage A batch {batch_index}/{len(batches)}: "
            f"{paths[0].name} .. {paths[-1].name}",
            flush=True,
        )
        results.append(run_batch(batch_index, paths, raw_dir, structured_dir, args.retries))

    manifest = compile_outputs(results, packet_paths)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
