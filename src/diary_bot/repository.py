"""Repository module providing all database operations for the Telegram Diary Bot.

Wraps an aiosqlite connection and provides typed data access methods with
retry logic for write operations.
"""

import asyncio
import functools
import json
from datetime import date, datetime
from typing import Any, Callable, Coroutine

import aiosqlite

from diary_bot.models import (
    CheckInStatus,
    DiaryEntry,
    Input,
    InputType,
    MoodCheckIn,
    MoodEntry,
    Tone,
    UserSettings,
)

# Default settings values
_DEFAULT_SETTINGS = {
    "tone": "reflective",
    "timezone": "UTC",
    "mood_check_in_times": json.dumps(["09:00", "13:00", "18:00"]),
    "inactivity_threshold_hours": "24",
    "memory_callback_time": "10:00",
}


def _retry_write(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Decorator that retries write operations up to 3 times with exponential backoff."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        delays = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms
        last_exception: Exception | None = None
        for attempt in range(3):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exception = exc
                if attempt < 2:
                    await asyncio.sleep(delays[attempt])
        raise last_exception  # type: ignore[misc]

    return wrapper


class Repository:
    """Data access layer abstracting all SQLite operations."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- Input operations ---

    @_retry_write
    async def save_input(self, entry_date: date, text: str, timestamp: datetime, input_type: str) -> int:
        """Save a text or voice input and return its ID."""
        cursor = await self._db.execute(
            "INSERT INTO inputs (entry_date, content, timestamp, input_type) VALUES (?, ?, ?, ?)",
            (entry_date.isoformat(), text, timestamp.isoformat(), input_type),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_inputs_for_date(self, entry_date: date) -> list[Input]:
        """Retrieve all inputs for a given date, ordered by timestamp."""
        cursor = await self._db.execute(
            "SELECT id, entry_date, content, timestamp, input_type FROM inputs "
            "WHERE entry_date = ? ORDER BY timestamp ASC",
            (entry_date.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [
            Input(
                id=row[0],
                entry_date=date.fromisoformat(row[1]),
                content=row[2],
                timestamp=datetime.fromisoformat(row[3]),
                input_type=InputType(row[4]),
            )
            for row in rows
        ]

    # --- Diary operations ---

    @_retry_write
    async def save_diary_entry(
        self, entry_date: date, content: str, tone: str, special_instructions: str | None = None
    ) -> int:
        """Save or replace a diary entry for the given date. Returns entry ID."""
        cursor = await self._db.execute(
            "INSERT OR REPLACE INTO diary_entries (entry_date, content, tone, special_instructions, generated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                entry_date.isoformat(),
                content,
                tone,
                special_instructions,
                datetime.utcnow().isoformat(),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_diary_entry(self, entry_date: date) -> DiaryEntry | None:
        """Get the diary entry for a specific date, or None if not found."""
        cursor = await self._db.execute(
            "SELECT id, entry_date, content, tone, special_instructions, generated_at "
            "FROM diary_entries WHERE entry_date = ?",
            (entry_date.isoformat(),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return DiaryEntry(
            id=row[0],
            entry_date=date.fromisoformat(row[1]),
            content=row[2],
            tone=Tone(row[3]),
            special_instructions=row[4],
            generated_at=datetime.fromisoformat(row[5]),
        )

    async def get_entries_for_range(self, start_date: date, end_date: date) -> list[DiaryEntry]:
        """Get all diary entries within a date range (inclusive), ordered by date."""
        cursor = await self._db.execute(
            "SELECT id, entry_date, content, tone, special_instructions, generated_at "
            "FROM diary_entries WHERE entry_date >= ? AND entry_date <= ? ORDER BY entry_date ASC",
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = await cursor.fetchall()
        return [
            DiaryEntry(
                id=row[0],
                entry_date=date.fromisoformat(row[1]),
                content=row[2],
                tone=Tone(row[3]),
                special_instructions=row[4],
                generated_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

    # --- Mood operations ---

    @_retry_write
    async def save_mood_check_in(self, timestamp: datetime) -> int:
        """Create a new mood check-in record and return its ID."""
        cursor = await self._db.execute(
            "INSERT INTO mood_check_ins (scheduled_at, status) VALUES (?, ?)",
            (timestamp.isoformat(), CheckInStatus.PENDING.value),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    @_retry_write
    async def save_mood_response(
        self, check_in_id: int, text: str, timestamp: datetime, entry_date: date
    ) -> None:
        """Save a mood response linked to a check-in."""
        await self._db.execute(
            "INSERT INTO mood_responses (check_in_id, content, timestamp, entry_date) VALUES (?, ?, ?, ?)",
            (check_in_id, text, timestamp.isoformat(), entry_date.isoformat()),
        )
        await self._db.commit()

    async def get_mood_for_date(self, entry_date: date) -> list[MoodEntry]:
        """Get all mood responses for a given date."""
        cursor = await self._db.execute(
            "SELECT id, check_in_id, content, timestamp, entry_date FROM mood_responses "
            "WHERE entry_date = ? ORDER BY timestamp ASC",
            (entry_date.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [
            MoodEntry(
                id=row[0],
                check_in_id=row[1],
                content=row[2],
                timestamp=datetime.fromisoformat(row[3]),
                entry_date=date.fromisoformat(row[4]),
            )
            for row in rows
        ]

    async def get_pending_check_in(self) -> MoodCheckIn | None:
        """Get the most recent pending mood check-in, or None."""
        cursor = await self._db.execute(
            "SELECT id, scheduled_at, status FROM mood_check_ins "
            "WHERE status = ? ORDER BY scheduled_at DESC LIMIT 1",
            (CheckInStatus.PENDING.value,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return MoodCheckIn(
            id=row[0],
            scheduled_at=datetime.fromisoformat(row[1]),
            status=CheckInStatus(row[2]),
        )

    @_retry_write
    async def mark_check_in_expired(self, check_in_id: int) -> None:
        """Mark a mood check-in as expired."""
        await self._db.execute(
            "UPDATE mood_check_ins SET status = ? WHERE id = ?",
            (CheckInStatus.EXPIRED.value, check_in_id),
        )
        await self._db.commit()

    @_retry_write
    async def mark_check_in_responded(self, check_in_id: int) -> None:
        """Mark a mood check-in as responded."""
        await self._db.execute(
            "UPDATE mood_check_ins SET status = ? WHERE id = ?",
            (CheckInStatus.RESPONDED.value, check_in_id),
        )
        await self._db.commit()

    # --- Settings operations ---

    async def get_settings(self) -> UserSettings:
        """Get user settings, returning defaults for any missing keys."""
        cursor = await self._db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        stored = {row[0]: row[1] for row in rows}

        tone_str = stored.get("tone", _DEFAULT_SETTINGS["tone"])
        timezone = stored.get("timezone", _DEFAULT_SETTINGS["timezone"])
        mood_times_raw = stored.get("mood_check_in_times", _DEFAULT_SETTINGS["mood_check_in_times"])
        inactivity_raw = stored.get("inactivity_threshold_hours", _DEFAULT_SETTINGS["inactivity_threshold_hours"])
        memory_time = stored.get("memory_callback_time", _DEFAULT_SETTINGS["memory_callback_time"])

        # Parse mood check-in times from JSON
        mood_check_in_times: list[str] = json.loads(mood_times_raw)

        # Parse inactivity threshold
        inactivity_threshold_hours: int | None
        if inactivity_raw is None or inactivity_raw.lower() == "disabled":
            inactivity_threshold_hours = None
        else:
            inactivity_threshold_hours = int(inactivity_raw)

        # Parse memory callback time
        memory_callback_time: str | None
        if memory_time is None or memory_time.lower() == "disabled":
            memory_callback_time = None
        else:
            memory_callback_time = memory_time

        return UserSettings(
            tone=Tone(tone_str),
            timezone=timezone,
            mood_check_in_times=mood_check_in_times,
            inactivity_threshold_hours=inactivity_threshold_hours,
            memory_callback_time=memory_callback_time,
        )

    @_retry_write
    async def update_setting(self, key: str, value: str) -> None:
        """Insert or update a single setting."""
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._db.commit()

    # --- Day boundary operations ---

    async def get_day_boundary_state(self, entry_date: date) -> dict | None:
        """Get the day boundary state for a specific date."""
        cursor = await self._db.execute(
            "SELECT entry_date, diary_generated_at, next_day_collection_active "
            "FROM day_boundary_state WHERE entry_date = ?",
            (entry_date.isoformat(),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "entry_date": row[0],
            "diary_generated_at": row[1],
            "next_day_collection_active": bool(row[2]),
        }

    @_retry_write
    async def save_day_boundary_state(
        self, entry_date: date, diary_generated_at: datetime, next_day_active: bool
    ) -> None:
        """Save or update the day boundary state for a given date."""
        # Check if a record already exists
        cursor = await self._db.execute(
            "SELECT id FROM day_boundary_state WHERE entry_date = ?",
            (entry_date.isoformat(),),
        )
        existing = await cursor.fetchone()
        if existing:
            await self._db.execute(
                "UPDATE day_boundary_state SET diary_generated_at = ?, next_day_collection_active = ? "
                "WHERE entry_date = ?",
                (diary_generated_at.isoformat(), int(next_day_active), entry_date.isoformat()),
            )
        else:
            await self._db.execute(
                "INSERT INTO day_boundary_state (entry_date, diary_generated_at, next_day_collection_active) "
                "VALUES (?, ?, ?)",
                (entry_date.isoformat(), diary_generated_at.isoformat(), int(next_day_active)),
            )
        await self._db.commit()

    # --- Delete operations ---

    @_retry_write
    async def delete_entries_by_date(self, target_date: date) -> int:
        """Delete all inputs, diary entries, and mood responses for a specific date.

        Returns total number of rows deleted across all tables.
        """
        date_str = target_date.isoformat()
        total = 0

        cursor = await self._db.execute(
            "DELETE FROM inputs WHERE entry_date = ?", (date_str,)
        )
        total += cursor.rowcount

        cursor = await self._db.execute(
            "DELETE FROM diary_entries WHERE entry_date = ?", (date_str,)
        )
        total += cursor.rowcount

        cursor = await self._db.execute(
            "DELETE FROM mood_responses WHERE entry_date = ?", (date_str,)
        )
        total += cursor.rowcount

        await self._db.commit()
        return total

    @_retry_write
    async def delete_entries_by_range(self, start_date: date, end_date: date) -> int:
        """Delete all inputs, diary entries, and mood responses within a date range (inclusive).

        Returns total number of rows deleted across all tables.
        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        total = 0

        cursor = await self._db.execute(
            "DELETE FROM inputs WHERE entry_date >= ? AND entry_date <= ?",
            (start_str, end_str),
        )
        total += cursor.rowcount

        cursor = await self._db.execute(
            "DELETE FROM diary_entries WHERE entry_date >= ? AND entry_date <= ?",
            (start_str, end_str),
        )
        total += cursor.rowcount

        cursor = await self._db.execute(
            "DELETE FROM mood_responses WHERE entry_date >= ? AND entry_date <= ?",
            (start_str, end_str),
        )
        total += cursor.rowcount

        await self._db.commit()
        return total

    @_retry_write
    async def delete_all_data(self) -> int:
        """Delete all data from all tables. Returns total number of rows deleted."""
        total = 0
        for table in ("inputs", "diary_entries", "mood_responses", "mood_check_ins", "day_boundary_state", "settings"):
            cursor = await self._db.execute(f"DELETE FROM {table}")  # noqa: S608
            total += cursor.rowcount
        await self._db.commit()
        return total

    # --- Export operations ---

    async def get_all_entries_ordered(self) -> list[dict]:
        """Get all entries grouped by date for export, ordered by date ascending.

        Returns a list of dicts, each containing:
        - date: ISO date string
        - inputs: list of input dicts
        - mood_responses: list of mood response dicts
        - generated_diary: diary entry dict or None
        """
        # Get all distinct dates from inputs, diary_entries, and mood_responses
        cursor = await self._db.execute(
            "SELECT DISTINCT entry_date FROM ("
            "  SELECT entry_date FROM inputs "
            "  UNION SELECT entry_date FROM diary_entries "
            "  UNION SELECT entry_date FROM mood_responses"
            ") ORDER BY entry_date ASC"
        )
        date_rows = await cursor.fetchall()

        result: list[dict] = []
        for (date_str,) in date_rows:
            # Get inputs for this date
            cursor = await self._db.execute(
                "SELECT content, timestamp, input_type FROM inputs "
                "WHERE entry_date = ? ORDER BY timestamp ASC",
                (date_str,),
            )
            input_rows = await cursor.fetchall()
            inputs = [
                {"content": row[0], "timestamp": row[1], "type": row[2]}
                for row in input_rows
            ]

            # Get mood responses for this date
            cursor = await self._db.execute(
                "SELECT content, timestamp FROM mood_responses "
                "WHERE entry_date = ? ORDER BY timestamp ASC",
                (date_str,),
            )
            mood_rows = await cursor.fetchall()
            mood_responses = [
                {"content": row[0], "timestamp": row[1]}
                for row in mood_rows
            ]

            # Get diary entry for this date
            cursor = await self._db.execute(
                "SELECT content, tone, generated_at FROM diary_entries WHERE entry_date = ?",
                (date_str,),
            )
            diary_row = await cursor.fetchone()
            generated_diary: dict | None = None
            if diary_row:
                generated_diary = {
                    "content": diary_row[0],
                    "tone": diary_row[1],
                    "generated_at": diary_row[2],
                }

            result.append({
                "date": date_str,
                "inputs": inputs,
                "mood_responses": mood_responses,
                "generated_diary": generated_diary,
            })

        return result
