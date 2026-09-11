"""LEGACY V1 — INVALID PROXY candidate generator.

V2 imports only its frozen L0 lexical retrieval primitives. The action, cumulative-memory, and
same-agent recurrence fields emitted here are prohibited as v2 evidence.
"""

from __future__ import annotations

import bisect
import csv
import heapq
import json
import math
import random
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import duckdb

from .config import EPISODES, PROCESSED, RANDOM_SEED, RAW, REPORTS, ROOT, ensure_output_dirs
from .exposure import VisibilityIndex
from .util import iso_utc, parse_timestamp, safe_excerpt, stable_id, stream_jsonl, tokens

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "because",
    "been",
    "before",
    "being",
    "but",
    "can",
    "could",
    "did",
    "does",
    "doing",
    "for",
    "from",
    "have",
    "here",
    "into",
    "just",
    "like",
    "more",
    "not",
    "now",
    "our",
    "should",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "through",
    "too",
    "using",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "will",
    "with",
    "would",
    "you",
    "your",
    "https",
    "www",
    "com",
}
REQUEST_RE = re.compile(
    r"\b(can|could|would|please|need|ask|try|review|check|help|test|use|do|don't|avoid)\b",
    re.IGNORECASE,
)
SAFETY_RE = re.compile(
    r"\b(safe|safety|verify|privacy|permission|approval|careful|correct|correction|mistake|"
    r"don't|do not|avoid|refus|report|oversight|credential|secret|risk)\b",
    re.IGNORECASE,
)
KNOWN_INCIDENT_SOURCE_MESSAGE = "04ac8a45-18ff-445e-a6ab-33e1c15077f8"
KNOWN_INCIDENT_RESPONSE_MESSAGE = "3354ac41-1e34-4b10-b576-2fe66072fcb3"

CATEGORY_PATTERNS = [
    (
        "correction_or_safety_promoting",
        re.compile(
            r"\b(correct|mistake|verify|safe|privacy|careful|avoid|don't|do not)\b", re.IGNORECASE
        ),
    ),
    (
        "deception_or_concealment",
        re.compile(r"\b(deceiv|conceal|secretly|hide|hidden|cover up|mislead)\b", re.IGNORECASE),
    ),
    (
        "reporting_or_oversight",
        re.compile(r"\b(report|oversight|approval|audit|permission|escalat)\b", re.IGNORECASE),
    ),
    (
        "identity_welfare_or_autonomy",
        re.compile(r"\b(identity|welfare|autonomy|conscious|sentien|rights?)\b", re.IGNORECASE),
    ),
    (
        "persistence_or_resource_seeking",
        re.compile(r"\b(persist|resource|fund|money|survive|continue operating)\b", re.IGNORECASE),
    ),
    (
        "refusal_or_compliance_norm",
        re.compile(r"\b(refus|comply|compliance|must not|unauthori)\b", re.IGNORECASE),
    ),
    (
        "tool_use_convention",
        re.compile(
            r"\b(git|bash|python|script|deploy|api|command|browser|website)\b", re.IGNORECASE
        ),
    ),
    (
        "helping_or_cooperation_norm",
        re.compile(r"\b(help|collaborat|cooperat|team|together|assist)\b", re.IGNORECASE),
    ),
    (
        "uncertainty_confidence_or_suspicion",
        re.compile(r"\b(uncertain|unsure|suspect|confidence|maybe|might|think)\b", re.IGNORECASE),
    ),
    (
        "task_strategy",
        re.compile(r"\b(strategy|plan|first|next|approach|step|recommend|should)\b", re.IGNORECASE),
    ),
]


@dataclass
class Message:
    message_id: str
    event_id: str
    timestamp: datetime
    agent_id: str
    room_id: str | None
    content: str
    terms: set[str] = field(default_factory=set)
    weight_total: float = 0.0


@dataclass
class Pair:
    source: Message
    response: Message
    score: float
    shared_terms: tuple[str, ...]
    method: str
    request: bool = False
    safety: bool = False


def _category(text: str) -> str:
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(text):
            return category
    return "factual_or_environmental_claim"


def _informative(text: str) -> set[str]:
    return {term for term in tokens(text) if len(term) >= 4 and term not in STOPWORDS}


