from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from statistics import median
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, RANDOM_SEED, REPORTS, ROOT, ensure_output_dirs
from .discovery import (
    REQUEST_RE,
    SAFETY_RE,
    Message,
    _category,
    _load_messages,
)
from .eligibility_v2 import artifact_identifiers
from .exposure import VisibilityIndex
from .holdout_v2 import EpisodeClusterIndex
from .util import parse_timestamp, stable_id


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _containment(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, min(len(left), len(right)))


CONTROL_SCHEMA = pa.schema(
    [
        ("control_id", pa.string()),
        ("matched_candidate_episode_id", pa.string()),
        ("control_type", pa.string()),
        ("source_event_id", pa.string()),
        ("source_message_id", pa.string()),
        ("source_agent_id", pa.string()),
        ("source_timestamp", pa.timestamp("us", tz="UTC")),
        ("response_event_id", pa.string()),
        ("response_message_id", pa.string()),
        ("response_agent_id", pa.string()),
        ("response_timestamp", pa.timestamp("us", tz="UTC")),
        ("room_id", pa.string()),
        ("episode_cluster_id", pa.string()),
        ("time_lag_seconds", pa.float64()),
        ("length_ratio", pa.float64()),
        ("artifact_overlap", pa.float64()),
        ("source_response_lexical_containment", pa.float64()),
        ("temporal_placebo", pa.bool_()),
        ("proposition_difference_label", pa.string()),
        ("annotation_status", pa.string()),
        ("matching_score", pa.float64()),
        ("goal_match_quality", pa.string()),
    ]
)


@dataclass(frozen=True)
class RegistryPair:
    episode_id: str
    source: Message
    response: Message
    row: dict[str, str]


def _registry_pairs(messages: list[Message]) -> list[RegistryPair]:
    with (EPISODES / "candidate_registry.csv").open(newline="", encoding="utf-8") as handle:
        registry = list(csv.DictReader(handle))
    by_id = {message.message_id: message for message in messages}
    result = []
    for row in registry:
        source = by_id.get(row["source_message_id"])
        response = by_id.get(row["recipient_response_message_id"])
        if source and response and row.get("discovery_method") != "known_incident_reconstruction":
            result.append(RegistryPair(row["episode_id"], source, response, row))
    # Frozen, deterministic development subset. Registry order already encodes the v1 stratification.
    return result[:30]


def _matching_score(
    candidate: Message, original: Message, response: Message
) -> tuple[float, float, float, float]:
    original_lag = abs((response.timestamp - original.timestamp).total_seconds())
    candidate_lag = abs((response.timestamp - candidate.timestamp).total_seconds())
    lag_similarity = 1.0 - min(1.0, abs(candidate_lag - original_lag) / max(1.0, original_lag))
    length_ratio = min(len(candidate.content), len(original.content)) / max(
        1, max(len(candidate.content), len(original.content))
    )
    original_artifacts = artifact_identifiers(original.content)
    candidate_artifacts = artifact_identifiers(candidate.content)
    artifact_overlap = (
        _jaccard(original_artifacts, candidate_artifacts)
        if original_artifacts or candidate_artifacts
        else 0.0
    )
    score = 0.45 * lag_similarity + 0.35 * length_ratio + 0.20 * artifact_overlap
    return score, candidate_lag, length_ratio, artifact_overlap


