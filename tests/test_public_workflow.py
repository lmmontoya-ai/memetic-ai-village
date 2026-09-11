from __future__ import annotations

import gzip
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from memetic_village.preflight import protect_annotations

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_script("check_repository")
exporter = load_script("export_public_results")
analysis = load_script("analyze_machine_annotations_v2_2")


def test_blank_template_slots_are_not_counted_as_claims() -> None:
    rows = [
        {"event_id": "event-1", "atomic_proposition": "", "exact_claim_span": ""},
        {"event_id": "event-2", "atomic_proposition": "A factual claim", "exact_claim_span": "A"},
        {"event_id": "event-3", "atomic_proposition": " ", "exact_claim_span": " "},
    ]
    assert analysis.count_extracted_claims(rows) == 1


def test_no_claim_and_disagreement_have_distinct_denominators() -> None:
    result = analysis.rate_summary(
        [
            "positive",
            "negative",
            "abstention_or_disagreement",
            "ineligible_no_valid_claim_pair",
        ]
    )
    assert result["valid_claim_pair_unit_count"] == 3
    assert result["positive_rate_conditional_on_ascertainability"] == 0.5
    assert result["positive_lower_bound_among_valid_pairs"] == pytest.approx(1 / 3)
    assert result["positive_upper_bound_among_valid_pairs"] == pytest.approx(2 / 3)


def test_public_export_drops_unapproved_text_and_rejects_text_in_numeric_fields() -> None:
    public = json.loads((ROOT / "reports/public_results_v2_2.json").read_text())
    source = {key: public[key] for key in ("scope", "stage_a", "stage_a_to_b", "retrieval_results")}
    source["strict_two_judge_evidence_ladder"] = public["evidence_ladder"]
    source["reliability_diagnostics"] = {
        label: {**metric, "bootstrap_95_ci": {"gwet_ac1": metric["ac1_cluster_bootstrap_95_ci"]}}
        for label, metric in public["reliability_diagnostics"].items()
    }
    marker = "PRIVATE_SENTINEL_DO_NOT_EXPORT"
    source["raw_transcript"] = marker
    source["strict_two_judge_evidence_ladder"]["positive_pair_details"] = [{"text": marker}]
    source["scope"]["private_notes"] = marker
    assert marker not in json.dumps(exporter.public_summary(source))
    source["scope"]["development_units"] = marker
    with pytest.raises(ValueError, match="numeric or boolean"):
        exporter.public_summary(source)


def test_restricted_new_stage_and_force_added_data_are_rejected(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("annotations/\n", encoding="utf-8")
    private = tmp_path / "annotations/v9/stage_b/annotator_1_comparisons.csv"
    private.parent.mkdir(parents=True)
    private.write_text("synthetic restricted payload", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", str(private)], check=True)
    files = checker.collect_files(tmp_path, staged=True)
    assert files[private.relative_to(tmp_path).as_posix()] == b""
    assert any("allowlist" in error for error in checker.check_files(files, check_freeze=False))


def test_secret_diagnostics_do_not_echo_the_credential() -> None:
    token = "hf_" + "a" * 34
    errors = checker.check_files(
        {"example.txt": ("first line\n" + token).encode()}, check_freeze=False
    )
    assert len(errors) == 1
    assert "example.txt:2" in errors[0]
    assert token not in errors[0]


def test_link_to_private_local_file_is_not_a_valid_public_link() -> None:
    errors = checker.check_files(
        {
            "README.md": b"[Trace](annotations/v2_2/machine/trace.txt)",
        },
        check_freeze=False,
    )
    assert len(errors) == 1
    assert "absent from public files" in errors[0]


def test_documented_preexisting_freeze_drift_does_not_hide_new_changes() -> None:
    freeze = json.loads((ROOT / "reports/pre_annotation_freeze_v2_2.json").read_text())
    files = {
        relative.replace("\\", "/"): (ROOT / relative.replace("\\", "/")).read_bytes()
        for relative in freeze["frozen_file_hashes"]
    }
    files["reports/pre_annotation_freeze_v2_2.json"] = json.dumps(freeze).encode()
    files["reports/protocol_integrity_review.json"] = (
        ROOT / "reports/protocol_integrity_review.json"
    ).read_bytes()
    assert not checker.check_files(files)
    files["src/memetic_village/protocol_v2_2.py"] += b"\n# An unreviewed change\n"
    assert any("frozen bytes differ" in error for error in checker.check_files(files))


@pytest.mark.parametrize("command", ["v2-2-freeze", "v2-1-all", "v2-all"])
def test_regeneration_preserves_completed_human_annotations(tmp_path: Path, command: str) -> None:
    path = tmp_path / "annotations/v2_2/stage_a/annotator_1_claims.csv"
    path.parent.mkdir(parents=True)
    original = "event_id,atomic_proposition\nevent-1,A completed claim\n"
    path.write_text(original)
    with pytest.raises(ValueError, match="preserve signed inputs"):
        protect_annotations(tmp_path, command)
    assert path.read_text() == original


def test_compile_cannot_overwrite_completed_stage_b_but_blank_slots_are_allowed(tmp_path: Path):
    path = tmp_path / "annotations/v2_2/stage_b/annotator_1_comparisons.csv"
    path.parent.mkdir(parents=True)
    path.write_text("claim_pair_id,proposition_equivalence\npair-1,\n")
    protect_annotations(tmp_path, "v2-2-compile-stage-b")
    path.write_text("claim_pair_id,proposition_equivalence\npair-1,yes\n")
    with pytest.raises(ValueError):
        protect_annotations(tmp_path, "v2-2-compile-stage-b")


def test_cli_verification_failure_has_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    from memetic_village import cli

    monkeypatch.setattr("sys.argv", ["village-pipeline", "v2-2-verify"])
    monkeypatch.setattr(cli, "verify_v2_2", lambda: {"status": "fail"})
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1


def test_inventory_does_not_publish_nested_raw_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memetic_village import inventory

    raw = tmp_path / "raw"
    raw.mkdir()
    reports = tmp_path / "reports"
    reports.mkdir()
    marker = "PRIVATE_SYNTHETIC_MESSAGE_CONTENT"
    with gzip.open(raw / "events.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "id": "event-1",
                    "created_at": "2026-01-01T00:00:00Z",
                    "data": {"content": marker, "output": marker},
                }
            )
            + "\n"
        )
    monkeypatch.setattr(inventory, "ROOT", tmp_path)
    monkeypatch.setattr(inventory, "RAW", raw)
    monkeypatch.setattr(inventory, "REPORTS", reports)
    monkeypatch.setattr(inventory, "CORE_TABLES", ("events",))
    monkeypatch.setattr(inventory, "ensure_output_dirs", lambda: None)
    monkeypatch.setattr(inventory, "_audit_foreign_keys", lambda _: [])
    result = inventory.build_inventory()
    public_csv = (tmp_path / "data_inventory.csv").read_text()
    assert result["tables"]["events"]["rows"] == 1
    assert "data.content" in public_csv
    assert marker not in public_csv
    assert "examples" not in public_csv


def test_public_check_rejects_old_inventory_sample_column() -> None:
    errors = checker.check_files(
        {"data_inventory.csv": b"table,field,examples\n"}, check_freeze=False
    )
    assert any("without sample values" in error for error in errors)
