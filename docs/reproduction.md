# Reproduction guide

There are three levels of reproduction: public software checks, deterministic reconstruction from approved data, and recomputation from saved machine labels. New model calls are a separate activity and may not reproduce the old judgments exactly.

## Public checkout

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git. Python 3.11 is the reference interpreter; the project supports Python 3.11 through 3.13. The lockfile pins the dependency resolution. CI is configured to use uv 0.9.26, the version used for the local repository review.

From the repository root:

```sh
uv sync --locked --dev
uv run --frozen village-pipeline --help
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen python scripts/check_repository.py
uv run --frozen python scripts/audit_yaml_blank_line_case.py --syntax-only
uv build
```

No dataset or API token is needed. Eleven tests marked `data` are skipped by default. The remaining tests cover timestamp ambiguity, eligibility rules, claim pairing, abstentions, reliability rules, annotation preservation, export filtering, and public-file integrity. The YAML example reproduces only the general syntax counterexample.

`check_repository.py` scans tracked and unignored working files. It also checks staged bytes when staged changes exist. Before committing, `--staged` checks the entire Git index, including restricted files added with `git add -f`. It checks relative Markdown file links, a conservative set of credential patterns, and the documented protocol hashes. Pattern checks cannot certify that arbitrary prose is free of personal or sensitive information.

The original freeze has two documented mismatches. Public checks compare those files to the dated [integrity review](../reports/protocol_integrity_review.json) and report the drift separately. They do not turn the original freeze into a pass. `.gitattributes` prevents checkout line-ending conversion from changing the four protocol files' byte hashes.

## Approved dataset reconstruction

Use a separate checkout for regeneration. Some commands replace derived tables, packets, and blank templates. The CLI refuses broad regeneration when it finds completed human labels, but existing machine-run evidence and freeze records should still be preserved before rebuilding.

1. Obtain access through the [AI Village dataset page](https://huggingface.co/datasets/aidigestorg/ai-village) and accept its research conditions.
2. Authenticate locally with `uv run hf auth login`, or configure `HF_TOKEN` outside the repository. Do not paste tokens into code or tracked files.
3. Download the pinned snapshot with `uv run --frozen village-pipeline download`.

The manifest lists about 3.25 GiB of compressed raw data. Allow additional disk and memory for decompression, DuckDB work, Parquet outputs, and local annotation packets. Peak memory, total disk use, and end-to-end runtime have not been benchmarked for a new machine.

The old README omitted the initial reconstruction steps. A fresh clone needs these before the v2 pipeline:

```sh
uv run --frozen village-pipeline manifest
uv run --frozen village-pipeline inventory
uv run --frozen village-pipeline timeline
uv run --frozen village-pipeline exposures
uv run --frozen village-pipeline candidates
uv run --frozen village-pipeline v2-all
uv run --frozen village-pipeline v2-1-all
uv run --frozen pytest -q --run-data
```

`manifest` contacts Hugging Face to record revision metadata. `v2-all` also retrieves selected development screenshots; the historical local run downloaded 25. Raw screenshot files remain ignored. The base `exposures` and `candidates` steps produce legacy inputs needed by later reconstruction. Their old proxy metrics are retired and must not be interpreted as evidence of adoption or causal influence.

The stages above are inferred from the current code's dependencies. This repository review ran the existing local data tests; it did not perform a new multi-gigabyte download or a complete reconstruction from empty storage. The CLI currently assumes a repository checkout and writes under its root. Installing the wheel alone is not a supported research-data workflow.

## Protocol freeze and human review

The original `v2-2-freeze` command generates blank Stage A files and replaces the freeze record. Do not use it to erase the currently documented hash mismatch. Reconcile the [development deviations](reviewer_guide.md) and version the corrected protocol first.

The existing workspace's `uv run --frozen village-pipeline v2-2-verify` returns a failure because the original codebook and compiler hashes no longer match. This is the expected integrity finding, not a passed check. The original verifier also checks that Stage A is blank; it is a pre-annotation verifier, not a completed-annotation validator.

After a corrected development protocol is recorded, both reviewers must independently finish Stage A and sign the independence declarations. `v2-2-compile-stage-b` is the available deterministic pairing compiler. Later human stages and a v2.2 reliability adapter still need implementation and validation. `v2-1-reliability` cannot substitute for that adapter.

## Recompute the preliminary machine analysis

This requires the saved, restricted machine labels and development key from the original run. Downloading the raw snapshot does not recreate those model judgments. The scripts do not send messages or invoke models in this recomputation path:

```sh
uv run --frozen python scripts/analyze_machine_annotations_v2_2.py
uv run --frozen python scripts/export_public_results.py
uv run --frozen python scripts/audit_yaml_blank_line_case.py
```

The first command recomputes rates and clustered agreement from the final labels. The second writes only named numeric and boolean aggregates, documented limitations, and hashes to [public_results_v2_2.json](../reports/public_results_v2_2.json). The third verifies that the syntax counterexample corresponds to the extracted claim. Detailed JSON and exact label files stay local.

`scripts/run_fable_stage_*.py` contain the historical prompts and schema checks and invoke a local model CLI. They require access to that service and can incur costs. They are not part of CI or the public quickstart. Fable High is a run label rather than a guaranteed single resolved model identity. The Sol Max labels came from an interactive workflow; there is no equivalent standalone runner in this repository.

## Holdout and changes

The holdout cutoff and [sampling plan](holdout_sampling_plan_v2.2.json) are retained. Reconstruction may compute structural metadata over the export, but semantic inspection, sample changes motivated by holdout outcomes, and threshold tuning are separate research actions. This repository review did not open holdout semantic content or run new judges.

Report a failure with the command, Python/uv versions, code commit, dataset revision, and an error message with credentials and raw content removed. For research-affecting repairs, preserve the old result, log the change, regenerate affected packets, and restart the affected stage as specified by the protocol.
