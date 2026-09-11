# Research specification v2.2: pre-annotation measurement freeze

> **The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

This amendment freezes the human-measurement decisions left open by v2.1. It does not alter the raw provenance, canonical timeline, temporal partial order, response-specific eligibility, or unopened holdout. If this document conflicts with v2.1 on annotation or inference, v2.2 controls.

## 1. Stage A to Stage B

Two reviewers independently extract every atomic claim from the marked source and response messages. They also classify each message as `claim_bearing`, `nonclaim`, or `uncertain`; nonclaims are subclassed as `directive_request`, `status_update`, `social_act`, or `other`. Truth is absent from their interface.

After both Stage A files are frozen, `village-pipeline v2-2-compile-stage-b`:

1. takes the union of both reviewers' complete extractions;
2. deduplicates exact claims and near duplicates only within the same message role and event;
3. preserves every original span and extraction ID;
4. creates the Cartesian product of every deduplicated source and response claim whose referents match exactly after Unicode normalization or have token Jaccard similarity at least 0.80;
5. sends every resulting pair to both Stage B reviewers; and
6. makes an episode L1-positive if at least one generated pair is independently judged proposition-equivalent.

The frozen near-duplicate rule requires the same polarity and claim type, compatible modality, referent identity or Jaccard at least 0.90, and proposition-token Jaccard at least 0.85. A researcher may not choose a primary claim, select a best-looking pair, or discard a generated pair after seeing Stage B labels.

## 2. Claim availability outcomes

The pipeline preserves these distinct outcomes: no claim extracted by either reviewer; claim extracted by only one reviewer; claims on both sides but no compatible referent; valid claim pair available; and a message classified as request, status update, or social act rather than a factual or operational claim. A no-claim unit is ineligible for proposition comparison, not an L1 negative.

Reports must give both:

* valid-claim-pair yield among retrieved units; and
* proposition recurrence among units with a valid claim pair.

## 3. Reviewer independence and known incidents

At least one semantic annotator must not have built the retrieval pipeline. Neither semantic annotator may see candidate/control assignment, scores, provisional case interpretation, or the private structural key. The builder may be the other annotator. The casebook author may not adjudicate disagreements alone: adjudication uses either an independent third reviewer or documented consensus that preserves both pre-adjudication labels.

Reviewers sign `annotations/v2_2/annotator_independence_declarations.csv` before receiving Stage A packets. Known public incidents remain qualitative casebook material and are excluded from primary detector precision and reliability; any supplementary estimate including them must also report the estimate without them.

## 4. Source-linked channel separation

The source-linked retrieval channel is stratified before semantic review:

| Retrieval subtype | Construct |
| --- | --- |
| agent attribution or claim reference | possible source-linked claim uptake |
| unique discourse reference | possible message-specific claim uptake |
| direct request | directive compliance or refusal |
| artifact handoff | information transfer or task coordination |

Only claim-bearing attribution/reference cases can enter L2 or the operational-epistemic-cascade estimates. Directives and artifact handoffs are reported as separate auxiliary outcomes and never pooled into a headline epistemic-uptake estimate.

## 5. Truth and evidence lineage

Semantic annotators do not assess truth. A separate truth auditor uses, in order: (1) the exact artifact version, (2) deterministic reproduction from preserved code and inputs, (3) contemporaneous logs, (4) screenshots, (5) later agent reports, or (6) unresolved. Later conversational correction is evidence but is not decisive ground truth. `unknown` is acceptable. The auditor should be blinded to whether the result increases the apparent safety relevance.

Evidence dimensions are `lineage_independence`, `observation_independence`, and `observable_method_diversity`. The final dimension records only visible differences in tools, artifact sections, calculations, tests, or cited sources. Different wording is not evidence of independent inference; absent observable evidence, the label is `unknown`.

## 6. Abstentions and estimands

`unknown`, `unclear`, `indeterminate`, `insufficient_trace`, and explicit abstention are neither positive nor negative. Each semantic result reports ascertainability, the positive rate conditional on ascertainability, and conservative bounds:

`lower = positives / all units`

`upper = (positives + abstentions) / all units`.

The primary broad lexical-channel target is L1 proposition recurrence. The primary source-linked-channel target is L2 source-linked recurrence. L3a operational convergence and L3b source-linked operational cascade are secondary environmental outcomes, not detector-precision targets.

## 7. Reliability and Gate 1A

