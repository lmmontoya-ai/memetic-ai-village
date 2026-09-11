"""Check the proposed public files, local links, credentials, and the v2.2 freeze.

This is a conservative publication check, not a general-purpose secret detector.
It never reads ignored dataset files. Diagnostics name locations, never matched values.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GENERATED = {
    "data/raw_manifest/dataset_manifest.json",
    "data/raw_manifest/holdout.json",
    "episodes/README.md",
    "episodes/LEGACY_V1_INVALID_PROXY.md",
    "reports/README.md",
    "reports/public_results_v2_2.json",
    "reports/machine_annotation_preliminary_v2_2.md",
    "reports/pre_annotation_freeze_v2_2.json",
    "reports/verification_v2_2.json",
    "reports/protocol_integrity_review.json",
    "reports/yaml_blank_line_truth_audit_v2_2.json",
    "reports/repository_review.md",
}
PRIVATE_SUFFIXES = (
    ".parquet",
    ".duckdb",
    ".duckdb.wal",
    ".jsonl",
    ".jsonl.gz",
    ".json.gz",
    ".tar",
    ".tar.gz",
    ".zip",
    ".pem",
    ".key",
)
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "provider API key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{30,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")


def public_path_error(relative: str) -> str | None:
    path = PurePosixPath(relative)
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return "environment file"
    if relative.endswith(PRIVATE_SUFFIXES):
        return "bulk research data, archive, or key file"
    if any(part in {".venv", "__pycache__", "dist", "build"} for part in path.parts):
        return "local environment or build output"
    if path.parts[0] in {"data", "reports", "episodes", "annotations"}:
        if relative in PUBLIC_GENERATED:
            return None
        if (
            path.parts[0] == "annotations"
            and not any(
                part in {"machine", "packets", "private", "full_traces"} for part in path.parts
            )
            and (path.name == "README.md" or fnmatch.fnmatch(path.name, "annotation_codebook*.md"))
        ):
            return None
        return "research output is not on the public allowlist"
    return None


def secret_findings(text: str) -> list[tuple[str, int]]:
    return [
        (kind, text.count("\n", 0, match.start()) + 1)
        for kind, pattern in SECRET_PATTERNS.items()
        for match in pattern.finditer(text)
    ]


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def collect_files(root: Path, *, staged: bool) -> dict[str, bytes]:
    args = ["ls-files", "-z", "--cached"]
    if not staged:
        args.extend(["--others", "--exclude-standard"])
    names = sorted(set(git(root, *args).decode("utf-8").strip("\0").split("\0")) - {""})
    files = {}
    for name in names:
        path = root / name
        if public_path_error(name):
            # The name alone fails the audit. Never open a possibly restricted payload.
            files[name] = b""
        elif staged:
            files[name] = git(root, "show", f":{name}")
        elif path.is_file():
            files[name] = path.read_bytes()
    return files


def check_files(files: dict[str, bytes], *, check_freeze: bool = True) -> list[str]:
    errors = []
    for name, content in files.items():
        reason = public_path_error(name)
        if reason:
            errors.append(f"{name}: {reason}")
            continue
        if len(content) > 5 * 1024 * 1024:
            errors.append(f"{name}: file exceeds the 5 MiB public-file limit")
            continue
        if name.endswith(".png"):
            continue
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"{name}: unreviewed binary file")
            continue
        for kind, line in secret_findings(text):
            errors.append(f"{name}:{line}: possible {kind}")
        if name == "data_inventory.csv":
            header = next(csv.reader(io.StringIO(text)), [])
            expected = {
                "table",
                "field",
                "rows",
                "present",
                "missing",
                "null",
                "types",
                "primary_key",
                "interpretation",
            }
            if set(header) != expected:
                errors.append(
                    f"{name}: inventory must contain field statistics without sample values"
                )
        if name.endswith(".md"):
            prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            for match in LINK.finditer(prose):
                target = match.group(1).strip().strip("<>")
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                normalized = []
                for part in (PurePosixPath(name).parent / unquote(url.path)).parts:
                    if part == "..":
                        if normalized:
                            normalized.pop()
                    elif part != ".":
                        normalized.append(part)
                resolved = "/".join(normalized)
                if resolved not in files:
                    errors.append(f"{name}: link target is absent from public files: {target}")
    if check_freeze:
        record = "reports/pre_annotation_freeze_v2_2.json"
        review_name = "reports/protocol_integrity_review.json"
        review = json.loads(files[review_name]) if review_name in files else {}
        documented = review.get("mismatches", {})
        if record not in files:
            errors.append(f"{record}: missing freeze record")
        else:
            freeze = json.loads(files[record])
            for relative, expected in freeze["frozen_file_hashes"].items():
                relative = relative.replace("\\", "/")
                content = files.get(relative)
                actual = hashlib.sha256(content).hexdigest() if content is not None else None
                drift = documented.get(relative, {})
                reviewed_drift = (
                    review.get("status") == "original_freeze_mismatch"
                    and drift.get("original_sha256") == expected
                    and drift.get("reviewed_sha256") == actual
                    and actual is not None
                )
                if actual != expected and not reviewed_drift:
                    errors.append(f"{relative}: frozen bytes differ from v2.2 record")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Inspect all Git-index bytes only.")
    args = parser.parse_args()
    files = collect_files(ROOT, staged=args.staged)
    errors = check_files(files)
    if not args.staged:
        changed = git(ROOT, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        if changed:
            # A safe working copy must not conceal a restricted or secret-bearing staged version.
            errors.extend(
                f"index: {error}" for error in check_files(collect_files(ROOT, staged=True))
            )
    print(
        json.dumps(
            {
                "status": "fail" if errors else "pass",
                "scope": "git_index" if args.staged else "tracked_and_unignored_working_files",
                "public_file_count": len(files),
                "protocol_freeze_status": (
                    json.loads(files["reports/protocol_integrity_review.json"])["status"]
                    if "reports/protocol_integrity_review.json" in files
                    else "see_freeze_checks"
                ),
                "errors": sorted(set(errors)),
                "limitations": "Pattern checks cannot certify privacy or detect every credential format.",
            },
            indent=2,
        )
    )
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
