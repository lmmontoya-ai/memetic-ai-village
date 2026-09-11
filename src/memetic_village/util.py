from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'_-]+", re.IGNORECASE)


def stream_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path.name} line {line_number}: {exc}") from exc


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.rstrip("Z")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_utc(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(*parts: Any, prefix: str = "ev") -> str:
    payload = "\x1f".join("" if part is None else str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def safe_excerpt(text: str | None, limit: int = 180) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"https?://\S+", "[URL]", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace("[REDACTED]", "[REDACTED]")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def flatten_fields(
    record: dict[str, Any], prefix: str = "", depth: int = 0, max_depth: int = 2
) -> Iterator[tuple[str, Any]]:
    for key, value in record.items():
        name = f"{prefix}.{key}" if prefix else key
        yield name, value
        if isinstance(value, dict) and depth < max_depth and key not in {"output", "content"}:
            yield from flatten_fields(value, name, depth + 1, max_depth)
