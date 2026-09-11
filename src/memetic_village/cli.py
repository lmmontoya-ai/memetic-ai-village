from __future__ import annotations

import argparse
import json

from .amendments_v2_1 import (
    build_action_and_memory_units,
    build_atomic_claim_and_evidence_templates,
    build_author_autocorrelation_diagnostic,
    build_casebook_amendments,
    build_fixed_author_local_comparisons,
    build_hard_control_development_set,
    build_sampling_frame_report,
    build_source_linked_channel,
    build_staged_annotation_packets,
    build_truth_audit,
    compute_structural_audit_if_available,
    compute_v2_1_reliability_if_available,
    rebuild_v2_1_structural_traces,
    run_v2_1_amendments,
    verify_v2_1,
)
from .annotation_v2 import build_annotation_packets, compute_reliability_if_available
from .casebook_v2 import build_featured_cases, download_featured_screenshots
from .config import ROOT
from .controls_v2 import build_blocked_permutations, build_matched_controls
from .discovery import build_candidates, refresh_registry_metadata
from .eligibility_v2 import build_response_eligibility
from .exposure import build_exposures, could_observe, validate_exposures
from .holdout_v2 import build_holdout_clusters
from .inventory import build_inventory
from .manifest import build_manifest, download_snapshot
from .outcomes_v2 import (
    build_action_windows,
    build_claim_lineage,
    build_memory_deltas,
    build_third_party_candidates,
)
from .preflight import protect_annotations
from .protocol_v2_2 import (
    compile_stage_b_v2_2,
    freeze_annotation_protocol_v2_2,
    verify_v2_2,
)
from .report import build_report
from .temporal_v2 import build_temporal_relations
from .timeline import build_timeline, finalize_timeline, retrieve_history
from .v2_pipeline import (
    audit_retired_terminology,
    build_eligibility_audit_sample,
    run_v2_pipeline,
    verify_v2,
)
from .validation import run_verification


