from __future__ import annotations

import gzip
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pyarrow
from huggingface_hub import HfApi, snapshot_download

from .config import DATASET_ID, DATASET_REVISION, RAW, ROOT
from .util import sha256_file

ALLOW_PATTERNS = [
    "*.jsonl.gz",
    "README.md",
    "SCHEMA.md",
    "CHANGELOG.md",
    "manifest.json",
    "example.py",
]


def download_snapshot() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        DATASET_ID,
        repo_type="dataset",
        revision=DATASET_REVISION,
        allow_patterns=ALLOW_PATTERNS,
        local_dir=RAW,
        token=True,
    )


def build_manifest() -> dict:
    api = HfApi()
    info = api.dataset_info(DATASET_ID, revision=DATASET_REVISION, files_metadata=True, token=True)
    upstream = {}
    for sibling in info.siblings:
        if (
            sibling.rfilename.startswith("images/")
            or sibling.rfilename == "village-transcript.json"
        ):
            continue
        if not any(
            sibling.rfilename.endswith(pattern.removeprefix("*")) for pattern in ALLOW_PATTERNS
        ):
            continue
        lfs = getattr(sibling, "lfs", None)
        upstream[sibling.rfilename] = {
            "bytes": sibling.size,
            "upstream_sha256": getattr(lfs, "sha256", None),
        }

    files = []
    for path in sorted(RAW.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        row_count = None
        if path.name.endswith(".jsonl.gz"):
            row_count = _count_gzip_lines(path)
        files.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "upstream_sha256": upstream.get(path.name, {}).get("upstream_sha256"),
                "row_count": row_count,
            }
        )
    manifest = {
        "dataset_id": DATASET_ID,
        "revision": DATASET_REVISION,
        "upstream_last_modified": info.last_modified.isoformat() if info.last_modified else None,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "scope": "all exported JSONL tables and documentation; transcript and screenshots excluded",
        "random_seed": 20260814,
        "software": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "duckdb": duckdb.__version__,
            "pyarrow": pyarrow.__version__,
        },
        "files": files,
    }
    target = ROOT / "data" / "raw_manifest" / "dataset_manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _count_gzip_lines(path: Path) -> int:
    count = 0
    with gzip.open(path, "rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            count += chunk.count(b"\n")
    return count
