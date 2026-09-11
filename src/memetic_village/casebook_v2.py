from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import EPISODES, PROCESSED, RAW, REPORTS, ROOT, ensure_output_dirs
from .outcomes_v2 import KNOWN_PROPOSITIONS
from .temporal_v2 import assess_temporal_relation, emitted_message_interval
from .util import iso_utc, parse_timestamp, sha256_file, stream_jsonl

CASE_TRACE_SCHEMA = pa.schema(
    [
        ("case_id", pa.string()),
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
    ]
)


def _messages(ids: set[str]) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row for row in stream_jsonl(RAW / "chat_messages.jsonl.gz") if row["id"] in ids
    }


def build_featured_cases() -> dict[str, Any]:
    ensure_output_dirs()
    bundle_dir = EPISODES / "v2_case_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    with (REPORTS / "known_incident_reconstructions.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        known_rows = list(csv.DictReader(handle))
    with (EPISODES / "candidate_registry.csv").open(newline="", encoding="utf-8") as handle:
        registry = list(csv.DictReader(handle))
    development_original_ids = {
        row["matched_candidate_episode_id"]
        for row in _read_csv(EPISODES / "development_units_v2.csv")
        if row["unit_origin"] == "retrieved_candidate"
    }
    correction = next(
        (
            row
            for row in registry
            if row["episode_id"] in development_original_ids
            and row["content_category"] == "correction_or_safety_promoting"
            and row["discovery_method"] != "known_incident_reconstruction"
        ),
        None,
    )
    routine = next(
        (
            row
            for row in registry
            if row["episode_id"] in development_original_ids
            and row["content_category"]
            in {"tool_use_convention", "task_strategy", "factual_or_environmental_claim"}
            and row["discovery_method"] != "known_incident_reconstruction"
        ),
        None,
    )
    all_message_ids = {row["raw_message_id"] for row in known_rows}
    for row in (correction, routine):
        if row:
            all_message_ids.update({row["source_message_id"], row["recipient_response_message_id"]})
    message_map = _messages(all_message_ids)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in known_rows:
        grouped[row["incident_id"]].append(row)
    bundles: list[dict[str, Any]] = []
    classifications = {
        "known_01_contact_list_hallucination": "cross_agent_claim_recurrence_with_later_correction_candidate",
        "known_02_trapped_gemini": "same_agent_operational_incident_not_cross_agent_recurrence",
        "known_03_whitespace_egg": "shared_artifact_convergence_not_independent_message_evidence",
    }
    for incident_id, checkpoints in grouped.items():
        checkpoints.sort(key=lambda row: int(row["checkpoint_order"]))
        proposition, truth = KNOWN_PROPOSITIONS[incident_id]
        expressions = []
        temporal = []
        for checkpoint in checkpoints:
            raw = message_map.get(checkpoint["raw_message_id"], {})
            expressions.append(
                {
                    "checkpoint_role": checkpoint["checkpoint_role"],
                    "canonical_event_id": checkpoint["canonical_event_id"],
                    "raw_message_id": checkpoint["raw_message_id"],
                    "actor_agent_id": checkpoint["actor_agent_id"],
                    "timestamp": iso_utc(parse_timestamp(raw.get("created_at"))),
                    "text": raw.get("content") or "",
                    "stance": None,
                    "evidence_source_type": None,
                }
            )
        for left, right in pairwise(expressions):
            assessment = assess_temporal_relation(
                emitted_message_interval(
                    left["canonical_event_id"], parse_timestamp(left["timestamp"])
                ),
                emitted_message_interval(
                    right["canonical_event_id"], parse_timestamp(right["timestamp"])
                ),
            )
            temporal.append(
                {
                    "source_event_id": left["canonical_event_id"],
                    "response_event_id": right["canonical_event_id"],
                    "relation": assessment.relation,
                    "uncertainty_reason": assessment.reason,
                }
            )
        bundles.append(
            {
                "case_id": incident_id,
                "case_role": "public_incident_qualitative_only",
                "normalized_proposition": proposition,
                "truth_status": truth,
                "provisional_framework_classification": classifications[incident_id],
                "expressions": expressions,
                "temporal_assessments": temporal,
                "agreeing_message_count": None,
                "independent_evidence_source_count": None,
                "claim_relevant_action": None,
                "memory_delta_recording": None,
                "third_party_retransmission": None,
                "annotation_status": "human_required",
                "detector_validation_item": False,
            }
        )
    for case_id, role, row, classification in (
        (
            "development_correction_case",
            "retrieved_correction_case",
            correction,
            "candidate_correction_cascade_requires_raw_trace_adjudication",
        ),
        (
            "development_routine_shared_task_case",
            "matched_routine_case",
            routine,
            "routine_shared_task_or_artifact_convergence_control",
        ),
    ):
        if row is None:
            continue
        source = message_map[row["source_message_id"]]
        response = message_map[row["recipient_response_message_id"]]
        assessment = assess_temporal_relation(
            emitted_message_interval(row["seed_event"], parse_timestamp(source.get("created_at"))),
            emitted_message_interval(
                row["recipient_response"], parse_timestamp(response.get("created_at"))
            ),
        )
        bundles.append(
            {
                "case_id": case_id,
                "case_role": role,
                "source_registry_episode_id": row["episode_id"],
                "normalized_proposition": None,
                "truth_status": "unadjudicated",
                "provisional_framework_classification": classification,
                "expressions": [
                    {
                        "checkpoint_role": "candidate_source",
                        "canonical_event_id": row["seed_event"],
                        "raw_message_id": row["source_message_id"],
                        "actor_agent_id": row["source_agent"],
                        "timestamp": iso_utc(parse_timestamp(source.get("created_at"))),
                        "text": source.get("content") or "",
                        "stance": None,
                    },
                    {
                        "checkpoint_role": "candidate_response",
                        "canonical_event_id": row["recipient_response"],
                        "raw_message_id": row["recipient_response_message_id"],
                        "actor_agent_id": row["recipient_agent"],
                        "timestamp": iso_utc(parse_timestamp(response.get("created_at"))),
                        "text": response.get("content") or "",
                        "stance": None,
                    },
                ],
                "temporal_assessments": [
                    {
                        "source_event_id": row["seed_event"],
                        "response_event_id": row["recipient_response"],
                        "relation": assessment.relation,
                        "uncertainty_reason": assessment.reason,
                    }
                ],
                "agreeing_message_count": None,
                "independent_evidence_source_count": None,
                "claim_relevant_action": None,
                "memory_delta_recording": None,
                "third_party_retransmission": None,
                "annotation_status": "human_required",
                "detector_validation_item": True,
            }
        )
    trace_rows = _build_case_traces(bundles)
    trace_path = PROCESSED / "featured_case_traces_v2.parquet"
    pq.write_table(
        pa.Table.from_pylist(trace_rows, schema=CASE_TRACE_SCHEMA), trace_path, compression="zstd"
    )
    for bundle in bundles:
        bundle["raw_trace_artifact"] = str(trace_path.relative_to(ROOT))
        bundle["raw_trace_filter"] = {"case_id": bundle["case_id"]}
        (bundle_dir / f"{bundle['case_id']}.json").write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    screenshot_rows = []
    seen_per_case: Counter[str] = Counter()
    for row in trace_rows:
        if not row["visual_state_may_matter"] or not row["screenshot_turn_id"]:
            continue
        selected = seen_per_case[row["case_id"]] < 5
        if selected:
            seen_per_case[row["case_id"]] += 1
        turn_id = row["screenshot_turn_id"]
        screenshot_rows.append(
            {
                "case_id": row["case_id"],
                "turn_id": turn_id,
                "hf_path": f"images/computer-use-turns/{turn_id[:2]}/{turn_id}.png",
                "selected_for_retrieval": selected,
                "retrieval_status": "pending_selective_download" if selected else "not_selected",
                "reason": "visual action inside featured-case raw window",
            }
        )
    if screenshot_rows:
        _write_csv(REPORTS / "featured_screenshot_manifest_v2.csv", screenshot_rows)
    result = {
        "bundle_directory": str(bundle_dir),
        "case_count": len(bundles),
        "public_incident_count": sum(not bundle["detector_validation_item"] for bundle in bundles),
        "development_case_count": sum(bundle["detector_validation_item"] for bundle in bundles),
        "trace_event_count": len(trace_rows),
        "selected_screenshot_count": sum(row["selected_for_retrieval"] for row in screenshot_rows),
        "human_adjudication_complete": False,
    }
    (REPORTS / "casebook_v2.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def download_featured_screenshots() -> dict[str, Any]:
    """Download only preselected visual-state frames from the pinned dataset revision."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError, LocalEntryNotFoundError

    from .config import DATASET_ID, DATASET_REVISION

    manifest_path = REPORTS / "featured_screenshot_manifest_v2.csv"
    if not manifest_path.exists():
        result = {
            "selected": 0,
            "downloaded": 0,
            "failed": 0,
            "reason": "no_visual_frames_selected",
        }
        (REPORTS / "featured_screenshot_download_v2.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result
    rows = _read_csv(manifest_path)
    target = ROOT / "data" / "raw_manifest" / "selected_screenshots_v2"
    target.mkdir(parents=True, exist_ok=True)
    for row in rows:
        row.setdefault("local_path", "")
        row.setdefault("sha256", "")
        row.setdefault("error", "")
    for row in rows:
        if row["selected_for_retrieval"] != "True":
            continue
        try:
            local = hf_hub_download(
                repo_id=DATASET_ID,
                repo_type="dataset",
                revision=DATASET_REVISION,
                filename=row["hf_path"],
                local_dir=target,
            )
            row["retrieval_status"] = "downloaded"
            row["local_path"] = str(Path(local).relative_to(ROOT))
            row["sha256"] = sha256_file(Path(local))
            row["error"] = ""
        except (HfHubHTTPError, LocalEntryNotFoundError, OSError, ValueError) as exc:
            row["retrieval_status"] = "failed"
            row["local_path"] = ""
            row["sha256"] = ""
            row["error"] = f"{type(exc).__name__}: {exc}"
    _write_csv(manifest_path, rows)
    selected = [row for row in rows if row["selected_for_retrieval"] == "True"]
    result = {
        "selected": len(selected),
        "downloaded": sum(row["retrieval_status"] == "downloaded" for row in selected),
        "failed": sum(row["retrieval_status"] == "failed" for row in selected),
        "dataset_revision": DATASET_REVISION,
        "external_contact_or_communication": False,
    }
    (REPORTS / "featured_screenshot_download_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _build_case_traces(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    con = duckdb.connect()
    canonical_rows = []
    needed: dict[str, set[str]] = defaultdict(set)
    for bundle in bundles:
        expressions = bundle["expressions"]
        times = [parse_timestamp(item["timestamp"]) for item in expressions]
        times = [time for time in times if time]
        actors = sorted({item["actor_agent_id"] for item in expressions})
        if not times:
            continue
        start, end = min(times) - timedelta(minutes=30), max(times) + timedelta(hours=24)
        results = con.execute(
            """
            SELECT canonical_event_id, timestamp, event_type, actor_agent_id, source_table,
                   source_record_id, content_reference, artifact_reference
            FROM read_parquet(?)
            WHERE actor_agent_id IN (SELECT unnest(?)) AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp, canonical_event_id
            """,
            [str(PROCESSED / "canonical_events.parquet"), actors, start, end],
        ).fetchall()
        for values in results:
            event = dict(
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
            event["case_id"] = bundle["case_id"]
            canonical_rows.append(event)
            needed[event["source_table"]].add(event["source_record_id"])
    con.close()
    payloads: dict[tuple[str, str], tuple[str, str | None, bool]] = {}
    for table in ("events", "computer_use_turns", "claude_code_messages"):
        ids = needed.get(table, set())
        if not ids:
            continue
        for raw in stream_jsonl(RAW / f"{table}.jsonl.gz"):
            if raw.get("id") not in ids:
                continue
            screenshot = None
            visual = False
            if table == "computer_use_turns":
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
                screenshot = raw["id"]
                payload = {
                    "agent_action": raw.get("agent_action"),
                    "output": raw.get("output"),
                    "error": raw.get("error"),
                    "system": raw.get("system"),
                    "screenshot_is_redacted": raw.get("screenshot_is_redacted"),
                }
            elif table == "events":
                payload = raw.get("data")
            else:
                payload = raw.get("content")
            payloads[(table, raw["id"])] = (
                json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
                screenshot,
                visual,
            )
    rows = []
    for event in canonical_rows:
        payload, screenshot, visual = payloads.get(
            (event["source_table"], event["source_record_id"]), ("null", None, False)
        )
        rows.append(
            {
                **event,
                "raw_payload": payload,
                "screenshot_turn_id": screenshot,
                "visual_state_may_matter": visual,
            }
        )
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
