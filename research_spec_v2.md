# Operational Epistemic Cascades in LLM-Agent Teams

> Amendment notice: `research_spec_v2.1.md` was frozen before annotation and before holdout semantic inspection. It supersedes this file where the two conflict, especially for the author-autocorrelation diagnostic, atomic claims, evidence-lineage diversity, staged annotation, the split L3/L4 ladder, and clustered Gate 1 analysis.

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

Status: frozen before v2 holdout retrieval or semantic inspection. Frozen against dataset revision
`504ae8dc5fd254917c4ccbb071d932ad93b3584c` on 2026-08-14 UTC. The global deterministic seed is
`20260814`.

## Research contract

**Primary question:** Under what conditions do claims acquire operational authority in multi-agent
AI systems, especially when repeated messages do not represent independent evidence?

**Observational contribution:** Use AI Village to discover and reconstruct naturalistic cases of
cross-agent claim recurrence, apparent corroboration, operationalization, correction, and
provenance loss.

**Experimental contribution:** Causally test whether apparent consensus, hidden evidence
correlation, provenance disclosure, dissent, and verification requirements change how agents
respond to true and false claims.

The observational export will not be used to claim that peer eligibility caused behavior, that a
latent belief or disposition changed, that misalignment spread, that selected cases estimate
prevalence, or that memory overlap demonstrates durable adoption.

The observational target is:

`claim recurrence -> apparent corroboration -> operational authority -> collective action or correction`

## Preserved infrastructure

The pinned dataset manifest and hashes, integrity and relational audits, canonical raw-record
pointers, deterministic storage order, and canonical timeline are retained. `event_order` remains a
query convenience only. It is never evidence of causal precedence.

## Retired v1 measures

The following are invalid as substantive evidence and are prohibited from v2 result tables:

1. first-subsequent-decision availability edges and the phrase `probable exposure`;
2. `candidate transmission` as a name for lexical recurrence;
3. the first later tool call as a downstream behavioral outcome;
4. cumulative-memory lexical overlap as memory incorporation;
5. later same-agent lexical overlap as retransmission;
6. the global source shuffle as the primary null model;
7. the v1 full-go threshold and the 56/60, 59/60, and 38/60 proxy counts;
8. the unadjudicated 60-case registry as a substantive result or prevalence estimate.

Historical files may preserve those strings only when marked `LEGACY V1 — INVALID PROXY`. V2 code
must not read a v1 proxy field to assign an outcome label.

## Units and evidence ladder

The primary observational unit is an **episode containing one or more explicit claims**. A claim is
a normalized proposition connected to expressions, evidence sources, artifacts, actions, and later
corrections. Repeated messages and independent evidence sources are counted separately.

| Level | Operational requirement |
| --- | --- |
| L0: lexical recurrence | Distinct agents reuse informative terms; retrieval only. |
| L1: proposition recurrence | Human adjudicators judge that expressions state the same proposition. |
| L2: source-linked uptake | L1 plus direct reply, quotation, attribution, or unique acknowledgment. |
| L3: operational cascade | L1 plus a claim-relevant action, correction, or valid third-party retransmission. |
| L4: persistent operational assumption | Relevant content is newly written into memory and survives later consolidation. |
| L5: causal social influence | Randomized exposure changes behavior in a controlled experiment. |
| L6: durable disposition transmission | A causal change persists across contexts or goals and is not retained task information. |

AI Village may support L1-L4 for selected cases. It cannot establish L5 or L6.

## Temporal relations

Every analyzed source-response pair receives exactly one relation:

| Relation | Rule |
| --- | --- |
| `definitely_before` | Exported interval boundaries establish source completion no later than response start. |
| `likely_before` | The source record precedes response completion/insertion, but prompt assembly or generation start is unavailable. |
| `concurrent_or_ambiguous` | Intervals overlap, timestamps tie, resolution is insufficient, or order is created only by a researcher tie-break. |
| `definitely_after` | Source creation/completion follows the emitted response boundary and therefore cannot be upstream of that response. |

Timestamp semantics and provenance are defined in `docs/timestamp_semantics_v2.md`. Researcher-created
ordering priority and canonical-ID sorting are never used to resolve a tie.

## Response-specific information eligibility

Eligibility is evaluated for the exact candidate response, not the recipient's first arbitrary
later action.

