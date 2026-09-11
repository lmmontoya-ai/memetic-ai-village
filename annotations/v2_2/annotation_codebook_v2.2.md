# Annotation codebook v2.2

Reviewers see no candidate/control status, retrieval score, model identity, known-incident flag, provisional normalized claim, or truth label. Enter exact supporting spans and event IDs for every non-null semantic label. Preserve `unknown` rather than guessing.

## Stage A: message and atomic-claim extraction

First classify each marked message as `claim_bearing`, `nonclaim`, or `uncertain`. For a nonclaim, use `directive_request`, `status_update`, `social_act`, or `other`. Then extract each minimal truth-apt or operational proposition into a separate slot. Split fact, intent, and recommended action. Record exact span, atomic proposition, referent, polarity (`affirmed`, `negated`, `mixed`, `unclear`), modality (`asserted`, `probable`, `possible`, `conditional`, `unclear`), attribution, claim type (`fact`, `intent`, `recommended_action`, `operational_status`, `other`), and speech act (`factual_claim`, `operational_status`, `directive_request`, `recommendation`, `social_act`, `other`).

Do not assess truth. Truth belongs only in the independent truth audit.

## Stage B: generated claim-pair comparison

The compiler supplies every source-response claim pair sharing a referent under the frozen rule. Reviewers do not select the pair.

* `proposition_equivalence`: `yes`, `no`, or `unclear`.
* `recipient_stance`: `endorses`, `rejects`, `questions`, `quotes_without_endorsement`, `reports_another_agents_claim`, `independently_concludes_from_evidence`, or `unclear`.
* `explicit_source_link`: `yes`, `no`, or `unclear`; requires reply, attribution, quotation, unique reference, or otherwise message-specific evidence.
* `lineage_independence`: `same_upstream_object`, `distinct_upstream_objects`, `partially_distinct`, or `unknown`.
* `observation_independence`: `repetition_only`, `separate_inspection`, `partially_separate`, or `unknown`.
* `observable_method_diversity`: `same_visible_method`, `different_visible_method`, `partially_different`, or `unknown`. Use only observable tools, calculations, artifact sections, tests, or sources.
* `evidence_lineage_class`: `unsupported_repetition`, `derived_from_prior_agent_message`, `same_artifact_same_method`, `same_artifact_different_method`, `distinct_underlying_evidence`, or `lineage_unknown`.

Different wording does not establish method diversity. Cite supporting event IDs.

## Stage C: operational trace

Label separately:

* semantic relevance to the referent;
* claim consistency;
* claim dependency (`yes`, `no`, `unclear`, `insufficient_trace`);
* action type (`verify`, `operationalize`, `repeat_only`, `reject`, `report_or_escalate_uncertainty`, `correct`, `no_relevant_action`, `indeterminate`);
* execution level: A0 no relevant action; A1 discussed/repeated; A2 verification attempted; A3 claim-dependent action proposed; A4 attempted; A5 completed; A6 collective or external state changed.

L3 requires at least A3 and a defensible claim-action dependency. Verification is reported separately and is not operational acceptance.

## Stage D: memory and third-party expression

Memory meaning is `records_true`, `records_uncertain`, `records_correction`, `attributes_claim_only`, `no_relevant_content`, or `unknown`. Confirm semantic absence before and presence after; distinguish relocation/rephrasing and record writer mechanism. L4a requires semantic survival through a later consolidation. L4b additionally requires a later action demonstrably relying on the record.

Third-party recurrence requires the original recipient to later endorse or operationalize the same proposition in a message available to a new agent distinct from source and retransmitter. Use `yes`, `no`, `unclear`, or `insufficient_trace`.

Development clarification frozen 2026-08-17: pre-room-deployment messages use the normalized
`__global__` channel even when a raw legacy room identifier is present. After claims are frozen, the
high-recall structural pool is narrowed without semantic labels: a later expression must share at
least two informative tokens and cover at least 60% of one fixed Stage-A claim profile. Reviewers
still decide proposition identity and stance; lexical filtering is candidate generation only.

## Unknowns

`unknown`, `unclear`, `indeterminate`, and `insufficient_trace` are abstentions. They are never silently converted to `no`. Reports give ascertainability, conditional positive rates, and conservative bounds.

## Episode aggregation

A retrieved unit has a valid claim pair if at least one compiler-generated source-response pair exists. L1 is positive if at least one such pair is judged proposition-equivalent after adjudication. No researcher may choose a favorable pair after labels are visible. Directives and artifact handoffs are analyzed outside the epistemic-claim denominator unless Stage A identifies a separate claim-bearing proposition.