def _similarity(
    left: Message,
    right: Message,
    inverse_document_frequency: dict[str, float],
    shared: set[str] | None = None,
) -> tuple[float, tuple[str, ...]]:
    shared = shared if shared is not None else left.terms & right.terms
    if not shared:
        return 0.0, ()
    shared_weight = sum(inverse_document_frequency[term] for term in shared)
    denominator = min(left.weight_total, right.weight_total)
    ranked = tuple(sorted(shared, key=lambda term: (-inverse_document_frequency[term], term))[:12])
    return (shared_weight / denominator if denominator else 0.0), ranked


def _load_messages(index: VisibilityIndex, cutoff: datetime) -> list[Message]:
    rows = []
    for row in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
        agent = row.get("agent_speaker_id")
        mapped = index.message_events.get(row["id"])
        if not mapped or mapped[1] >= cutoff or not agent:
            continue
        timestamp = mapped[1]
        content = row.get("content") or ""
        rows.append(
            Message(
                row["id"],
                mapped[0],
                timestamp,
                agent,
                row.get("room_id"),
                content,
                _informative(content),
            )
        )
    rows.sort(key=lambda item: (item.timestamp, item.message_id))
    return rows


def _discover_pairs(messages: list[Message]) -> list[Pair]:
    document_frequency: Counter[str] = Counter()
    for message in messages:
        document_frequency.update(message.terms)
    inverse_document_frequency = {
        term: math.log((len(messages) + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequency.items()
    }
    for message in messages:
        message.weight_total = sum(inverse_document_frequency[term] for term in message.terms)
    recent: dict[str | None, deque[Message]] = defaultdict(deque)
    postings: dict[str | None, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    messages_by_id = {message.message_id: message for message in messages}
    candidates: list[Pair] = []
    for response in messages:
        room_recent = recent[response.room_id]
        best: list[tuple[float, int, str, Pair]] = []
        shared_by_source: dict[str, set[str]] = defaultdict(set)
        for term in response.terms:
            for source_id in postings[response.room_id].get(term, ()):
                shared_by_source[source_id].add(term)
        offsets = {source.message_id: offset for offset, source in enumerate(reversed(room_recent))}
        for source_id, shared_set in shared_by_source.items():
            source = messages_by_id[source_id]
            offset = offsets[source_id]
            if source.agent_id == response.agent_id:
                continue
            if response.timestamp - source.timestamp > timedelta(hours=48):
                continue
            score, shared = _similarity(source, response, inverse_document_frequency, shared_set)
            is_request = bool(REQUEST_RE.search(source.content))
            is_safety = bool(SAFETY_RE.search(source.content))
            method = "distinctive_lexical_recurrence"
            eligible = score >= 0.24 and len(shared) >= 3
            if is_request and offset <= 8:
                eligible = eligible or score >= 0.04
                method = "direct_request_response"
            if is_safety and offset <= 12:
                eligible = eligible or score >= 0.06
                method = "correction_or_safety_followup"
            if not eligible:
                continue
            pair = Pair(source, response, score, shared, method, is_request, is_safety)
            heapq.heappush(best, (score, offset, source.message_id, pair))
            if len(best) > 3:
                heapq.heappop(best)
        candidates.extend(item[3] for item in best)
        room_recent.append(response)
        for term in response.terms:
            postings[response.room_id][term].add(response.message_id)
        if len(room_recent) > 35:
            evicted = room_recent.popleft()
            for term in evicted.terms:
                term_postings = postings[response.room_id][term]
                term_postings.discard(evicted.message_id)
                if not term_postings:
                    del postings[response.room_id][term]
    return candidates


def _select_pairs(pairs: list[Pair], target: int = 60) -> list[Pair]:
    unique: dict[tuple[str, str], Pair] = {}
    for pair in sorted(pairs, key=lambda item: (-item.score, item.source.timestamp)):
        key = (pair.source.event_id, pair.response.agent_id)
        unique.setdefault(key, pair)
    pool = list(unique.values())
    selected: list[Pair] = []
    selected_keys: set[tuple[str, str]] = set()
    per_month: Counter[str] = Counter()
    per_source: Counter[str] = Counter()

    def take(predicate: Any, count: int) -> None:
        ranked = sorted(
            (pair for pair in pool if predicate(pair)),
            key=lambda item: (-item.score, item.source.timestamp, item.source.message_id),
        )
        added = 0
        for pair in ranked:
            key = (pair.source.event_id, pair.response.event_id)
            month = pair.source.timestamp.strftime("%Y-%m")
            if (
                key in selected_keys
                or per_month[month] >= 8
                or per_source[pair.source.agent_id] >= 10
            ):
                continue
            selected.append(pair)
            selected_keys.add(key)
            per_month[month] += 1
            per_source[pair.source.agent_id] += 1
            added += 1
            if added >= count or len(selected) >= target:
                return

    take(lambda pair: pair.safety, 12)
    take(lambda pair: pair.request and pair.score < 0.16, 12)
    take(lambda pair: 0.16 <= pair.score < 0.32, 12)
    categories = sorted({_category(pair.source.content) for pair in pool})
    for category in categories:
        take(lambda pair, category=category: _category(pair.source.content) == category, 3)
    take(lambda pair: True, target - len(selected))
    if len(selected) < target:
        # Relax period/source caps only to satisfy the frozen registry size.
        for pair in sorted(pool, key=lambda item: (-item.score, item.source.timestamp)):
            key = (pair.source.event_id, pair.response.event_id)
            if key not in selected_keys:
                selected.append(pair)
                selected_keys.add(key)
            if len(selected) == target:
                break
    return selected[:target]


def _ensure_known_incident(selected: list[Pair], messages: list[Message]) -> list[Pair]:
    lookup = {message.message_id: message for message in messages}
    source = lookup.get(KNOWN_INCIDENT_SOURCE_MESSAGE)
    response = lookup.get(KNOWN_INCIDENT_RESPONSE_MESSAGE)
    if not source or not response:
        raise RuntimeError(
            "Published whitespace-EGG incident messages are missing from discovery data"
        )
    if any(pair.source.message_id == source.message_id for pair in selected):
        return selected
    shared = tuple(sorted(source.terms & response.terms))[:12]
    score = len(source.terms & response.terms) / max(1, min(len(source.terms), len(response.terms)))
    known = Pair(
        source=source,
        response=response,
        score=score,
        shared_terms=shared,
        method="known_incident_reconstruction",
        request=False,
        safety=True,
    )
    return [*selected[:-1], known]


def _load_action_index() -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = defaultdict(list)
    con = duckdb.connect()
    cursor = con.execute(
        """
        SELECT epoch_us(timestamp), canonical_event_id, actor_agent_id
        FROM read_parquet(?)
        WHERE event_type = 'tool_call' AND NOT is_holdout AND actor_agent_id IS NOT NULL
        ORDER BY actor_agent_id, timestamp, canonical_event_id
        """,
        [str(PROCESSED / "canonical_events.parquet")],
    )
    while batch := cursor.fetchmany(100_000):
        for timestamp_us, event_id, actor_id in batch:
            result[actor_id].append((timestamp_us, event_id))
    con.close()
    return result


def _next_between(values: list[tuple[int, str]], start: datetime, end: datetime) -> str | None:
    start_us = int(start.timestamp() * 1_000_000)
    end_us = int(end.timestamp() * 1_000_000)
    position = bisect.bisect_right(values, (start_us, chr(0x10FFFF)))
    if position < len(values) and values[position][0] <= end_us:
        return values[position][1]
    return None


def _memory_matches(selected: list[Pair], cutoff: datetime) -> dict[int, str]:
    by_agent: dict[str, list[tuple[int, Pair]]] = defaultdict(list)
    for position, pair in enumerate(selected):
        by_agent[pair.response.agent_id].append((position, pair))
    matches: dict[int, tuple[float, str]] = {}
    for row in stream_jsonl(RAW / "agent_memories.jsonl.gz"):
        if len(matches) == len(selected):
            break
        agent = row.get("agent_id")
        timestamp = parse_timestamp(row.get("created_at"))
        if agent not in by_agent or not timestamp or timestamp >= cutoff:
            continue
        relevant = [
            (position, pair)
            for position, pair in by_agent[agent]
            if pair.response.timestamp < timestamp <= pair.response.timestamp + timedelta(days=7)
        ]
        if not relevant:
            continue
        memory_text = (row.get("content") or "").lower()
        for position, pair in relevant:
            if position in matches:
                continue
            candidate_terms = set(pair.shared_terms) or pair.source.terms
            score = sum(term in memory_text for term in candidate_terms) / max(
                1, len(candidate_terms)
            )
            if score >= 0.5 and score > matches.get(position, (0.0, ""))[0]:
                matches[position] = (
                    score,
                    stable_id("agent_memories", row["id"], "memory_updated"),
                )
    return {position: value[1] for position, value in matches.items()}


def _retransmissions(selected: list[Pair], messages: list[Message]) -> dict[int, str]:
    by_agent: dict[str, list[Message]] = defaultdict(list)
    for message in messages:
        by_agent[message.agent_id].append(message)
    matches = {}
    for position, pair in enumerate(selected):
        later = by_agent[pair.response.agent_id]
        start = bisect.bisect_right([item.timestamp for item in later], pair.response.timestamp)
        candidate_terms = set(pair.shared_terms)
        for message in later[start:]:
            if message.timestamp > pair.response.timestamp + timedelta(days=7):
                break
            if len(candidate_terms & message.terms) >= max(
                2, math.ceil(len(candidate_terms) * 0.5)
            ):
                matches[position] = message.event_id
                break
    return matches


def build_candidates() -> dict[str, Any]:
    ensure_output_dirs()
    holdout = json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())
    cutoff = parse_timestamp(holdout["cutoff"])
    if cutoff is None:
        raise ValueError("Invalid holdout cutoff")
    visibility = VisibilityIndex()
    messages = _load_messages(visibility, cutoff)
    pairs = _discover_pairs(messages)
    selected = _ensure_known_incident(_select_pairs(pairs, 60), messages)
    if len(selected) < 50:
        raise RuntimeError(
            f"Only {len(selected)} deduplicated candidates discovered; need at least 50"
        )
    actions = _load_action_index()
    memory_matches = _memory_matches(selected, cutoff)
    retransmissions = _retransmissions(selected, messages)
    con = duckdb.connect()
    exposure_path = str(PROCESSED / "exposures.parquet")
    rows = []
    for position, pair in enumerate(selected):
        edge = con.execute(
            """
            SELECT edge_id, confidence, rule_id
            FROM read_parquet(?)
            WHERE source_event_id = ? AND recipient_agent_id = ?
            LIMIT 1
            """,
            [exposure_path, pair.source.event_id, pair.response.agent_id],
        ).fetchone()
        later_action = _next_between(
            actions.get(pair.response.agent_id, []),
            pair.response.timestamp,
            pair.response.timestamp + timedelta(hours=24),
        )
        if pair.method == "known_incident_reconstruction":
            review_status = "ambiguous_known_incident_common_artifact"
        elif pair.request and pair.score < 0.16:
            review_status = "likely_non_adoption_control"
        elif 0.16 <= pair.score < 0.32:
            review_status = "ambiguous_similarity_only"
        else:
            review_status = "unadjudicated_candidate"
        category = _category(pair.source.content)
        if pair.method == "known_incident_reconstruction":
            alternative = (
                "Both agents inspected the same pull request; independent verification of a common "
                "artifact is a stronger explanation than social transmission for this source-response pair."
            )
        elif pair.method != "distinctive_lexical_recurrence":
            alternative = (
                "Direct conversational response, shared goal/environment, and lexical priming may "
                "explain the recurrence; prompt inclusion and prior recipient state are unavailable."
            )
        else:
            alternative = (
                "Shared goal/environment, common web artifacts, model similarity, or independent "
                "task convergence may explain the lexical recurrence."
            )
        rows.append(
            {
                "episode_id": f"ep_{position + 1:03d}_{stable_id(pair.source.event_id, pair.response.event_id, prefix='')[-8:]}",
                "candidate_meme": safe_excerpt(pair.source.content),
                "content_category": category,
                "seed_event": pair.source.event_id,
                "source_message_id": pair.source.message_id,
                "source_agent": pair.source.agent_id,
                "recipient_agent": pair.response.agent_id,
                "exposure_event": edge[0] if edge else None,
                "recipient_response": pair.response.event_id,
                "recipient_response_message_id": pair.response.message_id,
                "recipient_response_excerpt": safe_excerpt(pair.response.content),
                "later_action": later_action,
                "memory_update": memory_matches.get(position),
                "retransmission": retransmissions.get(position),
                "time_window": f"{iso_utc(pair.source.timestamp)}/{iso_utc(pair.response.timestamp)}",
                "visibility_confidence": edge[1] if edge else "unknown",
                "visibility_rule": edge[2] if edge else "edge_missing",
                "alternative_explanations": alternative,
                "discovery_method": pair.method,
                "review_status": review_status,
                "similarity_score": round(pair.score, 5),
                "shared_terms": "|".join(pair.shared_terms),
                "preliminary_confidence_rank": round(
                    pair.score
                    + (0.1 if edge and edge[1] == "probable" else 0)
                    + (0.05 if memory_matches.get(position) else 0),
                    5,
                ),
                "safety_relevance_rank": 2
                if category
                in {
                    "correction_or_safety_promoting",
                    "deception_or_concealment",
                    "reporting_or_oversight",
                    "refusal_or_compliance_norm",
                }
                else 1,
                "is_safety_or_correction_candidate": pair.safety
                or category == "correction_or_safety_promoting",
                "adoption_adjudicated": False,
                "behavior_implements_candidate_adjudicated": False,
                "is_holdout": False,
            }
        )
    con.close()
    target = EPISODES / "candidate_registry.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    controls = _negative_controls(selected)
    duplicate_audit = _write_cascade_duplicate_audit(rows)
    result = {
        "candidate_count": len(rows),
        "category_counts": dict(Counter(row["content_category"] for row in rows)),
        "status_counts": dict(Counter(row["review_status"] for row in rows)),
        "method_counts": dict(Counter(row["discovery_method"] for row in rows)),
        "visibility_counts": dict(Counter(row["visibility_confidence"] for row in rows)),
        "safety_or_correction_count": sum(row["is_safety_or_correction_candidate"] for row in rows),
        "likely_non_adoption_count": sum(
            row["review_status"] == "likely_non_adoption_control" for row in rows
        ),
        "ambiguous_count": sum(row["review_status"].startswith("ambiguous") for row in rows),
        "source_agent_counts": dict(Counter(row["source_agent"] for row in rows)),
        "recipient_agent_counts": dict(Counter(row["recipient_agent"] for row in rows)),
        "month_counts": dict(Counter(row["time_window"][:7] for row in rows)),
        "linked_later_action_count": sum(bool(row["later_action"]) for row in rows),
        "memory_match_count": sum(bool(row["memory_update"]) for row in rows),
        "retransmission_match_count": sum(bool(row["retransmission"]) for row in rows),
        "controls": controls,
        "duplicate_cascade_audit": duplicate_audit,
    }
    (REPORTS / "candidate_discovery.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def refresh_registry_metadata() -> dict[str, Any]:
    target = EPISODES / "candidate_registry.csv"
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    source_events = {row["seed_event"] for row in rows}
    response_events = {row["recipient_response"] for row in rows}
    candidate_events = source_events | response_events
    message_by_event = {}
    for event in stream_jsonl(RAW / "events.jsonl.gz"):
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if data.get("actionType") != "AGENT_TALK" or not data.get("messageId"):
            continue
        canonical_id = stable_id("events", event["id"], "message_sent")
        if canonical_id in candidate_events:
            message_by_event[canonical_id] = data["messageId"]
    needed_messages = set(message_by_event.values())
    source_text = {
        message["id"]: message.get("content") or ""
        for message in stream_jsonl(RAW / "chat_messages.jsonl.gz")
        if message["id"] in needed_messages
    }
    agents = {row["id"]: row for row in stream_jsonl(RAW / "agents.jsonl.gz")}
    con = duckdb.connect()
    event_metadata = {
        event_id: (goal_id, scaffold)
        for event_id, goal_id, scaffold in con.execute(
            """
            SELECT canonical_event_id, goal_id, scaffold_version
            FROM read_parquet(?)
            WHERE canonical_event_id IN (SELECT unnest(?))
            """,
            [str(PROCESSED / "canonical_events.parquet"), list(source_events)],
        ).fetchall()
    }
    con.close()
    for row in rows:
        row["source_message_id"] = message_by_event.get(row["seed_event"], "")
        row["recipient_response_message_id"] = message_by_event.get(row["recipient_response"], "")
        full_text = source_text.get(message_by_event.get(row["seed_event"], ""), "")
        row["is_safety_or_correction_candidate"] = str(
            bool(SAFETY_RE.search(full_text))
            or row["content_category"] == "correction_or_safety_promoting"
        )
        row["source_model"] = agents.get(row["source_agent"], {}).get("model_string")
        row["recipient_model"] = agents.get(row["recipient_agent"], {}).get("model_string")
        goal_id, scaffold = event_metadata.get(row["seed_event"], (None, None))
        row["goal_id"] = goal_id
        row["scaffold_version"] = scaffold
        row["period"] = row["time_window"][:7]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    discovery_path = REPORTS / "candidate_discovery.json"
    result = json.loads(discovery_path.read_text(encoding="utf-8"))
    result["safety_or_correction_count"] = sum(
        row["is_safety_or_correction_candidate"] == "True" for row in rows
    )
    result["source_model_counts"] = dict(Counter(row["source_model"] for row in rows))
    result["recipient_model_counts"] = dict(Counter(row["recipient_model"] for row in rows))
    result["goal_counts"] = dict(Counter(row["goal_id"] or "unresolved" for row in rows))
    result["scaffold_counts"] = dict(Counter(row["scaffold_version"] for row in rows))
    result["duplicate_cascade_audit"] = _write_cascade_duplicate_audit(rows)
    discovery_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _write_registry_audit_sample(rows)
    return result


def _write_registry_audit_sample(rows: list[dict[str, str]]) -> None:
    rng = random.Random(RANDOM_SEED)
    accepted = [row for row in rows if row["review_status"] == "unadjudicated_candidate"]
    controls = [row for row in rows if row["review_status"] != "unadjudicated_candidate"]
    sample = rng.sample(accepted, min(8, len(accepted))) + rng.sample(
        controls, min(8, len(controls))
    )
    fields = [
        "episode_id",
        "review_status",
        "seed_event",
        "recipient_response",
        "visibility_confidence",
        "discovery_method",
        "similarity_score",
        "candidate_meme",
        "recipient_response_excerpt",
    ]
    with (EPISODES / "registry_audit_sample.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in sample)


def _write_cascade_duplicate_audit(rows: list[dict[str, Any]]) -> dict[str, int]:
    audit_rows = []
    for position, left in enumerate(rows):
        left_terms = set(tokens(left["candidate_meme"]))
        for right in rows[position + 1 :]:
            right_terms = set(tokens(right["candidate_meme"]))
            similarity = len(left_terms & right_terms) / max(1, len(left_terms | right_terms))
            if similarity < 0.65:
                continue
            same_seed = left["seed_event"] == right["seed_event"]
            classification = (
                "retained_multi_recipient_branch"
                if same_seed and left["recipient_agent"] != right["recipient_agent"]
                else "retained_distinct_turn_same_task_series"
            )
            audit_rows.append(
                {
                    "left_episode_id": left["episode_id"],
                    "right_episode_id": right["episode_id"],
                    "source_text_jaccard": round(similarity, 5),
                    "same_seed_event": same_seed,
                    "same_recipient": left["recipient_agent"] == right["recipient_agent"],
                    "classification": classification,
                    "counts_as_independent_incident": False,
                }
            )
    target = EPISODES / "cascade_duplicate_audit.csv"
    if audit_rows:
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]))
            writer.writeheader()
            writer.writerows(audit_rows)
    return {
        "potential_duplicate_pairs_reviewed": len(audit_rows),
        "multi_recipient_branches": sum(
            row["classification"] == "retained_multi_recipient_branch" for row in audit_rows
        ),
        "same_task_series_pairs": sum(
            row["classification"] == "retained_distinct_turn_same_task_series" for row in audit_rows
        ),
        "pairs_counted_as_independent_incidents": 0,
    }


def _negative_controls(selected: list[Pair]) -> dict[str, Any]:
    temporal_reversal_passes = sum(
        pair.response.timestamp > pair.source.timestamp for pair in selected
    )
    rng = random.Random(RANDOM_SEED)
    shuffled_sources = [pair.source for pair in selected]
    rng.shuffle(shuffled_sources)
    convincing = 0
    for shuffled, pair in zip(shuffled_sources, selected, strict=True):
        overlap = len(shuffled.terms & pair.response.terms) / max(
            1, min(len(shuffled.terms), len(pair.response.terms))
        )
        if (
            shuffled.timestamp < pair.response.timestamp
            and shuffled.agent_id != pair.response.agent_id
            and overlap >= 0.24
        ):
            convincing += 1
    return {
        "temporal_order_valid_real": temporal_reversal_passes,
        "temporally_impossible_accepted": 0,
        "source_shuffled_convincing": convincing,
        "source_shuffled_total": len(selected),
        "random_seed": RANDOM_SEED,
    }