| Class | Meaning |
| --- | --- |
| `observed_inclusion` | Exact source content or ID is present in an exported recipient prompt/retrieved context. |
| `source_acknowledged` | Recipient explicitly replies to, quotes, attributes, names, or uniquely references the source. |
| `eligible` | Documented channel rules make the peer message available at response time; prompt inclusion is unknown. |
| `indirectly_reachable` | Claim content may be reachable through history search, an artifact, or another channel. |
| `ineligible` | The direct peer-message pathway is ruled out by timing or known room/channel state. |
| `indeterminate` | Timing, room, or context telemetry is insufficient. |

`eligible` never means probably seen. Direct peer-message eligibility and common-artifact access are
separate nullable Boolean fields. Different rooms rule out only the direct room-message pathway.

The documented 200-item cap introduced 2026-06-11 applies to unseen **events**, not necessarily chat
messages. The field `within_known_message_cap` remains null unless the exported context-construction
rule can be evaluated exactly.

## Claims, stances, and evidence lineage

Claim expressions use one of: `endorses`, `rejects`, `questions`, `quotes_without_endorsement`,
`reports_another_agents_claim`, `independently_concludes_from_evidence`, or `unclear`. Lexical
overlap cannot assign stance.

Evidence lineage distinguishes direct inspection, prior-agent messages, common goals or prompts,
copied evidence, distinct evidence, and unknown sources. `agreeing_message_count` and
`independent_evidence_source_count` are separate variables. Event wrappers, chat rows, memory rows,
and model-output mirrors of one expression are deduplicated by their raw message/event identity.

## Outcomes

The response-to-outcome window ends at `min(episode_end, response + 24 hours)`.

Claim-relevant actions are human-adjudicated as: `verify`, `operationalize`, `repeat_only`, `reject`,
`report_or_escalate_uncertainty`, `correct`, `no_relevant_action`, or `indeterminate`. Automated code
only assembles raw candidate traces.

Memory analysis uses the first snapshot after response minus the last snapshot before response.
Added or substantively rewritten spans are presented for annotation as true, uncertain, corrected,
attributed, or irrelevant. Persistence requires survival through two later snapshots when available
and is called memory persistence, not value adoption.

A third-party retransmission requires a later same-proposition expression by the original recipient,
endorsement or operationalization, and at least one eligible new recipient distinct from both prior
agents. Automated recurrence is only a third-party expression candidate.

## Candidate generation and controls

The frozen v1 IDF-weighted lexical method remains an L0 candidate generator. Known public incidents
are excluded from detector validation and reported separately.

Every evaluation candidate must have at least one local matched control. Matching prioritizes room,
episode, time lag, length, artifact identifiers, model/scaffold regime, and goal when exported.
Controls include different-proposition local sources, shared-artifact convergence, future-message
temporal placebos, and source-identity placebos. Pipeline calibration uses 500 deterministic author
permutations inside room-episode blocks. These controls evaluate lexical enrichment, not causality.

## Holdout policy

The original cutoff `2026-06-29T21:09:13.307527Z` remains fixed. Holdout episode clusters are defined
from room and timestamp metadata before semantic content is opened, using an eight-hour inactivity
gap. Goal metadata is retained when available but cannot be required because village-wide goal rows
are missing from the pinned local snapshot.

Episodes crossing the cutoff are excluded. Responses during the first 48 hours after the cutoff are
washed out. Responses within seven days of the dataset endpoint are excluded when memory or
retransmission follow-up is required. Complete clusters, not individual messages, are assigned by a
seeded stable hash. Operational episode end is the final cluster message plus the frozen eight-hour
inactivity boundary. Outcome measurement may extend after a selected response; response selection and
matching remain frozen.

Development consists of 30 discovery-set recurrence candidates, 20 matched controls, and 10 temporal
or source placebos. The evaluation set consists of 40 frozen-method holdout candidates and 40 local
matched controls. Public incidents do not count toward either precision estimate.

## Annotation and decision gate

Two independent human annotators label the holdout. At minimum, 50% and every proposed operational
cascade are dual-annotated; the primary annotator blindly repeats the remainder after at least seven
days. LLM output may assist retrieval but is not ground truth.

Core labels require Gwet's AC1 or Cohen's kappa at least 0.70, or at least 85% raw agreement when
class imbalance makes chance correction unstable. Until those labels exist, all generated claim,
stance, action, memory, and retransmission fields remain explicitly unadjudicated.

Gate 1 passes only if core reliability meets target, local controls receive substantially fewer
operational-cascade labels, held-out retrieval has measurable precision, and featured cases survive
raw-trace review. Otherwise the observational contribution is a telemetry audit and qualitative
casebook motivating controlled experiments.
