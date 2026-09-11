# V2.1 staged annotation handoff

Do not begin annotation until `uv run village-pipeline v2-1-verify` passes.

1. Read `annotation_codebook_v2.1.md`.
2. Complete both reviewers' Stage A files independently using only `stage_a/packets`.
3. Freeze Stage A and construct claim IDs before releasing Stage B.
4. Freeze Stage B before releasing compact operational traces in Stage C.
5. Freeze the target propositions and action judgments before releasing Stage D.
6. A separate reviewer completes `structural/reviewer_audit.csv`; these labels are not included in semantic inter-rater reliability.
7. Never open `private/blinding_and_structural_key.csv` until all development labels are frozen.

The source-linked retrieval channel and hard-control inventory are frozen, but the holdout's semantic content remains unopened.

