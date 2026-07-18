"""
PHASE 5a: SQLite storage for claim history.

Zero-setup local database -- creates verimed.db automatically on first run.
"""

import sqlite3
import json
from datetime import datetime

DB_FILE = "verimed.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_text TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence INTEGER,
            explanation TEXT,
            sources TEXT,
            entities TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_result(claim_text: str, result: dict):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO history
           (claim_text, verdict, confidence, explanation, sources, entities, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            claim_text,
            result.get("verdict", "Unknown"),
            result.get("confidence", 0),
            result.get("explanation", ""),
            json.dumps(result.get("sources", [])),
            json.dumps([e["text"] for e in result.get("entities", [])]),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def get_history(limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_trending_verdicts(limit: int = 5) -> list[dict]:
    """Most frequently checked claims (approximate, groups by exact text match)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT claim_text, verdict, COUNT(*) as check_count, MAX(timestamp) as last_checked
        FROM history
        GROUP BY claim_text
        ORDER BY check_count DESC, last_checked DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_stats() -> dict:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM history")
    total = cur.fetchone()[0]
    cur.execute("SELECT verdict, COUNT(*) FROM history GROUP BY verdict")
    by_verdict = dict(cur.fetchall())
    conn.close()
    return {"total_checked": total, "by_verdict": by_verdict}
