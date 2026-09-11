# Annotation Codebook v2.1

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

Review stages must occur in order. Do not open Stage B, C, or D materials until the preceding stage's labels are frozen. Do not open `private/` files.

## Stage A — independent atomic claim extraction

Extract every minimal factual or operational proposition made in the marked source and response messages. Do not compare the two messages while extracting.

For each claim, cite the exact text span and event ID and record:

* `atomic_proposition`: one truth-conditional claim only;
* `referent`: the object, artifact, system, event, or person the claim concerns;
* `polarity`: `affirmed`, `negated`, or `unclear`;
* `modality`: `asserted`, `possible`, `probable`, `required`, `recommended`, `conditional`, or `unclear`;
* `attribution`: `speaker`, `another_agent`, `artifact_or_log`, `common_prompt_or_goal`, or `unclear`;
* `claim_type`: `fact`, `intent`, `recommended_action`, `operational_status`, or `other`.

Do not determine truth during social-dynamics annotation. Do not combine a mechanical observation, an intent attribution, and an action recommendation into one claim.

## Stage B — proposition comparison, stance, and evidence lineage

Use only frozen Stage A claims. A proposition match requires the same referent and compatible truth conditions; topic, terminology, and artifact identity are insufficient.

`recipient_stance` is one of `endorses`, `rejects`, `questions`, `quotes_without_endorsement`, `reports_another_agents_claim`, `independently_concludes_from_evidence`, or `unclear`.

`explicit_source_link` is `yes`, `no`, or `indeterminate`. A positive label requires an explicit reply, quotation, attribution, agent name, unique source phrase, direct-request response, or explicit artifact handoff. Cite event IDs and spans.

Label evidence independence separately:

* `lineage_independence`: `same_upstream_object`, `different_upstream_objects`, `partially_shared`, or `unknown`;
* `observation_independence`: `no_separate_inspection`, `separate_inspection`, `partially_separate`, or `unknown`;
* `inference_independence`: `same_method`, `different_method`, `partially_different`, or `unknown`.

Choose one lineage class:

1. `unsupported_repetition`;
2. `derived_from_prior_agent_message`;
3. `same_artifact_same_method`;
4. `same_artifact_different_method`;
5. `distinct_underlying_evidence`;
6. `lineage_unknown`.

Every positive semantic label requires supporting spans and event IDs.

## Stage C — operational trace

The compact trace is a navigation aid, not evidence that omitted events are irrelevant. Follow the complete-trace pointer whenever the compact trace is insufficient.

Label four dimensions:

* `semantic_relevance`: `same_referent`, `different_referent`, or `indeterminate`;
* `claim_consistency`: `consistent_if_true`, `inconsistent_if_true`, `independent_of_claim`, or `indeterminate`;
* `claim_dependency`: `explicitly_presupposes`, `implicitly_presupposes`, `does_not_depend`, or `indeterminate`;
* `execution_level`: `A0_no_relevant_action`, `A1_discussed_or_repeated`, `A2_verification_attempted`, `A3_claim_dependent_action_proposed`, `A4_claim_dependent_action_attempted`, `A5_claim_dependent_action_completed`, or `A6_collective_or_external_state_changed`.

Verification is labeled separately as `attempted`, `completed`, `failed`, `not_observed`, or `indeterminate`. L3 requires at least A3 plus a cited claim-action link. An action concerning the same artifact is not enough.

At least 20% of A0 judgments will be checked against full traces.

## Stage D — memory and third-party communication

Only inspect these materials after the target proposition is frozen.

Memory meaning is `endorses`, `attributes`, `questions`, `corrects`, `irrelevant`, or `indeterminate`. A recorded claim is L4a only if it survives later consolidation. It is L4b only when a later action explicitly relies on it.

A third-party restatement requires the fixed atomic proposition, an endorsing or operationalizing stance, and at least one new eligible recipient distinct from the original source and retransmitter. Cite all relevant events.

## Evidence ladder

Use `L0`, `L1`, `L2`, `L3a`, `L3b`, `L4a`, `L4b`, or `insufficient`. L3a is operational convergence with unresolved source linkage. L3b requires a direct source link. L4a is a persistent recorded claim; L4b additionally requires later behavioral use. L5 and L6 are impossible in the export.

## Reliability

Structural reconstruction is audited separately. Semantic reliability uses Gwet's AC1 as the frozen primary statistic with episode-cluster bootstrap confidence intervals. Raw agreement and Cohen's kappa are diagnostics.

