# Contributing

Use the [reproduction guide](docs/reproduction.md) to install the locked development environment. Work in a branch and keep a change focused enough for another researcher to inspect.

Before a pull request, run:

```sh
uv sync --locked --dev
uv run --frozen ruff check src tests scripts
uv run --frozen pytest -q
uv run --frozen python scripts/check_repository.py
uv build
```

When approved local data are available, also run `uv run --frozen pytest -q --run-data`. Missing private inputs fail in that opt-in mode. Do not treat a skipped data test as a verified research invariant.

## Research changes

Describe the affected construct, data selection, and resulting interpretation. Preserve pre-change evidence for changes to retrieval, temporal ordering, claim pairing, controls, annotation, or aggregation. Add a row to [the decision log](docs/decision_log.csv) and state whether development or holdout content had been inspected. Never silently update an old freeze hash to make it pass.

Add regression tests for changes that could alter inclusion, evidence labels, uncertainty, or data publication. Synthetic inputs should be sufficient for unit tests. Keep machine labels separate from human labels, and do not substitute model agreement for independent human reliability.

A pull request should explain the problem and new behavior, validation performed, and any effect on existing results or protocol versions. Mention incomplete checks directly.

## Data and public files

Raw tables, screenshots, transcripts, model responses, private keys, and populated annotation sheets stay local. `.gitignore` excludes generated research trees by default. New public outputs require a deliberate allowlist change in both `.gitignore` and `scripts/check_repository.py`, plus a content review. Use the aggregate exporter where possible.

Run `uv run --frozen python scripts/check_repository.py --staged` before committing. Do not use `git add -f` to bypass data exclusions. Avoid attaching restricted examples or credentials to public issues; use synthetic examples and non-sensitive identifiers.

The [dataset policy](docs/dataset_restrictions.md) and [NOTICE](NOTICE) describe upstream terms. Original contributions are covered by the repository's MIT license.
