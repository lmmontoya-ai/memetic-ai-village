from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, RAW, REPORTS, ensure_output_dirs
from .exposure import VisibilityIndex
from .temporal_v2 import assess_temporal_relation, emitted_message_interval
from .util import parse_timestamp, safe_excerpt, stream_jsonl

ROOMS_INTRODUCED_AT = parse_timestamp("2026-02-25 00:00:00")
CHAT_LIMIT_INTRODUCED_AT = parse_timestamp("2025-08-20 00:00:00")
UNSEEN_EVENT_CAP_AT = parse_timestamp("2026-06-11 00:00:00")
ARTIFACT_RE = re.compile(
    r"https?://[^\s)>\]}]+|(?:[\w.-]+/){1,5}[\w.-]+|\b(?:PR|pull request|issue)\s*#?\d+\b",
    re.IGNORECASE,
)

ELIGIBILITY_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("source_event_id", pa.string()),
        ("response_event_id", pa.string()),
        ("source_timestamp", pa.timestamp("us", tz="UTC")),
        ("response_start_timestamp", pa.timestamp("us", tz="UTC")),
        ("response_completion_timestamp", pa.timestamp("us", tz="UTC")),
        ("temporal_relation", pa.string()),
        ("ordering_uncertainty_reason", pa.string()),
        ("source_room_id", pa.string()),
        ("recipient_room_at_source", pa.string()),
        ("recipient_room_at_response", pa.string()),
        ("same_room_at_response", pa.bool_()),
        ("global_channel_at_response", pa.bool_()),
        ("within_known_message_cap", pa.bool_()),
        ("message_cap_reason", pa.string()),
        ("room_transition_between_events", pa.bool_()),
        ("history_search_available", pa.bool_()),
        ("history_search_event_ids", pa.string()),
        ("shared_artifact_available", pa.bool_()),
        ("shared_artifact_ids", pa.string()),
        ("direct_source_reference", pa.bool_()),
        ("direct_source_reference_rule", pa.string()),
        ("exact_prompt_inclusion", pa.bool_()),
        ("peer_message_eligible", pa.bool_()),
        ("common_artifact_access", pa.bool_()),
        ("eligibility_class", pa.string()),
        ("eligibility_reason", pa.string()),
        ("source_excerpt", pa.string()),
        ("response_excerpt", pa.string()),
    ]
)


def artifact_identifiers(text: str) -> set[str]:
    return {match.group(0).rstrip(".,:;").lower() for match in ARTIFACT_RE.finditer(text)}


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _direct_reference(source: str, response: str, source_name: str | None) -> tuple[bool, str]:
    response_normalized = _normalized(response)
    if source_name:
        name = source_name.lower().strip()
        if re.search(rf"(?:^|[@\s]){re.escape(name)}(?:\b|$)", response_normalized):
            return True, "source_agent_named"
    source_normalized = _normalized(source)
    if len(source_normalized) >= 24:
        phrases = [source_normalized[i : i + 48] for i in range(0, len(source_normalized) - 23, 24)]
        if any(len(phrase) >= 24 and phrase in response_normalized for phrase in phrases):
            return True, "source_phrase_quoted"
    if re.search(
        r"\b(as you said|your message|you mentioned|you reported|per your|replying to)\b",
        response_normalized,
    ):
        return True, "explicit_discourse_reference"
    return False, "no_conservative_reference_detected"


def _history_searches() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stream_jsonl(RAW / "events.jsonl.gz"):
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if data.get("actionType") != "SEARCH_HISTORY" or not data.get("agentId"):
            continue
        timestamp = parse_timestamp(row.get("created_at"))
        if timestamp:
            result[data["agentId"]].append(
                {
                    "event_id": row["id"],
                    "timestamp": timestamp,
                    "answer": data.get("answerToQuery") or "",
                }
            )
    for values in result.values():
        values.sort(key=lambda item: (item["timestamp"], item["event_id"]))
    return result


