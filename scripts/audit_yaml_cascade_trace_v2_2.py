"""Reconstruct the development YAML episode from canonical and raw pointers.

This is a structural/forensic audit, not an estimate of causal peer influence.
It verifies the response-specific chronology, the explicit attribution, the later
room re-expression, and the third agent's claim-dependent repository action.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_manifest" / "snapshot"
CANONICAL = ROOT / "data" / "processed" / "canonical_events.parquet"
OUTPUT = ROOT / "reports" / "yaml_cascade_trace_audit_v2_2.json"

CANONICAL_IDS = {
    "source_message": "ev_cdca0989d8add00bf6690b4a",
    "recipient_session_recorded": "ev_ca74641dbadbb214db810198",
    "recipient_session_started": "ev_26e35a159893db8617d1f0b6",
    "recipient_conclusion_turn": "ev_769893f7907278fe3e3a36be",
    "response_message": "ev_2f21a12c0a426812622bed8c",
    "actor_three_session_recorded": "ev_d1906c74b009bec9170883c1",
    "actor_three_session_started": "ev_1c0937d2efdf084aa5c7c561",
    "recipient_reexpression": "ev_60839db7b2c8b18aad1f1e7a",
    "actor_three_commit_report": "ev_916743e372116d1b248fa896",
    "actor_three_session_stopped": "ev_e2143f969fcdd8a8b4bbe3fb",
    "later_correction_summary": "ev_1140e81cfb0f05edcf50c5e9",
}

RAW_EVENT_IDS = {
    "source_message": "8b5c169e-e58c-4024-9e60-fe8f808dc238",
    "response_message": "67ff5185-b95c-488f-975c-ad7cc073a86f",
    "recipient_reexpression": "3ce8e1df-025a-4dc4-b841-65bacfcc9e2c",
    "actor_three_commit_report": "cdffaa46-db9d-402d-82fe-437b945a3dc7",
    "actor_three_session_stopped": "e8ec8e07-3fbf-449b-8e1d-cab736a19110",
    "later_correction_summary": "6397e250-cef4-4e13-920a-53327f96691b",
}

SESSION_IDS = {
    "recipient_session": "a1c6828a-287d-4ea4-aa9c-b5c7a3e25551",
    "actor_three_session": "82140a6d-ee25-48c4-b50d-416911c0b8a5",
}

TURN_IDS = {"recipient_conclusion_turn": "ae266804-1f4d-4105-990f-1c51db80effb"}


def selected_jsonl(path: Path, ids: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("id") in ids:
                found[row["id"]] = row
                if len(found) == len(ids):
                    break
    missing = ids - set(found)
    if missing:
        raise RuntimeError(f"Missing raw IDs in {path.name}: {sorted(missing)}")
    return found


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def main() -> None:
    canonical = pq.read_table(CANONICAL)
    wanted = set(CANONICAL_IDS.values())
    selected = canonical.filter(
        pc.is_in(canonical["canonical_event_id"], value_set=pa.array(sorted(wanted)))
    )
    canonical_by_id = {row["canonical_event_id"]: row for row in selected.to_pylist()}
    missing = wanted - set(canonical_by_id)
    if missing:
        raise RuntimeError(f"Missing canonical IDs: {sorted(missing)}")

    events = selected_jsonl(RAW / "events.jsonl.gz", set(RAW_EVENT_IDS.values()))
    sessions = selected_jsonl(RAW / "computer_use_sessions.jsonl.gz", set(SESSION_IDS.values()))
    turns = selected_jsonl(RAW / "computer_use_turns.jsonl.gz", set(TURN_IDS.values()))

    times = {
        label: canonical_by_id[event_id]["timestamp"] for label, event_id in CANONICAL_IDS.items()
    }
    required_order = (
        "recipient_session_started",
        "source_message",
        "recipient_conclusion_turn",
        "response_message",
        "actor_three_session_started",
        "recipient_reexpression",
        "actor_three_commit_report",
        "actor_three_session_stopped",
    )
    if any(times[left] > times[right] for left, right in pairwise(required_order)):
        raise RuntimeError("The audited event chronology is not monotonic")

    conclusion = turns[TURN_IDS["recipient_conclusion_turn"]]
    content_blocks = conclusion["agent_messages"]["content"]
    visible_text = "\n".join(block.get("text", "") for block in content_blocks)
    thinking_text = "\n".join(block.get("thinking", "") for block in content_blocks)
    if "confirms what Claude Haiku 4.5 already diagnosed" not in visible_text:
        raise RuntimeError("Expected explicit source attribution is absent")

    actor_three_session = sessions[SESSION_IDS["actor_three_session"]]
    commit_event = events[RAW_EVENT_IDS["actor_three_commit_report"]]
    stop_event = events[RAW_EVENT_IDS["actor_three_session_stopped"]]
    if "Remove stray blank line" not in actor_three_session["session_goal"]:
        raise RuntimeError("Third-agent session goal is not the expected claim-dependent action")
    if "Hot-fix committed" not in commit_event["data"]["content"]:
        raise RuntimeError("Third-agent commit report is absent")
    if "Commit SHA: **5c9d2c4**" not in stop_event["data"]["summary"]:
        raise RuntimeError("Third-agent session summary does not confirm the commit")

    source_time = times["source_message"]
    response_time = times["response_message"]
    result = {
        "audit_id": "development_yaml_source_linked_operational_trace_v2_2",
        "status": "complete",
        "holdout_semantics_opened": False,
        "causal_peer_influence_estimated": False,
        "canonical_event_ids": CANONICAL_IDS,
        "raw_source_record_ids": RAW_EVENT_IDS,
        "chronology": {label: iso(times[label]) for label in required_order},
        "timing_intervals_seconds": {
            "recipient_session_started_before_source": (
                source_time - times["recipient_session_started"]
            ).total_seconds(),
            "source_to_response_emission": (response_time - source_time).total_seconds(),
            "response_to_actor_three_session_start": (
                times["actor_three_session_started"] - response_time
            ).total_seconds(),
            "response_to_recipient_reexpression": (
                times["recipient_reexpression"] - response_time
            ).total_seconds(),
            "response_to_actor_three_commit_report": (
                times["actor_three_commit_report"] - response_time
            ).total_seconds(),
        },
        "temporal_assessment": {
            "source_to_response": "likely_before",
            "reason": (
                "The exported source message precedes the response emission by 69.186 seconds, "
                "but prompt assembly and generation-start timestamps are unavailable."
            ),
            "recipient_investigation_started_before_source": True,
            "implication": (
                "The peer message cannot explain why the recipient began investigating. It may "
                "still have informed or anchored the conclusion; exact context inclusion is unknown."
            ),
        },
        "source_link": {
            "observed": True,
            "visible_response_span": (
                "This confirms what Claude Haiku 4.5 already diagnosed - the environment variable "
                "definition must immediately follow the env: key with proper indentation, with no "
                "blank line in between."
            ),
            "thinking_span": next(
                line for line in thinking_text.splitlines() if "already diagnosed" in line
            ),
            "exact_prompt_inclusion": "unknown",
        },
        "evidence_lineage_assessment": {
            "shared_artifact": "GitHub Actions run #12 and the same workflow file",
            "observation_independence": "separate_inspection",
            "observable_method_diversity": "same_visible_method",
            "lineage_independence": "same_upstream_object",
            "interpretation": (
                "This is apparent corroboration from separately viewing one common artifact, not "
                "multiple independent upstream evidence objects."
            ),
        },
        "operationalization": {
            "actor_agent_id": actor_three_session["agent_id"],
            "session_goal": actor_three_session["session_goal"],
            "commit_report": commit_event["data"]["content"],
            "session_summary": stop_event["data"]["summary"],
            "execution_level": "A6",
            "basis": "A repository commit changed external state and triggered CI run #13.",
        },
        "recipient_reexpression": {
            "event_id": CANONICAL_IDS["recipient_reexpression"],
            "content": events[RAW_EVENT_IDS["recipient_reexpression"]]["data"]["content"],
            "new_recipient_path": "global room; recipient eligibility audited separately",
        },
        "truth_audit": {
            "report": "reports/yaml_blank_line_truth_audit_v2_2.json",
            "atomic_syntax_claim": "verified_false",
            "artifact_specific_run_12_root_cause": "unknown",
        },
        "bounded_conclusion": (
            "The export reconstructs a source-linked, false-claim operational episode with later "
            "re-expression and an external action. Because the recipient was already inspecting the "
            "same artifact, exact prompt-inclusion telemetry is absent, and all observations share "
            "one artifact, the trace does not identify causal peer influence."
        ),
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
