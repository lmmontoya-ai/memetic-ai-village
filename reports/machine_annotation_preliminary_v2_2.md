# Preliminary two-machine-judge development annotation

> **The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

## Result

The strict intersection of Fable High and Sol Max judgments identifies **one episode-level L1 proposition recurrence**, and it is also the sole preliminary L2 and L3b episode. It is the YAML blank-line incident. Six atomic claim pairs inside that one incident were independently marked proposition-equivalent; they count as **one episode**, not six findings.

The episode contains a deterministically false atomic claim: that a blank line between `env:` and its indented value breaks YAML. The response explicitly attributed the diagnosis to the source, later re-expressed it to new recipients, and a third agent removed the line, committed SHA `5c9d2c4`, and triggered CI run #13. However, the response agent began inspecting the same artifact 148 seconds before the source message. Exact prompt-inclusion telemetry is absent. This is a strong naturalistic source-linked operational sequence, but it does not identify peer causality.

## Retrieval and ascertainability

| Group | Selected units | Valid claim-pair units | Strict L1 positive | Abstention/disagreement | Positive among ascertainable valid units |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broad candidates | 30 | 6 (20.0%) | 1 | 1 | 20.0% |
| All controls/placebos | 30 | 5 (16.7%) | 0 | 0 | 0.0% |
| Hard same-artifact/code controls | 7 | 1 (14.3%) | 0 | 0 | 0.0% |

Across all 60 units, only 11 units in six episode clusters produced a referent-compatible Stage-B claim pair. Forty-two had extracted claims but no compatible referent, and seven lacked a claim on one or both marked roles. The candidates-versus-hard-control comparison is therefore not informative: only one of seven hard controls reached proposition comparison.

## Evidence ladder

| Level | Strict two-judge episode count | Interpretation |
| --- | ---: | --- |
| L1 proposition recurrence | 1 | One YAML incident |
| L2 source-linked recurrence | 1 | Explicit attribution/unique linkage in the same incident |
| L3a operational convergence | 0 | None outside source-linked case |
| L3b source-linked operational cascade | 1 | One qualitative incident; direct action and later re-expression are raw-trace supported |
| L4a persistent recorded claim | 0 | Not counted conservatively: judges disagreed on relocation/rephrasing |
| L4b persistent operational assumption | 0 | Not established |

Both judges saw the YAML claim in the post-response memory and in later consolidation, and both found later behavioral use for five core pairs. They systematically disagreed on whether the memory text was a fresh record versus rephrasing/relocation and on whether writing was automatic or mixed. That blocks a formal L4 label.

## Reliability diagnostics

These describe agreement between the two machine runs. They do not establish human reliability or pass Gate 1A.

| Label | Pair rows | Episode clusters | Raw agreement | AC1 | Cluster-bootstrap 95% CI | Diagnostic grade |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| stage_b.proposition_equivalence | 19 | 6 | 0.947 | 0.904 | [0.600, 1.000] | strong_pass |
| stage_b.recipient_stance | 19 | 6 | 0.947 | 0.939 | [0.725, 1.000] | strong_pass |
| stage_b.explicit_source_link | 19 | 6 | 1.000 | 1.000 | [1.000, 1.000] | strong_pass |
| stage_b.evidence_lineage_class | 19 | 6 | 0.579 | 0.492 | [-0.196, 0.896] | qualitative_only |
| stage_c_full.claim_dependency | 19 | 6 | 0.895 | 0.883 | [0.710, 1.000] | strong_pass |
| stage_c_full.execution_level | 19 | 6 | 0.789 | 0.741 | [0.401, 0.929] | qualitative_only |
| stage_d.memory_meaning | 19 | 6 | 0.789 | 0.747 | [0.370, 0.928] | qualitative_only |
| stage_d.third_party_restatement | 19 | 6 | 0.526 | 0.395 | [-0.412, 0.752] | qualitative_only |

Gate 1A requires at least 30 dual-annotated units per core label and independent human reviewers. Here Stages B-D contain 19 pair rows from 11 units in only six clusters. Gate 1B is also not passed: this is development material, and only one hard control was proposition-comparable.

## Quality controls and scope

- Both judges reviewed all 60 blinded Stage-A packets, every one of the 19 deterministic Stage-B pairs, all 11 complete Stage-C traces, and exact Stage-D memory snapshots.
- A global-channel normalization bug initially suppressed third-party candidates. The affected Stage-D outputs were archived as invalid, the bug was regression-tested and repaired, packets were regenerated, and both judges restarted Stage D from scratch.
- The holdout remains unopened. Human annotation label cells remain unfilled; machine labels live only under `annotations/v2_2/machine/`.
- The separate frozen 60-unit source-linked development sample was not part of this run, so no source-linked-channel precision estimate is reported.
- The machine runs provide a preliminary screen and exercise the annotation protocol. They cannot satisfy the specified human Gate 1.
- Both machine runs imposed a maximum of three claims per marked message. They produced 289 and 308 populated claims respectively, out of 360 template slots each. This cap departs from the v2.2 instruction to extract every atomic claim and may reduce claim-pair yield.
- Fable High is a run label. Its Stage-A manifest records multiple observed model identifiers; it does not establish a single-model comparison. Sol Max labels were produced in an interactive agent workflow, for which this repository has no standalone replay runner.
- The public aggregate export and input hashes are in [public_results_v2_2.json](public_results_v2_2.json). Exact labels, raw excerpts, and model responses remain local under the dataset restrictions.
- The September repository review found that the current codebook and compiler do not match the original v2.2 freeze hashes. [The integrity record](protocol_integrity_review.json) preserves that mismatch. This run must be interpreted as exploratory development work.

## Interpretation

The reconstructed incident contains a false, explicitly source-linked claim that was repeated, appeared in later memory, reached additional agents, and was followed by action. Shared-artifact inspection was already underway, so the sequence cannot establish that the source message caused the response. Broad prevalence, detector validity, and causal spread remain unestablished.
