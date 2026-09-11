# Visibility and exposure rules

> **LEGACY V1 — INVALID PROXY.** The first-subsequent-decision graph and its confidence labels are
> retired. V2 uses exact-response eligibility in `research_spec_v2.md`.

These rules apply to the pinned 2026-07-26 export and implement the definitions in
`research_spec.md`. They reconstruct availability, not latent attention or belief.

## Evidence available

The export contains ordered activity events, messages and their rooms, agent creation/current-room
metadata, and `ENTER_ROOM` moves after rooms launched. The upstream changelog says chat was globally
available before 2026-02-25; Rooms v1 then filtered context to the current room. Chat context was
limited from 2025-08-20, and unseen events were capped at 200 from 2026-06-11. Exact raw prompts,
call logs, historic prompt snapshots, and complete context-selection logic are not exported.

## Computed levels

| Level | Reproducible rule |
|---|---|
| `confirmed` | Exact source item occurs in an exported recipient prompt/retrieved-context record. No ordinary chat edge in this snapshot currently satisfies this rule. |
| `probable` | Before 2025-08-20, source preceded the recipient decision while chat was global and the changelog documents the later introduction of a context limit. This is rule-based prompt availability, not proof of attention. |
| `possible` | Time order is valid and global access or known same-room membership is compatible, but truncation/retrieval prevents an inclusion claim. |
| `ruled_out` | Decision is no later than the source, or known Rooms v1 state places source and recipient in different rooms. |
| `unknown` | Recipient room or a subsequent decision cannot be reconstructed from exported telemetry. |

The implementation always returns an assessment object containing the level, availability flag,
prompt-inclusion flag, rule identifier, and explanation. A same-room edge never becomes `confirmed`
without prompt evidence.

## Room reconstruction

Before Rooms v1, active agents are treated as sharing the global chat. From 2026-02-25 onward, the
latest `ENTER_ROOM` event at or before the source time determines historic membership. If none is
available, the historic room is unknown; the agent's export-time `current_room_id` is not projected
backward. Soft-deleted rooms remain valid historical identifiers. Agent activity is bounded by its
creation time and last exported actor event; this is an operational interval, not a claim about the
official roster date.

## Decision time and graph semantics

For each source agent message, each other operationally active agent receives one temporal assessment.
The decision time is that recipient's first subsequent canonical event, capped at seven days. The
edge means the source item was available by that time at the stated confidence. `ruled_out` and
`unknown` rows are retained as negative/uncertain controls. Future-to-past calls are always ruled out.

## Known limitations

Room initialization snapshots and exact prompt contents are absent. Search-history results can expose
older messages, but their query-specific prompt insertion is not comprehensively reconstructable.
Shared goals, websites, artifacts, human messages, summaries, and independent convergence remain
common causes. The graph therefore supports candidate screening and telemetry-gap measurement, not a
causal transmission estimate.
