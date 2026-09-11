# AI Village operational epistemic cascades

An independent research project on how claims recur across AI agents, acquire apparent corroboration, and enter actions or memory. The study uses the [AI Digest / AI Village dataset](https://huggingface.co/datasets/aidigestorg/ai-village).

**Current status:** exploratory reconstruction and preliminary machine annotation. One development episode contains a repeated, explicitly attributed false YAML claim followed by action. Human validation, detector validity, and causal peer influence remain unestablished. The September 2026 repository review also found two documented mismatches in the original protocol freeze.

## Objective and motivation

The research question is: when agents repeat an operational claim, what evidence distinguishes uptake from a peer, independent inspection of the same artifact, ordinary coordination, and repetition without endorsement?

This matters because several agents can appear to corroborate a claim while relying on the same evidence. A mistaken diagnosis might then influence a code change, persist in memory, or reach another agent. Corrections can follow those same paths. Understanding these sequences requires checking what agents could access, what they actually said, and what they subsequently did.

Here, an *operational epistemic cascade* means a source-linked claim recurrence followed by claim-dependent action, correction, or restatement to another agent. It is an observational classification. The project reserves causal claims for future randomized exposure experiments.

## Start here

| To review | Read |
| --- | --- |
| Current findings and their denominators | [Preliminary results](reports/machine_annotation_preliminary_v2_2.md) and [aggregate JSON](reports/public_results_v2_2.json) |
| Method, alternative explanations, and questions for AI Digest | [Reviewer guide](docs/reviewer_guide.md) |
| Setup, public checks, and reconstruction with approved data | [Reproduction guide](docs/reproduction.md) |
| Engineering findings and unresolved research gaps | [Repository review](reports/repository_review.md) |
| Exact measurement rules | [v2.2 specification](research_spec_v2.2.md), with [v2.1](research_spec_v2.1.md) and [v2](research_spec_v2.md) as its base |

## Current results

The machine run reviewed 60 development units spanning 24 episode clusters. A unit is a selected source/response event pair; a cluster groups units belonging to the same incident. Multiple claim pairs from one incident are not independent findings.

| Development group | Selected units | Units with a compatible claim pair | Positive units, both judges | Disagreement or abstention |
| --- | ---: | ---: | ---: | ---: |
| Broad lexical candidates | 30 | 6 | 1 | 1 |
| Controls and placebos combined | 30 | 5 | 0 | 0 |
| Hard same-artifact/code controls, a subset of the row above | 7 | 1 | 0 | 0 |

Only 11 of 60 units reached proposition comparison, yielding 19 claim pairs in six clusters. Of the other 49 units, 42 had no compatible referent and seven lacked a claim on one or both sides. These units are ineligible for that comparison; they are not negative recurrence labels.

The candidate positive rate is 1/5 among ascertainable, comparable units. That denominator excludes 24 ineligible units and one disagreement. It is not a prevalence estimate for AI Village. With only one comparable hard control, the study cannot establish detector validity.

The single positive incident reaches preliminary L1 proposition recurrence, L2 source-linked recurrence, and L3b source-linked operational cascade. Six equivalent claim pairs describe this one incident. Neither persistent recorded claims nor later operational use of memory meets the conservative L4 criteria.

The incident's general claim that a blank line breaks YAML is refuted by a small parser counterexample. The exact workflow revision was not preserved locally, so the full cause of its failed CI run remains unresolved. The response agent had also begun inspecting the shared artifact 148 seconds before the source message. That alternative explanation prevents a causal interpretation.

These are **machine judgments**, from runs labeled Fable High and Sol Max. Both limited extraction to three claims per marked message, contrary to the specification's exhaustive-extraction rule. The completed claim counts are 289 and 308. Fable's manifest reports multiple model identifiers, and the Sol run has no standalone replay runner. See the [reviewer guide](docs/reviewer_guide.md) for these and other protocol deviations.

## Methodology

1. Pin and inventory the data. The snapshot revision is `504ae8dc5fd254917c4ccbb071d932ad93b3584c`. Ten exported tables produce 2,567,830 canonical events. [The manifest](data/raw_manifest/dataset_manifest.json) records source hashes; [the inventory](data_inventory.md) describes coverage and missing telemetry.
2. Reconstruct timing and access. Use timestamp intervals and response-specific information eligibility. A message being available does not establish that it appeared in the recipient's prompt or influenced a decision.
3. Retrieve development candidates and controls. Compare lexical candidates with fixed-author local controls, including seven hard controls involving the same artifact or code. Keep a separate source-linked retrieval channel, which has not yet been annotated.
4. Separate semantic judgments. Stage A extracts claims; Stage B compares every referent-compatible pair; Stage C judges claim-action dependence; Stage D examines memory and third-party restatement. Truth assessment and structural auditing have separate roles.
5. Report missing judgments and dependence. Preserve abstentions, report denominators and bounds, and cluster uncertainty by episode. The human protocol specifies Gwet's AC1 per label; machine agreement cannot satisfy the human review gate.
6. Preserve the holdout. The cutoff is `2026-06-29T21:09:13.307527Z`, with cluster separation, a 48-hour washout, and endpoint follow-up rules. Semantic holdout inspection has not been performed in this review. The [sampling plan](docs/holdout_sampling_plan_v2.2.json) records the intended one-shot evaluation.

The original v2.2 freeze no longer matches the current codebook and compiler bytes. [The integrity review](reports/protocol_integrity_review.json) preserves the old and current hashes. The original verification now correctly reports failure. This must be reconciled before human or confirmatory holdout annotation; public engineering checks do not certify a valid research freeze.

## Run the public checks

Use Python 3.11, the reference version, and [uv](https://docs.astral.sh/uv/getting-started/installation/). These commands work in PowerShell and POSIX shells without dataset access or API credentials.

```sh
git clone https://github.com/lmmontoya-ai/memetic-ai-village.git
cd memetic-ai-village
uv sync --locked --dev
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen python scripts/check_repository.py
uv run --frozen python scripts/audit_yaml_blank_line_case.py --syntax-only
```

The default test run skips 11 data integration tests explicitly. An approved, reconstructed local workspace can run them with `uv run --frozen pytest -q --run-data`. Public CI covers Python 3.11 through 3.13 on Linux and Windows; its workflow is included, but remote CI execution is pending the first push containing these changes.

Full reconstruction needs approved Hugging Face access, about 3.25 GiB of compressed source files, and additional working storage. Read the [reproduction guide](docs/reproduction.md) before generating artifacts or running model judges.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/memetic_village/` | Reconstruction, eligibility, controls, annotation compilation, and verification |
| `scripts/` | Machine-run tools, aggregation, public export, and repository checks |
| `tests/` | Synthetic tests, public-artifact checks, and opt-in data integration tests |
| `reports/` | Public aggregate findings, provenance, and the repository review |
| `annotations/` | Public codebooks and handoff notes; actual packets and labels stay local |
| `data/raw_manifest/` | Source manifest and holdout cutoff; raw tables stay local |
| `docs/` | Review and reproduction guides, method amendments, and decision history |
| `episodes/` | Local generated registries and case bundles, excluded from public Git |

The v1 plans and proxy measures are historical. [Metric retirement](docs/legacy_metric_retirement.md) explains why first-subsequent-action, cumulative-memory, and author-shuffle measures cannot support the current inference. Historical plans are proposals, not completion records.

## Next research steps

Reconcile the protocol hashes and document a new development amendment before human annotation. Remove the three-claim extraction cap, finish the v2.2 human Stage C/D and reliability path, obtain independent semantic and structural review, and assess the separate source-linked sample. Freeze the corrected workflow before opening the holdout. Randomized peer-exposure experiments remain future work.

## License, attribution, and contributions

Original project code and documentation use the [MIT license](LICENSE). The [notice](NOTICE) excludes upstream data and third-party excerpts from that grant. AI Village data retain [AI Digest's research terms](docs/dataset_restrictions.md); raw tables, screenshots, populated annotations, and bulk transcripts are excluded from this public repository.

Cite this repository at the commit you used, using [CITATION.cff](CITATION.cff), and cite the dataset separately: AI Digest, "AI Village dataset", 2026, [AI Village](https://theaidigest.org/village).

See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and research-change rules. This is independent work by Luis Miguel Montoya Henao. AI Digest review does not imply endorsement.
