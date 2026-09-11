"""Build claim-frozen development packets for machine Stages C and D.

The construction is deterministic and uses every compiler-generated Stage-B
claim pair.  It does not select pairs using Stage-B semantic labels.  Stage-C
retrieval is driven by the frozen Stage-A propositions/referents and preserved
artifact identifiers, as required by research_spec_v2.2 section 9.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAIR_PATH = (
    ROOT / "annotations" / "v2_2" / "machine" / "combined" / "stage_b" / "unannotated_pairs.csv"
)
V22_STAGE_A = ROOT / "annotations" / "v2_2" / "stage_a" / "packets"
V21_STAGE_C = ROOT / "annotations" / "v2_1" / "stage_c" / "packets"
V21_STAGE_D = ROOT / "annotations" / "v2_1" / "stage_d" / "packets"
V21_FULL_TRACES = ROOT / "annotations" / "v2_1" / "full_traces"
OUTPUT = ROOT / "annotations" / "v2_2" / "machine" / "combined"

TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)
ARTIFACT_RE = re.compile(
    r"(?:https?://\S+|(?:[\w.-]+/)+[\w.-]+|\b[0-9a-f]{7,64}\b|\b[\w.-]+\.(?:csv|json|ya?ml|md|txt|py|js|ts|tsx|html|css|pdf|xlsx?|zip)\b)",
    re.IGNORECASE,
)
STOPWORDS = {
    "about",
    "after",
    "again",
    "agent",
    "before",
    "being",
    "claim",
    "could",
    "does",
    "from",
    "have",
    "into",
    "message",
    "other",
    "response",
    "same",
    "should",
    "speaker",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "using",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}
ACTION_TERMS = {
    "approve",
    "approved",
    "approval",
    "escalate",
    "escalated",
    "export",
    "exported",
    "inspect",
    "inspected",
    "revert",
    "reverted",
    "rollback",
    "rolled",
    "verify",
    "verified",
    "verification",
    "validate",
    "validated",
    "publish",
    "published",
    "delete",
    "deleted",
    "remove",
    "removed",
    "assign",
    "assigned",
    "execute",
    "executed",
    "commit",
    "committed",
    "deploy",
    "deployed",
    "report",
    "reported",
}
CORRECTION_TERMS = {
    "actually",
    "correction",
    "corrected",
    "false",
    "incorrect",
    "mistake",
    "mistaken",
    "retract",
    "retracted",
    "wrong",
    "contradict",
    "contradicted",
    "disconfirm",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(TOKEN_RE.findall(text))


def tokens(value: Any) -> set[str]:
    return {
        token for token in normalized(value).split() if len(token) >= 4 and token not in STOPWORDS
    }


def searchable(event: dict[str, Any]) -> str:
    return normalized(
        " ".join(
            str(event.get(key) or "")
            for key in (
                "event_type",
                "content_reference",
                "artifact_reference",
                "raw_payload",
                "message_text",
            )
        )
    )


def read_gzip(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_gzip(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)


def read_pairs() -> list[dict[str, str]]:
    with PAIR_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fixed_pair(row: dict[str, str]) -> dict[str, Any]:
    return {
        "claim_pair_id": row["claim_pair_id"],
        "source_claim_id": row["source_claim_id"],
        "response_claim_id": row["response_claim_id"],
        "source_exact_spans": json.loads(row["source_exact_spans"]),
        "response_exact_spans": json.loads(row["response_exact_spans"]),
        "source_atomic_proposition": row["source_atomic_proposition"],
        "response_atomic_proposition": row["response_atomic_proposition"],
        "source_referent": row["source_referent"],
        "response_referent": row["response_referent"],
    }


def claim_frozen_third_party_candidates(
    fixed_pairs: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Narrow structural candidates using frozen Stage-A claims, never Stage-B labels.

    The structural extractor intentionally favors recall and can return hundreds of
    locally topical messages after global-channel normalization.  Stage D compares a
    later message to the now-frozen atomic claim, so retain candidates with at least
    two informative shared tokens and 60% coverage of one fixed claim profile.  The
    matching IDs and scores are emitted for auditability.
    """
    profiles: list[tuple[str, set[str]]] = []
    for pair in fixed_pairs:
        values = [
            pair.get("source_atomic_proposition"),
            pair.get("response_atomic_proposition"),
            pair.get("source_referent"),
            pair.get("response_referent"),
            *pair.get("source_exact_spans", []),
            *pair.get("response_exact_spans", []),
        ]
        profile = set().union(*(tokens(value) for value in values))
        profiles.append((pair["claim_pair_id"], profile))

    retained: list[dict[str, Any]] = []
    for candidate in candidates:
        later_tokens = tokens(candidate.get("later_expression_text"))
        matches = []
        for claim_pair_id, profile in profiles:
            overlap = later_tokens & profile
            coverage = len(overlap) / max(1, len(profile))
            if len(overlap) >= 2 and coverage >= 0.60:
                matches.append(
                    {
                        "claim_pair_id": claim_pair_id,
                        "overlap_tokens": sorted(overlap),
                        "claim_profile_coverage": coverage,
                    }
                )
        if matches:
            retained.append({**candidate, "claim_frozen_matches": matches})
    return retained