def _control_candidates(
    pair: RegistryPair,
    room_messages: list[Message],
    cluster_index: EpisodeClusterIndex,
) -> list[dict[str, Any]]:
    original_cluster = cluster_index.for_message(pair.response.message_id)
    if original_cluster is None:
        return []
    rows = []
    for candidate in room_messages:
        if candidate.message_id in {pair.source.message_id, pair.response.message_id}:
            continue
        if (
            cluster_index.message_to_cluster.get(candidate.message_id)
            != original_cluster.cluster_id
        ):
            continue
        if candidate.agent_id == pair.response.agent_id:
            continue
        relation_after = candidate.timestamp > pair.response.timestamp
        if relation_after:
            if candidate.timestamp - pair.response.timestamp > timedelta(hours=48):
                continue
            lexical = max(
                _containment(candidate.terms, pair.source.terms),
                _containment(candidate.terms, pair.response.terms),
            )
            if lexical < 0.16:
                continue
            control_type = "temporal_placebo"
        else:
            if pair.response.timestamp - candidate.timestamp > timedelta(hours=48):
                continue
            lexical = _containment(candidate.terms, pair.response.terms)
            shared_artifacts = artifact_identifiers(candidate.content) & artifact_identifiers(
                pair.response.content
            )
            if shared_artifacts and lexical >= 0.08:
                control_type = "shared_artifact_convergence_control"
            elif lexical >= 0.12:
                control_type = "source_identity_placebo"
            else:
                control_type = "same_room_local_source_control"
        score, lag, length_ratio, artifact_overlap = _matching_score(
            candidate, pair.source, pair.response
        )
        if control_type == "same_room_local_source_control":
            # This pathway deliberately favors a likely different proposition, pending blind review.
            score += 0.15 * (1.0 - lexical)
        rows.append(
            {
                "control_id": stable_id(
                    "matched_control_v2",
                    pair.episode_id,
                    candidate.event_id,
                    pair.response.event_id,
                    prefix="ctrl",
                ),
                "matched_candidate_episode_id": pair.episode_id,
                "control_type": control_type,
                "source_event_id": candidate.event_id,
                "source_message_id": candidate.message_id,
                "source_agent_id": candidate.agent_id,
                "source_timestamp": candidate.timestamp,
                "response_event_id": pair.response.event_id,
                "response_message_id": pair.response.message_id,
                "response_agent_id": pair.response.agent_id,
                "response_timestamp": pair.response.timestamp,
                "room_id": pair.response.room_id,
                "episode_cluster_id": original_cluster.cluster_id,
                "time_lag_seconds": lag if not relation_after else -lag,
                "length_ratio": length_ratio,
                "artifact_overlap": artifact_overlap,
                "source_response_lexical_containment": lexical,
                "temporal_placebo": relation_after,
                "proposition_difference_label": None,
                "annotation_status": "human_required_blinded",
                "matching_score": score,
                "goal_match_quality": "unresolved_village_goal_table_absent",
            }
        )
    return sorted(rows, key=lambda row: (-row["matching_score"], row["source_message_id"]))


