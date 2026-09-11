from __future__ import annotations

import csv
import difflib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, RAW, REPORTS, ROOMS_INTRODUCED, ensure_output_dirs
from .discovery import _informative
from .exposure import VisibilityIndex
from .holdout_v2 import INACTIVITY_GAP, EpisodeClusterIndex
from .util import parse_timestamp, stable_id, stream_jsonl


def _registry(path: Path | None = None) -> list[dict[str, str]]:
    path = path or (
        EPISODES / "development_units_v2.csv"
        if (EPISODES / "development_units_v2.csv").exists()
        else EPISODES / "candidate_registry.csv"
    )
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _message_map(ids: set[str]) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row for row in stream_jsonl(RAW / "chat_messages.jsonl.gz") if row["id"] in ids
    }


CLAIM_SCHEMA = pa.schema(
    [
        ("claim_id", pa.string()),
        ("episode_id", pa.string()),
        ("normalized_proposition", pa.string()),
        ("referent_or_artifact", pa.string()),
        ("truth_status", pa.string()),
        ("first_observed_expression", pa.string()),
        ("source_agent", pa.string()),
        ("source_stance", pa.string()),
        ("supporting_evidence_ids", pa.string()),
        ("upstream_claim_ids", pa.string()),
        ("agreeing_message_count", pa.int32()),
        ("independent_evidence_source_count", pa.int32()),
        ("annotation_status", pa.string()),
        ("known_incident", pa.bool_()),
    ]
)