def marked_message_events(blind_id: str) -> list[dict[str, Any]]:
    packet = read_gzip(V22_STAGE_A / f"{blind_id}.json.gz")
    events = []
    for row in packet["context_messages"]:
        if row.get("role") not in {"source", "response"}:
            continue
        events.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "event_type": f"marked_{row['role']}_message",
                "actor_label": row["actor_label"],
                "message_text": row["text"],
                "selection_reasons": [f"mandatory_marked_{row['role']}"],
            }
        )
    if len(events) != 2:
        raise ValueError(f"{blind_id}: expected two marked message events")
    return events


def compile_compact_trace(
    blind_id: str,
    pairs: list[dict[str, str]],
    full_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frozen_texts = [
        row[field]
        for row in pairs
        for field in (
            "source_atomic_proposition",
            "response_atomic_proposition",
            "source_referent",
            "response_referent",
        )
        if row.get(field)
    ]
    frozen_terms = (
        set().union(*(tokens(value) for value in frozen_texts)) if frozen_texts else set()
    )
    artifacts = {
        match.group(0).rstrip(".,;:)]}").casefold()
        for value in frozen_texts
        for match in ARTIFACT_RE.finditer(value)
    }
    reasons: dict[int, set[str]] = defaultdict(set)
    n = len(full_events)
    for index in list(range(min(5, n))) + list(range(max(0, n - 5), n)):
        reasons[index].add("mandatory_first_or_last_five")

    relevant_artifact_indices: dict[str, list[int]] = defaultdict(list)
    for index, event in enumerate(full_events):
        text = searchable(event)
        event_tokens = set(text.split())
        term_overlap = frozen_terms & event_tokens
        artifact_hits = {artifact for artifact in artifacts if artifact and artifact in text}
        phrase_match = any(
            len(normalized(value)) >= 8 and normalized(value) in text for value in frozen_texts
        )
        referent_match = phrase_match or len(term_overlap) >= 2 or bool(artifact_hits)
        if referent_match:
            reasons[index].add("mandatory_frozen_claim_or_referent_match")
        if artifact_hits:
            reasons[index].add("mandatory_artifact_match")
            for artifact in artifact_hits:
                relevant_artifact_indices[artifact].append(index)
        if referent_match and event_tokens & ACTION_TERMS:
            reasons[index].add("mandatory_claim_relevant_action_anchor")
        if referent_match and event_tokens & CORRECTION_TERMS:
            reasons[index].add("mandatory_correction_anchor")
        if referent_match and (
            event.get("visual_state_may_matter") or event.get("screenshot_turn_id")
        ):
            reasons[index].add("mandatory_associated_visual_evidence")

    for indices in relevant_artifact_indices.values():
        if indices:
            reasons[max(indices)].add("mandatory_last_observed_artifact_state")

    anchor_indices = sorted(reasons)
    for anchor in anchor_indices:
        for neighbor in range(max(0, anchor - 2), min(n, anchor + 3)):
            if neighbor not in reasons:
                reasons[neighbor].add("chronological_neighbor")

    mandatory = {
        index
        for index, why in reasons.items()
        if any(reason.startswith("mandatory_") for reason in why)
    }
    optional = [index for index in sorted(reasons) if index not in mandatory]
    allowance = max(0, 120 - len(mandatory))
    selected = sorted(mandatory | set(optional[:allowance]))
    trace = marked_message_events(blind_id)
    for index in selected:
        event = dict(full_events[index])
        event["selection_reasons"] = sorted(reasons[index])
        trace.append(event)
    trace.sort(key=lambda event: (str(event.get("timestamp") or ""), event["event_id"]))
    metadata = {
        "algorithm": "v2.2_claim_frozen_deterministic_trace_v1",
        "frozen_term_count": len(frozen_terms),
        "artifact_identifier_count": len(artifacts),
        "full_trace_event_count": n,
        "selected_full_trace_event_count": len(selected),
        "marked_messages_injected": 2,
        "display_event_count": len(trace),
        "display_cap_excludes_unremovable_mandatory_events": 120,
        "mandatory_event_count": len(mandatory),
        "optional_neighbor_count_included": len(selected) - len(mandatory),
        "omitted_full_trace_event_count": n - len(selected),
        "omissions_disclosed": True,
        "pair_selection_used_stage_b_labels": False,
    }
    return trace, metadata


def main() -> None:
    pairs = read_pairs()
    if not pairs:
        raise SystemExit("No Stage-B claim pairs found")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in pairs:
        grouped[row["blind_unit_id"]].append(row)
    stage_c_dir = OUTPUT / "stage_c" / "packets"
    stage_d_dir = OUTPUT / "stage_d" / "packets"
    c_counts = []
    d_candidate_count_before_claim_filter = 0
    d_candidate_count = 0
    for blind_id in sorted(grouped):
        old_c = read_gzip(V21_STAGE_C / f"{blind_id}.json.gz")
        old_d = read_gzip(V21_STAGE_D / f"{blind_id}.json.gz")
        full_path = V21_FULL_TRACES / f"{blind_id}.json.gz"
        full = read_gzip(full_path)
        fixed_pairs = [fixed_pair(row) for row in grouped[blind_id]]
        compact, generation = compile_compact_trace(blind_id, grouped[blind_id], full["events"])
        common = {
            "blind_unit_id": blind_id,
            "episode_cluster_id": old_c["episode_cluster_id"],
            "source_event_id": old_c["source_event_id"],
            "response_event_id": old_c["response_event_id"],
            "fixed_claim_pairs": fixed_pairs,
            "all_generated_pairs_included": True,
            "stage_b_semantic_labels_used": False,
        }
        stage_c = {
            **common,
            "stage": "C_v2_2_operational_trace_after_claim_freeze",
            "compact_trace_generation": generation,
            "compact_trace": compact,
            "complete_trace_path": str(full_path.relative_to(ROOT)),
        }
        third_party_before_filter = old_d["third_party_expression_candidates"]
        third_party_after_filter = claim_frozen_third_party_candidates(
            fixed_pairs, third_party_before_filter
        )
        stage_d = {
            **common,
            "stage": "D_v2_2_memory_and_third_party_after_claim_freeze",
            "memory_delta": old_d["memory_delta"],
            "memory_trace_limitations": (
                "Mechanical before/delta/after reconstruction; semantic absence, relocation, "
                "writer mechanism, and later reliance require reviewer assessment and may remain unknown."
            ),
            "third_party_expression_candidates": third_party_after_filter,
            "third_party_claim_filter": {
                "uses_stage_b_semantic_labels": False,
                "minimum_informative_token_overlap": 2,
                "minimum_fixed_claim_profile_coverage": 0.60,
                "candidate_count_before_filter": len(third_party_before_filter),
                "candidate_count_after_filter": len(third_party_after_filter),
            },
        }
        write_gzip(stage_c_dir / f"{blind_id}.json.gz", stage_c)
        write_gzip(stage_d_dir / f"{blind_id}.json.gz", stage_d)
        c_counts.append(generation)
        d_candidate_count_before_claim_filter += len(third_party_before_filter)
        d_candidate_count += len(third_party_after_filter)

    manifest = {
        "stage": "C_D_v2_2_claim_frozen_packet_compilation",
        "machine_annotation_not_human_ground_truth": True,
        "unit_count": len(grouped),
        "fixed_claim_pair_count": len(pairs),
        "stage_c_packet_count": len(grouped),
        "stage_d_packet_count": len(grouped),
        "third_party_candidate_count_before_claim_filter": d_candidate_count_before_claim_filter,
        "third_party_candidate_count": d_candidate_count,
        "third_party_claim_filter": {
            "minimum_informative_token_overlap": 2,
            "minimum_fixed_claim_profile_coverage": 0.60,
            "uses_stage_b_semantic_labels": False,
        },
        "stage_b_positive_labels_used": False,
        "all_generated_pairs_included": True,
        "total_full_trace_events": sum(row["full_trace_event_count"] for row in c_counts),
        "total_display_events": sum(row["display_event_count"] for row in c_counts),
        "total_omitted_events_disclosed": sum(
            row["omitted_full_trace_event_count"] for row in c_counts
        ),
        "input_sha256": {
            str(PAIR_PATH.relative_to(ROOT)): sha256(PAIR_PATH),
        },
        "status": "complete",
    }
    output_path = OUTPUT / "stage_c_d_packet_manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