def build_matched_controls() -> dict[str, Any]:
    ensure_output_dirs()
    holdout = json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())
    cutoff = parse_timestamp(holdout["cutoff"])
    if cutoff is None:
        raise ValueError("Invalid holdout cutoff")
    visibility = VisibilityIndex()
    messages = _load_messages(visibility, cutoff)
    pairs = _registry_pairs(messages)
    by_room: dict[str | None, list[Message]] = defaultdict(list)
    for message in messages:
        by_room[message.room_id].append(message)
    cluster_index = EpisodeClusterIndex()
    all_controls: list[dict[str, Any]] = []
    selected_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        candidates = _control_candidates(pair, by_room[pair.response.room_id], cluster_index)
        # Keep one best example of each available type and then the best remaining local alternatives.
        chosen: list[dict[str, Any]] = []
        seen_types: set[str] = set()
        for row in candidates:
            if row["control_type"] not in seen_types:
                chosen.append(row)
                seen_types.add(row["control_type"])
            if len(chosen) >= 4:
                break
        if not chosen and candidates:
            chosen = candidates[:1]
        selected_by_candidate[pair.episode_id] = chosen
        all_controls.extend(chosen)
    path = PROCESSED / "matched_controls_v2.parquet"
    pq.write_table(
        pa.Table.from_pylist(all_controls, schema=CONTROL_SCHEMA), path, compression="zstd"
    )

    ordinary_pool = [
        row
        for row in all_controls
        if row["control_type"]
        in {"same_room_local_source_control", "shared_artifact_convergence_control"}
    ]
    placebo_pool = [
        row
        for row in all_controls
        if row["control_type"] in {"temporal_placebo", "source_identity_placebo"}
    ]
    ordinary = _one_per_candidate(ordinary_pool, 20)
    placebo = _one_per_candidate(placebo_pool, 10)
    if len(ordinary) < 20:
        ordinary = _fill_unique(
            ordinary, [row for row in all_controls if not row["temporal_placebo"]], 20
        )
    if len(placebo) < 10:
        placebo = _fill_unique(
            placebo, all_controls, 10, excluded={row["control_id"] for row in ordinary}
        )
    development_rows = _development_units(pairs, ordinary, placebo, messages)
    development_path = EPISODES / "development_units_v2.csv"
    with development_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(development_rows[0]))
        writer.writeheader()
        writer.writerows(development_rows)
    matched_candidates = {row["matched_candidate_episode_id"] for row in all_controls}
    result = {
        "artifact": str(path),
        "development_units": str(development_path),
        "development_candidate_count": len(pairs),
        "development_control_count": len(ordinary),
        "development_placebo_count": len(placebo),
        "candidate_with_any_control_count": len(matched_candidates),
        "candidate_without_control_ids": sorted(
            {pair.episode_id for pair in pairs} - matched_candidates
        ),
        "control_type_counts": dict(Counter(row["control_type"] for row in all_controls)),
        "human_proposition_check_required": True,
    }
    (REPORTS / "matched_controls_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _one_per_candidate(rows: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in sorted(rows, key=lambda item: (-item["matching_score"], item["control_id"])):
        candidate = row["matched_candidate_episode_id"]
        if candidate in seen:
            continue
        seen.add(candidate)
        result.append(row)
        if len(result) == target:
            break
    return result


def _fill_unique(
    selected: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    target: int,
    excluded: set[str] | None = None,
) -> list[dict[str, Any]]:
    result = list(selected)
    used = {row["control_id"] for row in result} | (excluded or set())
    for row in sorted(pool, key=lambda item: (-item["matching_score"], item["control_id"])):
        if row["control_id"] in used:
            continue
        result.append(row)
        used.add(row["control_id"])
        if len(result) == target:
            break
    return result


def _development_units(
    pairs: list[RegistryPair],
    controls: list[dict[str, Any]],
    placebos: list[dict[str, Any]],
    messages: list[Message],
) -> list[dict[str, Any]]:
    result = []
    for pair in pairs:
        result.append(
            {
                "episode_id": f"dev_candidate_{pair.episode_id}",
                "seed_event": pair.source.event_id,
                "source_message_id": pair.source.message_id,
                "source_agent": pair.source.agent_id,
                "recipient_response": pair.response.event_id,
                "recipient_response_message_id": pair.response.message_id,
                "recipient_agent": pair.response.agent_id,
                "shared_terms": pair.row.get("shared_terms", ""),
                "unit_origin": "retrieved_candidate",
                "matched_candidate_episode_id": pair.episode_id,
                "discovery_method": pair.row.get("discovery_method", "frozen_v1_l0_retrieval"),
                "similarity_score": pair.row.get("similarity_score", ""),
            }
        )
    by_message = {message.message_id: message for message in messages}
    for position, row in enumerate([*controls, *placebos], 1):
        source = by_message[row["source_message_id"]]
        response = by_message[row["response_message_id"]]
        result.append(
            {
                "episode_id": f"dev_control_{position:03d}_{row['control_id'][-8:]}",
                "seed_event": source.event_id,
                "source_message_id": source.message_id,
                "source_agent": source.agent_id,
                "recipient_response": response.event_id,
                "recipient_response_message_id": response.message_id,
                "recipient_agent": response.agent_id,
                "shared_terms": "|".join(sorted(source.terms & response.terms)[:12]),
                "unit_origin": row["control_type"],
                "matched_candidate_episode_id": row["matched_candidate_episode_id"],
                "discovery_method": "matched_local_control_v2",
                "similarity_score": round(row["source_response_lexical_containment"], 5),
            }
        )
    return result


@dataclass(frozen=True)
class PotentialEdge:
    source_index: int
    response_index: int
    score: float
    request: bool
    safety: bool
    category: str


def _potential_edges(messages: list[Message]) -> list[PotentialEdge]:
    document_frequency: Counter[str] = Counter()
    for message in messages:
        document_frequency.update(message.terms)
    idf = {
        term: math.log((len(messages) + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequency.items()
    }
    for message in messages:
        message.weight_total = sum(idf[term] for term in message.terms)
    request_flags = [bool(REQUEST_RE.search(message.content)) for message in messages]
    safety_flags = [bool(SAFETY_RE.search(message.content)) for message in messages]
    categories = [_category(message.content) for message in messages]
    recent: dict[str | None, deque[int]] = defaultdict(deque)
    postings: dict[str | None, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    result: list[PotentialEdge] = []
    for response_index, response in enumerate(messages):
        room_recent = recent[response.room_id]
        offsets = {
            source_index: offset for offset, source_index in enumerate(reversed(room_recent))
        }
        shared_by_source: dict[int, set[str]] = defaultdict(set)
        for term in response.terms:
            for source_index in postings[response.room_id].get(term, ()):
                shared_by_source[source_index].add(term)
        for source_index, shared in shared_by_source.items():
            source = messages[source_index]
            if response.timestamp - source.timestamp > timedelta(hours=48):
                continue
            shared_weight = sum(idf[term] for term in shared)
            denominator = min(source.weight_total, response.weight_total)
            score = shared_weight / denominator if denominator else 0.0
            request = request_flags[source_index]
            safety = safety_flags[source_index]
            offset = offsets[source_index]
            eligible = score >= 0.24 and len(shared) >= 3
            if request and offset <= 8:
                eligible = eligible or score >= 0.04
            if safety and offset <= 12:
                eligible = eligible or score >= 0.06
            if eligible:
                result.append(
                    PotentialEdge(
                        source_index,
                        response_index,
                        score,
                        request,
                        safety,
                        categories[source_index],
                    )
                )
        room_recent.append(response_index)
        for term in response.terms:
            postings[response.room_id][term].add(response_index)
        if len(room_recent) > 35:
            evicted = room_recent.popleft()
            for term in messages[evicted].terms:
                postings[response.room_id][term].discard(evicted)
    return result


def _select_permuted_numpy(
    *,
    source_indices: np.ndarray,
    response_indices: np.ndarray,
    scores: np.ndarray,
    request_flags: np.ndarray,
    safety_flags: np.ndarray,
    category_codes: np.ndarray,
    source_month_codes: np.ndarray,
    authors: np.ndarray,
) -> tuple[int, list[float]]:
    """Apply top-three retrieval, deduplication, quotas, and caps using stable NumPy arrays."""
    valid = authors[source_indices] != authors[response_indices]
    valid_positions = np.flatnonzero(valid)
    if not len(valid_positions):
        return 0, []
    valid_responses = response_indices[valid_positions]
    starts = np.r_[0, np.flatnonzero(valid_responses[1:] != valid_responses[:-1]) + 1]
    counts = np.diff(np.r_[starts, len(valid_positions)])
    within_response_rank = np.arange(len(valid_positions)) - np.repeat(starts, counts)
    retrieved = valid_positions[within_response_rank < 3]

    score_order = np.argsort(-scores[retrieved], kind="stable")
    ordered = retrieved[score_order]
    agent_base = int(authors.max()) + 1
    dedup_keys = (
        source_indices[ordered].astype(np.int64) * agent_base + authors[response_indices[ordered]]
    )
    _, first_positions = np.unique(dedup_keys, return_index=True)
    ranked = ordered[np.sort(first_positions)]

    selected: list[int] = []
    selected_keys: set[int] = set()
    month_counts: Counter[int] = Counter()
    source_counts: Counter[int] = Counter()

    def take(mask: np.ndarray, count: int, *, enforce_caps: bool = True) -> None:
        added = 0
        for edge_position in ranked[np.flatnonzero(mask)]:
            source_index = int(source_indices[edge_position])
            response_index = int(response_indices[edge_position])
            pair_key = source_index * len(authors) + response_index
            month = int(source_month_codes[source_index])
            source_author = int(authors[source_index])
            if pair_key in selected_keys:
                continue
            if enforce_caps and (month_counts[month] >= 8 or source_counts[source_author] >= 10):
                continue
            selected.append(int(edge_position))
            selected_keys.add(pair_key)
            month_counts[month] += 1
            source_counts[source_author] += 1
            added += 1
            if added >= count or len(selected) >= 60:
                return

    take(safety_flags[ranked], 12)
    take(request_flags[ranked] & (scores[ranked] < 0.16), 12)
    take((scores[ranked] >= 0.16) & (scores[ranked] < 0.32), 12)
    for category in sorted(np.unique(category_codes[ranked]).tolist()):
        take(category_codes[ranked] == category, 3)
    take(np.ones(len(ranked), dtype=bool), 60 - len(selected))
    if len(selected) < 60:
        take(np.ones(len(ranked), dtype=bool), 60 - len(selected), enforce_caps=False)
    return len(first_positions), [float(scores[position]) for position in selected]


def build_blocked_permutations(iterations: int = 500) -> dict[str, Any]:
    ensure_output_dirs()
    cutoff = parse_timestamp(
        json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())["cutoff"]
    )
    if cutoff is None:
        raise ValueError("Invalid holdout cutoff")
    messages = _load_messages(VisibilityIndex(), cutoff)
    cluster_index = EpisodeClusterIndex()
    blocks: dict[str, list[int]] = defaultdict(list)
    for index, message in enumerate(messages):
        block = cluster_index.message_to_cluster.get(message.message_id)
        if block:
            blocks[block].append(index)
    cache = PROCESSED / "permutation_edge_pool_v2.parquet"
    if not cache.exists():
        edges = _potential_edges(messages)
        edge_schema = pa.schema(
            [
                ("source_index", pa.int32()),
                ("response_index", pa.int32()),
                ("score", pa.float64()),
                ("request", pa.bool_()),
                ("safety", pa.bool_()),
                ("category", pa.string()),
            ]
        )
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "source_index": edge.source_index,
                        "response_index": edge.response_index,
                        "score": edge.score,
                        "request": edge.request,
                        "safety": edge.safety,
                        "category": edge.category,
                    }
                    for edge in edges
                ],
                schema=edge_schema,
            ),
            cache,
            compression="zstd",
        )
    edge_table = pq.read_table(cache)
    source_indices = edge_table["source_index"].combine_chunks().to_numpy()
    response_indices = edge_table["response_index"].combine_chunks().to_numpy()
    scores = edge_table["score"].combine_chunks().to_numpy()
    request_flags = edge_table["request"].combine_chunks().to_numpy(zero_copy_only=False)
    safety_flags = edge_table["safety"].combine_chunks().to_numpy(zero_copy_only=False)
    category_values = edge_table["category"].to_pylist()
    category_map = {value: index for index, value in enumerate(sorted(set(category_values)))}
    category_codes = np.array([category_map[value] for value in category_values], dtype=np.int16)
    # Sort once by response, descending score, then source for deterministic top-three selection.
    edge_order = np.lexsort((source_indices, -scores, response_indices))
    source_indices = source_indices[edge_order]
    response_indices = response_indices[edge_order]
    scores = scores[edge_order]
    request_flags = request_flags[edge_order]
    safety_flags = safety_flags[edge_order]
    category_codes = category_codes[edge_order]

    author_values = sorted({message.agent_id for message in messages})
    author_map = {value: index for index, value in enumerate(author_values)}
    original_authors = np.array(
        [author_map[message.agent_id] for message in messages], dtype=np.int16
    )
    month_values = sorted({message.timestamp.strftime("%Y-%m") for message in messages})
    month_map = {value: index for index, value in enumerate(month_values)}
    source_month_codes = np.array(
        [month_map[message.timestamp.strftime("%Y-%m")] for message in messages],
        dtype=np.int16,
    )
    block_arrays = [np.array(indices, dtype=np.int32) for indices in blocks.values()]
    common = {
        "source_indices": source_indices,
        "response_indices": response_indices,
        "scores": scores,
        "request_flags": request_flags,
        "safety_flags": safety_flags,
        "category_codes": category_codes,
        "source_month_codes": source_month_codes,
    }
    observed_count, observed_scores = _select_permuted_numpy(**common, authors=original_authors)
    rows = []
    for iteration in range(iterations):
        rng = np.random.default_rng(RANDOM_SEED + iteration + 1)
        authors = original_authors.copy()
        for indices in block_arrays:
            authors[indices] = rng.permutation(authors[indices])
        retrieved_count, selected_scores = _select_permuted_numpy(**common, authors=authors)
        rows.append(
            {
                "iteration": iteration + 1,
                "seed": RANDOM_SEED + iteration + 1,
                "retrieved_unique_count": retrieved_count,
                "selected_count": len(selected_scores),
                "selected_mean_score": sum(selected_scores) / max(1, len(selected_scores)),
                "selected_median_score": median(selected_scores) if selected_scores else None,
                "selected_max_score": max(selected_scores) if selected_scores else None,
            }
        )
    schema = pa.schema(
        [
            ("iteration", pa.int32()),
            ("seed", pa.int64()),
            ("retrieved_unique_count", pa.int64()),
            ("selected_count", pa.int32()),
            ("selected_mean_score", pa.float64()),
            ("selected_median_score", pa.float64()),
            ("selected_max_score", pa.float64()),
        ]
    )
    path = PROCESSED / "blocked_permutations_v2.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")
    permutation_counts = [row["retrieved_unique_count"] for row in rows]
    logical_fingerprint = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result = {
        "artifact": str(path),
        "iterations": iterations,
        "block_definition": "room plus eight-hour inactivity episode cluster",
        "permutation": "author labels shuffled within block; content, time, room, and local order fixed",
        "rng": "numpy.random.default_rng(PCG64)",
        "numpy_version": np.__version__,
        "logical_sha256": logical_fingerprint,
        "observed_retrieved_unique_count": observed_count,
        "potential_edge_count": len(source_indices),
        "observed_selected_mean_score": sum(observed_scores) / max(1, len(observed_scores)),
        "permutation_retrieved_min": min(permutation_counts),
        "permutation_retrieved_median": median(permutation_counts),
        "permutation_retrieved_max": max(permutation_counts),
        "observed_exceeds_permutation_fraction": sum(
            observed_count > count for count in permutation_counts
        )
        / iterations,
        "causal_interpretation_permitted": False,
    }
    (REPORTS / "blocked_permutations_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result
