"""Unit tests for the SchedulerService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from diary_bot.models import Tone, UserSettings
from diary_bot.scheduler_service import SchedulerService


@pytest.fixture
def mock_scheduler():
    """Create a mock AsyncIOScheduler."""
    scheduler = MagicMock()
    scheduler.add_job = MagicMock()
    scheduler.remove_all_jobs = MagicMock()
    scheduler.remove_job = MagicMock()
    scheduler.get_job = MagicMock(return_value=None)
    return scheduler


@pytest.fixture
def mock_mood_service():
    """Create a mock MoodService."""
    service = MagicMock()
    service.send_check_in = AsyncMock()
    return service


@pytest.fixture
def mock_memory_service():
    """Create a mock MemoryService."""
    service = MagicMock()
    service.check_and_send_memory = AsyncMock()
    return service


@pytest.fixture
def mock_reminder_service():
    """Create a mock ReminderService."""
    service = MagicMock()
    service.send_reminder = AsyncMock()
    service.record_activity = MagicMock()
    return service


@pytest.fixture
def mock_bot():
    """Create a mock Telegram bot."""
    return MagicMock()


@pytest.fixture
def mock_diary_service():
    """Create a mock DiaryService."""
    service = MagicMock()
    service.auto_generate_diary = AsyncMock()
    return service


@pytest.fixture
def scheduler_service(
    mock_scheduler,
    mock_mood_service,
    mock_memory_service,
    mock_reminder_service,
    mock_diary_service,
    mock_bot,
):
    """Create a SchedulerService with all mock dependencies."""
    return SchedulerService(
        scheduler=mock_scheduler,
        mood_service=mock_mood_service,
        memory_service=mock_memory_service,
        reminder_service=mock_reminder_service,
        diary_service=mock_diary_service,
        authorized_user_id=12345,
        bot=mock_bot,
    )


def _make_settings(
    mood_times: list[str] | None = None,
    memory_time: str | None = None,
    inactivity_hours: int | None = None,
) -> UserSettings:
    """Helper to create UserSettings with defaults."""
    return UserSettings(
        tone=Tone.REFLECTIVE,
        timezone="UTC",
        mood_check_in_times=mood_times or ["09:00", "13:00", "20:00"],
        inactivity_threshold_hours=inactivity_hours,
        memory_callback_time=memory_time,
    )


class TestSetupSchedules:
    """Tests for setup_schedules method."""

    async def test_adds_mood_check_in_jobs_at_configured_times(
        self, scheduler_service, mock_scheduler, mock_mood_service, mock_bot
    ):
        """setup_schedules adds mood check-in jobs at configured times."""
        settings = _make_settings(mood_times=["08:30", "12:00", "19:30"])

        await scheduler_service.setup_schedules(settings)

        # Should remove all existing jobs first
        mock_scheduler.remove_all_jobs.assert_called_once()

        # Should add 3 mood check-in jobs
        mood_calls = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id", "").startswith("mood_check_in_")
        ]
        assert len(mood_calls) == 3

        # Verify job IDs
        job_ids = [call.kwargs["id"] for call in mood_calls]
        assert "mood_check_in_0" in job_ids
        assert "mood_check_in_1" in job_ids
        assert "mood_check_in_2" in job_ids

        # Verify the callable is mood_service.send_check_in
        for call in mood_calls:
            assert call.args[0] == mock_mood_service.send_check_in
            assert call.kwargs["args"] == [mock_bot]

    async def test_adds_memory_callback_job_when_time_configured(
        self, scheduler_service, mock_scheduler, mock_memory_service, mock_bot
    ):
        """setup_schedules adds memory callback job when time is configured."""
        settings = _make_settings(memory_time="21:00")

        await scheduler_service.setup_schedules(settings)

        memory_calls = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "memory_callback"
        ]
        assert len(memory_calls) == 1

        call = memory_calls[0]
        assert call.args[0] == mock_memory_service.check_and_send_memory
        assert call.kwargs["args"] == [mock_bot]

    async def test_does_not_add_memory_callback_when_time_is_none(
        self, scheduler_service, mock_scheduler
    ):
        """setup_schedules does not add memory callback when time is None."""
        settings = _make_settings(memory_time=None)

        await scheduler_service.setup_schedules(settings)

        memory_calls = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "memory_callback"
        ]
        assert len(memory_calls) == 0

    async def test_adds_inactivity_reminder_job_when_threshold_configured(
        self, scheduler_service, mock_scheduler, mock_reminder_service, mock_bot
    ):
        """setup_schedules adds inactivity reminder job when threshold is configured."""
        settings = _make_settings(inactivity_hours=4)

        await scheduler_service.setup_schedules(settings)

        reminder_calls = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "inactivity_reminder"
        ]
        assert len(reminder_calls) == 1

        call = reminder_calls[0]
        assert call.args[0] == mock_reminder_service.send_reminder
        assert call.kwargs["args"] == [mock_bot]

    async def test_does_not_add_inactivity_reminder_when_threshold_is_none(
        self, scheduler_service, mock_scheduler
    ):
        """setup_schedules does not add inactivity reminder when threshold is None."""
        settings = _make_settings(inactivity_hours=None)

        await scheduler_service.setup_schedules(settings)

        reminder_calls = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "inactivity_reminder"
        ]
        assert len(reminder_calls) == 0


class TestUpdateMoodTimes:
    """Tests for update_mood_times method."""

    async def test_removes_old_mood_jobs_and_adds_new_ones(
        self, scheduler_service, mock_scheduler, mock_mood_service, mock_bot
    ):
        """update_mood_times removes old mood jobs and adds new ones."""
        # Simulate existing jobs
        mock_scheduler.get_job = MagicMock(
            side_effect=lambda job_id: MagicMock() if "mood_check_in" in job_id else None
        )

        new_times = ["10:00", "14:00", "18:00"]
        await scheduler_service.update_mood_times(new_times)

        # Should attempt to remove old mood jobs
        assert mock_scheduler.remove_job.call_count == 3
        removed_ids = [call.args[0] for call in mock_scheduler.remove_job.call_args_list]
        assert "mood_check_in_0" in removed_ids
        assert "mood_check_in_1" in removed_ids
        assert "mood_check_in_2" in removed_ids

        # Should add 3 new mood jobs
        assert mock_scheduler.add_job.call_count == 3
        job_ids = [call.kwargs["id"] for call in mock_scheduler.add_job.call_args_list]
        assert "mood_check_in_0" in job_ids
        assert "mood_check_in_1" in job_ids
        assert "mood_check_in_2" in job_ids


class TestResetInactivityTimer:
    """Tests for reset_inactivity_timer method."""

    async def test_calls_reminder_service_record_activity(
        self, scheduler_service, mock_reminder_service
    ):
        """reset_inactivity_timer calls reminder_service.record_activity."""
        with patch("diary_bot.scheduler_service.datetime") as mock_datetime:
            mock_now = MagicMock()
            mock_datetime.utcnow.return_value = mock_now

            await scheduler_service.reset_inactivity_timer()

            mock_reminder_service.record_activity.assert_called_once_with(mock_now)
