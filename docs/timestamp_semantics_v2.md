# Timestamp and Partial-Order Specification v2

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

The export mirrors a live Postgres database. Unless stated otherwise, timestamps are UTC strings at
microsecond storage precision. Precision is not the same as semantic certainty: a six-digit fraction
does not reveal when prompt assembly or model generation began.

| Source | Field | Operational semantics | Start boundary? | Completion boundary? | Provenance |
| --- | --- | --- | --- | --- | --- |
| `events` | `created_at` | Event-row insertion/emission time; exact runtime boundary undocumented | no | weak completion proxy for emitted chat/event | upstream database |
| `events` | `event_index` | Unique monotone database sequence | no | no | upstream database |
| `events` | `updated_at` | Last row mutation, usually microseconds after creation | no | no | upstream database |
| `agents` | `created_at` | Agent-row creation; lower bound for exported activity | weak availability start | no | upstream database |
| `agents` | `updated_at` | Last metadata mutation/export-time state | no | no | upstream database |
| `chat_messages` | `created_at` | Message-row creation/emission | no | response-emission proxy | upstream database |
| `chat_messages` | `updated_at` | Last row mutation | no | no | upstream database |
| `chat_rooms` | `created_at` / `deleted_at` | Room configuration and soft-deletion boundaries | configuration start | configuration end when present | upstream database |
| `computer_use_sessions` | `created_at` | Session-row creation | weak session start | no | upstream database |
| `computer_use_sessions` | `updated_at` | Last row mutation, not a documented session end | no | no | upstream database |
| `computer_use_turns` | `created_at` | Turn-row creation; request/start versus completion is undocumented | no | unknown | upstream database |
| `computer_use_turns` | `updated_at` | Last row mutation; may follow tool output but semantics undocumented | no | unknown | upstream database |
| `agent_memories` | `created_at` | Snapshot insertion after consolidation | no | snapshot availability proxy | upstream database |
| `claude_code_messages` | `created_at` | SDK stream-row creation | no | message emission proxy | upstream database |
| `claude_code_sessions` | `created_at` | SDK session-row creation | weak session start | no | upstream database |
| `claude_code_sessions` | `updated_at` | Last SDK session-row mutation | no | undocumented | upstream database |
| `agent_goals` | `start_time` | Declared applicability boundary | yes | no | upstream goal configuration |
| `agent_goals` | `end_time` | Declared applicability boundary | no | yes | upstream goal configuration |
| changelog events | documented date | Deployment-date boundary, normally day resolution | approximate | approximate | upstream changelog |

## Derived event interval fields

`event_started_at` and `event_completed_at` are populated only when the source exports a defensible
boundary. A message's `created_at` is stored as `event_completed_at` with
`timestamp_semantics=response_emission_or_row_insertion`; its start remains null. A generic point
timestamp remains available for storage/querying but does not manufacture an interval.

`timestamp_provenance` records the table and field, for example
`chat_messages.created_at/upstream_database`. `ordering_uncertainty_reason` records the missing
boundary or conflict that prevents a stronger relation.

## Relation algorithm

1. If both source completion and response start exist and source completion is no later than response
   start, label `definitely_before`.
2. If source start is later than response completion, label `definitely_after`.
3. If exported intervals overlap, label `concurrent_or_ambiguous`.
4. If both are emitted-message completion proxies and the source timestamp is later than the response
   timestamp, label `definitely_after` for the proposed source-to-response direction.
5. If the source completion proxy is earlier but response start is missing, label `likely_before`.
6. Equal point timestamps, insufficient resolution, or order induced only by `ordering_priority`,
   `source_order`, `event_order`, or canonical-ID sorting are `concurrent_or_ambiguous`.

The deterministic event order may break ties for storage and pagination only.

## Known uncertainty

Ordinary exact prompts, included-message IDs, prompt-assembly timestamps, model-call start times, and
model-call completion times are not exported. Consequently most chat source-response pairs cannot be
`definitely_before`. Room/channel eligibility must be evaluated separately from temporal relation.
