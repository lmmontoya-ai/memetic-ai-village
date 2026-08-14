# AI Village Memetic Spread

This project assesses whether AI Village data can support defensible measurement of social transmission between AI agents.

The central sequence under study is:

`peer exposure → expressed adoption → behavioral expression → memory incorporation → retransmission or persistence`

The feasibility pilot is not intended to prove that agents acquired stable misaligned values. It asks whether safety-relevant beliefs, strategies, norms, and behavioral dispositions can be identified and tracked through communication, memory, and action well enough to justify a larger quantitative or experimental study.

## Project outputs

The planned feasibility pack includes:

- a documented dataset snapshot and reproducibility manifest;
- a canonical event timeline;
- an exposure graph with visibility-confidence labels;
- a registry of 50–100 candidate propagation episodes;
- a hand-labeled pilot and annotation-reliability results;
- traced case studies, including negative and safety-promoting cases;
- unresolved data requirements and a go, conditional-go, or pivot decision.

The longer-term outputs are a cautious LessWrong/Alignment Forum post, a preregistered follow-up agenda, and a foundation for a subsequent ICML project.

## Evidence discipline

Every candidate episode should separately examine the source, exposure path, recipient change, downstream behavior, memory or retransmission evidence, and strongest common-cause explanation. Observable language is preferred: “expressed belief” and “behavioral disposition” are used unless stronger evidence is available.

The analysis distinguishes semantic recurrence, temporal ordering, plausible exposure, expressed adoption, behavioral expression, memory incorporation, retransmission, persistence, amplification, and causal validation under intervention. Observational evidence alone should not be described as proof of causal spread or latent-value change.

## Repository layout

The planned structure is:

```text
data/          Raw manifests, interim data, and processed outputs
src/           Reproducible analysis code
notebooks/     Exploratory and confirmatory analysis notebooks
annotations/   Codebook and hand-labeled records
episodes/      Candidate propagation episodes and case studies
reports/       Feasibility and audit reports
post/          Publication and preregistration drafts
docs/          Project plan and supporting documentation
```

Raw or restricted data should not be committed unless its research-use conditions explicitly permit it. Dataset versions, retrieval dates, checksums, software versions, random seeds, and known missingness should be recorded in the reproducibility documentation.

## Current status

Project planning is captured in [`docs/PLAN.md`](docs/PLAN.md). The next setup milestones are to freeze the operational definitions in `research_spec.md`, document dataset access and restrictions, reserve a chronological holdout, and create the initial data inventory.

## Working period

August 14–September 30, 2026. The primary feasibility decision is targeted for September 7, 2026.
