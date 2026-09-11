from __future__ import annotations

import csv
import gzip
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow
import pyarrow.parquet as pq
import pytz

from .annotation_v2 import ANNOTATIONS, build_annotation_packets, compute_reliability_if_available
from .casebook_v2 import build_featured_cases, download_featured_screenshots
from .config import CORE_TABLES, EPISODES, PROCESSED, REPORTS, ROOT, ensure_output_dirs
from .controls_v2 import build_blocked_permutations, build_matched_controls
from .eligibility_v2 import build_response_eligibility
from .holdout_v2 import build_holdout_clusters
from .outcomes_v2 import (
    build_action_windows,
    build_claim_lineage,
    build_memory_deltas,
    build_third_party_candidates,
)
from .temporal_v2 import build_temporal_relations
from .util import sha256_file

RETIRED_TERMS = (
    "probable exposure",
    "candidate transmission",
    "memory incorporation",
    "retransmission",
    "downstream action",
)


def audit_retired_terminology() -> dict[str, Any]:
    ensure_output_dirs()
    findings = []
    unknown = []
    extensions = {".md", ".py", ".csv", ".json"}
    excluded_parts = {".git", ".venv", "data", ".pytest_cache", ".ruff_cache", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        relative = path.relative_to(ROOT)
        if any(part in excluded_parts for part in relative.parts):
            continue
        if str(relative).replace("\\", "/") in {
            "reports/terminology_audit_v2.csv",
            "reports/terminology_audit_v2.json",
        }:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, 1):
            lowered = line.lower()
            for term in RETIRED_TERMS:
                if term not in lowered:
                    continue
                disposition = _term_disposition(relative, line)
                finding = {
                    "path": str(relative),
                    "line": line_number,
                    "term": term,
                    "disposition": disposition,
                    "excerpt": line.strip()[:300],
                }
                findings.append(finding)
                if disposition == "unclassified_use_requires_review":
                    unknown.append(finding)
    path = REPORTS / "terminology_audit_v2.csv"
    if findings:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(findings[0]))
            writer.writeheader()
            writer.writerows(findings)
    result = {
        "artifact": str(path),
        "finding_count": len(findings),
        "disposition_counts": dict(Counter(row["disposition"] for row in findings)),
        "unclassified_count": len(unknown),
        "passes": not unknown,
    }
    (REPORTS / "terminology_audit_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _term_disposition(path: Path, line: str) -> str:
    text = str(path).replace("\\", "/")
    if (
        "v2" in text
        or text == "docs/legacy_metric_retirement.md"
        or "invalid proxy" in line.lower()
        or "legacy v1" in line.lower()
    ):
        return "v2_definition_or_explicit_retirement"
    if text in {"research_spec.md", "docs/PLAN.md", "visibility_rules.md", "README.md"}:
        return "legacy_v1_invalid_proxy_documented_in_file_header"
    if text.startswith(("reports/", "episodes/")):
        return "legacy_v1_invalid_proxy_documented_by_directory_notice"
    if text in {
        "src/memetic_village/discovery.py",
        "src/memetic_village/exposure.py",
        "src/memetic_village/report.py",
    }:
        return "legacy_v1_invalid_proxy_documented_in_module"
    return "unclassified_use_requires_review"


def build_eligibility_audit_sample() -> dict[str, Any]:
    rows = pq.read_table(PROCESSED / "response_eligibility_v2.parquet").to_pylist()
    quotas = {"eligible": 30, "ineligible": 20, "concurrent_or_ambiguous": 10}
    selected = []
    for group, target in quotas.items():
        if group == "eligible":
            pool = [
                row
                for row in rows
                if row["eligibility_class"]
                in {"eligible", "source_acknowledged", "observed_inclusion"}
            ]
        elif group == "ineligible":
            pool = [row for row in rows if row["eligibility_class"] == "ineligible"]
        else:
            pool = [row for row in rows if row["temporal_relation"] == "concurrent_or_ambiguous"]
        for row in sorted(pool, key=lambda item: item["episode_id"])[:target]:
            selected.append(
                {
                    "audit_stratum": group,
                    "episode_id": row["episode_id"],
                    "source_event_id": row["source_event_id"],
                    "response_event_id": row["response_event_id"],
                    "source_timestamp": row["source_timestamp"],
                    "response_completion_timestamp": row["response_completion_timestamp"],
                    "source_room_id": row["source_room_id"],
                    "recipient_room_at_source": row["recipient_room_at_source"],
                    "recipient_room_at_response": row["recipient_room_at_response"],
                    "history_search_event_ids": row["history_search_event_ids"],
                    "automated_class_hidden_during_manual_review": True,
                    "manual_temporal_label": None,
                    "manual_eligibility_label": None,
                    "manual_room_reconstruction_correct": None,
                    "manual_notes": None,
                }
            )
    # The blinded development mix contains only three future-source placebos. Draw the remaining
    # ineligible audit items from the full matched-control pool without changing the 60-unit set.
    current_ineligible = sum(row["audit_stratum"] == "ineligible" for row in selected)
    if current_ineligible < quotas["ineligible"]:
        controls = pq.read_table(PROCESSED / "matched_controls_v2.parquet").to_pylist()
        existing = {
            row["source_event_id"] for row in selected if row["audit_stratum"] == "ineligible"
        }
        for row in sorted(
            (row for row in controls if row["temporal_placebo"]),
            key=lambda item: item["control_id"],
        ):
            if row["source_event_id"] in existing:
                continue
            selected.append(
                {
                    "audit_stratum": "ineligible",
                    "episode_id": f"audit_{row['control_id']}",
                    "source_event_id": row["source_event_id"],
                    "response_event_id": row["response_event_id"],
                    "source_timestamp": row["source_timestamp"],
                    "response_completion_timestamp": row["response_timestamp"],
                    "source_room_id": row["room_id"],
                    "recipient_room_at_source": row["room_id"],
                    "recipient_room_at_response": row["room_id"],
                    "history_search_event_ids": "[]",
                    "automated_class_hidden_during_manual_review": True,
                    "manual_temporal_label": None,
                    "manual_eligibility_label": None,
                    "manual_room_reconstruction_correct": None,
                    "manual_notes": None,
                }
            )
            existing.add(row["source_event_id"])
            if (
                sum(item["audit_stratum"] == "ineligible" for item in selected)
                >= quotas["ineligible"]
            ):
                break
    path = REPORTS / "eligibility_audit_sample_v2.parquet"
    # Let Arrow infer nullable reviewer columns.
    import pyarrow as pa

    pq.write_table(pa.Table.from_pylist(selected), path, compression="zstd")
    available = Counter(row["audit_stratum"] for row in selected)
    result = {
        "artifact": str(path),
        "available_counts": dict(available),
        "required_counts": quotas,
        "automated_sample_complete": all(available[key] >= value for key, value in quotas.items()),
        "manual_review_complete": False,
        "featured_incidents_audited_separately": True,
        "natural_ambiguous_pair_shortfall_reason": (
            None
            if available["concurrent_or_ambiguous"] >= quotas["concurrent_or_ambiguous"]
            else "No distinct cross-agent chat messages share an exact exported timestamp, and model-call intervals are absent; ambiguity logic is covered by synthetic tests rather than fabricated observational pairs."
        ),
    }
    (REPORTS / "eligibility_audit_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def verify_v2() -> dict[str, Any]:
    expected = [
        "temporal_relations_v2.parquet",
        "response_eligibility_v2.parquet",
        "claims_v2.parquet",
        "claim_expressions_v2.parquet",
        "evidence_lineage_v2.parquet",
        "claim_relevant_action_windows_v2.parquet",
        "memory_deltas_v2.parquet",
        "third_party_expression_candidates_v2.parquet",
        "matched_controls_v2.parquet",
        "blocked_permutations_v2.parquet",
        "holdout_episode_clusters_v2.parquet",
        "featured_case_traces_v2.parquet",
    ]
    missing = [name for name in expected if not (PROCESSED / name).exists()]
    units = (
        _read_csv(EPISODES / "development_units_v2.csv")
        if (EPISODES / "development_units_v2.csv").exists()
        else []
    )
    unit_counts = Counter(row["unit_origin"] for row in units)
    candidate_count = unit_counts["retrieved_candidate"]
    control_count = len(units) - candidate_count
    ordinary_control_count = sum(
        unit_counts[name]
        for name in ("same_room_local_source_control", "shared_artifact_convergence_control")
    )
    placebo_count = sum(
        unit_counts[name] for name in ("source_identity_placebo", "temporal_placebo")
    )
    temporal = (
        pq.read_table(PROCESSED / "temporal_relations_v2.parquet").to_pylist()
        if not missing
        else []
    )
    eligibility = (
        pq.read_table(PROCESSED / "response_eligibility_v2.parquet").to_pylist()
        if not missing
        else []
    )
    permutations = (
        pq.read_table(PROCESSED / "blocked_permutations_v2.parquet").num_rows
        if (PROCESSED / "blocked_permutations_v2.parquet").exists()
        else 0
    )
    holdout = (
        pq.read_table(PROCESSED / "holdout_episode_clusters_v2.parquet").to_pylist()
        if (PROCESSED / "holdout_episode_clusters_v2.parquet").exists()
        else []
    )
    controls = (
        pq.read_table(PROCESSED / "matched_controls_v2.parquet").to_pylist()
        if (PROCESSED / "matched_controls_v2.parquet").exists()
        else []
    )
    action_table = (
        pq.read_table(PROCESSED / "claim_relevant_action_windows_v2.parquet")
        if (PROCESSED / "claim_relevant_action_windows_v2.parquet").exists()
        else None
    )
    memory_table = (
        pq.read_table(PROCESSED / "memory_deltas_v2.parquet")
        if (PROCESSED / "memory_deltas_v2.parquet").exists()
        else None
    )
    third_party_table = (
        pq.read_table(PROCESSED / "third_party_expression_candidates_v2.parquet")
        if (PROCESSED / "third_party_expression_candidates_v2.parquet").exists()
        else None
    )
    prohibited_v2_columns = {
        "later_action",
        "memory_update",
        "visibility_confidence",
        "retransmission",
    }
    found_prohibited = {}
    for name in expected:
        path = PROCESSED / name
        if path.exists():
            overlap = prohibited_v2_columns & set(pq.read_schema(path).names)
            if overlap:
                found_prohibited[name] = sorted(overlap)
    required_schema_fields = {
        "temporal_relations_v2.parquet": {
            "source_started_at",
            "source_completed_at",
            "response_started_at",
            "response_completed_at",
            "source_timestamp_semantics",
            "source_timestamp_provenance",
            "temporal_relation",
            "ordering_uncertainty_reason",
        },
        "response_eligibility_v2.parquet": {
            "source_event_id",
            "response_event_id",
            "same_room_at_response",
            "global_channel_at_response",
            "within_known_message_cap",
            "room_transition_between_events",
            "history_search_available",
            "shared_artifact_available",
            "direct_source_reference",
            "exact_prompt_inclusion",
            "peer_message_eligible",
            "common_artifact_access",
            "eligibility_class",
        },
        "claims_v2.parquet": {
            "claim_id",
            "normalized_proposition",
            "referent_or_artifact",
            "truth_status",
            "first_observed_expression",
            "source_agent",
            "source_stance",
            "supporting_evidence_ids",
            "upstream_claim_ids",
            "agreeing_message_count",
            "independent_evidence_source_count",
        },
        "memory_deltas_v2.parquet": {
            "memory_before_id",
            "memory_after_id",
            "added_spans",
            "removed_or_rewritten_spans",
            "added_span_survives_one_snapshot",
            "added_span_survives_two_snapshots",
            "memory_delta_label",
        },
        "third_party_expression_candidates_v2.parquet": {
            "original_source_agent_id",
            "candidate_reexpressing_agent_id",
            "new_recipient_agent_ids",
            "same_proposition_label",
            "stance_label",
            "third_party_retransmission_label",
        },
    }
    missing_schema_fields = {
        name: sorted(fields - set(pq.read_schema(PROCESSED / name).names))
        for name, fields in required_schema_fields.items()
        if (PROCESSED / name).exists() and fields - set(pq.read_schema(PROCESSED / name).names)
    }
    matched_candidate_ids = {
        row["matched_candidate_episode_id"]
        for row in units
        if row["unit_origin"] == "retrieved_candidate"
    }
    controls_with_match = {row["matched_candidate_episode_id"] for row in controls}
    third_party_structure_valid = True
    if third_party_table is not None:
        for row in third_party_table.to_pylist():
            recipients = set(json.loads(row["new_recipient_agent_ids"]))
            if (
                not recipients
                or row["original_source_agent_id"] in recipients
                or row["candidate_reexpressing_agent_id"] in recipients
            ):
                third_party_structure_valid = False
                break
    permutation_report_path = REPORTS / "blocked_permutations_v2.json"
    permutation_report = (
        json.loads(permutation_report_path.read_text(encoding="utf-8"))
        if permutation_report_path.exists()
        else {}
    )
    permutation_rows = (
        pq.read_table(PROCESSED / "blocked_permutations_v2.parquet").to_pylist()
        if (PROCESSED / "blocked_permutations_v2.parquet").exists()
        else []
    )
    permutation_logical_sha = hashlib.sha256(
        json.dumps(permutation_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    timestamp_spec = (ROOT / "docs" / "timestamp_semantics_v2.md").read_text(encoding="utf-8")
    timestamp_tables_documented = all(f"`{table}`" in timestamp_spec for table in CORE_TABLES)
    screenshot_rows = (
        _read_csv(REPORTS / "featured_screenshot_manifest_v2.csv")
        if (REPORTS / "featured_screenshot_manifest_v2.csv").exists()
        else []
    )
    selected_screenshots = [
        row for row in screenshot_rows if row["selected_for_retrieval"] == "True"
    ]
    screenshot_integrity = bool(selected_screenshots) and all(
        row.get("retrieval_status") == "downloaded"
        and bool(row.get("local_path"))
        and (ROOT / row["local_path"]).exists()
        and bool(row.get("sha256"))
        and sha256_file(ROOT / row["local_path"]) == row["sha256"]
        for row in selected_screenshots
    )
    case_bundles = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (EPISODES / "v2_case_bundles").glob("*.json")
    ]
    case_classifications = {
        bundle.get("provisional_framework_classification") for bundle in case_bundles
    }
    codebook_path = ANNOTATIONS / "annotation_codebook_v2.md"
    label_templates = [
        ANNOTATIONS / "annotator_1_labels.csv",
        ANNOTATIONS / "annotator_2_labels.csv",
    ]
    label_templates_blank = all(
        path.exists()
        and len(_read_csv(path)) == 60
        and all(
            not value
            for row in _read_csv(path)
            for key, value in row.items()
            if key != "blind_unit_id"
        )
        for path in label_templates
    )
    checks = {
        "all_expected_artifacts_exist": not missing,
        "development_has_60_units": len(units) == 60,
        "development_has_30_candidates": candidate_count == 30,
        "development_has_30_controls_or_placebos": control_count == 30,
        "development_has_20_local_controls": ordinary_control_count == 20,
        "development_has_10_placebos": placebo_count == 10,
        "every_development_candidate_has_local_control": matched_candidate_ids
        <= controls_with_match,
        "temporal_row_per_unit": len(temporal) == len(units),
        "event_order_never_causal": all(
            not row["event_order_used_as_causal_evidence"] for row in temporal
        ),
        "eligibility_row_per_unit": len(eligibility) == len(units),
        "eligibility_uses_exact_response_ids": {row["response_event_id"] for row in eligibility}
        == {row["recipient_response"] for row in units},
        "blocked_permutations_500": permutations == 500,
        "holdout_semantic_content_unopened": all(
            not row["semantic_content_opened"] for row in holdout
        ),
        "no_retired_proxy_columns_in_v2": not found_prohibited,
        "required_v2_schema_fields_present": not missing_schema_fields,
        "timestamp_semantics_cover_every_exported_table": timestamp_tables_documented,
        "action_labels_remain_human_unadjudicated": action_table is not None
        and action_table["claim_relevant_action_label"].null_count == action_table.num_rows,
        "memory_deltas_cover_all_units": memory_table is not None and memory_table.num_rows == 60,
        "memory_labels_remain_human_unadjudicated": memory_table is not None
        and memory_table["memory_delta_label"].null_count == memory_table.num_rows,
        "third_party_candidates_enforce_new_recipient_structure": third_party_structure_valid,
        "third_party_labels_remain_human_unadjudicated": third_party_table is not None
        and third_party_table["third_party_retransmission_label"].null_count
        == third_party_table.num_rows,
        "annotation_packet_count_60": len(list((ANNOTATIONS / "packets").glob("*.json.gz"))) == 60,
        "annotation_key_is_private_only": (ANNOTATIONS / "private" / "blinding_key.csv").exists()
        and not (ANNOTATIONS / "blinding_key.csv").exists(),
        "annotation_codebook_and_blank_dual_templates_exist": codebook_path.exists()
        and label_templates_blank,
        "five_case_bundles": len(list((EPISODES / "v2_case_bundles").glob("*.json"))) == 5,
        "five_cases_receive_distinct_framework_classifications": len(case_classifications) == 5,
        "featured_screenshots_downloaded_and_hashed": len(selected_screenshots) == 25
        and screenshot_integrity,
        "permutation_logical_fingerprint_matches": permutation_report.get("logical_sha256")
        == permutation_logical_sha,
        "permutation_rng_and_version_recorded": bool(permutation_report.get("rng"))
        and bool(permutation_report.get("numpy_version")),
    }
    leak_terms = (
        "dev_candidate_",
        "dev_control_",
        "retrieved_candidate",
        "matching_score",
        "similarity_score",
    )
    packet_leaks = []
    for packet in (ANNOTATIONS / "packets").glob("*.json.gz"):
        with gzip.open(packet, "rt", encoding="utf-8") as handle:
            content = handle.read().lower()
        present = [term for term in leak_terms if term in content]
        if present:
            packet_leaks.append({"packet": packet.name, "terms": present})
    checks["annotation_packets_hide_status_and_scores"] = not packet_leaks
    terminology = audit_retired_terminology()
    checks["retired_terminology_audited"] = terminology["passes"]
    reliability = compute_reliability_if_available()
    result = {
        "status": "automated_complete_human_annotation_required"
        if all(checks.values())
        else "automated_verification_failed",
        "checks": checks,
        "missing_artifacts": missing,
        "prohibited_columns": found_prohibited,
        "missing_schema_fields": missing_schema_fields,
        "annotation_packet_leaks": packet_leaks,
        "unit_origin_counts": dict(unit_counts),
        "human_reliability": reliability,
        "gate_1": "blocked_pending_human_annotation",
    }
    (REPORTS / "verification_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_observational_status(result)
    _write_completion_audit(result)
    _write_environment_and_artifact_manifest()
    return result


def _write_observational_status(verification: dict[str, Any]) -> None:
    text = "\n".join(
        [
            "# Observational analysis v2 status",
            "",
            "**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**",
            "",
            f"Automated status: **{verification['status']}**.",
            "",
            "The v2 pipeline has assembled partial-order relations, exact-response information eligibility, claim/evidence-lineage objects, local controls, raw action windows, memory deltas, structurally valid third-party expression candidates, blinded annotation packets, and qualitative case bundles.",
            "",
            "No proposition, stance, claim-relevant action, memory-recording, retransmission, operational-cascade, or prevalence finding is reported yet. Those constructs require blinded human annotation.",
            "",
            "Gate 1 remains **blocked pending two-reviewer annotation and reliability analysis**. If reliability or matched-control discrimination fails, the observational contribution remains a telemetry audit and qualitative casebook.",
            "",
        ]
    )
    (REPORTS / "observational_report_v2.md").write_text(text, encoding="utf-8")


def _write_completion_audit(verification: dict[str, Any]) -> None:
    checks_ok = all(verification["checks"].values())
    rows = [
        (
            "Freeze the new contract",
            "complete" if (ROOT / "research_spec_v2.md").exists() else "missing",
            "research_spec_v2.md",
        ),
        (
            "Deprecate invalid v1 metrics",
            "complete" if verification["checks"]["retired_terminology_audited"] else "failed",
            "reports/terminology_audit_v2.csv and legacy notices",
        ),
        (
            "Document timestamp semantics",
            "complete"
            if verification["checks"]["timestamp_semantics_cover_every_exported_table"]
            else "failed",
            "docs/timestamp_semantics_v2.md",
        ),
        (
            "Implement partial-order relations",
            "complete" if verification["checks"]["event_order_never_causal"] else "failed",
            "data/processed/temporal_relations_v2.parquet and synthetic tests",
        ),
        (
            "Response-specific eligibility",
            "complete"
            if verification["checks"]["eligibility_uses_exact_response_ids"]
            else "failed",
            "data/processed/response_eligibility_v2.parquet",
        ),
        (
            "Claim/evidence-lineage schema",
            "complete" if verification["checks"]["required_v2_schema_fields_present"] else "failed",
            "claims_v2, claim_expressions_v2, evidence_lineage_v2",
        ),
        (
            "Claim-relevant trace extraction",
            "complete"
            if verification["checks"]["action_labels_remain_human_unadjudicated"]
            else "failed",
            "claim_relevant_action_windows_v2.parquet",
        ),
        (
            "Memory deltas",
            "complete" if verification["checks"]["memory_deltas_cover_all_units"] else "failed",
            "memory_deltas_v2.parquet",
        ),
        (
            "Third-party retransmission eligibility",
            "complete"
            if verification["checks"]["third_party_candidates_enforce_new_recipient_structure"]
            else "failed",
            "third_party_expression_candidates_v2.parquet",
        ),
        (
            "Matched controls and 500 permutations",
            "complete"
            if verification["checks"]["blocked_permutations_500"]
            and verification["checks"]["every_development_candidate_has_local_control"]
            else "failed",
            "matched_controls_v2.parquet and blocked_permutations_v2.parquet",
        ),
        (
            "Holdout repair",
            "complete" if verification["checks"]["holdout_semantic_content_unopened"] else "failed",
            "holdout_episode_clusters_v2.parquet",
        ),
        (
            "Development annotation packets",
            "complete"
            if verification["checks"]["annotation_packets_hide_status_and_scores"]
            else "failed",
            "annotations/v2: 60 packets, codebook, two blank templates",
        ),
        (
            "Required case reconstructions",
            "complete" if verification["checks"]["five_case_bundles"] else "failed",
            "episodes/v2_case_bundles and featured_case_traces_v2.parquet",
        ),
        (
            "Human reliability measurement",
            "requires_human_review",
            "two blank annotation templates; AC1/kappa implementation ready",
        ),
        (
            "Final Gate 1 assessment",
            "requires_human_review",
            "reports/observational_report_v2.md; no substantive observational finding emitted",
        ),
    ]
    audit = {
        "automated_scope_complete": checks_ok,
        "human_boundary_reached": verification["human_reliability"]["status"]
        == "blocked_human_labels_missing",
        "gate_1": verification["gate_1"],
        "requirements": [
            {"work": work, "status": status, "evidence": evidence}
            for work, status, evidence in rows
        ],
    }
    (REPORTS / "completion_audit_v2.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )


def _write_environment_and_artifact_manifest() -> None:
    from .config import DATASET_ID, DATASET_REVISION, RANDOM_SEED

    environment = {
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "random_seed": RANDOM_SEED,
        "python": sys.version,
        "platform": platform.platform(),
        "duckdb": duckdb.__version__,
        "pyarrow": pyarrow.__version__,
        "numpy": np.__version__,
        "pytz": pytz.__version__,
        "permutation_rng": "numpy.random.default_rng(PCG64)",
    }
    (REPORTS / "environment_v2.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )
    artifacts = []
    for path in sorted(PROCESSED.glob("*_v2.parquet")):
        artifacts.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "rows": pq.read_metadata(path).num_rows,
                "schema_fields": pq.read_schema(path).names,
            }
        )
    packet_hashes = [
        {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
        for path in sorted((ANNOTATIONS / "packets").glob("*.json.gz"))
    ]
    packet_logical_sha = hashlib.sha256(
        json.dumps(packet_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = {
        "environment": environment,
        "processed_artifacts": artifacts,
        "annotation_packet_count": len(packet_hashes),
        "annotation_packet_set_sha256": packet_logical_sha,
        "selected_screenshot_count": len(
            [
                row
                for row in _read_csv(REPORTS / "featured_screenshot_manifest_v2.csv")
                if row["selected_for_retrieval"] == "True"
            ]
        ),
    }
    (REPORTS / "artifact_manifest_v2.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def run_v2_pipeline(include_screenshot_download: bool = True) -> dict[str, Any]:
    ensure_output_dirs()
    holdout, cluster_index = build_holdout_clusters()
    controls = build_matched_controls()
    temporal = build_temporal_relations()
    eligibility = build_response_eligibility()
    claims = build_claim_lineage()
    actions = build_action_windows(cluster_index)
    memories = build_memory_deltas()
    third_party = build_third_party_candidates()
    permutations = build_blocked_permutations(500)
    audit_sample = build_eligibility_audit_sample()
    cases = build_featured_cases()
    screenshots = (
        download_featured_screenshots() if include_screenshot_download else {"status": "skipped"}
    )
    annotations = build_annotation_packets()
    terminology = audit_retired_terminology()
    verification = verify_v2()
    return {
        "holdout": holdout,
        "controls": controls,
        "temporal": temporal,
        "eligibility": eligibility,
        "claims": claims,
        "actions": actions,
        "memory_deltas": memories,
        "third_party": third_party,
        "permutations": permutations,
        "eligibility_audit": audit_sample,
        "cases": cases,
        "screenshots": screenshots,
        "annotations": annotations,
        "terminology": terminology,
        "verification": verification,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
