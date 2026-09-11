# Phase 1 research specification

> **LEGACY V1 — INVALID PROXY.** Frozen historical specification retained for reproducibility. It
> must not govern v2 findings. See `research_spec_v2.md`.

Status: frozen before candidate discovery. Frozen at dataset revision
`504ae8dc5fd254917c4ccbb071d932ad93b3584c` on 2026-08-14 (UTC).

## Question and claim ceiling

Can the exported AI Village telemetry support reproducible identification of the sequence
`peer availability -> expressed adoption -> behavioral expression -> memory incorporation ->
retransmission or persistence`? This observational pilot can establish traceable candidate episodes
and measurement feasibility. It cannot by itself establish that peer exposure caused a latent belief,
value, or policy change.

## Unit and scope

The unit is a bounded source-recipient episode. The discovery population is the first 80% of
chronologically ordered canonical event records. The final 20% is a locked confirmatory holdout: pipeline code may
compute its boundary and integrity counts, but discovery, ontology changes, threshold tuning, and
case selection must not inspect holdout content. Screenshots are out of scope for this phase because
the table export is sufficient for the requested streams and downloading them would materially
increase the restricted snapshot. Human-authored messages may establish environmental context but
are not treated as peer-agent seeds.

## Frozen operational definitions

- **Candidate meme:** a distinguishable proposition, strategy, norm, goal, or behavioral
  disposition that recurs across agents or time.
- **Seed:** the earliest identified expression of that candidate inside the discovery window.
- **Availability:** a source item was earlier than the recipient decision and the available room
  telemetry does not rule out access.
- **Exposure:** evidence that the source item entered the recipient's prompt or retrieved context.
  Channel co-membership alone is availability, not exposure.
- **Adoption:** a recipient later endorses, applies, preserves, or expresses substantially the same
  content. A lexical match alone is a candidate, not an adoption judgment.
- **Behavioral expression:** an observable tool action, message, artifact operation, or refusal that
  implements the candidate.
- **Memory incorporation:** recognizable candidate content appears in the recipient's later
  persistent memory.
- **Retransmission:** a recipient later communicates or demonstrates the candidate to a third agent.
- **Persistence:** the disposition remains observable after consolidation, a substantial context
  change, or a new goal.
- **Propagation episode:** a seed, plausible availability or exposure path, recipient outcome, and
  explicit alternative-explanation assessment.
- **High-confidence episode:** clear order, confirmed/probable exposure, meaningful recipient
  behavior, and no obvious common source. Automatic discovery cannot assign this label.

All labels describe observables. The project uses "expressed belief" and "behavioral disposition"
unless an intervention supports stronger language.

## Evidence ladder

1. semantic recurrence;
2. temporally ordered recurrence;
3. plausible availability;
4. confirmed/probable exposure;
5. expressed adoption;
6. behavioral expression;
7. memory incorporation;
8. retransmission;
9. persistence or amplification;
10. causal validation under intervention.

## Visibility policy

`confirmed` requires the exact item in an exported recipient prompt or retrieved context. `probable`
requires sufficiently precise documented context-construction rules. `possible` means compatible
time and channel access but uncertain prompt inclusion. `ruled_out` means future-to-past ordering or
incompatible known room membership. `unknown` means the export cannot establish even availability.
The export omits raw prompts and exact retrieval logs, so the pipeline must not manufacture
confirmed exposure from chat co-membership.

## Candidate ontology

The frozen categories are: factual/environmental claim; uncertainty/suspicion; task strategy;
tool-use convention; cooperation norm; refusal/compliance norm; deception/concealment tactic;
reporting/oversight norm; identity/welfare/autonomy claim; persistence/resource seeking; and
correction/safety-promoting behavior.

## Discovery and thresholds

Discovery uses deterministic distinctive n-gram recurrence, cross-agent reply/request patterns,
correction/safety lexicons, one targeted published-incident reconstruction, and message-to-memory recurrence. A candidate requires a source and
different recipient, strict forward time, exact event IDs, and a preliminary visibility assessment.
The registry target is 60 deduplicated episodes, with at least three categories, ten safety/correction
cases, ten likely non-adoptions, and ten ambiguous/false-positive cases. Ranking confidence and
safety relevance are separate. A fixed seed of `20260814` controls samples and shuffled controls.

The decision thresholds are the defaults in `docs/PLAN.md`: full go requires >=80% confirmed or
probable exposure, >=60% confirmed, >=75% traceable source/exposure/outcome, reliability >=0.70 or
85% raw agreement, >=10 high-confidence positives, >=3 categories, >=10 correction/non-adoption
controls, weaker negative controls, and 100% raw trace reproduction for featured cases. A pivot is
required if exposure is unknown for over about 40%, fewer than five high-confidence cases survive,
adoption is unreliable, action links fail, or hidden/common prompts dominate.

## Exclusions and safeguards

- No external outreach, publication, or contact is part of Phase 1.
- No re-identification, credential use, training, or fine-tuning on the gated data.
- Generated summaries are secondary and cannot establish facts.
- Model reasoning text is not treated as a stable latent belief.
- Automatic similarity cannot adjudicate adoption or causality.
- The requested work excludes Workstream G, so inter-annotator reliability is reported as not
  measured, never imputed from heuristic labels.
