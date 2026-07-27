"""Week 4 — NPC ↔ player relationship state (the mechanism behind B2).

Affinity is an integer accumulated from gameplay events (a hard-coded delta
table — the LLM does NOT decide): the player steals -> the NPC turns cold and
charges more. The relationship label goes into the dialogue prompt and picks
the canned fallback line.
"""

import sqlite3
from pathlib import Path

from src import config

# Event -> affinity change. Same "kind" keys as scoring.FIXED_IMPORTANCE.
AFFINITY_DELTAS = {
    "player_attack_npc": -6,
    "player_theft": -5,
    "promise_broken": -4,
    "player_gift": +2,
    "promise_kept": +3,
    "trade": +1,
    "player_greeting": 0,
}

# (lower threshold, label) — scan top-down, take the first label with affinity >= threshold
_LABELS = [
    (6, "trusted"),
    (2, "warm"),
    (-1, "neutral"),
    (-5, "cold"),
    (-999, "hostile"),
]


def label(affinity: int) -> str:
    for threshold, name in _LABELS:
        if affinity >= threshold:
            return name
    return "hostile"


# Price multiplier by relationship — the game server uses this when validating
# adjust_price (B2: a player who stole gets charged more)
PRICE_MULTIPLIER = {
    "trusted": 0.9,
    "warm": 0.95,
    "neutral": 1.0,
    "cold": 1.15,
    "hostile": 1.3,
}


class RelationshipTracker:
    """(npc_id, player_id) -> affinity table, sharing the MemoryStore SQLite file."""

    def __init__(self, db_path: Path | None = None):
        path = Path(db_path or config.SQLITE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                npc_id TEXT NOT NULL, player_id TEXT NOT NULL,
                affinity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (npc_id, player_id)
            )
        """)
        self.conn.commit()

    def apply_event(self, npc_id: str, player_id: str, kind: str) -> int:
        """Apply the event's delta, return the new affinity."""
        delta = AFFINITY_DELTAS.get(kind, 0)
        with self.conn:
            self.conn.execute(
                "INSERT INTO relationships VALUES (?,?,?) "
                "ON CONFLICT(npc_id, player_id) DO UPDATE SET affinity = affinity + ?",
                (npc_id, player_id, delta, delta))
        return self.affinity(npc_id, player_id)

    def affinity(self, npc_id: str, player_id: str) -> int:
        row = self.conn.execute(
            "SELECT affinity FROM relationships WHERE npc_id = ? AND player_id = ?",
            (npc_id, player_id)).fetchone()
        return int(row[0]) if row else 0

    def label(self, npc_id: str, player_id: str) -> str:
        return label(self.affinity(npc_id, player_id))
