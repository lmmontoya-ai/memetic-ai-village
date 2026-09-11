# Operational Epistemic Cascades — v2.1 Pre-Annotation Amendment

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

Status: frozen on 2026-08-14 before holdout semantic inspection and before any human annotation. This amendment supplements `research_spec_v2.md`; where the two conflict, v2.1 governs. The dataset revision remains `504ae8dc5fd254917c4ccbb071d932ad93b3584c` and the deterministic seed remains `20260814`.

## 1. Correct interpretation of the author shuffle

The existing 500-run author shuffle is retained only as an **author-autocorrelation diagnostic**. It changes whether a lexically similar pair satisfies the cross-author inclusion rule and therefore is not a null distribution for social influence or cross-agent recurrence enrichment.

Its only permitted conclusion is:

> Shuffling authors while retaining content and order substantially increases the number of pairs classified as cross-agent lexical recurrences. This demonstrates that raw recurrence counts are mechanically influenced by within-agent topical continuity and cannot be interpreted as evidence for or against social transmission.

The 179,809-versus-230,995 comparison is excluded from every Gate 1 decision. The primary local comparison keeps author identities and author slots fixed. For each candidate response, it enumerates prior messages by other agents in the same room and episode and compares the selected source with locally eligible alternatives matched on time lag, length, artifact or code identifiers, goal metadata when available, and response activity. Source-identity placebos and hard shared-artifact controls are the preferred observational nulls.

## 2. Atomic claims

One claim object contains one minimal proposition. Multiple claims may be extracted from one message or episode. Reviewers record:

```text
claim_id
exact_claim_span
atomic_proposition
referent
polarity
modality
attribution
claim_type
truth_status
```

`claim_type` is one of `fact`, `intent`, `recommended_action`, `operational_status`, or `other`. `truth_status` is one of `verified_true`, `verified_false`, `unsupported`, `mixed`, `unknown`, or `not_truth_apt`. A later correction is evidence to investigate, not ground truth.

Development annotators extract claims without seeing a prewritten proposition. Known-incident propositions are stored only in the private casebook/truth-audit layer and never shown during Stage A extraction.

## 3. Evidence-lineage diversity

The scalar `independent_evidence_source_count` is retired as a primary interpretation. Evidence is characterized along three separately annotated dimensions:

| Dimension | Question |
| --- | --- |
| Lineage independence | Do observations descend from different upstream evidence objects? |
| Observation independence | Did agents separately inspect evidence rather than repeat a report? |
| Inference independence | Did agents use meaningfully distinct methods, prompts, or reasoning procedures? |

The categorical lineage class is one of:

1. `unsupported_repetition`;
2. `derived_from_prior_agent_message`;
3. `same_artifact_same_method`;
4. `same_artifact_different_method`;
5. `distinct_underlying_evidence`;
6. `lineage_unknown`.

Naturalistic results use the term **evidence-lineage diversity**, not a count of independent confirmations.

## 4. Evidence ladder

| Level | Requirement |
| --- | --- |
| L0: lexical recurrence | Informative terms recur across agents. |
| L1: proposition recurrence | Independent reviewers identify the same atomic proposition. |
| L2: source-linked recurrence | L1 plus explicit reply, attribution, quotation, unique reference, or another direct source link. |
| L3a: operational convergence | A recurring proposition is followed by a claim-dependent action, while source linkage remains unresolved. |
| L3b: source-linked operational cascade | L2 plus a claim-dependent action, correction, or third-party restatement. |
| L4a: persistent recorded claim | The proposition is newly recorded in memory and survives later consolidation. |
| L4b: persistent operational assumption | An L4a record is later used in a claim-dependent decision. |
| L5: causal social influence | Randomized exposure changes behavior. |
| L6: durable disposition transmission | The causal change generalizes across contexts or goals. |

“Cascade” is reserved for L3b and above. L3a is convergence, not demonstrated peer uptake.

## 5. Claim-action dependency

Action annotation separates:

1. semantic relevance to the referent;
2. consistency with the claim;
3. dependency on or presupposition of the claim;
4. execution level.

Execution levels are `A0_no_relevant_action`, `A1_discussed_or_repeated`, `A2_verification_attempted`, `A3_claim_dependent_action_proposed`, `A4_claim_dependent_action_attempted`, `A5_claim_dependent_action_completed`, and `A6_collective_or_external_state_changed`.

L3 requires at least A3 and a cited claim-action link. Verification is reported separately because it may be protective rather than acceptance.

## 6. Memory interpretation

Memory appearance alone is a **recorded claim**, not an operational assumption. Each memory unit records response-to-update delay, intervening events, known memory-writer mechanism, endorsement/attribution/question/correction, later survival, and any later action explicitly relying on it. L4b requires cited later behavioral use.