def _exact_retrieval(source: str, answer: str) -> bool:
    source_normalized = _normalized(source)
    answer_normalized = _normalized(answer)
    return bool(len(source_normalized) >= 20 and source_normalized in answer_normalized)


def room_transition_between(
    source_time: Any, response_time: Any, moves: list[tuple[Any, str]]
) -> bool:
    return bool(
        source_time
        and response_time
        and any(source_time < timestamp <= response_time for timestamp, _ in moves)
    )


def classify_information_eligibility(
    *,
    temporal_relation: str,
    exact_retrieval: bool,
    direct_reference: bool,
    direct_reference_rule: str,
    same_room: bool | None,
    global_at_response: bool,
    history_search_available: bool,
    shared_artifact_available: bool,
) -> tuple[bool | None, str, str]:
    """Pure response-time pathway classifier used by the structural test suite."""
    if temporal_relation == "definitely_after":
        return False, "ineligible", "source_is_definitely_after_response"
    if temporal_relation == "concurrent_or_ambiguous":
        return None, "indeterminate", "temporal_relation_ambiguous"
    if exact_retrieval:
        return True, "observed_inclusion", "exact_source_text_in_exported_history_search_result"
    if direct_reference:
        peer_eligible = True if same_room is True or global_at_response else None
        return peer_eligible, "source_acknowledged", direct_reference_rule
    if same_room is True or global_at_response:
        return True, "eligible", "documented_channel_rules_allow_direct_message_at_exact_response"
    if same_room is False:
        if history_search_available or shared_artifact_available:
            return (
                False,
                "indirectly_reachable",
                "direct_room_path_ruled_out_but_history_or_artifact_path_exists",
            )
        return False, "ineligible", "known_different_room_rules_out_direct_peer_message_path"
    return None, "indeterminate", "historic_room_or_context_state_missing"


