"""Unit tests for database schema initialization."""

import pytest

from diary_bot.database import init_db


@pytest.fixture
async def db():
    """Create an in-memory database with the full schema."""
    conn = await init_db(":memory:")
    yield conn
    await conn.close()


async def test_all_tables_created(db):
    """Verify that all expected tables are created."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    # Filter out internal sqlite tables (e.g. sqlite_sequence for AUTOINCREMENT)
    table_names = sorted(
        row[0] for row in rows if not row[0].startswith("sqlite_")
    )

    expected_tables = sorted([
        "settings",
        "inputs",
        "diary_entries",
        "mood_check_ins",
        "mood_responses",
        "day_boundary_state",
    ])

    assert table_names == expected_tables


async def test_all_indexes_created(db):
    """Verify that all expected indexes are created."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    rows = await cursor.fetchall()
    index_names = sorted(row[0] for row in rows)

    expected_indexes = sorted([
        "idx_inputs_entry_date",
        "idx_diary_entries_date",
        "idx_mood_responses_date",
    ])

    assert index_names == expected_indexes


async def test_wal_mode_enabled(tmp_path):
    """Verify that WAL journal mode is enabled on a file-based database."""
    db_path = str(tmp_path / "test.db")
    conn = await init_db(db_path)
    cursor = await conn.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row[0] == "wal"
    await conn.close()


async def test_settings_table_schema(db):
    """Verify the settings table has correct columns."""
    await db.execute("INSERT INTO settings (key, value) VALUES ('tone', 'reflective')")
    cursor = await db.execute("SELECT key, value FROM settings WHERE key='tone'")
    row = await cursor.fetchone()
    assert row == ("tone", "reflective")


async def test_inputs_table_schema(db):
    """Verify the inputs table has correct columns and constraints."""
    await db.execute(
        "INSERT INTO inputs (entry_date, content, timestamp, input_type) "
        "VALUES ('2024-01-15', 'Hello world', '2024-01-15T10:30:00', 'text')"
    )
    cursor = await db.execute("SELECT entry_date, content, timestamp, input_type FROM inputs")
    row = await cursor.fetchone()
    assert row == ("2024-01-15", "Hello world", "2024-01-15T10:30:00", "text")


async def test_inputs_table_check_constraint(db):
    """Verify input_type CHECK constraint rejects invalid values."""
    with pytest.raises(Exception):
        await db.execute(
            "INSERT INTO inputs (entry_date, content, timestamp, input_type) "
            "VALUES ('2024-01-15', 'test', '2024-01-15T10:30:00', 'invalid')"
        )


async def test_diary_entries_table_unique_constraint(db):
    """Verify entry_date UNIQUE constraint on diary_entries."""
    await db.execute(
        "INSERT INTO diary_entries (entry_date, content, tone, generated_at) "
        "VALUES ('2024-01-15', 'Entry 1', 'reflective', '2024-01-15T22:00:00')"
    )
    with pytest.raises(Exception):
        await db.execute(
            "INSERT INTO diary_entries (entry_date, content, tone, generated_at) "
            "VALUES ('2024-01-15', 'Entry 2', 'casual', '2024-01-15T23:00:00')"
        )


async def test_mood_check_ins_status_constraint(db):
    """Verify status CHECK constraint on mood_check_ins."""
    # Valid statuses should work
    await db.execute(
        "INSERT INTO mood_check_ins (scheduled_at, status) "
        "VALUES ('2024-01-15T09:00:00', 'pending')"
    )
    # Invalid status should fail
    with pytest.raises(Exception):
        await db.execute(
            "INSERT INTO mood_check_ins (scheduled_at, status) "
            "VALUES ('2024-01-15T12:00:00', 'invalid_status')"
        )


async def test_mood_responses_table_schema(db):
    """Verify mood_responses table works with a valid check_in reference."""
    await db.execute(
        "INSERT INTO mood_check_ins (scheduled_at, status) "
        "VALUES ('2024-01-15T09:00:00', 'responded')"
    )
    await db.execute(
        "INSERT INTO mood_responses (check_in_id, content, timestamp, entry_date) "
        "VALUES (1, 'Feeling good', '2024-01-15T09:05:00', '2024-01-15')"
    )
    cursor = await db.execute("SELECT check_in_id, content, entry_date FROM mood_responses")
    row = await cursor.fetchone()
    assert row == (1, "Feeling good", "2024-01-15")


async def test_day_boundary_state_table_schema(db):
    """Verify day_boundary_state table has correct columns and defaults."""
    await db.execute(
        "INSERT INTO day_boundary_state (entry_date) VALUES ('2024-01-15')"
    )
    cursor = await db.execute(
        "SELECT entry_date, diary_generated_at, next_day_collection_active "
        "FROM day_boundary_state"
    )
    row = await cursor.fetchone()
    assert row == ("2024-01-15", None, 0)


async def test_init_db_is_idempotent(db):
    """Verify that calling init_db multiple times doesn't raise errors."""
    # init_db was already called via fixture; calling again should be safe
    db2 = await init_db(":memory:")
    cursor = await db2.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    table_names = sorted(row[0] for row in rows)
    assert "settings" in table_names
    await db2.close()
