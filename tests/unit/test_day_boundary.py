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


class TestGetEntryDate:
    """Tests for the get_entry_date() method with 3 AM day boundary."""

    def test_normal_daytime_returns_same_date(self, service_utc):
        ts = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_late_night_returns_same_date(self, service_utc):
        ts = datetime(2024, 6, 15, 23, 59, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_before_3am_returns_previous_date(self, service_utc):
        # 2:59 AM belongs to previous day
        ts = datetime(2024, 6, 16, 2, 59, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_exactly_3am_returns_new_date(self, service_utc):
        # 3:00 AM starts the new day
        ts = datetime(2024, 6, 16, 3, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 16)

    def test_midnight_returns_previous_date(self, service_utc):
        # Midnight is before 3 AM, so belongs to previous day
        ts = datetime(2024, 6, 16, 0, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_1am_returns_previous_date(self, service_utc):
        ts = datetime(2024, 6, 16, 1, 0, 0, tzinfo=timezone.utc)
        assert service_utc.get_entry_date(ts) == date(2024, 6, 15)

    def test_timezone_conversion_ist(self, service_ist):
        # 2024-06-15 23:00 UTC = 2024-06-16 04:30 IST (after 3 AM IST)
        ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        assert service_ist.get_entry_date(ts) == date(2024, 6, 16)

    def test_timezone_before_3am_ist(self, service_ist):
        # 2024-06-15 21:00 UTC = 2024-06-16 02:30 IST (before 3 AM IST, so June 15)
        ts = datetime(2024, 6, 15, 21, 0, 0, tzinfo=timezone.utc)
        assert service_ist.get_entry_date(ts) == date(2024, 6, 15)


class TestGetEntryDateAsync:
    """Tests for the get_entry_date_async() — always returns logical date, no shifting."""

    @pytest.mark.asyncio
    async def test_returns_logical_date(self, service_utc):
        ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(ts)
        assert result == date(2024, 6, 15)

    @pytest.mark.asyncio
    async def test_before_3am_returns_previous_date(self, service_utc):
        ts = datetime(2024, 6, 16, 1, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(ts)
        assert result == date(2024, 6, 15)

    @pytest.mark.asyncio
    async def test_after_3am_returns_current_date(self, service_utc):
        ts = datetime(2024, 6, 16, 3, 30, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(ts)
        assert result == date(2024, 6, 16)

    @pytest.mark.asyncio
    async def test_no_day_shifting_after_diary_generated(self, service_utc):
        """Even after a diary is generated, inputs still belong to the same day."""
        # Generate diary at 10:30 PM
        gen_ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), gen_ts)

        # Input at 11:00 PM should STILL be June 15 (no shifting)
        input_ts = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 15)

    @pytest.mark.asyncio
    async def test_no_day_shifting_after_midnight(self, service_utc):
        """After midnight but before 3 AM, inputs still belong to previous day."""
        # Generate diary at 10:30 PM
        gen_ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), gen_ts)

        # Input at 12:30 AM still belongs to June 15
        input_ts = datetime(2024, 6, 16, 0, 30, 0, tzinfo=timezone.utc)
        result = await service_utc.get_entry_date_async(input_ts)
        assert result == date(2024, 6, 15)


class TestMarkDiaryGenerated:
    """Tests for the mark_diary_generated() method."""

    @pytest.mark.asyncio
    async def test_records_generation_timestamp(self, service_utc):
        ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        state = await service_utc._repo.get_day_boundary_state(date(2024, 6, 15))
        assert state is not None
        assert state["diary_generated_at"] == ts.isoformat()

    @pytest.mark.asyncio
    async def test_never_activates_next_day(self, service_utc):
        """mark_diary_generated never shifts inputs to next day."""
        ts = datetime(2024, 6, 15, 22, 30, 0, tzinfo=timezone.utc)
        await service_utc.mark_diary_generated(date(2024, 6, 15), ts)

        state = await service_utc._repo.get_day_boundary_state(date(2024, 6, 15))
        assert state is not None
        assert state["next_day_collection_active"] is False
