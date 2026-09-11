# Part I Execution Plan v2: Operational Epistemic Cascades

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

The frozen contract is `research_spec_v2.md`. This document records the implemented observational
workflow and its current boundary; it does not replace the contract.

## Implemented workflow

| Stage | Status | Primary evidence |
| --- | --- | --- |
| Contract and claim ceiling | Complete | `research_spec_v2.md` |
| V1 proxy retirement | Complete | `docs/legacy_metric_retirement.md`, terminology audit |
| Timestamp semantics | Complete | `docs/timestamp_semantics_v2.md` |
| Partial-order relations | Complete | `temporal_relations_v2.parquet`, synthetic tests |
| Exact-response eligibility | Complete | `response_eligibility_v2.parquet` |
| Claim and evidence-lineage objects | Complete, awaiting human labels | claim/expression/lineage Parquet files |
| Claim-relevant action windows | Complete, awaiting human labels | `claim_relevant_action_windows_v2.parquet` |
| Memory deltas | Complete, awaiting human labels | `memory_deltas_v2.parquet` |
| Third-party expression candidates | Complete, awaiting human labels | `third_party_expression_candidates_v2.parquet` |
| Local controls | Complete | `matched_controls_v2.parquet` |
| 500 blocked permutations | Complete and deterministic | `blocked_permutations_v2.parquet` |
| Holdout-safe clustering | Complete; semantic content unopened | `holdout_episode_clusters_v2.parquet` |
| Development annotation set | Complete | 60 blinded packets and codebook |
| Five featured cases | Complete, awaiting human labels | `episodes/v2_case_bundles/` |
| Human reliability and Gate 1 | Requires two human reviewers | blank reviewer templates and reliability command |

## Frozen development composition

The development set contains 30 frozen-method L0 recurrence candidates, 20 same-context controls,
and 10 temporal/source-identity placebos. Candidate/control identity and retrieval scores are stored
only in the private blinding key. Public incidents are qualitative case studies and do not enter the
development detector evaluation.

The original holdout cutoff remains `2026-06-29T21:09:13.307527Z`. Metadata-only clustering found 44
holdout-touching clusters; three cross the cutoff and are excluded. After the 48-hour washout and
seven-day follow-up rule, 27 clusters remain eligible: six in the holdout-development pool and 21 in
the evaluation pool. No holdout message text has been used for retrieval, ontology changes, or case
selection.

## Current non-substantive pipeline diagnostics

- The 60 development pairs contain 57 `likely_before` relations and three future-source placebos.
- Exact-response eligibility produces 54 `eligible`, three `source_acknowledged`, and three
  `ineligible` machine assessments; exact prompt inclusion is zero.
- The action extractor assembled 26,250 raw trace events but assigned zero semantic action labels.
- All 60 units have a before/after memory delta; zero semantic memory labels are assigned.
- The third-party extractor returned 97 structurally eligible lexical candidates across 14 units;
  zero are validated retransmissions.
- Twenty-five selectively chosen featured-case screenshots were downloaded from the pinned revision
  and hashed.
- In 500 within-room/episode author permutations, the observed unique L0 candidate count was 179,809
  versus a permutation median of 230,995. This is a lexical-pipeline diagnostic, not a causal test or
  population estimate.

## Reproduction

```powershell
uv sync
uv run village-pipeline v2-all
uv run village-pipeline v2-verify
uv run pytest -q
uv run ruff check src tests
```

The cached author-agnostic edge pool makes subsequent 500-permutation runs practical while retaining
the frozen 35-message, 48-hour, top-three, deduplication, quota, and cap rules.

## Human handoff

Two reviewers independently use `annotations/v2/packet_manifest.csv`, the packet directory, and the
codebook. They must not open `annotations/v2/private/blinding_key.csv`. After both label files are
filled, run:

```powershell
uv run village-pipeline v2-reliability
uv run village-pipeline v2-verify
```

Gate 1 remains unresolved until reliability and candidate-versus-control results are available.

