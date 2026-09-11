# V2 annotation handoff

> **The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

This directory contains the frozen, blinded 60-unit development annotation set. It is a codebook-development set, not a prevalence sample and not the holdout evaluation set.

## Reviewer procedure

1. Read `annotation_codebook_v2.md` completely.
2. Review only the compressed JSON packets listed in `packet_manifest.csv`.
3. Reviewer 1 fills `annotator_1_labels.csv`; reviewer 2 independently fills `annotator_2_labels.csv`.
4. Do not open `private/blinding_key.csv` until both label files are frozen. The key reveals candidate/control identity and is intentionally separated from the reviewer materials.
5. Do not consult the v1 candidate report, retrieval scores, known-incident narratives, or the generated v2 casebook while labeling.
6. Preserve the supplied `blind_unit_id` values and use only codebook-allowed labels. Leave a label blank only when the trace is genuinely insufficient and the codebook permits it.
7. Record an annotation timestamp and stable reviewer identifier before freezing each file.

All proposed operational cascades must be dual-annotated. The current templates contain all 60 units for both reviewers, which exceeds the minimum 50% dual-annotation requirement.

## Reliability and Gate 1

After both CSV files are frozen, run:

```powershell
uv run village-pipeline v2-reliability
uv run village-pipeline v2-verify
```

The reliability command reports raw agreement, Cohen's kappa, and Gwet's AC1 for the core labels. Gate 1 remains pending unless same proposition, stance, relevant action, and evidence lineage meet the preregistered threshold and the remaining Gate 1 conditions are satisfied.

