# v2.2 annotation handoff

Repository review status, September 2026: the original codebook/compiler hashes no longer match the freeze. Reconcile the [integrity findings](../../reports/protocol_integrity_review.json) and [workflow gaps](../../docs/reviewer_guide.md) before new human annotation. The instructions below describe the intended handoff; later human-stage automation is not complete.

Start with Stage A only. Reviewers complete both the message-classification and atomic-claim files independently. Do not open v2.1 Stage B: it is superseded because it allowed discretionary claim-slot pairing.

After both Stage A reviewers sign and freeze their files, run:

```text
uv run village-pipeline v2-2-compile-stage-b
```

This deterministically creates the Stage B comparison sheets. Stage C must then be regenerated from the frozen Stage A claims under the compact-trace rules in `research_spec_v2.2.md`; it must not be generated from favorable Stage B labels.

Before distributing packets, collect the reviewer independence declarations. Keep the private blinding key inaccessible to semantic reviewers.

The CSV templates, packets, model labels, and keys are generated locally and excluded from public Git. Machine results are reported separately in the [preliminary analysis](../../reports/machine_annotation_preliminary_v2_2.md). The old `v2-1-reliability` command does not read the v2.2 comparison schema and must not be presented as its completed-label adapter.
