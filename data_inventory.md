# AI Village data inventory

Generated from the pinned local snapshot. UTC timestamps are normalized internally; raw
timestamps are UTC without suffix, per the upstream schema. `data_inventory.csv` contains
one row per observed field, including nested event fields.

The public CSV contains field statistics only. Sample values are omitted because nested message and tool fields can contain restricted text.

| Table | Rows | Fields | Time range | Duplicate IDs |
|---|---:|---:|---|---:|
| `agents` | 41 | 22 | 2025-04-02T17:45:08.421915Z – 2026-07-25T00:09:26.411000Z | 0 |
| `chat_rooms` | 15 | 10 | 2025-04-02T17:45:08.369652Z – 2026-07-25T00:52:34.733000Z | 0 |
| `agent_goals` | 27 | 9 | 2026-07-03T13:56:18.946920Z – 2026-07-24T18:24:16.037641Z | 0 |
| `chat_messages` | 150,349 | 9 | 2025-04-02T17:47:10.664358Z – 2026-07-25T00:00:02.279970Z | 0 |
| `events` | 296,835 | 50 | 2025-04-02T17:47:10.816356Z – 2026-07-25T00:09:26.394570Z | 0 |
| `computer_use_sessions` | 56,033 | 8 | 2025-04-02T18:00:17.539001Z – 2026-07-25T00:09:26.406735Z | 0 |
| `computer_use_turns` | 1,767,130 | 85 | 2025-04-02T18:00:35.529327Z – 2026-07-25T00:01:09.704553Z | 0 |
| `agent_memories` | 202,550 | 5 | 2025-04-02T18:00:22.121581Z – 2026-07-25T00:09:26.378611Z | 0 |
| `claude_code_sessions` | 303 | 5 | 2026-01-26T19:05:50.054775Z – 2026-03-31T17:01:06.019490Z | 0 |
| `claude_code_messages` | 244,820 | 8 | 2026-01-26T19:05:50.026214Z – 2026-03-31T17:01:05.990115Z | 0 |

## Automated integrity checks

| Check | Scope | Count |
|---|---|---:|
| broken_agent_reference | `chat_messages.agent_speaker_id` | 0 |
| broken_agent_reference | `events.data.actor` | 0 |
| broken_message_reference | `events.data.messageId` | 0 |
| broken_room_reference | `chat_messages.room_id` | 0 |
| broken_room_reference | `events.data.roomId` | 0 |
| broken_session_reference | `computer_use_turns.session_id` | 0 |
| broken_session_reference | `events.data.computerUseSessionId` | 0 |
| chat_message_without_event | `chat_messages.id` | 1 |
| message_before_agent_created | `chat_messages` | 0 |
| message_before_room_created | `chat_messages` | 0 |
| record_before_agent_created | `agent_goals` | 0 |
| record_before_agent_created | `agent_memories` | 0 |
| record_before_agent_created | `claude_code_messages` | 0 |
| record_before_agent_created | `claude_code_sessions` | 0 |
| record_before_agent_created | `computer_use_sessions` | 0 |
| turn_without_model_response | `computer_use_turns.agent_messages` | 0 |

## Interpretation and known uncertainty

Primary keys are table `id` columns; `events.event_index` is the authoritative raw event
ordering. Foreign-key coverage is quantified above. Provider-shaped response fields are
heterogeneous and intentionally left as nested data. Exact prompts, raw call logs, historic
room snapshots before recorded moves, screenshot pixels, and private scaffold code are not in
this snapshot. Generated summaries are secondary evidence. See `visibility_rules.md` for the
consequences for exposure claims.

A deterministic 20-record structural sample per table is stored in
`reports/manual_sample.json`; it contains identifiers and field-presence metadata, not bulk
restricted text.
