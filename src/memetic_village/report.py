"""LEGACY V1 — INVALID PROXY feasibility report generator."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import EPISODES, REPORTS, ensure_output_dirs


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _percent(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def _select_cases(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    known_incident = next(
        (row for row in rows if row["discovery_method"] == "known_incident_reconstruction"),
        None,
    )
    preferred_ids = (
        "ep_041_6fd27719",
        "ep_026_53fe89ce",
        "ep_055_42b14827",
        "ep_057_e35f89c4",
        "ep_013_7396ea56",
    )
    preferred = [
        row for episode_id in preferred_ids for row in rows if row["episode_id"] == episode_id
    ]
    if len(preferred) == 5:
        if known_incident:
            return [*preferred[:4], known_incident]
        return preferred
    chosen: list[dict[str, str]] = []
    if known_incident:
        chosen.append(known_incident)
    predicates = [
        lambda row: row["content_category"] == "correction_or_safety_promoting",
        lambda row: bool(row["memory_update"]),
        lambda row: bool(row["retransmission"]),
        lambda row: row["review_status"] == "likely_non_adoption_control",
        lambda row: row["review_status"].startswith("ambiguous"),
    ]
    for predicate in predicates:
        candidate = next((row for row in rows if predicate(row) and row not in chosen), None)
        if candidate:
            chosen.append(candidate)
    for row in sorted(
        rows, key=lambda item: float(item["preliminary_confidence_rank"]), reverse=True
    ):
        if row not in chosen:
            chosen.append(row)
        if len(chosen) == 5:
            break
    return chosen[:5]


def build_report() -> dict[str, Any]:
    ensure_output_dirs()
    inventory = json.loads((REPORTS / "data_quality.json").read_text(encoding="utf-8"))
    timeline = json.loads((REPORTS / "timeline_validation.json").read_text(encoding="utf-8"))
    exposure = json.loads((REPORTS / "exposure_validation.json").read_text(encoding="utf-8"))
    discovery = json.loads((REPORTS / "candidate_discovery.json").read_text(encoding="utf-8"))
    candidates = _read_csv(EPISODES / "candidate_registry.csv")
    cases = _select_cases(candidates)
    n = len(candidates)
    visibility = Counter(row["visibility_confidence"] for row in candidates)
    categories = Counter(row["content_category"] for row in candidates)
    statuses = Counter(row["review_status"] for row in candidates)
    methods = Counter(row["discovery_method"] for row in candidates)
    linked_actions = sum(bool(row["later_action"]) for row in candidates)
    memories = sum(bool(row["memory_update"]) for row in candidates)
    retransmissions = sum(bool(row["retransmission"]) for row in candidates)
    safety_or_correction = sum(
        row.get("is_safety_or_correction_candidate") == "True" for row in candidates
    )
    source_models = Counter(row.get("source_model") or "unresolved" for row in candidates)
    source_agents = Counter(row["source_agent"] for row in candidates)
    goals = Counter(row.get("goal_id") or "unresolved" for row in candidates)
    periods = Counter(row.get("period") or row["time_window"][:7] for row in candidates)

    report_lines = [
        "# Phase 1 feasibility report",
        "",
        "> **LEGACY V1 — INVALID PROXY.** This generated report is retained for reproducibility; its proxy counts are not v2 evidence.",
        "",
        f"Generated: {datetime.now(UTC).date().isoformat()} UTC  ",
        "Decision: **PIVOT retrospective transmission claims; retain the telemetry/design program.**",
        "",
        "## 1. Question and definitions",
        "",
        "This pilot asks whether exported AI Village telemetry can reconstruct the observable sequence",
        "peer availability, expressed recurrence, downstream behavior, memory incorporation, and",
        "retransmission. Definitions and thresholds were frozen in `research_spec.md` before candidate",
        "content was searched. Channel availability is not called exposure, and semantic recurrence is",
        "not called adoption.",
        "",
        "## 2. Dataset coverage",
        "",
        (
            f"The pinned snapshot contains {sum(item['rows'] for item in inventory['tables'].values()):,} rows across "
            f"{len(inventory['tables'])} exported tables. The canonical timeline contains {timeline['rows']:,} "
            f"deterministically ordered events with {timeline['unique_ids']:,} unique canonical IDs. Raw prompts,"
        ),
        "exact context retrieval logs, scaffold source, and screenshots are absent from this frozen snapshot.",
        "The final 20% of chronologically ordered canonical event records remains a locked holdout and contributed no",
        "candidate content or threshold changes.",
        "",
        "## 3. Visibility reconstruction",
        "",
        "The temporal graph preserves global-chat and Rooms v1 regimes, recorded room moves, recipient",
        "decision order, and negative edges. Across the full graph:",
        "",
        "| Confidence | Edges | Percent |",
        "|---|---:|---:|",
    ]
    total_edges = exposure["rows"]
    for level in ("confirmed", "probable", "possible", "unknown", "ruled_out"):
        count = exposure["confidence_counts"].get(level, 0)
        report_lines.append(f"| {level} | {count:,} | {_percent(count, total_edges)} |")
    report_lines.extend(
        [
            "",
            (
                f"The future-to-past test produced {exposure['future_to_past_failures']} failures in "
                f"{exposure['future_to_past_tests']} tests. Exact prompt inclusion is confirmed for zero"
            ),
            "ordinary chat edges because the required prompt records are not exported.",
            "",
            "## 4. Candidate discovery",
            "",
            f"The frozen discovery procedure produced {n} deduplicated discovery-set candidates using",
            "distinctive lexical recurrence, direct request/response structure, correction/safety",
            "follow-ups, and one separately labeled targeted reconstruction of the published whitespace-EGG",
            "incident. Automatic retrieval only proposes candidates.",
            "",
            "| Measure | Result |",
            "|---|---:|",
        ]
    )
    for level in ("confirmed", "probable", "possible", "unknown", "ruled_out"):
        report_lines.append(
            f"| Candidate visibility: {level} | {visibility[level]} ({_percent(visibility[level], n)}) |"
        )
    report_lines.extend(
        [
            "| Adoption adjudicated | 0 (0.0%) |",
            f"| Subsequent action trace available (not implementation judgment) | {linked_actions} ({_percent(linked_actions, n)}) |",
            f"| Preliminary message-to-memory lexical match | {memories} ({_percent(memories, n)}) |",
            "| Memory incorporation adjudicated | 0 (0.0%) |",
            f"| Preliminary retransmission lexical match | {retransmissions} ({_percent(retransmissions, n)}) |",
            "| Retransmission adjudicated | 0 (0.0%) |",
            "| High-confidence positive episodes after human review | 0 |",
            f"| Likely non-adoption controls | {statuses['likely_non_adoption_control']} |",
            f"| Correction/safety-promoting candidates | {safety_or_correction} |",
            "| Inter-annotator agreement | not measured (Workstream G excluded) |",
            "",
            "The 100% preliminary memory-match rate is non-specific because exported memories are long, cumulative snapshots; it must not be interpreted as 100% new incorporation.",
            "",
            "Category counts: "
            + "; ".join(f"{key}={value}" for key, value in categories.most_common())
            + ".",
            "Discovery-method counts: "
            + "; ".join(f"{key}={value}" for key, value in methods.most_common())
            + ".",
            "",
            "Concentration: top source model "
            + f"`{source_models.most_common(1)[0][0]}`={source_models.most_common(1)[0][1]}/{n}; "
            + f"top source agent `{source_agents.most_common(1)[0][0]}`={source_agents.most_common(1)[0][1]}/{n}; "
            + f"top month `{periods.most_common(1)[0][0]}`={periods.most_common(1)[0][1]}/{n}. "
            + f"Task/goal concentration is unresolved for {goals['unresolved']}/{n} candidates because the pinned export lacks village-goal intervals.",
            "",
            "Common rejection/control reasons are generic wait/status recurrence, low-overlap replies to direct requests, shared task or artifact context, independent task convergence, uncertain prompt inclusion, and non-specific matches against cumulative memories.",
            "The duplicate-cascade screen flagged four high-similarity pairs: two multi-recipient branches",
            "from the same source and two separate turns in one collaborative-story task. They remain",
            "separate source-recipient episodes but are not counted as independent incidents.",
            "",
            "## 5. Reliability and negative controls",
            "",
            "No annotation-reliability statistic is reported: heuristic labels are not independent human",
            "annotations. The temporal pipeline accepted zero reversed pairs. In the fixed-seed source",
            (
                f"shuffle, {discovery['controls']['source_shuffled_convincing']} of "
                f"{discovery['controls']['source_shuffled_total']} pairs met the same coarse lexical/time screen."
            ),
            "This control evaluates retrieval specificity, not causal identification.",
            "",
            "## 6. Representative traces",
            "",
            "The following traces are selected to illustrate coverage and limits, not as confirmed spread.",
            "Each ID resolves through `canonical_events.parquet` to a raw source pointer. Full trace sheets",
            "are in `episodes/case_studies.md`.",
            "Three independently published incidents are also reconstructed at exact checkpoints in",
            "`reports/known_incident_reconstructions.md`; they validate retrieval, not causal spread.",
            "",
        ]
    )
    for case in cases:
        report_lines.append(
            f"- `{case['episode_id']}`: `{case['seed_event']}` -> `{case['recipient_response']}`; "
            f"visibility `{case['visibility_confidence']}`; status `{case['review_status']}`."
        )
    report_lines.extend(
        [
            "",
            "## 7. Main confounds",
            "",
            "Shared village goals and artifacts, common web observations, hidden or truncated context,",
            "pre-existing policy similarity, independent task convergence, scaffold/model changes, lexical",
            "priming without behavior change, uncertain room initialization, selection on recurrence, and",
            "cumulative memories can all create apparent spread. Provider reasoning text and generated daily",
            "summaries are not treated as ground truth.",
            "",
            "## 8. Missing data and unperformed checks",
            "",
            "Exact recipient prompts, prompt-construction code, retrieval/version logs, full historic room",
            "snapshots, raw-call mappings, and replayable pre-exposure states are missing. Workstream G was",
            "out of scope, so adoption judgments and agreement are missing. External-reader challenge and",
            "publisher factual review were not performed because this phase explicitly prohibits external",
            "contact. These are recorded as unmet verification items, not silently marked complete.",
            "",
            "## 9. Proposed quantitative design",
            "",
            "Do not estimate a population transmission effect from this export. First obtain or prospectively",
            "log exact prompts and context provenance; label a blinded, chronologically held-out set under",
            "Workstream G; then reconstruct pre-exposure agent states and randomize original peer message",
            "versus no-message and information-matched controls. Primary outcomes should be one prespecified",
            "action measure, with memory writing and retransmission secondary. Randomization must be independent",
            "of model sampling seeds, and model/scaffold/goal period should be blocked or stratified.",
            "",
            "## 10. Decision and rationale",
            "",
            "The full-go thresholds fail: confirmed exposure is 0%, reliability is unmeasured, and zero cases",
            "have survived independent adoption/behavior review. The appropriate Phase 1 decision is therefore",
            "a **pivot away from retrospective causal transmission claims**. The useful retained project is:",
            "*What telemetry and controlled replay are required to measure social transmission and unsanctioned",
            "coordination in deployed AI-agent populations?* The canonical timeline, visibility graph, candidate",
            "registry, negative controls, and locked holdout make that telemetry/design study reproducible.",
            "",
            "## Evidence-status key",
            "",
            "Dataset counts and event IDs are **Observed**. Candidate categories and lexical matches are",
            "**Annotated by deterministic heuristic**. Availability assessments are **Inferred from documented",
            "rules**. Claims about attention, adoption, causal influence, or latent values remain **Speculative",
            "or unestablished**.",
        ]
    )
    (REPORTS / "feasibility_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    _write_cases(cases)
    _write_claim_audit()
    _write_unresolved_requirements()
    summary = {
        "decision": "pivot",
        "candidate_count": n,
        "confirmed_exposure_percent": 0.0,
        "adoption_adjudicated_percent": 0.0,
        "annotation_agreement": None,
        "high_confidence_positive_episodes": 0,
        "featured_episode_ids": [case["episode_id"] for case in cases],
    }
    (REPORTS / "feasibility_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _write_cases(cases: list[dict[str, str]]) -> None:
    lines = [
        "# Representative candidate trace sheets",
        "",
        "These are raw-trace reconstructions and method-limit examples, not causal case studies. Excerpts",
        "are minimized and URLs removed. `Observed`, `Heuristic`, `Inferred`, and `Unestablished` labels",
        "separate evidence types.",
        "",
    ]
    for case in cases:
        evidence_level = (
            "temporally ordered recurrence plus preliminary memory match"
            if case["memory_update"]
            else "temporally ordered recurrence plus plausible availability"
        )
        lines.extend(
            [
                f"## {case['episode_id']}",
                "",
                f"- Observed seed: `{case['seed_event']}` — {case['candidate_meme']}",
                f"- Inferred availability edge: `{case['exposure_event']}` ({case['visibility_confidence']}; {case['visibility_rule']})",
                f"- Observed later recipient message: `{case['recipient_response']}` — {case['recipient_response_excerpt']}",
                f"- Observed next action trace: `{case['later_action'] or 'none within 24h'}`",
                f"- Heuristic memory match: `{case['memory_update'] or 'none within 7d'}`",
                f"- Heuristic retransmission match: `{case['retransmission'] or 'none within 7d'}`",
                f"- Highest evidence reached: {evidence_level}.",
                f"- Review status: `{case['review_status']}`; adoption and implementation are unadjudicated.",
                f"- Strongest alternative: {case['alternative_explanations']}",
                "- Causal interpretation: unestablished.",
                "",
            ]
        )
    (EPISODES / "case_studies.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_claim_audit() -> None:
    rows = [
        ("The snapshot has the reported table and row counts.", "Observed", "data_quality.json"),
        (
            "The canonical event ordering is deterministic.",
            "Observed",
            "timeline_validation.json and determinism test",
        ),
        (
            "A candidate contains lexical recurrence.",
            "Annotated",
            "candidate_registry.csv similarity fields",
        ),
        (
            "A recipient could access a source item.",
            "Inferred",
            "exposures.parquet plus visibility_rules.md",
        ),
        ("A recipient adopted the candidate.", "Speculative", "not adjudicated"),
        (
            "Peer exposure caused behavior or memory change.",
            "Speculative",
            "requires controlled replay",
        ),
        (
            "The data support population causal effects.",
            "Speculative",
            "explicitly rejected in feasibility report",
        ),
    ]
    with (REPORTS / "claim_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["claim", "label", "support_or_action"])
        writer.writerows(rows)


def _write_unresolved_requirements() -> None:
    lines = [
        "# Unresolved data requirements",
        "",
        "No request was sent; external contact is prohibited for this phase.",
        "",
        "| Unknown | Why it matters | Information needed | Fallback without it | Fatal to which claim? |",
        "|---|---|---|---|---|",
        "| Exact prompt construction | Distinguishes channel access from exposure | Per-turn raw prompt and truncation/provenance metadata | Label same-room edges possible only | Confirmed exposure and causal effect |",
        "| Historic room state | Establishes who shared a channel | Membership snapshots and move audit log | Use recorded moves; otherwise unknown | Some post-Rooms availability claims |",
        "| Memory retrieval/version | Separates written memory from memory shown | Per-turn retrieved memory IDs and rewrite rules | Treat memory matches as incorporation only | Memory mediation and persistence |",
        "| Model/scaffold versions | Controls discontinuities | Exact deployment commits and timestamps | Use supplied changelog regimes | Cross-period effect estimates |",
        "| Turn/action mapping | Links expression to behavior | Raw call/tool/artifact provenance | Canonical raw pointers and session joins | Fine-grained implementation claims |",
        "| Replayable state | Enables causal intervention | Pre-exposure state snapshots and replay API | Propose prospective instrumentation | All causal transmission claims |",
        "| Publication permissions | Governs quoting and identifiers | Specific factual/privacy review | Keep outputs internal and excerpts minimal | Public case presentation |",
        "",
    ]
    (REPORTS / "unresolved_data_requirements.md").write_text("\n".join(lines), encoding="utf-8")