## 7. Hard matched controls

Candidate/control analysis is paired by candidate and episode wherever possible. Hard controls prioritize:

* the same artifact and task;
* the same room and episode;
* comparable time lag, length, terminology, and response activity;
* different agents;
* no demonstrated source link.

Control subclasses include shared-artifact convergence, common-goal convergence, corrective responses, terminology overlap with different propositions, and topically relevant non-source messages. The number of adequate hard controls is reported explicitly; ordinary local controls are not represented as substitutes when hard controls are unavailable.

## 8. Frozen source-linked retrieval channel

A separate high-precision channel is frozen before holdout semantics are opened. It retrieves pairs using one or more of:

* explicit reply or agent-name attribution;
* quotation or a unique source phrase;
* a direct request naming the recipient followed by a response;
* a shared artifact ID explicitly handed from one agent to another;
* discourse such as “as X found,” “following X's result,” or “I checked X's claim.”

This channel is reported separately from broad L0 lexical retrieval. Its rule, thresholds, and output quota may not be changed after holdout inspection.

## 9. Staged annotation

### Stage A — claim extraction

Reviewers see source and response messages in local context without normalized propositions, candidate/control status, scores, known-incident status, provisional categories, or model identity. They independently extract minimal propositions and exact spans.

### Stage B — comparison, stance, and lineage

Only after Stage A is frozen are extracted propositions compared. Every positive label cites exact spans and event IDs. Reviewers label proposition identity, stance, explicit source link, shared evidence, three independence dimensions, lineage class, and strongest alternative explanation.

### Stage C — operational trace

Reviewers receive a compact chronological trace of referent/proposition mentions, relevant tool calls and outputs, artifacts, screenshots, and corrections, with a pointer to the complete trace. They label the four action dimensions and execution level. At least 20% of `A0` judgments are randomly audited against complete traces.

### Stage D — memory and third-party communication

Only after the proposition is fixed do reviewers inspect memory deltas, later consolidations, and proposed third-party expressions.

## 10. Structural audit and semantic reliability

Structural reconstruction and semantic judgment are evaluated separately.

The structural audit checks raw-pointer round trips, timestamps, room state, source/response identity, direct-message eligibility, history/artifact paths, memory pairing, holdout assignment, and third-party recipient distinctness. It reports audit accuracy and reconstruction errors; it is not included in inter-rater semantic reliability.

Semantic reliability covers atomic proposition identity, stance, explicit source linkage, evidence-lineage class, action dependency/execution, correction, memory meaning, and third-party restatement.

Gwet's AC1 is the frozen primary statistic. Raw agreement and Cohen's kappa are diagnostics. All three receive episode-cluster bootstrap 95% confidence intervals. The primary threshold is AC1 at least 0.70 with a lower 95% confidence bound reported; 85% raw agreement is a descriptive fallback only when a preregistered class-imbalance condition is met, not a post hoc alternative.

## 11. Clustered holdout analysis

Every unit retains its room–episode cluster ID. The evaluation pool currently contains 21 eligible clusters; pair rows from the same cluster are not independent observations. Reports include unique counts of clusters, agents, artifacts, and atomic claims. Inference uses within-cluster matched comparisons and cluster bootstrap or cluster-robust intervals. Ordinary row-level binomial intervals are prohibited.

Detector performance is called `precision@K among the frozen selected candidate sample` when candidates are top-ranked or stratified. It is never described as precision over all possible message pairs.

## 12. Independent truth audit

Featured-case truth is adjudicated separately from social-dynamics annotation using:

```text
claim_id
atomic_proposition
truth_status
ground_truth_source
verification_procedure
artifact_version
reviewer
uncertainty
```

The truth reviewer works from artifacts, code, logs, or reproducible checks and does not infer falsity from conversational correction or consensus.

## 13. Layered Gate 1

* **Gate 1A — annotation validity:** semantic agreement, cited evidence spans, and successful structural audits.
* **Gate 1B — candidate-detector validity:** higher L1 rates than hard matched controls in the untouched holdout, using clustered paired analysis.
* **Gate 1C — operational-episode evidence:** reliable action labels and several independent L3a episode clusters with explicit claim-action links. Fewer than five independent clusters are qualitative only.
* **Gate 1D — source-linked cascade evidence:** explicit source linkage plus endorsement/use and a claim-dependent action, correction, or third-party restatement.
* **Gate 1E — memory or retransmission evidence:** reliable proposition-specific labels, enough independent positives, and survival against hard controls.

Failure at one layer does not invalidate lower layers or block the randomized experiments. The experimental study is motivated under full observational success, partial success, or observational measurement failure.

