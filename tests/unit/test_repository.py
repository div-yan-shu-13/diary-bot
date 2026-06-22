"""Unit tests for the Repository class."""

import pytest
from datetime import date, datetime

from diary_bot.database import init_db
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
from diary_bot.repository import Repository


@pytest.fixture
async def repo():
    """Create a Repository backed by an in-memory database."""
    db = await init_db(":memory:")
    repository = Repository(db)
    yield repository
    await db.close()


# --- Input operations ---


class TestInputOperations:
    async def test_save_and_get_input(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        ts = datetime(2024, 1, 15, 10, 30, 0)

        input_id = await repo.save_input(entry_date, "Hello world", ts, "text")
        assert input_id is not None
        assert input_id > 0

        inputs = await repo.get_inputs_for_date(entry_date)
        assert len(inputs) == 1
        assert inputs[0].id == input_id
        assert inputs[0].entry_date == entry_date
        assert inputs[0].content == "Hello world"
        assert inputs[0].timestamp == ts
        assert inputs[0].input_type == InputType.TEXT

    async def test_get_inputs_empty_date(self, repo: Repository):
        inputs = await repo.get_inputs_for_date(date(2024, 1, 15))
        assert inputs == []

    async def test_multiple_inputs_same_date(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        await repo.save_input(entry_date, "Morning", datetime(2024, 1, 15, 8, 0), "text")
        await repo.save_input(entry_date, "Afternoon", datetime(2024, 1, 15, 14, 0), "voice")
        await repo.save_input(entry_date, "Evening", datetime(2024, 1, 15, 20, 0), "text")

        inputs = await repo.get_inputs_for_date(entry_date)
        assert len(inputs) == 3
        assert inputs[0].content == "Morning"
        assert inputs[1].content == "Afternoon"
        assert inputs[1].input_type == InputType.VOICE
        assert inputs[2].content == "Evening"

    async def test_inputs_different_dates_isolated(self, repo: Repository):
        await repo.save_input(date(2024, 1, 15), "Day 1", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_input(date(2024, 1, 16), "Day 2", datetime(2024, 1, 16, 10, 0), "text")

        inputs_15 = await repo.get_inputs_for_date(date(2024, 1, 15))
        inputs_16 = await repo.get_inputs_for_date(date(2024, 1, 16))
        assert len(inputs_15) == 1
        assert inputs_15[0].content == "Day 1"
        assert len(inputs_16) == 1
        assert inputs_16[0].content == "Day 2"


# --- Diary operations ---


class TestDiaryOperations:
    async def test_save_and_get_diary_entry(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        entry_id = await repo.save_diary_entry(entry_date, "Today was great.", "reflective")

        assert entry_id is not None
        entry = await repo.get_diary_entry(entry_date)
        assert entry is not None
        assert entry.entry_date == entry_date
        assert entry.content == "Today was great."
        assert entry.tone == Tone.REFLECTIVE
        assert entry.special_instructions is None

    async def test_save_diary_entry_with_special_instructions(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        await repo.save_diary_entry(entry_date, "Content", "poetic", "Focus on emotions")

        entry = await repo.get_diary_entry(entry_date)
        assert entry is not None
        assert entry.special_instructions == "Focus on emotions"
        assert entry.tone == Tone.POETIC

    async def test_save_diary_entry_replaces_existing(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        await repo.save_diary_entry(entry_date, "First version", "reflective")
        await repo.save_diary_entry(entry_date, "Second version", "casual")

        entry = await repo.get_diary_entry(entry_date)
        assert entry is not None
        assert entry.content == "Second version"
        assert entry.tone == Tone.CASUAL

    async def test_get_diary_entry_not_found(self, repo: Repository):
        entry = await repo.get_diary_entry(date(2024, 1, 15))
        assert entry is None

    async def test_get_entries_for_range(self, repo: Repository):
        await repo.save_diary_entry(date(2024, 1, 14), "Day 1", "reflective")
        await repo.save_diary_entry(date(2024, 1, 15), "Day 2", "casual")
        await repo.save_diary_entry(date(2024, 1, 16), "Day 3", "poetic")
        await repo.save_diary_entry(date(2024, 1, 17), "Day 4", "reflective")

        entries = await repo.get_entries_for_range(date(2024, 1, 15), date(2024, 1, 16))
        assert len(entries) == 2
        assert entries[0].content == "Day 2"
        assert entries[1].content == "Day 3"

    async def test_get_entries_for_range_empty(self, repo: Repository):
        entries = await repo.get_entries_for_range(date(2024, 1, 15), date(2024, 1, 20))
        assert entries == []


# --- Mood operations ---


class TestMoodOperations:
    async def test_save_mood_check_in(self, repo: Repository):
        ts = datetime(2024, 1, 15, 9, 0, 0)
        check_in_id = await repo.save_mood_check_in(ts)
        assert check_in_id is not None
        assert check_in_id > 0

    async def test_get_pending_check_in(self, repo: Repository):
        ts = datetime(2024, 1, 15, 9, 0, 0)
        check_in_id = await repo.save_mood_check_in(ts)

        pending = await repo.get_pending_check_in()
        assert pending is not None
        assert pending.id == check_in_id
        assert pending.status == CheckInStatus.PENDING
        assert pending.scheduled_at == ts

    async def test_get_pending_check_in_none(self, repo: Repository):
        pending = await repo.get_pending_check_in()
        assert pending is None

    async def test_mark_check_in_expired(self, repo: Repository):
        ts = datetime(2024, 1, 15, 9, 0, 0)
        check_in_id = await repo.save_mood_check_in(ts)

        await repo.mark_check_in_expired(check_in_id)

        # Should no longer appear as pending
        pending = await repo.get_pending_check_in()
        assert pending is None

    async def test_mark_check_in_responded(self, repo: Repository):
        ts = datetime(2024, 1, 15, 9, 0, 0)
        check_in_id = await repo.save_mood_check_in(ts)

        await repo.mark_check_in_responded(check_in_id)

        pending = await repo.get_pending_check_in()
        assert pending is None

    async def test_save_and_get_mood_response(self, repo: Repository):
        check_in_id = await repo.save_mood_check_in(datetime(2024, 1, 15, 9, 0, 0))
        entry_date = date(2024, 1, 15)

        await repo.save_mood_response(
            check_in_id, "Feeling good", datetime(2024, 1, 15, 9, 5, 0), entry_date
        )

        moods = await repo.get_mood_for_date(entry_date)
        assert len(moods) == 1
        assert moods[0].check_in_id == check_in_id
        assert moods[0].content == "Feeling good"
        assert moods[0].entry_date == entry_date

    async def test_get_mood_for_date_empty(self, repo: Repository):
        moods = await repo.get_mood_for_date(date(2024, 1, 15))
        assert moods == []

    async def test_get_pending_returns_most_recent(self, repo: Repository):
        await repo.save_mood_check_in(datetime(2024, 1, 15, 9, 0, 0))
        id2 = await repo.save_mood_check_in(datetime(2024, 1, 15, 13, 0, 0))

        pending = await repo.get_pending_check_in()
        assert pending is not None
        assert pending.id == id2


# --- Settings operations ---


class TestSettingsOperations:
    async def test_get_settings_defaults(self, repo: Repository):
        settings = await repo.get_settings()
        assert settings.tone == Tone.REFLECTIVE
        assert settings.timezone == "UTC"
        assert settings.mood_check_in_times == ["09:00", "13:00", "18:00"]
        assert settings.inactivity_threshold_hours == 24
        assert settings.memory_callback_time == "10:00"

    async def test_update_and_get_tone(self, repo: Repository):
        await repo.update_setting("tone", "poetic")
        settings = await repo.get_settings()
        assert settings.tone == Tone.POETIC

    async def test_update_timezone(self, repo: Repository):
        await repo.update_setting("timezone", "America/New_York")
        settings = await repo.get_settings()
        assert settings.timezone == "America/New_York"

    async def test_update_mood_check_in_times(self, repo: Repository):
        import json
        await repo.update_setting("mood_check_in_times", json.dumps(["10:00", "14:00", "19:00"]))
        settings = await repo.get_settings()
        assert settings.mood_check_in_times == ["10:00", "14:00", "19:00"]

    async def test_update_inactivity_disabled(self, repo: Repository):
        await repo.update_setting("inactivity_threshold_hours", "disabled")
        settings = await repo.get_settings()
        assert settings.inactivity_threshold_hours is None

    async def test_update_memory_callback_disabled(self, repo: Repository):
        await repo.update_setting("memory_callback_time", "disabled")
        settings = await repo.get_settings()
        assert settings.memory_callback_time is None

    async def test_update_setting_replaces_existing(self, repo: Repository):
        await repo.update_setting("tone", "poetic")
        await repo.update_setting("tone", "casual")
        settings = await repo.get_settings()
        assert settings.tone == Tone.CASUAL


# --- Day boundary operations ---


class TestDayBoundaryOperations:
    async def test_get_day_boundary_state_none(self, repo: Repository):
        state = await repo.get_day_boundary_state(date(2024, 1, 15))
        assert state is None

    async def test_save_and_get_day_boundary_state(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        generated_at = datetime(2024, 1, 15, 22, 15, 0)

        await repo.save_day_boundary_state(entry_date, generated_at, True)

        state = await repo.get_day_boundary_state(entry_date)
        assert state is not None
        assert state["entry_date"] == "2024-01-15"
        assert state["diary_generated_at"] == "2024-01-15T22:15:00"
        assert state["next_day_collection_active"] is True

    async def test_save_day_boundary_state_update(self, repo: Repository):
        entry_date = date(2024, 1, 15)
        await repo.save_day_boundary_state(entry_date, datetime(2024, 1, 15, 22, 0), False)
        await repo.save_day_boundary_state(entry_date, datetime(2024, 1, 15, 22, 30), True)

        state = await repo.get_day_boundary_state(entry_date)
        assert state is not None
        assert state["diary_generated_at"] == "2024-01-15T22:30:00"
        assert state["next_day_collection_active"] is True


# --- Delete operations ---


class TestDeleteOperations:
    async def test_delete_entries_by_date(self, repo: Repository):
        target = date(2024, 1, 15)
        await repo.save_input(target, "Text", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_diary_entry(target, "Diary", "reflective")
        check_in_id = await repo.save_mood_check_in(datetime(2024, 1, 15, 9, 0))
        await repo.save_mood_response(check_in_id, "Good", datetime(2024, 1, 15, 9, 5), target)

        total = await repo.delete_entries_by_date(target)
        assert total == 3  # 1 input + 1 diary + 1 mood response

        assert await repo.get_inputs_for_date(target) == []
        assert await repo.get_diary_entry(target) is None
        assert await repo.get_mood_for_date(target) == []

    async def test_delete_entries_by_date_preserves_other_dates(self, repo: Repository):
        await repo.save_input(date(2024, 1, 15), "Day 1", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_input(date(2024, 1, 16), "Day 2", datetime(2024, 1, 16, 10, 0), "text")

        await repo.delete_entries_by_date(date(2024, 1, 15))

        assert await repo.get_inputs_for_date(date(2024, 1, 15)) == []
        inputs_16 = await repo.get_inputs_for_date(date(2024, 1, 16))
        assert len(inputs_16) == 1
        assert inputs_16[0].content == "Day 2"

    async def test_delete_entries_by_range(self, repo: Repository):
        for day in range(14, 18):
            d = date(2024, 1, day)
            await repo.save_input(d, f"Day {day}", datetime(2024, 1, day, 10, 0), "text")

        total = await repo.delete_entries_by_range(date(2024, 1, 15), date(2024, 1, 16))
        assert total == 2

        assert await repo.get_inputs_for_date(date(2024, 1, 14)) != []
        assert await repo.get_inputs_for_date(date(2024, 1, 15)) == []
        assert await repo.get_inputs_for_date(date(2024, 1, 16)) == []
        assert await repo.get_inputs_for_date(date(2024, 1, 17)) != []

    async def test_delete_all_data(self, repo: Repository):
        await repo.save_input(date(2024, 1, 15), "Text", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_diary_entry(date(2024, 1, 15), "Diary", "reflective")
        await repo.update_setting("tone", "poetic")

        total = await repo.delete_all_data()
        assert total >= 3

        assert await repo.get_inputs_for_date(date(2024, 1, 15)) == []
        assert await repo.get_diary_entry(date(2024, 1, 15)) is None
        # After deleting all data, settings should return defaults
        settings = await repo.get_settings()
        assert settings.tone == Tone.REFLECTIVE


# --- Export operations ---


class TestExportOperations:
    async def test_get_all_entries_ordered_empty(self, repo: Repository):
        result = await repo.get_all_entries_ordered()
        assert result == []

    async def test_get_all_entries_ordered(self, repo: Repository):
        # Add data for two days
        await repo.save_input(date(2024, 1, 15), "Morning walk", datetime(2024, 1, 15, 8, 0), "text")
        await repo.save_input(date(2024, 1, 15), "Lunch meeting", datetime(2024, 1, 15, 12, 0), "text")
        await repo.save_diary_entry(date(2024, 1, 15), "Great day", "reflective")

        check_in_id = await repo.save_mood_check_in(datetime(2024, 1, 15, 9, 0))
        await repo.save_mood_response(
            check_in_id, "Feeling good", datetime(2024, 1, 15, 9, 5), date(2024, 1, 15)
        )

        await repo.save_input(date(2024, 1, 16), "New day", datetime(2024, 1, 16, 9, 0), "voice")

        result = await repo.get_all_entries_ordered()
        assert len(result) == 2

        # First date
        day1 = result[0]
        assert day1["date"] == "2024-01-15"
        assert len(day1["inputs"]) == 2
        assert day1["inputs"][0]["content"] == "Morning walk"
        assert day1["inputs"][0]["type"] == "text"
        assert day1["inputs"][1]["content"] == "Lunch meeting"
        assert len(day1["mood_responses"]) == 1
        assert day1["mood_responses"][0]["content"] == "Feeling good"
        assert day1["generated_diary"] is not None
        assert day1["generated_diary"]["content"] == "Great day"
        assert day1["generated_diary"]["tone"] == "reflective"

        # Second date
        day2 = result[1]
        assert day2["date"] == "2024-01-16"
        assert len(day2["inputs"]) == 1
        assert day2["inputs"][0]["content"] == "New day"
        assert day2["inputs"][0]["type"] == "voice"
        assert day2["mood_responses"] == []
        assert day2["generated_diary"] is None

    async def test_export_ordering_is_ascending(self, repo: Repository):
        # Insert in reverse order
        await repo.save_input(date(2024, 1, 17), "C", datetime(2024, 1, 17, 10, 0), "text")
        await repo.save_input(date(2024, 1, 15), "A", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_input(date(2024, 1, 16), "B", datetime(2024, 1, 16, 10, 0), "text")

        result = await repo.get_all_entries_ordered()
        dates = [entry["date"] for entry in result]
        assert dates == ["2024-01-15", "2024-01-16", "2024-01-17"]
