"""SQLite helpers for CallSense: calls, verdicts, transcript_cache."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "callsense.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    transcript TEXT NOT NULL,
    language_code TEXT,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    summary TEXT,
    verdict_text TEXT,
    risk_level TEXT,
    escalate_to_human INTEGER DEFAULT 0,
    source TEXT NOT NULL,          -- 'courtroom' | 'cache'
    verdict_id INTEGER
);

CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    verdict_text TEXT NOT NULL,
    advocate_text TEXT,
    challenger_text TEXT,
    judge_text TEXT,
    risk_level TEXT,
    escalate_to_human INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(category, subcategory)
);

CREATE TABLE IF NOT EXISTS transcript_cache (
    audio_hash TEXT PRIMARY KEY,
    transcript TEXT NOT NULL,
    language_code TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def find_verdict(conn, category: str, subcategory: str):
    row = conn.execute(
        "SELECT * FROM verdicts WHERE category = ? AND subcategory = ?",
        (category, subcategory),
    ).fetchone()
    return row


def bump_verdict_hit(conn, verdict_id: int):
    conn.execute(
        "UPDATE verdicts SET hit_count = hit_count + 1 WHERE id = ?",
        (verdict_id,),
    )


def insert_verdict(conn, category, subcategory, verdict_text, advocate_text,
                    challenger_text, judge_text, risk_level, escalate_to_human):
    cur = conn.execute(
        """INSERT INTO verdicts
           (category, subcategory, verdict_text, advocate_text, challenger_text,
            judge_text, risk_level, escalate_to_human, hit_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        (category, subcategory, verdict_text, advocate_text, challenger_text,
         judge_text, risk_level, int(escalate_to_human), now()),
    )
    return cur.lastrowid


def insert_call(conn, transcript, language_code, category, subcategory,
                 summary, verdict_text, risk_level, escalate_to_human, source, verdict_id):
    cur = conn.execute(
        """INSERT INTO calls
           (created_at, transcript, language_code, category, subcategory, summary,
            verdict_text, risk_level, escalate_to_human, source, verdict_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now(), transcript, language_code, category, subcategory, summary,
         verdict_text, risk_level, int(escalate_to_human), source, verdict_id),
    )
    return cur.lastrowid


def get_cached_transcript(conn, audio_hash: str):
    row = conn.execute(
        "SELECT * FROM transcript_cache WHERE audio_hash = ?", (audio_hash,)
    ).fetchone()
    return row


def store_transcript_cache(conn, audio_hash, transcript, language_code):
    conn.execute(
        """INSERT OR REPLACE INTO transcript_cache (audio_hash, transcript, language_code, created_at)
           VALUES (?, ?, ?, ?)""",
        (audio_hash, transcript, language_code, now()),
    )


def reset_demo_data(conn):
    """Wipe calls and verdicts but keep the transcript cache (Sarvam credits already spent)."""
    conn.execute("DELETE FROM calls")
    conn.execute("DELETE FROM verdicts")
