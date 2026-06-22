"""Unit tests for the DayBoundaryService."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from diary_bot.database import init_db
from diary_bot.day_boundary import DayBoundaryService
from diary_bot.repository import Repository


@pytest.fixture
async def repo():
    """Create a repository backed by an in-memory database."""
    db = await init_db(":memory:")
    try:
        yield Repository(db)
    finally:
        await db.close()


@pytest.fixture
def tz_utc():
    return ZoneInfo("UTC")


@pytest.fixture
def tz_ist():
    return ZoneInfo("Asia/Kolkata")


@pytest.fixture
def service_utc(repo, tz_utc):
    return DayBoundaryService(repo=repo, timezone=tz_utc)


@pytest.fixture
def service_ist(repo, tz_ist):
    return DayBoundaryService(repo=repo, timezone=tz_ist)


class TestIsPost10pm:
    """Tests for the is_post_10pm() method."""

    def test_before_10pm(self, service_utc):
        # 9:59 PM UTC
        ts = datetime(2024, 6, 15, 21, 59, 0, tzinfo=timezone.utc)
        assert service_utc.is_post_10pm(ts) is False

    def test_exactly_10pm(self, service_utc):
        # 10:00 PM UTC
        ts = datetime(2024, 6, 15, 22, 0, 0, tzinfo=timezone.utc)
        assert service_utc.is_post_10pm(ts) is True

    def test_after_10pm(self, service_utc):
        # 11:30 PM UTC
        ts = datetime(2024, 6, 15, 23, 30, 0, tzinfo=timezone.utc)
        assert service_utc.is_post_10pm(ts) is True

    def test_midnight(self, service_utc):
        # Midnight is hour 0, so not post-10PM
        ts = datetime(2024, 6, 16, 0, 0, 0, tzinfo=timezone.utc)
        assert service_utc.is_post_10pm(ts) is False

    def test_morning(self, service_utc):
        ts = datetime(2024, 6, 15, 8, 0, 0, tzinfo=timezone.utc)
        assert service_utc.is_post_10pm(ts) is False

    def test_with_different_timezone(self, service_ist):
        # 10:00 PM IST = 16:30 UTC
        ts = datetime(2024, 6, 15, 16, 30, 0, tzinfo=timezone.utc)
        assert service_ist.is_post_10pm(ts) is True

    def test_before_10pm_ist(self, service_ist):
        # 9:59 PM IST = 16:29 UTC
        ts = datetime(2024, 6, 15, 16, 29, 0, tzinfo=timezone.utc)
        assert service_ist.is_post_10pm(ts) is False


class TestGetEntryDate:
    """Tests for the get_entry_date() synchronous method."""

    def test_normal_daytime_returns_same_date(self, service_utc):
        ts = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_late_night_returns_same_date(self, service_utc):
        ts = datetime(2024, 6, 15, 23, 59, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_midnight_returns_new_date(self, service_utc):
        ts = datetime(2024, 6, 16, 0, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 16)

    def test_timezone_conversion(self, service_ist):
        # 2024-06-15 23:00 UTC = 2024-06-16 04:30 IST
        ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        assert service_ist.get_entry_date(ts) == date(2024, 6, 16)


class TestGetEntryDateAsync:
    """Tests for the get_entry_date_async() method with state checking."""

    @pytest.mark.asyncio
    async def test_no_state_returns_calendar_date(self, service_utc):
        ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(ts)
        assert result == date(2024, 6, 15)

    @pytest.mark.asyncio
    async def test_post_10pm_diary_shifts_to_next_day(self, service_utc):
        # Generate diary at 10:30 PM
        gen_ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), gen_ts)

        # Input at 11:00 PM should go to next day
        input_ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 16)

    @pytest.mark.asyncio
    async def test_pre_10pm_diary_does_not_shift(self, service_utc):
        # Generate diary at 3:00 PM (before 10 PM)
        gen_ts = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), gen_ts)

        # Input at 4:00 PM should still be today
        input_ts = datetime(2024, 6, 15, 16, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 15)

    @pytest.mark.asyncio
    async def test_after_midnight_always_new_date(self, service_utc):
        # Generate diary at 10:30 PM on June 15
        gen_ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), gen_ts)

        # Input at 12:30 AM on June 16 should be June 16
        # (the state for June 15 doesn't affect June 16's own date)
        input_ts = datetime(2024, 6, 16, 0, 30, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 16)

    @pytest.mark.asyncio
    async def test_no_state_for_today_returns_today(self, service_utc):
        # State exists for a different date, not today
        gen_ts = datetime(2024, 6, 14, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 14), gen_ts)

        # Input on June 15 should be June 15
        input_ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 15)


class TestMarkDiaryGenerated:
    """Tests for the mark_diary_generated() method."""

    @pytest.mark.asyncio
    async def test_post_10pm_activates_next_day(self, service_utc):
        ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        state = await service_utc._repo.get_day_boundary_state(date(2024, 6, 15))
        assert state is not None
        assert state["next_day_collection_active"] is True

    @pytest.mark.asyncio
    async def test_pre_10pm_does_not_activate_next_day(self, service_utc):
        ts = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        state = await service_utc._repo.get_day_boundary_state(date(2024, 6, 15))
        assert state is not None
        assert state["next_day_collection_active"] is False

    @pytest.mark.asyncio
    async def test_records_generation_timestamp(self, service_utc):
        ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        state = await service_utc._repo.get_day_boundary_state(date(2024, 6, 15))
        assert state is not None
        assert state["diary_generated_at"] == ts.isoformat()


class TestHasDiaryBeenGeneratedPost10pm:
    """Tests for the has_diary_been_generated_post_10pm() method."""

    @pytest.mark.asyncio
    async def test_no_state_returns_false(self, service_utc):
        result = await service_utc.has_diary_been_generated_post_10pm(date(2024, 6, 15))
        assert result is False

    @pytest.mark.asyncio
    async def test_post_10pm_diary_returns_true(self, service_utc):
        ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        result = await service_utc.has_diary_been_generated_post_10pm(date(2024, 6, 15))
        assert result is True

    @pytest.mark.asyncio
    async def test_pre_10pm_diary_returns_false(self, service_utc):
        ts = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        result = await service_utc.has_diary_been_generated_post_10pm(date(2024, 6, 15))
        assert result is False
