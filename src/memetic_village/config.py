from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw_manifest" / "snapshot"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
EPISODES = ROOT / "episodes"

DATASET_ID = "aidigestorg/ai-village"
DATASET_REVISION = "504ae8dc5fd254917c4ccbb071d932ad93b3584c"
RANDOM_SEED = 20260814
ROOMS_INTRODUCED = "2026-02-25 00:00:00"
CHAT_LIMIT_INTRODUCED = "2025-08-20 00:00:00"

CORE_TABLES = (
    "agents",
    "chat_rooms",
    "agent_goals",
    "chat_messages",
    "events",
    "computer_use_sessions",
    "computer_use_turns",
    "agent_memories",
    "claude_code_sessions",
    "claude_code_messages",
)


def ensure_output_dirs() -> None:
    for path in (INTERIM, PROCESSED, REPORTS, EPISODES):
        path.mkdir(parents=True, exist_ok=True)
