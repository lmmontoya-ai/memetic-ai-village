# Guide for AI Digest reviewers

The repository is ready for critique of its methods and preliminary findings. It does not claim a completed human validation study. Start with the [README](../README.md) and [current results](../reports/machine_annotation_preliminary_v2_2.md).

## What the study asks

When several agents repeat a claim, did they refer to the same proposition, could the response agent access the source message, and does the trace connect the claim to a later action? The main alternative is independent convergence on the same artifact. Other alternatives include common prompts, shared summaries, routine task language, requests, and quoted claims that the recipient never endorsed.

The observational unit is a source/response event pair. A pair can contain several atomic propositions. Related units share an episode-cluster ID, so one incident cannot supply several independent positives. A temporal sequence alone does not identify influence.

## How to audit a result

1. Check the denominator in [public_results_v2_2.json](../reports/public_results_v2_2.json). Separate the selected sample, units with a valid claim pair, ascertainable units, and independent episode clusters.
2. Read the [v2.2 specification](../research_spec_v2.2.md) and [codebook](../annotations/v2_2/annotation_codebook_v2.2.md). The specification defines the intended measurement; the deviations below describe the machine run actually performed.
3. For an approved local reconstruction, inspect the source and response event pointers, timing intervals, room state, and exact supporting spans. Packet contents and the blinding key are local files, not public Git artifacts.
4. Inspect the full action trace and exact memory snapshots. Agent narration is a claim to verify, not a ground-truth oracle. Reviewers should record unresolved artifact versions and missing context.
5. Evaluate the strongest common-cause explanation before assigning a source-linked or operational label. Shared-artifact inspection is already underway in the one positive YAML case.

The public JSON provides hashes of the detailed local result, both judges' final label files, pairing outcomes, the development key, and the analysis/export scripts. Those hashes support comparison with an authorized copy. They cannot replace access to the underlying evidence.

## Evidence levels and current support

| Level | Required interpretation | Current machine result |
| --- | --- | --- |
| L0 | Lexical recurrence | Retrieval signal only |
| L1 | Proposition recurrence | One episode |
| L2 | Source-linked proposition recurrence | The same episode |
| L3a | Operational convergence without resolved source linkage | Zero counted |
| L3b | L2 plus claim-dependent action, correction, or third-party restatement | The same episode |
| L4a | A persistent recorded claim, excluding relocation or rephrasing | Zero counted |
| L4b | A recorded claim demonstrably used in a later decision | Zero counted |
| L5 | Causal social influence under randomized exposure | Not tested |
| L6 | Causal disposition change across contexts or goals | Not tested |

Zero counted at L4 means the conservative two-judge criteria were not met. It does not show that no relevant memory process occurred.

The [YAML syntax audit](../reports/yaml_blank_line_truth_audit_v2_2.json) concerns a general syntax proposition. A parser accepts a blank line between a mapping key and its indented value. The exact original workflow bytes are absent, so this demonstration does not diagnose every cause of the actual CI failure. This YAML case is distinct from the historical PR #70 EGG-whitespace case.

## Design strengths

The source snapshot is pinned and hashed. Temporal ambiguity and prompt inclusion are separate judgments. Retrieval uses controls with fixed author identities, and the seven available hard controls are reported separately. Annotation separates propositions, stance, lineage, action, memory, and truth. Abstentions remain visible. Known incidents are qualitative material rather than primary detector-precision evidence. The author shuffle is retained only as an author-autocorrelation diagnostic.

## Deviations and unresolved implementation gaps

| Issue | Evidence and consequence | Work required before confirmation |
| --- | --- | --- |
| Original freeze no longer matches two files | The codebook and compiler hashes differ; the specification and holdout plan still match. The saved pass report was stale. [Integrity record](../reports/protocol_integrity_review.json). | Reconcile the development amendments and record a new version with its timing. Preserve the original freeze. |
| Incomplete claim extraction | Both machine runs allowed at most three claims per marked message. There are 289 and 308 populated claims, not 360 each. | Permit all claims and evaluate the effect on development pairing yield before freezing another evaluation. |
| Limited model-run provenance | Fable High is a run label whose Stage-A manifest records multiple observed model IDs. Sol Max used an interactive agent workflow. | Preserve provider-resolved model identity, instructions, inputs, sampling settings, and complete invocation records for future runs. Do not describe this as a controlled comparison of two fixed models. |
| Incomplete human workflow | The v2.2 compiler produces Stage B. The Stage C/D orchestration scripts target the machine directory. `v2-1-reliability` reads v2.1 unit-level files and `proposition_match`, not v2.2 claim-pair rows and `proposition_equivalence`. | Implement and test a v2.2 human adapter and trace release process before handing off later stages. |
| Small effective sample | Nineteen claim pairs come from 11 units and six clusters. Only one hard control is proposition-comparable. | Independent human labeling and an untouched evaluation with explicit ascertainability; do not relax thresholds after seeing holdout results. |
| Blinding limits | Run manifests declare blinding, but this is not an external audit. Raw memory prose can incidentally reveal model identities. | Obtain independent reviewers and report unavoidable identity leakage. Keep semantic reviewers away from result narratives and keys until their labels freeze. |
| Protocol files are not external preregistration | The current Git history does not timestamp the complete research workflow before the machine run. Internal dates and hashes do not prove public preregistration. | Publish a timestamped amendment before new confirmatory work. Describe the existing work as exploratory. |

The machine run corrected a global-room normalization bug and restarted Stage D. The affected old outputs remain archived locally and invalid for analysis. The codebook's August 17 clarification and [decision log](decision_log.csv) record that development change. This review has not reconstructed the missing original compiler/codebook bytes or independently certified every historical run declaration.

## Questions AI Digest can help resolve

- Do the reconstructed room, global-channel, and history-search rules match the infrastructure at the relevant times?
- Can recipient prompt inclusion or context-assembly timing be recovered for selected development episodes?
- Which memory writes were agent-driven, automatic, or mixed, and how did consolidation work at those dates?
- Can exact artifact versions and CI logs resolve the remaining truth questions?
- What shared goals, prompts, summaries, or tool state could explain apparent corroboration?
- Does the distinction between a source-linked sequence and a causal influence claim match what the exported telemetry can support?

Factual corrections should retain the original record and state which derived packets or results need regeneration. The [dataset policy](dataset_restrictions.md) describes what stays local; [CONTRIBUTING.md](../CONTRIBUTING.md) describes the engineering checks.
