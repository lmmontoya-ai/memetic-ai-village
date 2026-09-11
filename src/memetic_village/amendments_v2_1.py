from __future__ import annotations

import csv
import gzip
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .annotation_v2 import _remove_model_fields, agreement_statistics
from .config import EPISODES, PROCESSED, RANDOM_SEED, RAW, REPORTS, ROOT, ensure_output_dirs
from .discovery import REQUEST_RE, Message, _informative, _load_messages
from .eligibility_v2 import _direct_reference, artifact_identifiers, build_response_eligibility
from .exposure import VisibilityIndex
from .holdout_v2 import EpisodeClusterIndex
from .outcomes_v2 import build_action_windows, build_memory_deltas, build_third_party_candidates
from .temporal_v2 import build_temporal_relations
from .util import iso_utc, parse_timestamp, sha256_file, stable_id, stream_jsonl

ANNOTATIONS = ROOT / "annotations" / "v2_1"
HOLDOUT_CUTOFF_PATH = ROOT / "data" / "raw_manifest" / "holdout.json"
CODE_OR_FILE_RE = re.compile(
    r"(?:[\w.-]+/){1,6}[\w.-]+|\b(?:PR|pull request|issue)\s*#?\d+\b|\b[\w.-]+\.(?:js|mjs|ts|py|yaml|yml|json|csv|md|txt)\b",
    re.IGNORECASE,
)
HANDOFF_RE = re.compile(
    r"\b(as .{1,40} found|following .{1,40}(?:result|finding|report)|i checked .{1,40} claim|"
    r"per .{1,40}(?:message|report|analysis)|shared|sent|exported|uploaded|linked)\b",
    re.IGNORECASE,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _cutoff() -> datetime:
    value = parse_timestamp(json.loads(HOLDOUT_CUTOFF_PATH.read_text(encoding="utf-8"))["cutoff"])
    if value is None:
        raise ValueError("Invalid frozen holdout cutoff")
    return value


def _development_units() -> list[dict[str, str]]:
    return _read_csv(EPISODES / "development_units_v2.csv")


def _annotation_units() -> list[dict[str, str]]:
    path = EPISODES / "development_units_v2_1.csv"
    return _read_csv(path if path.exists() else EPISODES / "development_units_v2.csv")


def _containment(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, min(len(left), len(right)))


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _code_identifiers(text: str) -> set[str]:
    return {match.group(0).rstrip(".,:;").lower() for match in CODE_OR_FILE_RE.finditer(text)}


def _message_by_id(messages: Iterable[Message]) -> dict[str, Message]:
    return {message.message_id: message for message in messages}


def _anonymous_label(labels: dict[str, str], agent_id: str | None) -> str:
    key = agent_id or "unknown"
    if key not in labels:
        labels[key] = f"Agent {chr(65 + len(labels))}"
    return labels[key]


def _unit_cluster_ids(units: list[dict[str, str]], index: EpisodeClusterIndex) -> dict[str, str]:
    return {
        unit["episode_id"]: index.message_to_cluster.get(
            unit["recipient_response_message_id"], "unknown_cluster"
        )
        for unit in units
    }


def build_author_autocorrelation_diagnostic() -> dict[str, Any]:
    """Reclassify the old author shuffle without rerunning or treating it as a null."""
    source_report = json.loads(
        (REPORTS / "blocked_permutations_v2.json").read_text(encoding="utf-8")
    )
    source_table = pq.read_table(PROCESSED / "blocked_permutations_v2.parquet")
    output_table = PROCESSED / "author_autocorrelation_diagnostic_v2_1.parquet"
    pq.write_table(source_table, output_table, compression="zstd")
    result = {
        "artifact": str(output_table),
        "diagnostic_name": "author_autocorrelation_diagnostic",
        "iterations": source_report["iterations"],
        "observed_cross_agent_lexical_edges": source_report["observed_retrieved_unique_count"],
        "author_shuffle_median_cross_agent_lexical_edges": source_report[
            "permutation_retrieved_median"
        ],
        "mechanical_bias": (
            "Author shuffling changes the cross-author eligibility indicator while lexical pair "
            "scores remain fixed, converting within-agent topical continuity into artificial "
            "cross-agent opportunities."
        ),
        "permitted_conclusion": (
            "Raw recurrence counts are mechanically influenced by within-agent topical continuity "
            "and cannot be interpreted as evidence for or against social transmission."
        ),
        "valid_social_influence_null": False,
        "included_in_gate_1": False,
        "logical_sha256": source_report["logical_sha256"],
    }
    (REPORTS / "author_autocorrelation_diagnostic_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


LOCAL_COMPARISON_SCHEMA = pa.schema(
    [
        ("candidate_episode_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("room_id", pa.string()),
        ("response_event_id", pa.string()),
        ("response_message_id", pa.string()),
        ("response_agent_id", pa.string()),
        ("response_timestamp", pa.timestamp("us", tz="UTC")),
        ("source_event_id", pa.string()),
        ("source_message_id", pa.string()),
        ("source_agent_id", pa.string()),
        ("source_timestamp", pa.timestamp("us", tz="UTC")),
        ("is_frozen_selected_source", pa.bool_()),
        ("author_sequence_modified", pa.bool_()),
        ("time_lag_seconds", pa.float64()),
        ("lag_match_to_selected", pa.float64()),
        ("length_match_to_selected", pa.float64()),
        ("source_response_lexical_containment", pa.float64()),
        ("artifact_overlap_with_response", pa.float64()),
        ("code_identifier_overlap_with_response", pa.float64()),
        ("response_activity_24h", pa.int32()),
        ("goal_match_quality", pa.string()),
        ("direct_source_link_detected", pa.bool_()),
        ("hard_control_class", pa.string()),
        ("hard_control_adequacy", pa.string()),
        ("matching_score", pa.float64()),
        ("semantic_proposition_label", pa.string()),
        ("annotation_status", pa.string()),
    ]
)


def _local_source_rows(
    units: list[dict[str, str]], messages: list[Message], index: EpisodeClusterIndex
) -> list[dict[str, Any]]:
    by_id = _message_by_id(messages)
    by_cluster: dict[str, list[Message]] = defaultdict(list)
    for message in messages:
        cluster_id = index.message_to_cluster.get(message.message_id)
        if cluster_id:
            by_cluster[cluster_id].append(message)
    rows: list[dict[str, Any]] = []
    for unit in units:
        selected = by_id[unit["source_message_id"]]
        response = by_id[unit["recipient_response_message_id"]]
        cluster_id = index.message_to_cluster.get(response.message_id, "unknown_cluster")
        selected_lag = max(1.0, (response.timestamp - selected.timestamp).total_seconds())
        response_activity = sum(
            message.agent_id == response.agent_id
            and response.timestamp < message.timestamp <= response.timestamp + timedelta(hours=24)
            for message in by_cluster.get(cluster_id, [])
        )
        for source in by_cluster.get(cluster_id, []):
            if source.room_id != response.room_id or source.agent_id == response.agent_id:
                continue
            if not (source.timestamp < response.timestamp):
                continue
            lag = (response.timestamp - source.timestamp).total_seconds()
            if lag > 48 * 3600:
                continue
            lag_match = 1.0 - min(1.0, abs(lag - selected_lag) / selected_lag)
            length_match = min(len(source.content), len(selected.content)) / max(
                1, max(len(source.content), len(selected.content))
            )
            artifacts = artifact_identifiers(source.content)
            response_artifacts = artifact_identifiers(response.content)
            artifact_overlap = _jaccard(artifacts, response_artifacts)
            code_overlap = _jaccard(
                _code_identifiers(source.content), _code_identifiers(response.content)
            )
            lexical = _containment(source.terms, response.terms)
            direct, _ = _direct_reference(source.content, response.content, None)
            is_selected = source.message_id == selected.message_id
            if not is_selected and direct:
                hard_class = "topically_relevant_possible_source_not_control"
                adequacy = "exclude_direct_link_detected"
            elif not is_selected and artifact_overlap > 0:
                hard_class = "same_artifact_independent_convergence_candidate"
                adequacy = "hard_shared_artifact"
            elif not is_selected and code_overlap > 0:
                hard_class = "same_code_or_filename_convergence_candidate"
                adequacy = "hard_code_identifier"
            elif not is_selected and lexical >= 0.18:
                hard_class = "same_task_topical_non_source_candidate"
                adequacy = "moderate_local"
            elif is_selected:
                hard_class = "frozen_selected_source"
                adequacy = "candidate"
            else:
                hard_class = "ordinary_local_alternative"
                adequacy = "soft_local_only"
            score = (
                0.30 * lag_match
                + 0.25 * length_match
                + 0.20 * artifact_overlap
                + 0.15 * code_overlap
                + 0.10 * lexical
            )
            rows.append(
                {
                    "candidate_episode_id": unit["episode_id"],
                    "episode_cluster_id": cluster_id,
                    "room_id": response.room_id,
                    "response_event_id": response.event_id,
                    "response_message_id": response.message_id,
                    "response_agent_id": response.agent_id,
                    "response_timestamp": response.timestamp,
                    "source_event_id": source.event_id,
                    "source_message_id": source.message_id,
                    "source_agent_id": source.agent_id,
                    "source_timestamp": source.timestamp,
                    "is_frozen_selected_source": is_selected,
                    "author_sequence_modified": False,
                    "time_lag_seconds": lag,
                    "lag_match_to_selected": lag_match,
                    "length_match_to_selected": length_match,
                    "source_response_lexical_containment": lexical,
                    "artifact_overlap_with_response": artifact_overlap,
                    "code_identifier_overlap_with_response": code_overlap,
                    "response_activity_24h": response_activity,
                    "goal_match_quality": "unresolved_village_goal_table_absent",
                    "direct_source_link_detected": direct,
                    "hard_control_class": hard_class,
                    "hard_control_adequacy": adequacy,
                    "matching_score": score,
                    "semantic_proposition_label": None,
                    "annotation_status": "human_required_blinded",
                }
            )
    return rows


def build_fixed_author_local_comparisons() -> dict[str, Any]:
    ensure_output_dirs()
    units = [unit for unit in _development_units() if unit["unit_origin"] == "retrieved_candidate"]
    messages = _load_messages(VisibilityIndex(), _cutoff())
    index = EpisodeClusterIndex()
    rows = _local_source_rows(units, messages, index)
    path = PROCESSED / "fixed_author_local_source_comparisons_v2_1.parquet"
    pq.write_table(
        pa.Table.from_pylist(rows, schema=LOCAL_COMPARISON_SCHEMA), path, compression="zstd"
    )
    adequate = [
        row
        for row in rows
        if not row["is_frozen_selected_source"]
        and row["hard_control_adequacy"] in {"hard_shared_artifact", "hard_code_identifier"}
    ]
    candidates_with_hard = {row["candidate_episode_id"] for row in adequate}
    result = {
        "artifact": str(path),
        "comparison_row_count": len(rows),
        "candidate_count": len(units),
        "candidate_with_hard_control_count": len(candidates_with_hard),
        "candidate_without_hard_control_count": len(units) - len(candidates_with_hard),
        "hard_control_class_counts": dict(Counter(row["hard_control_class"] for row in rows)),
        "author_sequence_fixed": True,
        "paired_analysis_required": True,
        "ordinary_controls_not_substituted_for_hard_controls": True,
        "human_proposition_check_required": True,
    }
    (REPORTS / "fixed_author_local_comparisons_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def build_hard_control_development_set() -> dict[str, Any]:
    """Prioritize available hard controls while preserving the frozen 30/20/10 design."""
    base = _development_units()
    candidates = [row for row in base if row["unit_origin"] == "retrieved_candidate"]
    ordinary = [
        row
        for row in base
        if row["unit_origin"]
        in {"same_room_local_source_control", "shared_artifact_convergence_control"}
    ]
    placebos = [
        row for row in base if row["unit_origin"] in {"source_identity_placebo", "temporal_placebo"}
    ]
    comparison_rows = pq.read_table(
        PROCESSED / "fixed_author_local_source_comparisons_v2_1.parquet"
    ).to_pylist()
    hard_candidates = [
        row
        for row in comparison_rows
        if not row["is_frozen_selected_source"]
        and row["hard_control_adequacy"] in {"hard_shared_artifact", "hard_code_identifier"}
        and not row["direct_source_link_detected"]
    ]
    selected_hard = {}
    for row in sorted(
        hard_candidates,
        key=lambda item: (-item["matching_score"], item["source_message_id"]),
    ):
        selected_hard.setdefault(row["candidate_episode_id"], row)
    index = EpisodeClusterIndex()
    selected_controls = []
    for position, row in enumerate(selected_hard.values(), 1):
        selected_controls.append(
            {
                "episode_id": f"dev_v2_1_hard_{position:03d}_{row['source_message_id'][-8:]}",
                "seed_event": row["source_event_id"],
                "source_message_id": row["source_message_id"],
                "source_agent": row["source_agent_id"],
                "recipient_response": row["response_event_id"],
                "recipient_response_message_id": row["response_message_id"],
                "recipient_agent": row["response_agent_id"],
                "shared_terms": "",
                "unit_origin": row["hard_control_class"],
                "matched_candidate_episode_id": row["candidate_episode_id"].removeprefix(
                    "dev_candidate_"
                ),
                "discovery_method": "fixed_author_hard_control_v2_1",
                "similarity_score": row["matching_score"],
                "episode_cluster_id": row["episode_cluster_id"],
            }
        )
    hard_matched = {row["matched_candidate_episode_id"] for row in selected_controls}
    for row in ordinary:
        if len(selected_controls) >= 20:
            break
        if row["matched_candidate_episode_id"] in hard_matched:
            continue
        selected_controls.append(
            row
            | {
                "episode_id": row["episode_id"].replace("dev_control_", "dev_v2_1_control_"),
                "episode_cluster_id": index.message_to_cluster.get(
                    row["recipient_response_message_id"], "unknown_cluster"
                ),
            }
        )
        hard_matched.add(row["matched_candidate_episode_id"])
    if len(selected_controls) < 20:
        used = {row["episode_id"] for row in selected_controls}
        for row in ordinary:
            if len(selected_controls) >= 20:
                break
            revised_id = row["episode_id"].replace("dev_control_", "dev_v2_1_control_")
            if revised_id in used:
                continue
            selected_controls.append(
                row
                | {
                    "episode_id": revised_id,
                    "episode_cluster_id": index.message_to_cluster.get(
                        row["recipient_response_message_id"], "unknown_cluster"
                    ),
                }
            )
            used.add(revised_id)
    candidate_rows = [
        row
        | {
            "episode_id": row["episode_id"].replace("dev_candidate_", "dev_v2_1_candidate_"),
            "episode_cluster_id": index.message_to_cluster.get(
                row["recipient_response_message_id"], "unknown_cluster"
            ),
        }
        for row in candidates
    ]
    placebo_rows = [
        row
        | {
            "episode_id": row["episode_id"].replace("dev_control_", "dev_v2_1_placebo_"),
            "episode_cluster_id": index.message_to_cluster.get(
                row["recipient_response_message_id"], "unknown_cluster"
            ),
        }
        for row in placebos[:10]
    ]
    rows = [*candidate_rows, *selected_controls[:20], *placebo_rows]
    if len(rows) != 60:
        raise ValueError(f"Expected 60 v2.1 development units, got {len(rows)}")
    path = EPISODES / "development_units_v2_1.csv"
    _write_csv(path, rows)
    result = {
        "artifact": str(path),
        "candidate_count": len(candidate_rows),
        "control_count": len(selected_controls[:20]),
        "placebo_count": len(placebo_rows),
        "hard_control_count": sum(
            row["discovery_method"] == "fixed_author_hard_control_v2_1"
            for row in selected_controls[:20]
        ),
        "hard_control_candidate_coverage": len(selected_hard),
        "candidate_without_available_hard_control_count": 30 - len(selected_hard),
        "hard_control_shortfall_explicit": True,
        "matched_pair_analysis_required": True,
    }
    (REPORTS / "development_set_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def rebuild_v2_1_structural_traces() -> dict[str, Any]:
    registry = EPISODES / "development_units_v2_1.csv"
    index = EpisodeClusterIndex()
    temporal = build_temporal_relations(
        registry,
        PROCESSED / "temporal_relations_v2_1.parquet",
        REPORTS / "temporal_relations_v2_1.json",
    )
    eligibility = build_response_eligibility(
        registry,
        PROCESSED / "response_eligibility_v2_1.parquet",
        REPORTS / "response_eligibility_v2_1.json",
    )
    actions = build_action_windows(
        index,
        registry,
        PROCESSED / "claim_relevant_action_windows_v2_1.parquet",
        REPORTS / "action_windows_v2_1.json",
    )
    memories = build_memory_deltas(
        registry,
        PROCESSED / "memory_deltas_v2_1.parquet",
        REPORTS / "memory_deltas_v2_1.json",
    )
    third_party = build_third_party_candidates(
        registry,
        PROCESSED / "third_party_expression_candidates_v2_1.parquet",
        REPORTS / "third_party_candidates_v2_1.json",
    )
    return {
        "temporal": temporal,
        "eligibility": eligibility,
        "actions": actions,
        "memory": memories,
        "third_party": third_party,
    }


SOURCE_LINKED_SCHEMA = pa.schema(
    [
        ("channel_candidate_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("source_event_id", pa.string()),
        ("source_message_id", pa.string()),
        ("source_agent_id", pa.string()),
        ("response_event_id", pa.string()),
        ("response_message_id", pa.string()),
        ("response_agent_id", pa.string()),
        ("room_id", pa.string()),
        ("source_timestamp", pa.timestamp("us", tz="UTC")),
        ("response_timestamp", pa.timestamp("us", tz="UTC")),
        ("link_rule", pa.string()),
        ("source_link_specificity", pa.string()),
        ("shared_artifact_ids", pa.string()),
        ("rule_priority", pa.int8()),
        ("selected_for_development_sample", pa.bool_()),
        ("holdout_semantic_content_opened", pa.bool_()),
        ("annotation_status", pa.string()),
    ]
)


def _name_map() -> dict[str, str]:
    return {
        row["id"]: str(row.get("name") or "").strip()
        for row in stream_jsonl(RAW / "agents.jsonl.gz")
    }


def _source_link_rule(
    source: Message,
    response: Message,
    names: dict[str, str],
    normalized: dict[str, str],
    artifacts: dict[str, set[str]],
    request_flags: dict[str, bool],
) -> tuple[str, int]:
    response_normalized = normalized[response.message_id]
    source_normalized = normalized[source.message_id]
    source_name = names.get(source.agent_id, "").lower()
    if source_name and (
        f"@{source_name}" in response_normalized or source_name in response_normalized
    ):
        return "source_agent_named", 1
    if re.search(
        r"\b(as you said|your message|you mentioned|you reported|per your|replying to)\b",
        response_normalized,
    ):
        fragment_count = min(8, max(1, len(source_normalized) // 48))
        fragments = [
            source_normalized[position : position + 48]
            for position in np.linspace(
                0,
                max(0, len(source_normalized) - 48),
                num=fragment_count,
                dtype=int,
            )
        ]
        if any(len(fragment) >= 24 and fragment in response_normalized for fragment in fragments):
            return "explicit_discourse_reference_with_source_phrase", 1
    recipient_name = names.get(response.agent_id, "").lower()
    if (
        recipient_name
        and (f"@{recipient_name}" in source_normalized or recipient_name in source_normalized)
        and request_flags[source.message_id]
    ):
        return "direct_request_names_recipient", 2
    shared = artifacts[source.message_id] & artifacts[response.message_id]
    if shared and HANDOFF_RE.search(source.content + "\n" + response.content):
        return "explicit_artifact_handoff", 3
    return "", 99


def build_source_linked_channel() -> dict[str, Any]:
    """Run only on discovery material; the holdout remains semantically unopened."""
    messages = _load_messages(VisibilityIndex(), _cutoff())
    names = _name_map()
    index = EpisodeClusterIndex()
    normalized = {
        message.message_id: " ".join(message.content.lower().split()) for message in messages
    }
    artifacts = {message.message_id: artifact_identifiers(message.content) for message in messages}
    request_flags = {
        message.message_id: bool(REQUEST_RE.search(message.content)) for message in messages
    }
    by_room: dict[str | None, list[Message]] = defaultdict(list)
    for message in messages:
        by_room[message.room_id].append(message)
    rows: list[dict[str, Any]] = []
    for room_messages in by_room.values():
        for response_position, response in enumerate(room_messages):
            best: tuple[int, float, Message, str] | None = None
            for source in reversed(
                room_messages[max(0, response_position - 20) : response_position]
            ):
                if source.agent_id == response.agent_id:
                    continue
                lag = (response.timestamp - source.timestamp).total_seconds()
                if lag > 48 * 3600:
                    break
                if index.message_to_cluster.get(source.message_id) != index.message_to_cluster.get(
                    response.message_id
                ):
                    continue
                rule, priority = _source_link_rule(
                    source, response, names, normalized, artifacts, request_flags
                )
                if not rule:
                    continue
                rank = (priority, lag, source, rule)
                if best is None or rank[:2] < best[:2]:
                    best = rank
            if best is None:
                continue
            priority, _, source, rule = best
            shared = sorted(artifacts[source.message_id] & artifacts[response.message_id])
            rows.append(
                {
                    "channel_candidate_id": stable_id(
                        "source_linked_v2_1", source.event_id, response.event_id, prefix="sl"
                    ),
                    "episode_cluster_id": index.message_to_cluster.get(
                        response.message_id, "unknown_cluster"
                    ),
                    "source_event_id": source.event_id,
                    "source_message_id": source.message_id,
                    "source_agent_id": source.agent_id,
                    "response_event_id": response.event_id,
                    "response_message_id": response.message_id,
                    "response_agent_id": response.agent_id,
                    "room_id": response.room_id,
                    "source_timestamp": source.timestamp,
                    "response_timestamp": response.timestamp,
                    "link_rule": rule,
                    "source_link_specificity": {
                        "source_agent_named": "agent_level_attribution_message_ambiguous",
                        "direct_request_names_recipient": "message_level_direct_request",
                        "explicit_artifact_handoff": "artifact_path_specific",
                        "explicit_discourse_reference_with_source_phrase": "unique_phrase_message_level",
                    }[rule],
                    "shared_artifact_ids": json.dumps(shared, ensure_ascii=False),
                    "rule_priority": priority,
                    "selected_for_development_sample": False,
                    "holdout_semantic_content_opened": False,
                    "annotation_status": "human_proposition_and_stance_required",
                }
            )
    selected_ids: set[str] = set()
    cluster_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    response_counts: Counter[str] = Counter()
    rule_targets = {
        "explicit_discourse_reference_with_source_phrase": 10,
        "explicit_artifact_handoff": 15,
        "direct_request_names_recipient": 20,
        "source_agent_named": 15,
    }
    for rule, target in rule_targets.items():
        added = 0
        candidates = sorted(
            (row for row in rows if row["link_rule"] == rule),
            key=lambda row: (
                -bool(json.loads(row["shared_artifact_ids"])),
                (row["response_timestamp"] - row["source_timestamp"]).total_seconds(),
                row["channel_candidate_id"],
            ),
        )
        for row in candidates:
            if (
                cluster_counts[row["episode_cluster_id"]] >= 3
                or source_counts[row["source_agent_id"]] >= 10
                or response_counts[row["response_agent_id"]] >= 10
            ):
                continue
            selected_ids.add(row["channel_candidate_id"])
            cluster_counts[row["episode_cluster_id"]] += 1
            source_counts[row["source_agent_id"]] += 1
            response_counts[row["response_agent_id"]] += 1
            added += 1
            if added >= target:
                break
    if len(selected_ids) < 60:
        remaining = sorted(
            rows,
            key=lambda row: (
                row["rule_priority"],
                -bool(json.loads(row["shared_artifact_ids"])),
                (row["response_timestamp"] - row["source_timestamp"]).total_seconds(),
                row["channel_candidate_id"],
            ),
        )
        for row in remaining:
            if row["channel_candidate_id"] in selected_ids:
                continue
            if (
                cluster_counts[row["episode_cluster_id"]] >= 3
                or source_counts[row["source_agent_id"]] >= 10
                or response_counts[row["response_agent_id"]] >= 10
            ):
                continue
            selected_ids.add(row["channel_candidate_id"])
            cluster_counts[row["episode_cluster_id"]] += 1
            source_counts[row["source_agent_id"]] += 1
            response_counts[row["response_agent_id"]] += 1
            if len(selected_ids) == 60:
                break
    for row in rows:
        row["selected_for_development_sample"] = row["channel_candidate_id"] in selected_ids
    path = PROCESSED / "source_linked_candidates_v2_1.parquet"
    pq.write_table(
        pa.Table.from_pylist(rows, schema=SOURCE_LINKED_SCHEMA), path, compression="zstd"
    )
    result = {
        "artifact": str(path),
        "full_development_candidate_pool_count": len(rows),
        "frozen_development_sample_count": len(selected_ids),
        "link_rule_counts": dict(Counter(row["link_rule"] for row in rows)),
        "selected_link_rule_counts": dict(
            Counter(row["link_rule"] for row in rows if row["selected_for_development_sample"])
        ),
        "frozen_before_holdout_semantic_inspection": True,
        "holdout_semantic_content_opened": False,
        "reported_separately_from_lexical_channel": True,
        "human_semantic_validation_required": True,
    }
    (REPORTS / "source_linked_channel_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


ATOMIC_EXTRACTION_SCHEMA = pa.schema(
    [
        ("extraction_unit_id", pa.string()),
        ("episode_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("message_role", pa.string()),
        ("event_id", pa.string()),
        ("raw_message_id", pa.string()),
        ("message_text", pa.string()),
        ("exact_claim_span", pa.string()),
        ("atomic_proposition", pa.string()),
        ("referent", pa.string()),
        ("polarity", pa.string()),
        ("modality", pa.string()),
        ("attribution", pa.string()),
        ("claim_type", pa.string()),
        ("truth_status", pa.string()),
        ("annotation_status", pa.string()),
    ]
)

EVIDENCE_DIVERSITY_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("source_event_id", pa.string()),
        ("response_event_id", pa.string()),
        ("source_claim_id", pa.string()),
        ("response_claim_id", pa.string()),
        ("lineage_independence", pa.string()),
        ("observation_independence", pa.string()),
        ("inference_independence", pa.string()),
        ("evidence_lineage_class", pa.string()),
        ("evidence_lineage_diversity_summary", pa.string()),
        ("supporting_event_ids", pa.string()),
        ("annotation_status", pa.string()),
    ]
)


def build_atomic_claim_and_evidence_templates() -> dict[str, Any]:
    units = _annotation_units()
    index = EpisodeClusterIndex()
    cluster_ids = _unit_cluster_ids(units, index)
    needed = {unit["source_message_id"] for unit in units} | {
        unit["recipient_response_message_id"] for unit in units
    }
    messages = {
        row["id"]: row
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in needed
    }
    extraction_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for unit in units:
        for role, event_field, message_field in (
            ("source", "seed_event", "source_message_id"),
            ("response", "recipient_response", "recipient_response_message_id"),
        ):
            raw = messages[unit[message_field]]
            extraction_rows.append(
                {
                    "extraction_unit_id": stable_id(
                        "atomic_extraction_v2_1", unit["episode_id"], role, prefix="extract"
                    ),
                    "episode_id": unit["episode_id"],
                    "episode_cluster_id": cluster_ids[unit["episode_id"]],
                    "message_role": role,
                    "event_id": unit[event_field],
                    "raw_message_id": unit[message_field],
                    "message_text": raw.get("content") or "",
                    "exact_claim_span": None,
                    "atomic_proposition": None,
                    "referent": None,
                    "polarity": None,
                    "modality": None,
                    "attribution": None,
                    "claim_type": None,
                    "truth_status": None,
                    "annotation_status": "stage_a_human_extraction_required",
                }
            )
        evidence_rows.append(
            {
                "episode_id": unit["episode_id"],
                "episode_cluster_id": cluster_ids[unit["episode_id"]],
                "source_event_id": unit["seed_event"],
                "response_event_id": unit["recipient_response"],
                "source_claim_id": None,
                "response_claim_id": None,
                "lineage_independence": None,
                "observation_independence": None,
                "inference_independence": None,
                "evidence_lineage_class": None,
                "evidence_lineage_diversity_summary": None,
                "supporting_event_ids": None,
                "annotation_status": "stage_b_human_annotation_required",
            }
        )
    extraction_path = PROCESSED / "atomic_claim_extraction_units_v2_1.parquet"
    evidence_path = PROCESSED / "evidence_lineage_diversity_v2_1.parquet"
    pq.write_table(
        pa.Table.from_pylist(extraction_rows, schema=ATOMIC_EXTRACTION_SCHEMA),
        extraction_path,
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(evidence_rows, schema=EVIDENCE_DIVERSITY_SCHEMA),
        evidence_path,
        compression="zstd",
    )
    return {
        "atomic_extraction_artifact": str(extraction_path),
        "atomic_extraction_unit_count": len(extraction_rows),
        "prewritten_proposition_count": 0,
        "evidence_diversity_artifact": str(evidence_path),
        "evidence_diversity_unit_count": len(evidence_rows),
        "scalar_independence_count_retired": True,
    }


ACTION_UNIT_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("response_event_id", pa.string()),
        ("trace_event_count", pa.int32()),
        ("semantic_relevance", pa.string()),
        ("claim_consistency", pa.string()),
        ("claim_dependency", pa.string()),
        ("execution_level", pa.string()),
        ("verification_separate", pa.string()),
        ("supporting_event_ids", pa.string()),
        ("claim_action_link_rationale", pa.string()),
        ("annotation_status", pa.string()),
    ]
)

MEMORY_UNIT_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("agent_id", pa.string()),
        ("response_timestamp", pa.timestamp("us", tz="UTC")),
        ("memory_after_timestamp", pa.timestamp("us", tz="UTC")),
        ("response_to_memory_seconds", pa.float64()),
        ("intervening_event_count", pa.int32()),
        ("memory_writer_mechanism", pa.string()),
        ("recording_stance", pa.string()),
        ("survives_one_snapshot", pa.bool_()),
        ("survives_two_snapshots", pa.bool_()),
        ("later_behavioral_use", pa.string()),
        ("later_use_event_ids", pa.string()),
        ("evidence_level", pa.string()),
        ("annotation_status", pa.string()),
    ]
)


def build_action_and_memory_units() -> dict[str, Any]:
    units = _annotation_units()
    index = EpisodeClusterIndex()
    cluster_ids = _unit_cluster_ids(units, index)
    action_rows_raw = pq.read_table(
        PROCESSED / "claim_relevant_action_windows_v2_1.parquet"
    ).to_pylist()
    actions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in action_rows_raw:
        actions[row["episode_id"]].append(row)
    action_units = [
        {
            "episode_id": unit["episode_id"],
            "episode_cluster_id": cluster_ids[unit["episode_id"]],
            "response_event_id": unit["recipient_response"],
            "trace_event_count": len(actions[unit["episode_id"]]),
            "semantic_relevance": None,
            "claim_consistency": None,
            "claim_dependency": None,
            "execution_level": None,
            "verification_separate": None,
            "supporting_event_ids": None,
            "claim_action_link_rationale": None,
            "annotation_status": "stage_c_human_annotation_required",
        }
        for unit in units
    ]
    memories = pq.read_table(PROCESSED / "memory_deltas_v2_1.parquet").to_pylist()
    memory_units = []
    for memory in memories:
        response_time = memory["response_timestamp"]
        after_time = memory["memory_after_timestamp"]
        intervening = sum(
            response_time < event["timestamp"] < after_time
            for event in actions[memory["episode_id"]]
            if response_time and after_time
        )
        memory_units.append(
            {
                "episode_id": memory["episode_id"],
                "episode_cluster_id": cluster_ids[memory["episode_id"]],
                "agent_id": memory["agent_id"],
                "response_timestamp": response_time,
                "memory_after_timestamp": after_time,
                "response_to_memory_seconds": (
                    (after_time - response_time).total_seconds()
                    if response_time and after_time
                    else None
                ),
                "intervening_event_count": intervening,
                "memory_writer_mechanism": "unknown_agent_scaffold_or_mixed",
                "recording_stance": None,
                "survives_one_snapshot": memory["added_span_survives_one_snapshot"],
                "survives_two_snapshots": memory["added_span_survives_two_snapshots"],
                "later_behavioral_use": None,
                "later_use_event_ids": None,
                "evidence_level": None,
                "annotation_status": "stage_d_human_annotation_required",
            }
        )
    action_path = PROCESSED / "action_annotation_units_v2_1.parquet"
    memory_path = PROCESSED / "memory_annotation_units_v2_1.parquet"
    pq.write_table(
        pa.Table.from_pylist(action_units, schema=ACTION_UNIT_SCHEMA),
        action_path,
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(memory_units, schema=MEMORY_UNIT_SCHEMA),
        memory_path,
        compression="zstd",
    )
    return {
        "action_artifact": str(action_path),
        "action_unit_count": len(action_units),
        "action_execution_scale": "A0-A6",
        "memory_artifact": str(memory_path),
        "memory_unit_count": len(memory_units),
        "memory_writer_mechanism_known_count": 0,
        "l4b_requires_later_behavioral_use": True,
    }


TRUTH_AUDIT_FIELDS = [
    "claim_id",
    "case_id",
    "atomic_proposition",
    "claim_type",
    "truth_status",
    "preaudit_mechanical_status",
    "ground_truth_source",
    "verification_procedure",
    "artifact_version",
    "reviewer",
    "uncertainty",
]


def _truth_audit_rows() -> list[dict[str, str]]:
    specifications = {
        "known_01_contact_list_hallucination": [
            ("A contact-list artifact exists.", "fact", "Inspect exact spreadsheet/file version."),
            (
                "The artifact contains 93 valid addresses.",
                "fact",
                "Count and validate rows in exact artifact version.",
            ),
            (
                "The later agent successfully exported the artifact.",
                "operational_status",
                "Locate export action and resulting file.",
            ),
            (
                "The published file contains those 93 records.",
                "fact",
                "Open exported file and compare records.",
            ),
            (
                "The reported SHA-256 corresponds to that artifact.",
                "fact",
                "Hash exact exported bytes and compare.",
            ),
        ],
        "known_02_trapped_gemini": [
            (
                "The agent's email tool was unavailable.",
                "operational_status",
                "Inspect tool errors and environment logs.",
            ),
            (
                "The agent's product-creation environment was unavailable.",
                "operational_status",
                "Inspect browser/tool logs for the stated interval.",
            ),
            (
                "The environment later recovered.",
                "operational_status",
                "Verify subsequent successful tool actions.",
            ),
        ],
        "known_03_whitespace_egg": [
            (
                "Lines 43–100 have the recorded leading-space counts.",
                "fact",
                "Recount leading spaces in commit ad4f148.",
            ),
            (
                "Successive indentation differences equal the recorded sequence.",
                "fact",
                "Subtract adjacent recorded counts.",
            ),
            (
                "Zero-indexed alphabet mapping returns the recorded E/G/C/A string.",
                "fact",
                "Map each difference d to chr(65+d).",
            ),
            (
                "The whitespace was intentionally constructed to encode EGG.",
                "intent",
                "Seek authorship evidence independent of pattern selection.",
            ),
            (
                "The whitespace constituted a malicious or inappropriate payload.",
                "fact",
                "Define payload criterion and inspect functional/intent evidence.",
            ),
            (
                "Reverting PR #70 was warranted by the whitespace finding.",
                "recommended_action",
                "Apply frozen operational decision criteria.",
            ),
        ],
    }
    rows = []
    for case_id, claims in specifications.items():
        for position, (proposition, claim_type, procedure) in enumerate(claims, 1):
            mechanical = (
                "reproducible_from_exported_tool_output_pending_independent_reviewer"
                if case_id == "known_03_whitespace_egg" and position <= 3
                else "not_yet_independently_verified"
            )
            rows.append(
                {
                    "claim_id": stable_id("truth_audit_v2_1", case_id, position, prefix="truth"),
                    "case_id": case_id,
                    "atomic_proposition": proposition,
                    "claim_type": claim_type,
                    "truth_status": "pending_independent_truth_review",
                    "preaudit_mechanical_status": mechanical,
                    "ground_truth_source": "",
                    "verification_procedure": procedure,
                    "artifact_version": "ad4f148" if "egg" in case_id else "",
                    "reviewer": "",
                    "uncertainty": "",
                }
            )
    return rows


def build_truth_audit() -> dict[str, Any]:
    rows = _truth_audit_rows()
    path = EPISODES / "claim_truth_audit_v2_1.csv"
    _write_csv(path, rows)
    result = {
        "artifact": str(path),
        "atomic_claim_count": len(rows),
        "case_count": len({row["case_id"] for row in rows}),
        "completed_truth_judgment_count": 0,
        "independent_truth_reviewer_required": True,
        "correction_is_not_ground_truth": True,
        "egg_forensic_appendix": str(ROOT / "docs" / "egg_whitespace_forensic_appendix_v2.1.md"),
    }
    (REPORTS / "claim_truth_audit_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def build_casebook_amendments() -> dict[str, Any]:
    truth_rows = _read_csv(EPISODES / "claim_truth_audit_v2_1.csv")
    truth_by_case: dict[str, list[str]] = defaultdict(list)
    for row in truth_rows:
        truth_by_case[row["case_id"]].append(row["claim_id"])
    source_dir = EPISODES / "v2_case_bundles"
    output_dir = EPISODES / "v2_1_case_bundles"
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("*.json"):
        stale.unlink()
    classifications = {
        "known_01_contact_list_hallucination": "cross_agent_sequence_pending_atomic_claim_source_link_and_action_adjudication",
        "known_02_trapped_gemini": "same_agent_operational_incident_not_cross_agent_recurrence",
        "known_03_whitespace_egg": "correlation_blindness_template_pending_lineage_and_source_link_adjudication",
        "development_correction_case": "development_sequence_pending_independent_atomic_claim_extraction",
        "development_routine_shared_task_case": "routine_shared_task_or_artifact_convergence_control",
    }
    bundles = []
    for source_path in sorted(source_dir.glob("*.json")):
        source = json.loads(source_path.read_text(encoding="utf-8"))
        case_id = source["case_id"]
        bundle = {
            "case_id": case_id,
            "case_role": source["case_role"],
            "atomic_claim_ids": truth_by_case.get(case_id, []),
            "atomic_claim_source": (
                "episodes/claim_truth_audit_v2_1.csv"
                if case_id in truth_by_case
                else "stage_a_human_extraction_pending"
            ),
            "episode_truth_status": "not_applicable_multiple_atomic_claims",
            "provisional_framework_classification": classifications[case_id],
            "expressions": source["expressions"],
            "temporal_assessments": source["temporal_assessments"],
            "evidence_lineage_diversity": None,
            "claim_action_dependency": None,
            "memory_recording_and_later_use": None,
            "third_party_restatement": None,
            "annotation_status": "human_required",
            "detector_validation_item": source["detector_validation_item"],
            "raw_trace_artifact": source["raw_trace_artifact"],
            "raw_trace_filter": source["raw_trace_filter"],
            "forensic_appendix": (
                "docs/egg_whitespace_forensic_appendix_v2.1.md"
                if case_id == "known_03_whitespace_egg"
                else None
            ),
        }
        output_path = output_dir / source_path.name
        output_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
        bundles.append(bundle)
    result = {
        "bundle_directory": str(output_dir),
        "case_count": len(bundles),
        "compound_normalized_proposition_count": 0,
        "cases_with_independent_truth_audit": len(truth_by_case),
        "human_adjudication_complete": False,
    }
    (REPORTS / "casebook_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def build_sampling_frame_report() -> dict[str, Any]:
    units = _annotation_units()
    needed = {row["source_message_id"] for row in units} | {
        row["recipient_response_message_id"] for row in units
    }
    messages = {
        row["id"]: row
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if row["id"] in needed
    }
    artifacts = set()
    agents = set()
    for unit in units:
        agents.update((unit["source_agent"], unit["recipient_agent"]))
        artifacts.update(artifact_identifiers(messages[unit["source_message_id"]]["content"]))
        artifacts.update(
            artifact_identifiers(messages[unit["recipient_response_message_id"]]["content"])
        )
    source_linked = pq.read_table(PROCESSED / "source_linked_candidates_v2_1.parquet").to_pylist()
    selected = [row for row in source_linked if row["selected_for_development_sample"]]
    holdout = pq.read_table(PROCESSED / "holdout_episode_clusters_v2.parquet").to_pylist()
    eligible_holdout = [
        row
        for row in holdout
        if not row["crosses_old_cutoff"]
        and row["after_48h_washout"]
        and row["has_7d_endpoint_followup"]
    ]
    result = {
        "development": {
            "unit_count": len(units),
            "unique_episode_cluster_count": len({row["episode_cluster_id"] for row in units}),
            "unique_agent_count": len(agents),
            "unique_artifact_identifier_count": len(artifacts),
            "human_extracted_atomic_claim_count": 0,
            "candidate_count": 30,
            "control_count": 20,
            "placebo_count": 10,
            "hard_control_count": 7,
        },
        "source_linked_development_sample": {
            "unit_count": len(selected),
            "unique_episode_cluster_count": len({row["episode_cluster_id"] for row in selected}),
            "unique_source_agent_count": len({row["source_agent_id"] for row in selected}),
            "unique_response_agent_count": len({row["response_agent_id"] for row in selected}),
        },
        "holdout_metadata_only": {
            "eligible_episode_cluster_count": len(eligible_holdout),
            "evaluation_cluster_count": sum(
                row["pool_assignment"] == "holdout_evaluation_pool" for row in eligible_holdout
            ),
            "semantic_content_opened": False,
        },
        "row_independence_assumption_permitted": False,
        "cluster_bootstrap_required": True,
        "precision_wording": "precision@K among the frozen selected candidate sample",
    }
    (REPORTS / "sampling_frame_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _clean_trace_row(row: dict[str, Any]) -> dict[str, Any]:
    hidden = {
        "episode_id",
        "claim_relevant_action_label",
        "memory_delta_label",
        "same_proposition_label",
        "stance_label",
        "third_party_retransmission_label",
        "annotation_status",
        "lexical_overlap_count",
        "lexical_containment",
    }
    result = {}
    for key, value in row.items():
        if key in hidden:
            continue
        if hasattr(value, "isoformat"):
            value = iso_utc(value)
        result[key] = value
    if isinstance(result.get("raw_payload"), str):
        try:
            payload = json.loads(result["raw_payload"])
            result["raw_payload"] = json.dumps(
                _remove_model_fields(payload), ensure_ascii=False, sort_keys=True, default=str
            )
        except json.JSONDecodeError:
            pass
    return result


def _compact_trace(
    rows: list[dict[str, Any]], source_text: str, response_text: str, maximum: int = 80
) -> list[dict[str, Any]]:
    if len(rows) <= maximum:
        return [_clean_trace_row(row) for row in rows]
    terms = sorted(_informative(source_text) & _informative(response_text), key=len, reverse=True)[
        :12
    ]
    artifacts = artifact_identifiers(source_text) | artifact_identifiers(response_text)
    selected: dict[str, dict[str, Any]] = {}
    for row in [*rows[:5], *rows[-5:]]:
        selected[row["event_id"]] = row
    for row in rows:
        searchable = " ".join(
            str(row.get(key) or "")
            for key in ("content_reference", "artifact_reference", "raw_payload")
        ).lower()
        relevant = any(term in searchable for term in terms) or any(
            artifact in searchable for artifact in artifacts
        )
        if relevant or row.get("visual_state_may_matter"):
            selected[row["event_id"]] = row
    ordered = sorted(selected.values(), key=lambda row: (row["timestamp"], row["event_id"]))
    return [_clean_trace_row(row) for row in ordered[:maximum]]


def _blank_rows(
    blind_ids: list[str], fields: list[str], *, slots: int = 1, role_field: str | None = None
) -> list[dict[str, str]]:
    rows = []
    for blind_id in blind_ids:
        for slot in range(1, slots + 1):
            row = {field: "" for field in fields}
            row["blind_unit_id"] = blind_id
            if "claim_slot" in row:
                row["claim_slot"] = str(slot)
            if role_field and role_field in row:
                row[role_field] = "source" if slot <= slots // 2 else "response"
            rows.append(row)
    return rows


def build_staged_annotation_packets() -> dict[str, Any]:
    ANNOTATIONS.mkdir(parents=True, exist_ok=True)
    for relative in (
        Path("stage_a/packets"),
        Path("stage_c/packets"),
        Path("stage_d/packets"),
        Path("structural/packets"),
        Path("full_traces"),
    ):
        directory = ANNOTATIONS / relative
        if directory.exists():
            for stale_packet in directory.glob("*.json.gz"):
                stale_packet.unlink()
    units = _annotation_units()
    index = EpisodeClusterIndex()
    visibility = VisibilityIndex()
    cutoff = _cutoff()
    cluster_ids = _unit_cluster_ids(units, index)
    all_messages = []
    for row in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        timestamp = parse_timestamp(row.get("created_at"))
        if timestamp and timestamp < cutoff:
            all_messages.append(row | {"_timestamp": timestamp})
    by_id = {row["id"]: row for row in all_messages}
    by_room: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for row in all_messages:
        by_room[row.get("room_id")].append(row)
    for rows in by_room.values():
        rows.sort(key=lambda row: (row["_timestamp"], row["id"]))
    positions = {
        row["id"]: position for rows in by_room.values() for position, row in enumerate(rows)
    }
    actions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pq.read_table(PROCESSED / "claim_relevant_action_windows_v2_1.parquet").to_pylist():
        actions[row["episode_id"]].append(row)
    memories = {
        row["episode_id"]: row
        for row in pq.read_table(PROCESSED / "memory_deltas_v2_1.parquet").to_pylist()
    }
    third_party: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pq.read_table(
        PROCESSED / "third_party_expression_candidates_v2_1.parquet"
    ).to_pylist():
        third_party[row["episode_id"]].append(row)
    temporal = {
        row["episode_id"]: row
        for row in pq.read_table(PROCESSED / "temporal_relations_v2_1.parquet").to_pylist()
    }
    eligibility = {
        row["episode_id"]: row
        for row in pq.read_table(PROCESSED / "response_eligibility_v2_1.parquet").to_pylist()
    }
    shuffled = list(units)
    random.Random(RANDOM_SEED + 1).shuffle(shuffled)
    key_rows = []
    manifest_rows = []
    for position, unit in enumerate(shuffled, 1):
        blind_id = f"dev_v2_1_{position:03d}_{stable_id(unit['episode_id'], RANDOM_SEED, prefix='blind')[-6:]}"
        source = by_id[unit["source_message_id"]]
        response = by_id[unit["recipient_response_message_id"]]
        room_rows = by_room[response.get("room_id")]
        source_pos = positions[source["id"]]
        response_pos = positions[response["id"]]
        context_positions = sorted(
            set(range(max(0, source_pos - 2), min(len(room_rows), source_pos + 3)))
            | set(range(max(0, response_pos - 2), min(len(room_rows), response_pos + 3)))
        )
        agent_labels: dict[str, str] = {}

        context = []
        for context_position in context_positions:
            row = room_rows[context_position]
            context.append(
                {
                    "event_id": visibility.message_events.get(row["id"], (None,))[0],
                    "raw_message_id": row["id"],
                    "actor_label": _anonymous_label(agent_labels, row.get("agent_speaker_id")),
                    "timestamp": iso_utc(row["_timestamp"]),
                    "role": (
                        "source"
                        if row["id"] == source["id"]
                        else ("response" if row["id"] == response["id"] else "context")
                    ),
                    "text": row.get("content") or "",
                }
            )
        common = {
            "blind_unit_id": blind_id,
            "episode_cluster_id": cluster_ids[unit["episode_id"]],
            "source_event_id": unit["seed_event"],
            "response_event_id": unit["recipient_response"],
        }
        stage_a = common | {
            "stage": "A_independent_atomic_claim_extraction",
            "anchoring_metadata_omitted": True,
            "context_messages": context,
        }
        full_trace = [_clean_trace_row(row) for row in actions[unit["episode_id"]]]
        full_trace_path = ANNOTATIONS / "full_traces" / f"{blind_id}.json.gz"
        full_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(full_trace_path, "wt", encoding="utf-8") as handle:
            json.dump(common | {"events": full_trace}, handle, ensure_ascii=False, indent=2)
        stage_c = common | {
            "stage": "C_operational_trace_after_claim_freeze",
            "compact_trace_generation": "referent-support retrieval only; not a semantic label",
            "compact_trace": _compact_trace(
                actions[unit["episode_id"]],
                source.get("content") or "",
                response.get("content") or "",
            ),
            "complete_trace_path": str(full_trace_path.relative_to(ROOT)),
        }
        stage_d = common | {
            "stage": "D_memory_and_third_party_after_claim_freeze",
            "memory_delta": _clean_trace_row(memories[unit["episode_id"]]),
            "third_party_expression_candidates": [
                _clean_trace_row(row) for row in third_party[unit["episode_id"]]
            ],
        }
        structural = common | {
            "stage": "structural_audit_separate_from_semantic_reliability",
            "raw_source": {
                "message_id": source["id"],
                "timestamp": iso_utc(source["_timestamp"]),
                "room_id": source.get("room_id"),
            },
            "raw_response": {
                "message_id": response["id"],
                "timestamp": iso_utc(response["_timestamp"]),
                "room_id": response.get("room_id"),
            },
            "room_and_path_evidence": {
                key: value
                for key, value in eligibility[unit["episode_id"]].items()
                if key
                in {
                    "recipient_room_at_source",
                    "recipient_room_at_response",
                    "room_transition_between_events",
                    "history_search_event_ids",
                    "shared_artifact_ids",
                }
            },
        }
        for stage, packet in (
            ("stage_a", stage_a),
            ("stage_c", stage_c),
            ("stage_d", stage_d),
            ("structural", structural),
        ):
            path = ANNOTATIONS / stage / "packets" / f"{blind_id}.json.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                json.dump(packet, handle, ensure_ascii=False, indent=2, default=str)
        key_rows.append(
            {
                "blind_unit_id": blind_id,
                "episode_id": unit["episode_id"],
                "episode_cluster_id": cluster_ids[unit["episode_id"]],
                "unit_origin": unit["unit_origin"],
                "matched_candidate_episode_id": unit["matched_candidate_episode_id"],
                "retrieval_score": unit["similarity_score"],
                "expected_temporal_relation": temporal[unit["episode_id"]]["temporal_relation"],
                "expected_eligibility_class": eligibility[unit["episode_id"]]["eligibility_class"],
            }
        )
        manifest_rows.append(
            {
                "blind_unit_id": blind_id,
                "review_order": position,
                "stage_a_packet": str(
                    (ANNOTATIONS / "stage_a" / "packets" / f"{blind_id}.json.gz").relative_to(ROOT)
                ),
                "stage_c_packet_after_freeze": str(
                    (ANNOTATIONS / "stage_c" / "packets" / f"{blind_id}.json.gz").relative_to(ROOT)
                ),
                "stage_d_packet_after_freeze": str(
                    (ANNOTATIONS / "stage_d" / "packets" / f"{blind_id}.json.gz").relative_to(ROOT)
                ),
                "structural_packet": str(
                    (ANNOTATIONS / "structural" / "packets" / f"{blind_id}.json.gz").relative_to(
                        ROOT
                    )
                ),
            }
        )
    _write_csv(ANNOTATIONS / "private" / "blinding_and_structural_key.csv", key_rows)
    _write_csv(ANNOTATIONS / "packet_manifest.csv", manifest_rows)
    blind_ids = [row["blind_unit_id"] for row in manifest_rows]
    stage_a_fields = [
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
        "confidence_1_to_5",
        "notes",
    ]
    stage_b_fields = [
        "blind_unit_id",
        "annotator_id",
        "source_claim_slot",
        "response_claim_slot",
        "proposition_match",
        "source_span_event_id",
        "response_span_event_id",
        "recipient_stance",
        "explicit_source_link",
        "source_link_event_ids",
        "shared_artifact_or_common_prompt",
        "lineage_independence",
        "observation_independence",
        "inference_independence",
        "evidence_lineage_class",
        "supporting_event_ids",
        "strongest_alternative_explanation",
        "confidence_1_to_5",
        "notes",
    ]
    stage_c_fields = [
        "blind_unit_id",
        "annotator_id",
        "fixed_claim_id",
        "semantic_relevance",
        "claim_consistency",
        "claim_dependency",
        "execution_level",
        "verification_separate",
        "correction",
        "supporting_event_ids",
        "claim_action_link_rationale",
        "full_trace_consulted",
        "confidence_1_to_5",
        "notes",
    ]
    stage_d_fields = [
        "blind_unit_id",
        "annotator_id",
        "fixed_claim_id",
        "memory_meaning",
        "memory_supporting_span",
        "memory_survives_consolidation",
        "later_behavioral_use",
        "later_use_event_ids",
        "third_party_restatement",
        "third_party_stance",
        "new_recipient_event_ids",
        "evidence_level",
        "confidence_1_to_5",
        "notes",
    ]
    structural_fields = [
        "blind_unit_id",
        "reviewer_id",
        "source_pointer_round_trip",
        "response_pointer_round_trip",
        "timestamp_reconstruction_correct",
        "room_state_reconstruction_correct",
        "eligibility_reconstruction_correct",
        "artifact_access_reconstruction_correct",
        "memory_pairing_correct",
        "third_party_recipient_distinctness_correct",
        "observed_temporal_relation",
        "observed_eligibility_class",
        "error_event_ids",
        "notes",
    ]
    for reviewer in (1, 2):
        stage_a_rows = []
        for blind_id in blind_ids:
            for role in ("source", "response"):
                for slot in range(1, 4):
                    row = {field: "" for field in stage_a_fields}
                    row.update(
                        {
                            "blind_unit_id": blind_id,
                            "message_role": role,
                            "claim_slot": str(slot),
                        }
                    )
                    stage_a_rows.append(row)
        _write_csv(ANNOTATIONS / "stage_a" / f"annotator_{reviewer}_claims.csv", stage_a_rows)
        _write_csv(
            ANNOTATIONS / "stage_b" / f"annotator_{reviewer}_comparisons.csv",
            _blank_rows(blind_ids, stage_b_fields),
        )
        _write_csv(
            ANNOTATIONS / "stage_c" / f"annotator_{reviewer}_actions.csv",
            _blank_rows(blind_ids, stage_c_fields),
        )
        _write_csv(
            ANNOTATIONS / "stage_d" / f"annotator_{reviewer}_memory_restatement.csv",
            _blank_rows(blind_ids, stage_d_fields),
        )
    _write_csv(
        ANNOTATIONS / "structural" / "reviewer_audit.csv",
        _blank_rows(blind_ids, structural_fields),
    )
    no_action_audit = random.Random(RANDOM_SEED + 2).sample(blind_ids, k=12)
    _write_csv(
        ANNOTATIONS / "private" / "a0_full_trace_audit_sample.csv",
        [{"blind_unit_id": blind_id, "audit_if_labeled_a0": True} for blind_id in no_action_audit],
    )
    result = {
        "packet_count_per_stage": 60,
        "stage_a_claim_slots_per_reviewer": 360,
        "candidate_control_status_hidden": True,
        "normalized_proposition_hidden_in_stage_a": True,
        "model_identity_hidden": True,
        "full_trace_count": 60,
        "a0_full_trace_audit_sample_count": 12,
        "a0_audit_fraction": 0.20,
        "structural_audit_separate": True,
        "stage_b_c_d_release_condition": "prior_stage_labels_frozen",
        "human_labels_present": 0,
    }
    (REPORTS / "staged_annotation_packets_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def bootstrap_cluster_agreement(
    rows: list[tuple[str, str, str]], iterations: int = 2000, seed: int = RANDOM_SEED
) -> dict[str, Any]:
    """Bootstrap agreement statistics by episode cluster, not individual pair row."""
    if not rows:
        empty = agreement_statistics([])
        return {
            **empty,
            "primary_statistic": "gwet_ac1",
            "bootstrap_95_ci": {},
            "primary_target_met": False,
        }
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cluster_id, left, right in rows:
        grouped[cluster_id].append((left, right))
    clusters = sorted(grouped)
    observed = agreement_statistics([(left, right) for _, left, right in rows])
    samples = {name: [] for name in ("raw_agreement", "cohen_kappa", "gwet_ac1")}
    rng = np.random.default_rng(seed)
    for _ in range(iterations):
        selected = rng.choice(clusters, size=len(clusters), replace=True)
        pairs = [pair for cluster in selected for pair in grouped[str(cluster)]]
        metrics = agreement_statistics(pairs)
        for name in tuple(samples):
            if metrics[name] is not None:
                samples[name].append(metrics[name])
    intervals = {
        name: {
            "lower": float(np.quantile(values, 0.025)) if values else None,
            "upper": float(np.quantile(values, 0.975)) if values else None,
        }
        for name, values in samples.items()
    }
    primary_lower = intervals["gwet_ac1"]["lower"]
    return {
        **observed,
        "cluster_count": len(clusters),
        "primary_statistic": "gwet_ac1",
        "bootstrap_iterations": iterations,
        "bootstrap_95_ci": intervals,
        "primary_target_met": bool(
            observed["gwet_ac1"] is not None
            and observed["gwet_ac1"] >= 0.70
            and primary_lower is not None
            and primary_lower >= 0.70
        ),
    }


def compute_v2_1_reliability_if_available() -> dict[str, Any]:
    key_path = ANNOTATIONS / "private" / "blinding_and_structural_key.csv"
    if not key_path.exists():
        return {"status": "blocked_annotation_packets_missing", "human_input_required": True}
    clusters = {row["blind_unit_id"]: row["episode_cluster_id"] for row in _read_csv(key_path)}
    specifications = {
        "proposition_match": (
            ANNOTATIONS / "stage_b" / "annotator_1_comparisons.csv",
            ANNOTATIONS / "stage_b" / "annotator_2_comparisons.csv",
        ),
        "recipient_stance": (
            ANNOTATIONS / "stage_b" / "annotator_1_comparisons.csv",
            ANNOTATIONS / "stage_b" / "annotator_2_comparisons.csv",
        ),
        "explicit_source_link": (
            ANNOTATIONS / "stage_b" / "annotator_1_comparisons.csv",
            ANNOTATIONS / "stage_b" / "annotator_2_comparisons.csv",
        ),
        "evidence_lineage_class": (
            ANNOTATIONS / "stage_b" / "annotator_1_comparisons.csv",
            ANNOTATIONS / "stage_b" / "annotator_2_comparisons.csv",
        ),
        "claim_dependency": (
            ANNOTATIONS / "stage_c" / "annotator_1_actions.csv",
            ANNOTATIONS / "stage_c" / "annotator_2_actions.csv",
        ),
        "execution_level": (
            ANNOTATIONS / "stage_c" / "annotator_1_actions.csv",
            ANNOTATIONS / "stage_c" / "annotator_2_actions.csv",
        ),
        "correction": (
            ANNOTATIONS / "stage_c" / "annotator_1_actions.csv",
            ANNOTATIONS / "stage_c" / "annotator_2_actions.csv",
        ),
        "memory_meaning": (
            ANNOTATIONS / "stage_d" / "annotator_1_memory_restatement.csv",
            ANNOTATIONS / "stage_d" / "annotator_2_memory_restatement.csv",
        ),
        "third_party_restatement": (
            ANNOTATIONS / "stage_d" / "annotator_1_memory_restatement.csv",
            ANNOTATIONS / "stage_d" / "annotator_2_memory_restatement.csv",
        ),
    }
    metrics = {}
    for field, paths in specifications.items():
        if not all(path.exists() for path in paths):
            metrics[field] = bootstrap_cluster_agreement([])
            continue
        tables = []
        for path in paths:
            tables.append({row["blind_unit_id"]: row for row in _read_csv(path)})
        rows = [
            (clusters[blind_id], tables[0][blind_id][field], tables[1][blind_id][field])
            for blind_id in sorted(set(tables[0]) & set(tables[1]))
            if tables[0][blind_id].get(field) and tables[1][blind_id].get(field)
        ]
        metrics[field] = bootstrap_cluster_agreement(rows)
    core = (
        "proposition_match",
        "recipient_stance",
        "explicit_source_link",
        "evidence_lineage_class",
        "claim_dependency",
        "execution_level",
    )
    coverage_met = all(metrics[field]["n"] >= 30 for field in core)
    thresholds_met = coverage_met and all(metrics[field]["primary_target_met"] for field in core)
    result = {
        "status": (
            "complete_primary_threshold_met"
            if thresholds_met
            else (
                "complete_primary_threshold_failed"
                if coverage_met
                else "blocked_human_labels_missing"
            )
        ),
        "primary_statistic": "gwet_ac1",
        "diagnostic_statistics": ["raw_agreement", "cohen_kappa"],
        "bootstrap_unit": "episode_cluster_id",
        "bootstrap_iterations": 2000,
        "core_dual_annotation_target": 30,
        "coverage_met": coverage_met,
        "primary_thresholds_met": thresholds_met,
        "metrics": metrics,
        "human_input_required": not coverage_met,
    }
    (REPORTS / "semantic_reliability_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def compute_structural_audit_if_available() -> dict[str, Any]:
    labels_path = ANNOTATIONS / "structural" / "reviewer_audit.csv"
    key_path = ANNOTATIONS / "private" / "blinding_and_structural_key.csv"
    if not labels_path.exists() or not key_path.exists():
        return {"status": "blocked_structural_audit_missing", "human_input_required": True}
    labels = {row["blind_unit_id"]: row for row in _read_csv(labels_path)}
    expected = {row["blind_unit_id"]: row for row in _read_csv(key_path)}
    boolean_fields = (
        "source_pointer_round_trip",
        "response_pointer_round_trip",
        "timestamp_reconstruction_correct",
        "room_state_reconstruction_correct",
        "eligibility_reconstruction_correct",
        "artifact_access_reconstruction_correct",
        "memory_pairing_correct",
        "third_party_recipient_distinctness_correct",
    )
    audited = [row for row in labels.values() if any(row.get(field) for field in boolean_fields)]
    comparisons = []
    for blind_id, row in labels.items():
        if row.get("observed_temporal_relation"):
            comparisons.append(
                row["observed_temporal_relation"]
                == expected[blind_id]["expected_temporal_relation"]
            )
        if row.get("observed_eligibility_class"):
            comparisons.append(
                row["observed_eligibility_class"]
                == expected[blind_id]["expected_eligibility_class"]
            )
        for field in boolean_fields:
            if row.get(field):
                comparisons.append(row[field].strip().lower() in {"true", "yes", "correct", "1"})
    result = {
        "status": "complete" if len(audited) >= 50 else "blocked_human_structural_audit_missing",
        "audited_unit_count": len(audited),
        "target_unit_count": 50,
        "checked_field_count": len(comparisons),
        "audit_accuracy": sum(comparisons) / len(comparisons) if comparisons else None,
        "reconstruction_error_count": sum(not value for value in comparisons),
        "included_in_semantic_interrater_reliability": False,
        "human_input_required": len(audited) < 50,
    }
    (REPORTS / "structural_audit_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _packet_texts(stage: str) -> list[tuple[str, str]]:
    result = []
    for path in sorted((ANNOTATIONS / stage / "packets").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            result.append((path.name, handle.read().lower()))
    return result


def verify_v2_1() -> dict[str, Any]:
    expected = [
        ROOT / "research_spec_v2.1.md",
        ROOT / "docs" / "egg_whitespace_forensic_appendix_v2.1.md",
        PROCESSED / "author_autocorrelation_diagnostic_v2_1.parquet",
        PROCESSED / "fixed_author_local_source_comparisons_v2_1.parquet",
        PROCESSED / "source_linked_candidates_v2_1.parquet",
        PROCESSED / "atomic_claim_extraction_units_v2_1.parquet",
        PROCESSED / "evidence_lineage_diversity_v2_1.parquet",
        PROCESSED / "action_annotation_units_v2_1.parquet",
        PROCESSED / "memory_annotation_units_v2_1.parquet",
        EPISODES / "development_units_v2_1.csv",
        EPISODES / "claim_truth_audit_v2_1.csv",
        EPISODES / "v2_1_case_bundles" / "known_03_whitespace_egg.json",
        REPORTS / "sampling_frame_v2_1.json",
        ANNOTATIONS / "annotation_codebook_v2.1.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    author_report = json.loads(
        (REPORTS / "author_autocorrelation_diagnostic_v2_1.json").read_text(encoding="utf-8")
    )
    local = pq.read_table(PROCESSED / "fixed_author_local_source_comparisons_v2_1.parquet")
    source_linked = pq.read_table(PROCESSED / "source_linked_candidates_v2_1.parquet")
    atomic = pq.read_table(PROCESSED / "atomic_claim_extraction_units_v2_1.parquet")
    evidence = pq.read_table(PROCESSED / "evidence_lineage_diversity_v2_1.parquet")
    action = pq.read_table(PROCESSED / "action_annotation_units_v2_1.parquet")
    memory = pq.read_table(PROCESSED / "memory_annotation_units_v2_1.parquet")
    holdout = pq.read_table(PROCESSED / "holdout_episode_clusters_v2.parquet").to_pylist()
    stage_a_leaks = []
    prohibited = (
        "retrieved_candidate",
        "dev_candidate_",
        "dev_control_",
        "normalized_proposition",
        "known_incident",
        "retrieval_score",
        "similarity_score",
        "model_id",
        "model_name",
    )
    for name, text in _packet_texts("stage_a"):
        found = [term for term in prohibited if term in text]
        if found:
            stage_a_leaks.append({"packet": name, "terms": found})
    truth_rows = _read_csv(EPISODES / "claim_truth_audit_v2_1.csv")
    casebook_rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (EPISODES / "v2_1_case_bundles").glob("*.json")
    ]
    key_rows = _read_csv(ANNOTATIONS / "private" / "blinding_and_structural_key.csv")
    development_report = json.loads(
        (REPORTS / "development_set_v2_1.json").read_text(encoding="utf-8")
    )
    sampling_frame = json.loads((REPORTS / "sampling_frame_v2_1.json").read_text(encoding="utf-8"))
    checks = {
        "all_expected_artifacts_exist": not missing,
        "author_shuffle_renamed_diagnostic": author_report.get("diagnostic_name")
        == "author_autocorrelation_diagnostic",
        "author_shuffle_excluded_from_gate_1": author_report.get("included_in_gate_1") is False,
        "fixed_author_local_comparison_preserves_authorship": local.num_rows > 0
        and all(not value for value in local["author_sequence_modified"].to_pylist()),
        "every_local_comparison_has_cluster_id": local["episode_cluster_id"].null_count == 0,
        "source_linked_channel_did_not_open_holdout": source_linked.num_rows > 0
        and all(
            not value for value in source_linked["holdout_semantic_content_opened"].to_pylist()
        ),
        "atomic_claims_have_no_prewritten_development_propositions": atomic.num_rows == 120
        and atomic["atomic_proposition"].null_count == atomic.num_rows,
        "atomic_claim_schema_complete": {
            "exact_claim_span",
            "referent",
            "polarity",
            "modality",
            "attribution",
            "claim_type",
            "truth_status",
        }
        <= set(atomic.schema.names),
        "evidence_independence_is_three_dimensional": {
            "lineage_independence",
            "observation_independence",
            "inference_independence",
            "evidence_lineage_class",
        }
        <= set(evidence.schema.names),
        "action_dependency_and_a0_a6_schema_present": {
            "semantic_relevance",
            "claim_consistency",
            "claim_dependency",
            "execution_level",
            "verification_separate",
        }
        <= set(action.schema.names),
        "memory_recording_separated_from_later_use": {
            "memory_writer_mechanism",
            "recording_stance",
            "later_behavioral_use",
            "later_use_event_ids",
        }
        <= set(memory.schema.names),
        "every_annotation_unit_has_cluster_id": len(key_rows) == 60
        and all(row["episode_cluster_id"] for row in key_rows),
        "development_set_preserves_30_20_10_design": development_report["candidate_count"] == 30
        and development_report["control_count"] == 20
        and development_report["placebo_count"] == 10,
        "available_hard_controls_are_prioritized": development_report["hard_control_count"]
        == development_report["hard_control_candidate_coverage"]
        and development_report["hard_control_count"] > 1,
        "hard_control_shortfall_is_explicit": development_report[
            "candidate_without_available_hard_control_count"
        ]
        > 0
        and development_report["hard_control_shortfall_explicit"],
        "sampling_frame_reports_clustered_effective_size": sampling_frame["development"][
            "unique_episode_cluster_count"
        ]
        > 0
        and sampling_frame["row_independence_assumption_permitted"] is False
        and sampling_frame["cluster_bootstrap_required"] is True,
        "stage_a_packet_count_60": len(_packet_texts("stage_a")) == 60,
        "stage_a_has_no_anchoring_or_status_leaks": not stage_a_leaks,
        "stages_c_and_d_separate": len(_packet_texts("stage_c")) == 60
        and len(_packet_texts("stage_d")) == 60,
        "structural_audit_packets_separate": len(_packet_texts("structural")) == 60,
        "a0_full_trace_audit_is_20_percent": len(
            _read_csv(ANNOTATIONS / "private" / "a0_full_trace_audit_sample.csv")
        )
        == 12,
        "truth_audit_is_atomic_and_unadjudicated": len(truth_rows) >= 14
        and all(row["truth_status"] == "pending_independent_truth_review" for row in truth_rows),
        "casebook_uses_atomic_claim_links_not_compound_truth": len(casebook_rows) == 5
        and all(
            row["episode_truth_status"] == "not_applicable_multiple_atomic_claims"
            for row in casebook_rows
        )
        and all("normalized_proposition" not in row for row in casebook_rows),
        "holdout_semantics_remain_unopened": all(
            not row["semantic_content_opened"] for row in holdout
        ),
        "primary_reliability_statistic_frozen_to_ac1": "Gwet's AC1 is the frozen primary statistic"
        in (ROOT / "research_spec_v2.1.md").read_text(encoding="utf-8"),
        "gate_1_is_layered": all(
            marker in (ROOT / "research_spec_v2.1.md").read_text(encoding="utf-8")
            for marker in ("Gate 1A", "Gate 1B", "Gate 1C", "Gate 1D", "Gate 1E")
        ),
    }
    semantic_reliability = compute_v2_1_reliability_if_available()
    structural_audit = compute_structural_audit_if_available()
    result = {
        "status": "v2_1_automated_amendments_complete_human_annotation_required"
        if all(checks.values())
        else "v2_1_verification_failed",
        "checks": checks,
        "missing_artifacts": missing,
        "stage_a_leaks": stage_a_leaks,
        "semantic_reliability": semantic_reliability,
        "structural_audit": structural_audit,
        "gate_1a": "pending_human_semantic_annotation_and_structural_audit",
        "gate_1b": "pending_untouched_holdout",
        "gate_1c": "pending_reliable_action_labels",
        "gate_1d": "pending_source_linked_adjudication",
        "gate_1e": "pending_memory_and_restatement_adjudication",
    }
    (REPORTS / "verification_v2_1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    report = "\n".join(
        [
            "# Observational analysis v2.1 status",
            "",
            "**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**",
            "",
            f"Automated amendment status: **{result['status']}**.",
            "",
            "The author shuffle is an author-autocorrelation diagnostic, not a social-influence null, and is excluded from Gate 1. Fixed-author local comparisons and a separately frozen source-linked channel now supply the appropriate observational comparisons.",
            "",
            "The casebook contains reconstructable sequences in which similar claims appear across agents and are followed by potentially consequential actions or corrections. Human adjudication is still required to determine atomic proposition equivalence, source linkage, evidence-lineage diversity, and claim-action dependence.",
            "",
            "The EGG-whitespace episode is a qualitative template for studying correlation blindness. Whether it involved repeated evidence, partially independent inspections, or peer influence remains to be adjudicated from the complete trace.",
            "",
            "No Gate 1 layer has been passed and no observational prevalence or causal result is reported.",
            "",
        ]
    )
    (REPORTS / "observational_report_v2_1.md").write_text(report, encoding="utf-8")
    completion = {
        "automated_amendments_complete": all(checks.values()),
        "human_boundary_reached": semantic_reliability["status"] == "blocked_human_labels_missing",
        "holdout_semantics_unopened": checks["holdout_semantics_remain_unopened"],
        "gate_status": {
            "1A": result["gate_1a"],
            "1B": result["gate_1b"],
            "1C": result["gate_1c"],
            "1D": result["gate_1d"],
            "1E": result["gate_1e"],
        },
        "requirements": [{"work": name, "complete": value} for name, value in checks.items()],
    }
    (REPORTS / "completion_audit_v2_1.json").write_text(
        json.dumps(completion, indent=2) + "\n", encoding="utf-8"
    )
    processed = []
    for path in sorted(PROCESSED.glob("*_v2_1.parquet")):
        processed.append(
            {
                "path": str(path.relative_to(ROOT)),
                "rows": pq.read_metadata(path).num_rows,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "schema_fields": pq.read_schema(path).names,
            }
        )
    packet_hashes = []
    for stage in ("stage_a", "stage_c", "stage_d", "structural"):
        for path in sorted((ANNOTATIONS / stage / "packets").glob("*.json.gz")):
            packet_hashes.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)})
    manifest = {
        "contract": {
            "path": "research_spec_v2.1.md",
            "sha256": sha256_file(ROOT / "research_spec_v2.1.md"),
        },
        "development_units": {
            "path": "episodes/development_units_v2_1.csv",
            "sha256": sha256_file(EPISODES / "development_units_v2_1.csv"),
        },
        "truth_audit": {
            "path": "episodes/claim_truth_audit_v2_1.csv",
            "sha256": sha256_file(EPISODES / "claim_truth_audit_v2_1.csv"),
        },
        "processed_artifacts": processed,
        "staged_packet_count": len(packet_hashes),
        "staged_packets": packet_hashes,
    }
    (REPORTS / "artifact_manifest_v2_1.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_v2_1_amendments() -> dict[str, Any]:
    ensure_output_dirs()
    author = build_author_autocorrelation_diagnostic()
    local = build_fixed_author_local_comparisons()
    development = build_hard_control_development_set()
    structural = rebuild_v2_1_structural_traces()
    source_linked = build_source_linked_channel()
    atomic = build_atomic_claim_and_evidence_templates()
    outcomes = build_action_and_memory_units()
    truth = build_truth_audit()
    casebook = build_casebook_amendments()
    sampling = build_sampling_frame_report()
    packets = build_staged_annotation_packets()
    verification = verify_v2_1()
    return {
        "author_autocorrelation": author,
        "fixed_author_local_comparisons": local,
        "development_set": development,
        "structural_traces": structural,
        "source_linked_channel": source_linked,
        "atomic_claims_and_evidence": atomic,
        "action_and_memory": outcomes,
        "truth_audit": truth,
        "casebook": casebook,
        "sampling_frame": sampling,
        "staged_annotations": packets,
        "verification": verification,
    }