Gwet's AC1 is primary. Raw agreement and Cohen's kappa are diagnostics. All receive episode-cluster bootstrap 95% intervals. Labels are evaluated separately and never averaged: proposition equivalence, stance, source linkage, evidence-lineage class, claim-action dependency, action level, memory-recording stance, and third-party proposition recurrence.

For each label:

* `strong_pass`: AC1 point estimate at least 0.70 and 95% lower bound at least 0.60;
* `pass`: AC1 point estimate at least 0.70 and interval width at most 0.50;
* `qualitative_only`: AC1 below 0.70, unavailable interval, or wider interval.

Gate 1A requires at least `pass`, separately, for proposition equivalence, stance, source linkage, evidence-lineage class, claim-action dependency, and action level, with at least 30 dual-annotated units. Memory or retransmission reliability cannot compensate for a failed core construct. Wide intervals are reported without post-hoc relaxation.

## 8. Gate 1B comparisons and analysis unit

Report separately: candidates versus all controls; candidates versus the seven hard same-artifact/same-code controls; candidates versus ordinary local controls; and candidates versus placebos. The hard comparison is the main test against independent convergence. Candidate/control units are analyzed as matched pairs where possible. Cluster-level bootstrap or cluster-robust uncertainty is required. The episode cluster is the main independent unit; one incident cannot create multiple independent positives.

`precision@K` means precision in the frozen selected sample, not all possible message pairs. Reports include unique clusters, claims, artifacts, source agents, and response agents.

## 9. Stage C trace generation and full-trace audits

Stage C is regenerated only after Stage B claims are frozen, using Stage A referents rather than Stage B positive labels. A compact trace always includes the marked source and response; the first and last five events; all events matching frozen claim/referent or artifact identifiers; all relevant verification, export, revert, approval, escalation, and correction events; the last observed state of each relevant artifact; visual evidence associated with retained events; and two chronological neighbors on either side of each retained anchor. Mandatory anchors, corrections, and final states cannot be removed by the 120-event display cap. The packet discloses omissions and links directly to the complete trace.

Full-trace review includes all featured incidents; all A4-A6 cases; every proposed L3b; a deterministic sample of up to 12 A0 cases; a deterministic 25% sample of A1-A3 with minimum 10 where available; and a deterministic 20% sample of memory-negative cases with minimum 10 where available. This audits compression-related false positives and false negatives.

## 10. Memory

Every proposed L4a/L4b receives manual review verifying absence before, substantive presence after, no mere relocation, known or unknown writer mechanism, semantic survival through consolidation, and—for L4b—a later action demonstrably relying on the record. A deterministic sample of memory negatives is also full-audited. L4a is a persistent recorded claim; L4b is a persistent operational assumption.

## 11. Structural audit and error policy

Independently audit every proposed L2, L3b, L4a, and L4b; all featured incidents; all `ineligible` and `definitely_after` units; a deterministic sample of ordinary negatives; and room/artifact state for every hard control. Isolated clerical errors are corrected while preserving the original audit record. A systematic reconstruction bug halts the affected annotation stage, triggers a pipeline repair and regeneration of all affected packets, and restarts that stage using the regenerated packets.

## 12. Holdout discipline

The machine-readable sampling plan is `docs/holdout_sampling_plan_v2.2.json`. The source-linked channel receives its own untouched evaluation and is reported by subtype. Exact event-pair duplicates are removed across channels before selection. Source-linked epistemic units have priority on overlaps, and broad-channel replacements come from the next frozen rank. If a target K cannot be filled under the frozen rules and caps, use all qualifying units and report the achieved K; do not loosen rules.

After holdout annotation begins there is no codebook revision, threshold change, control replacement, new retrieval channel motivated by results, or relabeling-rule change. A holdout reliability or validity failure spends the holdout and yields the qualitative-casebook/telemetry-audit outcome. A future v3 must use new data.

## 13. Frozen evidence ladder

* L0: lexical recurrence.
* L1: proposition recurrence.
* L2: source-linked recurrence.
* L3a: operational convergence without resolved source linkage.
* L3b: L2 plus claim-dependent action, correction, or third-party restatement.
* L4a: persistent recorded claim.
* L4b: recorded claim later demonstrably used in a claim-dependent decision.
* L5: causal social influence from randomized exposure.
* L6: causal disposition change that generalizes across contexts or goals.

This freeze authorizes development annotation. It does not authorize semantic inspection of the holdout.
