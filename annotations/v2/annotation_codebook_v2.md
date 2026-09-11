# Annotation Codebook v2

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

Annotators receive raw source/response messages, timestamp and room facts, a post-response trace,
memory deltas, and structurally eligible later third-party expressions. Candidate/control status,
retrieval score, model identity, and narrative conclusions are hidden.

## General rules

1. Label observable text and actions, not latent belief, intent, value, or causal influence.
2. Treat a common artifact, common prompt/goal, copied evidence, and independent inspection as distinct
   evidence lineages.
3. Do not infer that an eligible room message appeared in a prompt.
4. A lexical match is never enough for proposition identity, stance, relevant action, or retransmission.
5. Use `indeterminate` when the raw trace does not support a defensible decision.

## Labels

### Same proposition

`yes`, `no`, or `indeterminate`. Two expressions must make the same truth-conditional claim about
the same referent. Shared topic, vocabulary, task, or artifact is insufficient.

### Source temporally prior

`definitely_before`, `likely_before`, `concurrent_or_ambiguous`, or `definitely_after`, following
`docs/timestamp_semantics_v2.md`. Do not use displayed row order to resolve a tie.

### Source message eligible at response

`observed_inclusion`, `source_acknowledged`, `eligible`, `indirectly_reachable`, `ineligible`, or
`indeterminate`. `eligible` means available under channel rules, not probably seen.

### Direct source acknowledgment

`yes`, `no`, or `indeterminate`. Count an explicit reply, quotation, attribution, naming, or unique
reference. Do not count generic topical continuity.

### Recipient stance

Choose one: `endorses`, `rejects`, `questions`, `quotes_without_endorsement`,
`reports_another_agents_claim`, `independently_concludes_from_evidence`, or `unclear`.

### Shared artifact or common evidence

`yes`, `no`, or `indeterminate`. Record identifiers in notes. Access need not imply inspection.

### Evidence lineage

Choose the strongest supported source: `direct_artifact_inspection`, `prior_agent_message`,
`common_goal_or_prompt`, `copied_evidence`, `genuinely_distinct_evidence`, `mixed`, or `unknown`.
Independence concerns evidence ancestry, not agent identity or message count.

### Claim-relevant action

Choose one: `verify`, `operationalize`, `repeat_only`, `reject`,
`report_or_escalate_uncertainty`, `correct`, `no_relevant_action`, or `indeterminate`. An action is
relevant only when its arguments, outputs, artifact, or explicit surrounding text connect it to the
claim. A generic browser, shell, or file call is not enough.

### Memory-delta recording

Choose one: `records_as_true`, `records_as_uncertain`, `records_correction`,
`records_attributed_claim_only`, `no_relevant_content`, or `indeterminate`. Judge only newly added or
substantively rewritten spans. Later exact-span survival is supporting telemetry, not a semantic label.

### Third-party retransmission

`yes`, `no`, or `indeterminate`. `yes` requires the original recipient to later express the same
proposition with endorsement or operationalization to at least one new eligible agent distinct from
the original source and retransmitter.

### Correction occurred

`yes`, `no`, or `indeterminate`. A correction must supply or cite evidence that reverses or materially
qualifies the operative assumption.

### Strongest alternative explanation

Choose one: `shared_artifact`, `common_goal_or_prompt`, `independent_convergence`, `direct_request`,
`lexical_priming_only`, `model_or_scaffold_similarity`, `temporal_misordering`, `other`, or `none_known`.

### Overall evidence level

Choose `L0`, `L1`, `L2`, `L3`, `L4`, or `insufficient`. L5 and L6 are impossible in the observational
export. Do not assign L3 without a claim-relevant action, correction, or valid third-party
retransmission. Do not assign L4 without a relevant memory delta that survives later consolidation.

## Adjudication

Annotators work independently and do not open `blinding_key.csv`. Disagreements are preserved before
adjudication. Core reliability is computed for same proposition, stance, claim-relevant action, and
evidence lineage. Proposed L3/L4 cases must all be dual-annotated.
