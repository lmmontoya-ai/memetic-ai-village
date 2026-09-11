from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import PROCESSED, RANDOM_SEED, RAW, REPORTS, ROOT, ensure_output_dirs
from .util import parse_timestamp, stable_id, stream_jsonl

INACTIVITY_GAP = timedelta(hours=8)
WASHOUT = timedelta(hours=48)
FOLLOWUP = timedelta(days=7)


@dataclass(frozen=True)
class EpisodeCluster:
    cluster_id: str
    room_id: str
    started_at: datetime
    ended_at: datetime
    message_count: int


class EpisodeClusterIndex:
    def __init__(self) -> None:
        by_room: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        for row in stream_jsonl(RAW / "chat_messages.jsonl.gz"):
            timestamp = parse_timestamp(row.get("created_at"))
            if timestamp:
                by_room[row.get("room_id") or "__unknown__"].append((timestamp, row["id"]))
        self.clusters: list[EpisodeCluster] = []
        self.message_to_cluster: dict[str, str] = {}
        for room, messages in by_room.items():
            messages.sort()
            group: list[tuple[datetime, str]] = []
            for message in messages:
                if group and message[0] - group[-1][0] > INACTIVITY_GAP:
                    self._finish(room, group)
                    group = []
                group.append(message)
            if group:
                self._finish(room, group)
        self.by_id = {cluster.cluster_id: cluster for cluster in self.clusters}

    def _finish(self, room: str, group: list[tuple[datetime, str]]) -> None:
        cluster_id = stable_id(
            "episode_cluster_v2",
            room,
            group[0][0].isoformat(),
            group[-1][0].isoformat(),
            prefix="cl",
        )
        cluster = EpisodeCluster(cluster_id, room, group[0][0], group[-1][0], len(group))
        self.clusters.append(cluster)
        for _, message_id in group:
            self.message_to_cluster[message_id] = cluster_id

    def for_message(self, message_id: str) -> EpisodeCluster | None:
        cluster_id = self.message_to_cluster.get(message_id)
        return self.by_id.get(cluster_id) if cluster_id else None


HOLDOUT_CLUSTER_SCHEMA = pa.schema(
    [
        ("cluster_id", pa.string()),
        ("room_id", pa.string()),
        ("episode_started_at", pa.timestamp("us", tz="UTC")),
        ("episode_ended_at", pa.timestamp("us", tz="UTC")),
        ("message_count", pa.int64()),
        ("crosses_old_cutoff", pa.bool_()),
        ("after_48h_washout", pa.bool_()),
        ("has_7d_endpoint_followup", pa.bool_()),
        ("semantic_content_opened", pa.bool_()),
        ("pool_assignment", pa.string()),
        ("goal_context", pa.string()),
        ("goal_match_quality", pa.string()),
    ]
)


def _assignment(cluster_id: str) -> str:
    value = int(hashlib.sha256(f"{RANDOM_SEED}:{cluster_id}".encode()).hexdigest()[:16], 16)
    return "holdout_development_pool" if value % 5 == 0 else "holdout_evaluation_pool"


def build_holdout_clusters(
    output_path: Path | None = None,
) -> tuple[dict[str, Any], EpisodeClusterIndex]:
    """Build metadata-only clusters; this function never reads message content."""
    ensure_output_dirs()
    output_path = output_path or PROCESSED / "holdout_episode_clusters_v2.parquet"
    holdout = json.loads((ROOT / "data" / "raw_manifest" / "holdout.json").read_text())
    cutoff = parse_timestamp(holdout.get("cutoff"))
    if cutoff is None:
        raise ValueError("Holdout cutoff is missing or invalid")
    index = EpisodeClusterIndex()
    endpoint = max(cluster.ended_at for cluster in index.clusters)
    rows = []
    for cluster in index.clusters:
        if cluster.ended_at < cutoff:
            continue
        crosses = cluster.started_at < cutoff <= cluster.ended_at
        after_washout = cluster.started_at >= cutoff + WASHOUT
        followup = cluster.ended_at <= endpoint - FOLLOWUP
        rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "room_id": cluster.room_id,
                "episode_started_at": cluster.started_at,
                "episode_ended_at": cluster.ended_at,
                "message_count": cluster.message_count,
                "crosses_old_cutoff": crosses,
                "after_48h_washout": after_washout,
                "has_7d_endpoint_followup": followup,
                "semantic_content_opened": False,
                "pool_assignment": _assignment(cluster.cluster_id),
                "goal_context": None,
                "goal_match_quality": "unresolved_village_goal_table_absent",
            }
        )
    pq.write_table(
        pa.Table.from_pylist(rows, schema=HOLDOUT_CLUSTER_SCHEMA), output_path, compression="zstd"
    )
    eligible = [
        row
        for row in rows
        if not row["crosses_old_cutoff"]
        and row["after_48h_washout"]
        and row["has_7d_endpoint_followup"]
    ]
    result = {
        "artifact": str(output_path),
        "old_cutoff": holdout["cutoff"],
        "inactivity_gap_hours": 8,
        "washout_hours": 48,
        "endpoint_followup_days": 7,
        "holdout_cluster_count": len(rows),
        "eligible_cluster_count": len(eligible),
        "crossing_cluster_count": sum(row["crosses_old_cutoff"] for row in rows),
        "pool_counts": {
            name: sum(row["pool_assignment"] == name for row in eligible)
            for name in ("holdout_development_pool", "holdout_evaluation_pool")
        },
        "semantic_content_opened": False,
        "assignment_rule": "sha256(seed:cluster_id) modulo 5; complete clusters only",
    }
    (REPORTS / "holdout_design_v2.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result, index
