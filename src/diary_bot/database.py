"""SQLite database schema initialization module.

Provides async database initialization that creates all tables and indexes
on startup using aiosqlite. Enables WAL mode for better concurrent read performance.
"""

import aiosqlite

_SCHEMA_SQL = """
-- User settings (single row for single-user mode)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Raw inputs collected throughout the day
CREATE TABLE IF NOT EXISTS inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input_type TEXT NOT NULL CHECK(input_type IN ('text', 'voice')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inputs_entry_date ON inputs(entry_date);

-- Generated diary entries
CREATE TABLE IF NOT EXISTS diary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    tone TEXT NOT NULL,
    special_instructions TEXT,
    generated_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_diary_entries_date ON diary_entries(entry_date);

-- Mood check-ins
CREATE TABLE IF NOT EXISTS mood_check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'responded', 'expired')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mood responses linked to check-ins
CREATE TABLE IF NOT EXISTS mood_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_in_id INTEGER NOT NULL REFERENCES mood_check_ins(id),
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mood_responses_date ON mood_responses(entry_date);

-- Track day boundary state (post-10PM diary generation)
CREATE TABLE IF NOT EXISTS day_boundary_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    diary_generated_at TEXT,
    next_day_collection_active INTEGER NOT NULL DEFAULT 0
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Initialize the database: open connection, enable WAL mode, and create schema.

    Args:
        db_path: Path to the SQLite database file, or ":memory:" for in-memory.

    Returns:
        An open aiosqlite connection with all tables and indexes created.
    """
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.executescript(_SCHEMA_SQL)
    await db.commit()
    return db