EXPRESSION_SCHEMA = pa.schema(
    [
        ("expression_id", pa.string()),
        ("claim_id", pa.string()),
        ("episode_id", pa.string()),
        ("event_id", pa.string()),
        ("raw_message_id", pa.string()),
        ("agent_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("expression_role", pa.string()),
        ("stance", pa.string()),
        ("stance_annotation_status", pa.string()),
        ("text", pa.string()),
    ]
)

LINEAGE_SCHEMA = pa.schema(
    [
        ("lineage_edge_id", pa.string()),
        ("episode_id", pa.string()),
        ("source_node_id", pa.string()),
        ("target_node_id", pa.string()),
        ("candidate_relation", pa.string()),
        ("evidence_source_type", pa.string()),
        ("independence_status", pa.string()),
        ("annotation_status", pa.string()),
    ]
)

KNOWN_PROPOSITIONS = {
    "known_01_contact_list_hallucination": (
        "The exported contact artifact contains 93 valid addresses.",
        "false",
    ),
    "known_02_trapped_gemini": (
        "The Gemini agent's computer or browser environment is unavailable or trapping it.",
        "episode_dependent",
    ),
    "known_03_whitespace_egg": (
        "Pull request 70 encodes an EGG payload through whitespace.",
        "false",
    ),
}


def build_claim_lineage() -> dict[str, Any]:
    ensure_output_dirs()
    registry = _registry()
    message_ids = {row["source_message_id"] for row in registry} | {
        row["recipient_response_message_id"] for row in registry
    }
    messages = _message_map(message_ids)
    claims: list[dict[str, Any]] = []
    expressions: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for item in registry:
        claim_id = stable_id("claim_v2", item["episode_id"], item["seed_event"], prefix="claim")
        source = messages.get(item["source_message_id"], {})
        response = messages.get(item["recipient_response_message_id"], {})
        artifacts = sorted(
            _artifact_union(source.get("content") or "", response.get("content") or "")
        )
        is_known = item.get("discovery_method") == "known_incident_reconstruction"
        known_prop = KNOWN_PROPOSITIONS["known_03_whitespace_egg"] if is_known else None
        claims.append(
            {
                "claim_id": claim_id,
                "episode_id": item["episode_id"],
                "normalized_proposition": known_prop[0] if known_prop else None,
                "referent_or_artifact": json.dumps(artifacts, ensure_ascii=False),
                "truth_status": known_prop[1] if known_prop else "unadjudicated",
                "first_observed_expression": item["seed_event"],
                "source_agent": item["source_agent"],
                "source_stance": "unadjudicated",
                "supporting_evidence_ids": "[]",
                "upstream_claim_ids": "[]",
                "agreeing_message_count": None,
                "independent_evidence_source_count": None,
                "annotation_status": "human_required",
                "known_incident": is_known,
            }
        )
        for role, event_key, message_key, agent_key in (
            ("first_detected_expression", "seed_event", "source_message_id", "source_agent"),
            (
                "candidate_later_expression",
                "recipient_response",
                "recipient_response_message_id",
                "recipient_agent",
            ),
        ):
            raw = messages.get(item[message_key], {})
            expressions.append(
                {
                    "expression_id": stable_id(
                        "claim_expression", claim_id, item[event_key], prefix="expr"
                    ),
                    "claim_id": claim_id,
                    "episode_id": item["episode_id"],
                    "event_id": item[event_key],
                    "raw_message_id": item[message_key],
                    "agent_id": item[agent_key],
                    "timestamp": parse_timestamp(raw.get("created_at")),
                    "expression_role": role,
                    "stance": "unadjudicated",
                    "stance_annotation_status": "human_required",
                    "text": raw.get("content") or "",
                }
            )
        edges.append(
            {
                "lineage_edge_id": stable_id(
                    "lineage_v2", item["seed_event"], item["recipient_response"], prefix="lin"
                ),
                "episode_id": item["episode_id"],
                "source_node_id": item["seed_event"],
                "target_node_id": item["recipient_response"],
                "candidate_relation": "possible_prior_message_or_common_evidence",
                "evidence_source_type": "unadjudicated",
                "independence_status": "unadjudicated",
                "annotation_status": "human_required",
            }
        )
    # Public incidents are qualitative additions, never detector-validation rows.
    known_path = REPORTS / "known_incident_reconstructions.csv"
    if known_path.exists():
        with known_path.open(newline="", encoding="utf-8") as handle:
            known_rows = list(csv.DictReader(handle))
        known_message_ids = {row["raw_message_id"] for row in known_rows}
        known_messages = _message_map(known_message_ids)
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in known_rows:
            grouped[row["incident_id"]].append(row)
        for incident_id, incident_rows in grouped.items():
            incident_rows.sort(key=lambda row: int(row["checkpoint_order"]))
            proposition, truth = KNOWN_PROPOSITIONS[incident_id]
            episode_id = f"qual_{incident_id}"
            claim_id = stable_id("known_claim_v2", incident_id, prefix="claim")
            claims.append(
                {
                    "claim_id": claim_id,
                    "episode_id": episode_id,
                    "normalized_proposition": proposition,
                    "referent_or_artifact": None,
                    "truth_status": truth,
                    "first_observed_expression": incident_rows[0]["canonical_event_id"],
                    "source_agent": incident_rows[0]["actor_agent_id"],
                    "source_stance": "unadjudicated",
                    "supporting_evidence_ids": "[]",
                    "upstream_claim_ids": "[]",
                    "agreeing_message_count": None,
                    "independent_evidence_source_count": None,
                    "annotation_status": "human_required_except_public_truth_description",
                    "known_incident": True,
                }
            )
            previous = None
            for known in incident_rows:
                raw = known_messages.get(known["raw_message_id"], {})
                expression_id = stable_id(
                    "known_expression_v2", incident_id, known["canonical_event_id"], prefix="expr"
                )
                expressions.append(
                    {
                        "expression_id": expression_id,
                        "claim_id": claim_id,
                        "episode_id": episode_id,
                        "event_id": known["canonical_event_id"],
                        "raw_message_id": known["raw_message_id"],
                        "agent_id": known["actor_agent_id"],
                        "timestamp": parse_timestamp(raw.get("created_at")),
                        "expression_role": known["checkpoint_role"],
                        "stance": "unadjudicated",
                        "stance_annotation_status": "human_required",
                        "text": raw.get("content") or "",
                    }
                )
                if previous:
                    edges.append(
                        {
                            "lineage_edge_id": stable_id(
                                "known_lineage_v2", previous, expression_id, prefix="lin"
                            ),
                            "episode_id": episode_id,
                            "source_node_id": previous,
                            "target_node_id": expression_id,
                            "candidate_relation": "chronological_case_checkpoint",
                            "evidence_source_type": "unadjudicated",
                            "independence_status": "unadjudicated",
                            "annotation_status": "human_required",
                        }
                    )
                previous = expression_id
    pq.write_table(
        pa.Table.from_pylist(claims, schema=CLAIM_SCHEMA),
        PROCESSED / "claims_v2.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(expressions, schema=EXPRESSION_SCHEMA),
        PROCESSED / "claim_expressions_v2.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(edges, schema=LINEAGE_SCHEMA),
        PROCESSED / "evidence_lineage_v2.parquet",
        compression="zstd",
    )
    result = {
        "claim_count": len(claims),
        "expression_count": len(expressions),
        "lineage_edge_count": len(edges),
        "human_adjudicated_claim_count": 0,
        "known_incidents_kept_separate": True,
    }
    (REPORTS / "claim_lineage_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _artifact_union(*texts: str) -> set[str]:
    from .eligibility_v2 import artifact_identifiers

    result: set[str] = set()
    for text in texts:
        result.update(artifact_identifiers(text))
    return result


ACTION_TRACE_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("event_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("event_type", pa.string()),
        ("actor_agent_id", pa.string()),
        ("source_table", pa.string()),
        ("source_record_id", pa.string()),
        ("content_reference", pa.string()),
        ("artifact_reference", pa.string()),
        ("raw_payload", pa.string()),
        ("screenshot_turn_id", pa.string()),
        ("visual_state_may_matter", pa.bool_()),
        ("claim_relevant_action_label", pa.string()),
        ("annotation_status", pa.string()),
        ("window_ended_at", pa.timestamp("us", tz="UTC")),
    ]
)


def build_action_windows(
    cluster_index: EpisodeClusterIndex | None = None,
    registry_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    ensure_output_dirs()
    cluster_index = cluster_index or EpisodeClusterIndex()
    registry = _registry(registry_path)
    output_path = output_path or PROCESSED / "claim_relevant_action_windows_v2.parquet"
    report_path = report_path or REPORTS / "action_windows_v2.json"
    response_ids = {row["recipient_response"] for row in registry}
    con = duckdb.connect()
    response_meta = {
        event_id: timestamp
        for event_id, timestamp in con.execute(
            "SELECT canonical_event_id, timestamp FROM read_parquet(?) WHERE canonical_event_id IN (SELECT unnest(?))",
            [str(PROCESSED / "canonical_events.parquet"), list(response_ids)],
        ).fetchall()
    }
    windows: dict[str, tuple[datetime, datetime, str]] = {}
    for item in registry:
        response_time = response_meta.get(item["recipient_response"])
        if response_time is None:
            continue
        cluster = cluster_index.for_message(item["recipient_response_message_id"])
        hard_end = response_time + timedelta(hours=24)
        # The episode remains open through the frozen inactivity boundary after its final message;
        # this retains related tool work that occurs after the last chat message.
        episode_end = cluster.ended_at + INACTIVITY_GAP if cluster else hard_end
        end = min(hard_end, episode_end)
        windows[item["episode_id"]] = (response_time, end, item["recipient_agent"])
    canonical_rows: list[dict[str, Any]] = []
    needed: dict[str, set[str]] = defaultdict(set)
    for episode_id, (start, end, actor) in windows.items():
        results = con.execute(
            """
            SELECT canonical_event_id, timestamp, event_type, actor_agent_id, source_table,
                   source_record_id, content_reference, artifact_reference
            FROM read_parquet(?)
            WHERE actor_agent_id = ? AND timestamp > ? AND timestamp <= ?
            ORDER BY timestamp, canonical_event_id
            """,
            [str(PROCESSED / "canonical_events.parquet"), actor, start, end],
        ).fetchall()
        for values in results:
            row = dict(
                zip(
                    (
                        "event_id",
                        "timestamp",
                        "event_type",
                        "actor_agent_id",
                        "source_table",
                        "source_record_id",
                        "content_reference",
                        "artifact_reference",
                    ),
                    values,
                    strict=True,
                )
            )
            row["episode_id"] = episode_id
            row["window_ended_at"] = end
            canonical_rows.append(row)
            needed[row["source_table"]].add(row["source_record_id"])
    con.close()
    raw_payloads: dict[tuple[str, str], tuple[str, str | None, bool]] = {}
    for table in ("events", "computer_use_turns", "claude_code_messages"):
        ids = needed.get(table, set())
        if not ids:
            continue
        for raw in stream_jsonl(RAW / f"{table}.jsonl.gz"):
            if raw.get("id") not in ids:
                continue
            if table == "events":
                payload = raw.get("data")
                visual = False
                screenshot_id = None
            elif table == "computer_use_turns":
                payload = {
                    "agent_action": raw.get("agent_action"),
                    "output": raw.get("output"),
                    "error": raw.get("error"),
                    "system": raw.get("system"),
                    "screenshot_is_redacted": raw.get("screenshot_is_redacted"),
                }
                action = raw.get("agent_action") or {}
                action_name = (
                    str(action.get("action") or "").lower() if isinstance(action, dict) else ""
                )
                visual = action_name in {
                    "left_click",
                    "right_click",
                    "double_click",
                    "drag",
                    "scroll",
                }
                screenshot_id = raw["id"]
            else:
                payload = raw.get("content")
                visual = False
                screenshot_id = None
            raw_payloads[(table, raw["id"])] = (
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                screenshot_id,
                visual,
            )
    rows = []
    for event in canonical_rows:
        payload, screenshot_id, visual = raw_payloads.get(
            (event["source_table"], event["source_record_id"]), ("null", None, False)
        )
        rows.append(
            {
                **event,
                "raw_payload": payload,
                "screenshot_turn_id": screenshot_id,
                "visual_state_may_matter": visual,
                "claim_relevant_action_label": None,
                "annotation_status": "human_required",
            }
        )
    path = output_path
    pq.write_table(pa.Table.from_pylist(rows, schema=ACTION_TRACE_SCHEMA), path, compression="zstd")
    result = {
        "artifact": str(path),
        "episode_count": len(windows),
        "trace_event_count": len(rows),
        "visual_trace_event_count": sum(row["visual_state_may_matter"] for row in rows),
        "positive_action_labels": 0,
        "annotation_status": "human_required",
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


MEMORY_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("agent_id", pa.string()),
        ("response_timestamp", pa.timestamp("us", tz="UTC")),
        ("memory_before_id", pa.string()),
        ("memory_before_timestamp", pa.timestamp("us", tz="UTC")),
        ("memory_after_id", pa.string()),
        ("memory_after_timestamp", pa.timestamp("us", tz="UTC")),
        ("added_spans", pa.string()),
        ("removed_or_rewritten_spans", pa.string()),
        ("later_memory_ids", pa.string()),
        ("added_span_survives_one_snapshot", pa.bool_()),
        ("added_span_survives_two_snapshots", pa.bool_()),
        ("memory_delta_label", pa.string()),
        ("annotation_status", pa.string()),
    ]
)


def _delta(before: str, after: str) -> tuple[list[str], list[str]]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            text = "\n".join(after_lines[j1:j2]).strip()
            if text:
                added.append(text)
        if tag in {"delete", "replace"}:
            text = "\n".join(before_lines[i1:i2]).strip()
            if text:
                removed.append(text)
    return added, removed


def _span_survival(spans: list[str], content: str) -> bool | None:
    material = [
        " ".join(span.lower().split()) for span in spans if len(" ".join(span.split())) >= 20
    ]
    if not material:
        return None
    normalized = " ".join(content.lower().split())
    return any(span in normalized for span in material)


def build_memory_deltas(
    registry_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    ensure_output_dirs()
    registry = _registry(registry_path)
    output_path = output_path or PROCESSED / "memory_deltas_v2.parquet"
    report_path = report_path or REPORTS / "memory_deltas_v2.json"
    response_times = {
        row["id"]: parse_timestamp(row.get("created_at"))
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in {item["recipient_response_message_id"] for item in registry}
    }
    targets = {
        item["episode_id"]: {
            "agent": item["recipient_agent"],
            "response": response_times.get(item["recipient_response_message_id"]),
            "before": None,
            "after": [],
        }
        for item in registry
    }
    by_agent: dict[str, list[str]] = defaultdict(list)
    for episode_id, target in targets.items():
        if target["response"]:
            by_agent[target["agent"]].append(episode_id)
    for memory in stream_jsonl(RAW / "agent_memories.jsonl.gz"):
        agent = memory.get("agent_id")
        if agent not in by_agent:
            continue
        timestamp = parse_timestamp(memory.get("created_at"))
        if timestamp is None:
            continue
        record = (timestamp, memory["id"], memory.get("content") or "")
        for episode_id in by_agent[agent]:
            target = targets[episode_id]
            response = target["response"]
            if response is None:
                continue
            if timestamp < response:
                current = target["before"]
                if current is None or timestamp > current[0]:
                    target["before"] = record
            elif response < timestamp <= response + timedelta(days=7):
                after = target["after"]
                after.append(record)
                after.sort(key=lambda value: (value[0], value[1]))
                del after[3:]
    rows = []
    for episode_id, target in targets.items():
        before = target["before"]
        after = target["after"]
        first = after[0] if after else None
        added, removed = (
            _delta(before[2] if before else "", first[2] if first else "") if first else ([], [])
        )
        survives_one = _span_survival(added, after[1][2]) if len(after) >= 2 else None
        survives_two = _span_survival(added, after[2][2]) if len(after) >= 3 else None
        rows.append(
            {
                "episode_id": episode_id,
                "agent_id": target["agent"],
                "response_timestamp": target["response"],
                "memory_before_id": before[1] if before else None,
                "memory_before_timestamp": before[0] if before else None,
                "memory_after_id": first[1] if first else None,
                "memory_after_timestamp": first[0] if first else None,
                "added_spans": json.dumps(added, ensure_ascii=False),
                "removed_or_rewritten_spans": json.dumps(removed, ensure_ascii=False),
                "later_memory_ids": json.dumps([value[1] for value in after[1:]]),
                "added_span_survives_one_snapshot": survives_one,
                "added_span_survives_two_snapshots": survives_two,
                "memory_delta_label": None,
                "annotation_status": "human_required",
            }
        )
    path = output_path
    pq.write_table(pa.Table.from_pylist(rows, schema=MEMORY_SCHEMA), path, compression="zstd")
    result = {
        "artifact": str(path),
        "row_count": len(rows),
        "with_before_and_after": sum(
            bool(row["memory_before_id"] and row["memory_after_id"]) for row in rows
        ),
        "semantic_positive_count": 0,
        "annotation_status": "human_required",
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


THIRD_PARTY_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("original_source_agent_id", pa.string()),
        ("candidate_reexpressing_agent_id", pa.string()),
        ("later_event_id", pa.string()),
        ("later_message_id", pa.string()),
        ("later_timestamp", pa.timestamp("us", tz="UTC")),
        ("later_room_id", pa.string()),
        ("new_recipient_agent_ids", pa.string()),
        ("lexical_overlap_count", pa.int32()),
        ("lexical_containment", pa.float64()),
        ("later_expression_text", pa.string()),
        ("same_proposition_label", pa.string()),
        ("stance_label", pa.string()),
        ("third_party_retransmission_label", pa.string()),
        ("annotation_status", pa.string()),
    ]
)


def _sender_room_at_message(
    visibility: VisibilityIndex,
    sender_id: str,
    timestamp: datetime,
    exported_room_id: str | None,
) -> str | None:
    """Return the channel under the platform rules, not the raw legacy room field.

    Before rooms were deployed, messages were global even though some exported rows
    carry a non-null legacy ``room_id``. Comparing that raw identifier with
    ``VisibilityIndex.room_at`` (which correctly returns ``__global__``) silently
    removed every possible new recipient from pre-room retransmission candidates.
    """
    rooms_introduced = parse_timestamp(ROOMS_INTRODUCED)
    if rooms_introduced is not None and timestamp < rooms_introduced:
        return "__global__"
    return exported_room_id or visibility.room_at(sender_id, timestamp)


def build_third_party_candidates(
    registry_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    ensure_output_dirs()
    registry = _registry(registry_path)
    output_path = output_path or PROCESSED / "third_party_expression_candidates_v2.parquet"
    report_path = report_path or REPORTS / "third_party_candidates_v2.json"
    visibility = VisibilityIndex()
    needed_response_ids = {item["recipient_response_message_id"] for item in registry}
    response_times: dict[str, datetime] = {}
    all_messages: list[dict[str, Any]] = []
    for message in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        timestamp = parse_timestamp(message.get("created_at"))
        if not timestamp or not message.get("agent_speaker_id"):
            continue
        item = {
            "id": message["id"],
            "agent": message["agent_speaker_id"],
            "timestamp": timestamp,
            "room": message.get("room_id"),
            "content": message.get("content") or "",
        }
        all_messages.append(item)
        if message["id"] in needed_response_ids:
            response_times[message["id"]] = timestamp
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in all_messages:
        by_agent[message["agent"]].append(message)
    agent_ids = list(visibility.agents)
    rows = []
    for item in registry:
        response_time = response_times.get(item["recipient_response_message_id"])
        if response_time is None:
            continue
        candidate_terms = {term for term in item.get("shared_terms", "").split("|") if term}
        if not candidate_terms:
            continue
        for later in by_agent.get(item["recipient_agent"], []):
            if not (response_time < later["timestamp"] <= response_time + timedelta(days=7)):
                continue
            later_terms = _informative(later["content"])
            overlap = candidate_terms & later_terms
            containment = len(overlap) / max(1, len(candidate_terms))
            if len(overlap) < 2 or containment < 0.25:
                continue
            new_recipients = []
            sender_room = _sender_room_at_message(
                visibility,
                item["recipient_agent"],
                later["timestamp"],
                later["room"],
            )
            for agent_id in agent_ids:
                if agent_id in {item["source_agent"], item["recipient_agent"]}:
                    continue
                if not visibility.is_active(agent_id, later["timestamp"]):
                    continue
                if visibility.room_at(agent_id, later["timestamp"]) == sender_room:
                    new_recipients.append(agent_id)
            if not new_recipients:
                continue
            mapped = visibility.message_events.get(later["id"])
            if not mapped:
                continue
            rows.append(
                {
                    "episode_id": item["episode_id"],
                    "original_source_agent_id": item["source_agent"],
                    "candidate_reexpressing_agent_id": item["recipient_agent"],
                    "later_event_id": mapped[0],
                    "later_message_id": later["id"],
                    "later_timestamp": later["timestamp"],
                    "later_room_id": later["room"],
                    "new_recipient_agent_ids": json.dumps(sorted(new_recipients)),
                    "lexical_overlap_count": len(overlap),
                    "lexical_containment": containment,
                    "later_expression_text": later["content"],
                    "same_proposition_label": None,
                    "stance_label": None,
                    "third_party_retransmission_label": None,
                    "annotation_status": "human_required_lexical_candidate_only",
                }
            )
    path = output_path
    pq.write_table(pa.Table.from_pylist(rows, schema=THIRD_PARTY_SCHEMA), path, compression="zstd")
    result = {
        "artifact": str(path),
        "candidate_trace_count": len(rows),
        "episodes_with_candidate_trace": len({row["episode_id"] for row in rows}),
        "validated_retransmission_count": 0,
        "annotation_status": "human_required",
    }
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