def main() -> None:
    parser = argparse.ArgumentParser(prog="village-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "download",
        "manifest",
        "inventory",
        "timeline",
        "timeline-finalize",
        "exposures",
        "exposures-validate",
        "candidates",
        "candidates-refresh",
        "report",
        "verify",
        "all",
        "v2-holdout",
        "v2-controls",
        "v2-temporal",
        "v2-eligibility",
        "v2-claims",
        "v2-actions",
        "v2-memory",
        "v2-third-party",
        "v2-permutations",
        "v2-cases",
        "v2-screenshots",
        "v2-annotations",
        "v2-terminology",
        "v2-audit-sample",
        "v2-reliability",
        "v2-verify",
        "v2-all",
        "v2-1-author-diagnostic",
        "v2-1-local-controls",
        "v2-1-source-linked",
        "v2-1-claims",
        "v2-1-outcomes",
        "v2-1-truth",
        "v2-1-cases",
        "v2-1-sampling-frame",
        "v2-1-annotations",
        "v2-1-reliability",
        "v2-1-verify",
        "v2-1-all",
        "v2-2-freeze",
        "v2-2-compile-stage-b",
        "v2-2-verify",
    ):
        subparsers.add_parser(command)
    history = subparsers.add_parser("history")
    history.add_argument("--agent-id")
    history.add_argument("--goal-id")
    history.add_argument("--event-id")
    history.add_argument("--hours", type=int, default=24)
    history.add_argument("--limit", type=int, default=100)
    observe = subparsers.add_parser("could-observe")
    observe.add_argument("recipient_id")
    observe.add_argument("source_event_id")
    observe.add_argument("decision_timestamp")
    args = parser.parse_args()
    try:
        protect_annotations(ROOT, args.command)
    except ValueError as error:
        parser.error(str(error))

    if args.command == "download":
        download_snapshot()
        result = {"download": "complete"}
    elif args.command == "manifest":
        result = build_manifest()
    elif args.command == "inventory":
        result = build_inventory()
    elif args.command == "timeline":
        result = build_timeline()
    elif args.command == "timeline-finalize":
        result = finalize_timeline()
    elif args.command == "exposures":
        result = build_exposures()
    elif args.command == "exposures-validate":
        result = validate_exposures()
    elif args.command == "candidates":
        result = build_candidates()
    elif args.command == "candidates-refresh":
        result = refresh_registry_metadata()
    elif args.command == "report":
        result = build_report()
    elif args.command == "verify":
        result = run_verification()
    elif args.command == "v2-holdout":
        result = build_holdout_clusters()[0]
    elif args.command == "v2-controls":
        result = build_matched_controls()
    elif args.command == "v2-temporal":
        result = build_temporal_relations()
    elif args.command == "v2-eligibility":
        result = build_response_eligibility()
    elif args.command == "v2-claims":
        result = build_claim_lineage()
    elif args.command == "v2-actions":
        result = build_action_windows()
    elif args.command == "v2-memory":
        result = build_memory_deltas()
    elif args.command == "v2-third-party":
        result = build_third_party_candidates()
    elif args.command == "v2-permutations":
        result = build_blocked_permutations(500)
    elif args.command == "v2-cases":
        result = build_featured_cases()
    elif args.command == "v2-screenshots":
        result = download_featured_screenshots()
    elif args.command == "v2-annotations":
        result = build_annotation_packets()
    elif args.command == "v2-terminology":
        result = audit_retired_terminology()
    elif args.command == "v2-audit-sample":
        result = build_eligibility_audit_sample()
    elif args.command == "v2-reliability":
        result = compute_reliability_if_available()
    elif args.command == "v2-verify":
        result = verify_v2()
    elif args.command == "v2-all":
        result = run_v2_pipeline()
    elif args.command == "v2-1-author-diagnostic":
        result = build_author_autocorrelation_diagnostic()
    elif args.command == "v2-1-local-controls":
        result = {
            "local_comparisons": build_fixed_author_local_comparisons(),
            "development_set": build_hard_control_development_set(),
            "structural_traces": rebuild_v2_1_structural_traces(),
        }
    elif args.command == "v2-1-source-linked":
        result = build_source_linked_channel()
    elif args.command == "v2-1-claims":
        result = build_atomic_claim_and_evidence_templates()
    elif args.command == "v2-1-outcomes":
        result = build_action_and_memory_units()
    elif args.command == "v2-1-truth":
        result = build_truth_audit()
    elif args.command == "v2-1-cases":
        result = build_casebook_amendments()
    elif args.command == "v2-1-sampling-frame":
        result = build_sampling_frame_report()
    elif args.command == "v2-1-annotations":
        result = build_staged_annotation_packets()
    elif args.command == "v2-1-reliability":
        result = {
            "semantic": compute_v2_1_reliability_if_available(),
            "structural": compute_structural_audit_if_available(),
        }
    elif args.command == "v2-1-verify":
        result = verify_v2_1()
    elif args.command == "v2-1-all":
        result = run_v2_1_amendments()
    elif args.command == "v2-2-freeze":
        result = freeze_annotation_protocol_v2_2()
    elif args.command == "v2-2-compile-stage-b":
        result = compile_stage_b_v2_2()
    elif args.command == "v2-2-verify":
        result = verify_v2_2()
    elif args.command == "history":
        result = retrieve_history(
            agent_id=args.agent_id,
            goal_id=args.goal_id,
            event_id=args.event_id,
            hours=args.hours,
            limit=args.limit,
        )
    elif args.command == "could-observe":
        result = could_observe(
            args.recipient_id, args.source_event_id, args.decision_timestamp
        ).__dict__
    else:
        result = {}
        result["manifest"] = build_manifest()
        result["inventory"] = build_inventory()
        result["timeline"] = build_timeline()
        result["exposures"] = build_exposures()
        result["candidates"] = build_candidates()
        result["report"] = build_report()
        result["verification"] = run_verification()
    print(json.dumps(result, indent=2, default=str))
    if str(result.get("status", "")).startswith(("fail", "blocked")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