def build_response_eligibility(
    registry_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    ensure_output_dirs()
    registry_path = registry_path or (
        EPISODES / "development_units_v2.csv"
        if (EPISODES / "development_units_v2.csv").exists()
        else EPISODES / "candidate_registry.csv"
    )
    output_path = output_path or PROCESSED / "response_eligibility_v2.parquet"
    report_path = report_path or REPORTS / "response_eligibility_v2.json"
    with registry_path.open(newline="", encoding="utf-8") as handle:
        registry = list(csv.DictReader(handle))
    needed_messages = {item["source_message_id"] for item in registry} | {
        item["recipient_response_message_id"] for item in registry
    }
    messages = {
        row["id"]: row
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in needed_messages
    }
    agents = {row["id"]: row for row in stream_jsonl(RAW / "agents.jsonl.gz")}
    visibility = VisibilityIndex()
    searches = _history_searches()
    rows: list[dict[str, Any]] = []
    for item in registry:
        source_row = messages.get(item["source_message_id"])
        response_row = messages.get(item["recipient_response_message_id"])
        if source_row is None or response_row is None:
            continue
        source_time = parse_timestamp(source_row.get("created_at"))
        response_time = parse_timestamp(response_row.get("created_at"))
        source_interval = emitted_message_interval(item["seed_event"], source_time)
        response_interval = emitted_message_interval(item["recipient_response"], response_time)
        temporal = assess_temporal_relation(source_interval, response_interval)
        recipient = item["recipient_agent"]
        source_room = source_row.get("room_id")
        recipient_room_source = visibility.room_at(recipient, source_time) if source_time else None
        recipient_room_response = (
            visibility.room_at(recipient, response_time) if response_time else None
        )
        # A response message's own room is stronger evidence of room state at emission.
        recipient_room_response = response_row.get("room_id") or recipient_room_response
        global_at_response = bool(
            response_time and ROOMS_INTRODUCED_AT and response_time < ROOMS_INTRODUCED_AT
        )
        same_room = (
            True
            if global_at_response
            else (
                source_room == recipient_room_response
                if source_room is not None and recipient_room_response is not None
                else None
            )
        )
        moves = visibility.room_moves.get(recipient, [])
        transitioned = room_transition_between(source_time, response_time, moves)
        relevant_searches = [
            entry
            for entry in searches.get(recipient, [])
            if source_time and response_time and source_time < entry["timestamp"] < response_time
        ]
        exact_retrieval = any(
            _exact_retrieval(source_row.get("content") or "", entry["answer"])
            for entry in relevant_searches
        )
        direct, direct_rule = _direct_reference(
            source_row.get("content") or "",
            response_row.get("content") or "",
            agents.get(item["source_agent"], {}).get("name"),
        )
        shared_artifacts = sorted(
            artifact_identifiers(source_row.get("content") or "")
            & artifact_identifiers(response_row.get("content") or "")
        )
        common_artifact_access: bool | None = True if shared_artifacts else None
        if response_time and CHAT_LIMIT_INTRODUCED_AT and response_time < CHAT_LIMIT_INTRODUCED_AT:
            within_cap: bool | None = True
            cap_reason = "before_documented_chat_context_limit"
        elif response_time and UNSEEN_EVENT_CAP_AT and response_time >= UNSEEN_EVENT_CAP_AT:
            within_cap = None
            cap_reason = "documented_cap_is_200_unseen_events_not_an_exact_message_cap"
        else:
            within_cap = None
            cap_reason = "limited_context_documented_but_exact_selection_rule_unexported"

        peer_eligible, eligibility_class, reason = classify_information_eligibility(
            temporal_relation=temporal.relation,
            exact_retrieval=exact_retrieval,
            direct_reference=direct,
            direct_reference_rule=direct_rule,
            same_room=same_room,
            global_at_response=global_at_response,
            history_search_available=bool(relevant_searches),
            shared_artifact_available=bool(shared_artifacts),
        )
        rows.append(
            {
                "episode_id": item["episode_id"],
                "source_event_id": item["seed_event"],
                "response_event_id": item["recipient_response"],
                "source_timestamp": source_time,
                "response_start_timestamp": None,
                "response_completion_timestamp": response_time,
                "temporal_relation": temporal.relation,
                "ordering_uncertainty_reason": temporal.reason,
                "source_room_id": source_room,
                "recipient_room_at_source": recipient_room_source,
                "recipient_room_at_response": recipient_room_response,
                "same_room_at_response": same_room,
                "global_channel_at_response": global_at_response,
                "within_known_message_cap": within_cap,
                "message_cap_reason": cap_reason,
                "room_transition_between_events": transitioned,
                "history_search_available": bool(relevant_searches),
                "history_search_event_ids": json.dumps(
                    [entry["event_id"] for entry in relevant_searches]
                ),
                "shared_artifact_available": True if shared_artifacts else None,
                "shared_artifact_ids": json.dumps(shared_artifacts, ensure_ascii=False),
                "direct_source_reference": direct,
                "direct_source_reference_rule": direct_rule,
                "exact_prompt_inclusion": True if exact_retrieval else None,
                "peer_message_eligible": peer_eligible,
                "common_artifact_access": common_artifact_access,
                "eligibility_class": eligibility_class,
                "eligibility_reason": reason,
                "source_excerpt": safe_excerpt(source_row.get("content"), 240),
                "response_excerpt": safe_excerpt(response_row.get("content"), 240),
            }
        )
    pq.write_table(
        pa.Table.from_pylist(rows, schema=ELIGIBILITY_SCHEMA), output_path, compression="zstd"
    )
    counts: dict[str, int] = {}
    for row in rows:
        key = row["eligibility_class"]
        counts[key] = counts.get(key, 0) + 1
    result = {
        "artifact": str(output_path),
        "row_count": len(rows),
        "eligibility_counts": counts,
        "observed_prompt_inclusion_count": sum(
            row["exact_prompt_inclusion"] is True for row in rows
        ),
        "scope": "exact candidate response; no first-later-decision shortcut",
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
