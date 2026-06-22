"""Unit tests for ReminderService."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from diary_bot.models import Err, Ok
from diary_bot.reminder_service import ReminderError, ReminderService


@pytest.fixture
def service() -> ReminderService:
    """Create a ReminderService with a 24-hour threshold."""
    return ReminderService(authorized_user_id=12345, threshold_hours=24)


@pytest.fixture
def disabled_service() -> ReminderService:
    """Create a ReminderService with reminders disabled."""
    return ReminderService(authorized_user_id=12345, threshold_hours=None)


class TestRecordActivity:
    """Tests for record_activity method."""

    def test_updates_last_input_time(self, service: ReminderService) -> None:
        """record_activity updates last input time."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)

        assert service._last_input_time == now

    def test_resets_reminder_sent_flag(self, service: ReminderService) -> None:
        """record_activity resets reminder_sent flag."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        # Simulate a reminder being sent
        service.record_activity(now)
        service.mark_reminder_sent()
        assert service._reminder_sent is True

        # New activity should reset the flag
        later = datetime(2024, 1, 16, 12, 0, 0)
        service.record_activity(later)
        assert service._reminder_sent is False


class TestShouldSendReminder:
    """Tests for should_send_reminder method."""

    def test_returns_false_when_disabled(self, disabled_service: ReminderService) -> None:
        """should_send_reminder returns False when disabled."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        disabled_service.record_activity(now)

        check_time = now + timedelta(hours=48)
        assert disabled_service.should_send_reminder(check_time) is False

    def test_returns_false_when_no_activity_recorded(self, service: ReminderService) -> None:
        """should_send_reminder returns False when no activity recorded."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        assert service.should_send_reminder(now) is False

    def test_returns_false_when_reminder_already_sent(self, service: ReminderService) -> None:
        """should_send_reminder returns False when reminder already sent."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)
        service.mark_reminder_sent()

        check_time = now + timedelta(hours=48)
        assert service.should_send_reminder(check_time) is False

    def test_returns_true_when_threshold_exceeded(self, service: ReminderService) -> None:
        """should_send_reminder returns True when threshold exceeded."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)

        check_time = now + timedelta(hours=24)
        assert service.should_send_reminder(check_time) is True

    def test_returns_false_when_threshold_not_exceeded(self, service: ReminderService) -> None:
        """should_send_reminder returns False when threshold not yet exceeded."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)

        check_time = now + timedelta(hours=23, minutes=59)
        assert service.should_send_reminder(check_time) is False


class TestMarkReminderSent:
    """Tests for mark_reminder_sent method."""

    def test_prevents_subsequent_reminders_until_new_activity(
        self, service: ReminderService
    ) -> None:
        """mark_reminder_sent prevents subsequent reminders until new activity."""
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)

        # Threshold exceeded, reminder should fire
        check_time = now + timedelta(hours=25)
        assert service.should_send_reminder(check_time) is True

        # Mark reminder sent
        service.mark_reminder_sent()

        # Even with more time passing, should not fire again
        later = now + timedelta(hours=50)
        assert service.should_send_reminder(later) is False

        # New activity resets, so another reminder can fire later
        new_activity = now + timedelta(hours=51)
        service.record_activity(new_activity)
        after_new_threshold = new_activity + timedelta(hours=24)
        assert service.should_send_reminder(after_new_threshold) is True


class TestValidateThreshold:
    """Tests for validate_threshold static method."""

    def test_accepts_valid_range(self) -> None:
        """validate_threshold accepts valid range (1 to 168)."""
        assert ReminderService.validate_threshold(1) == Ok(1)
        assert ReminderService.validate_threshold(24) == Ok(24)
        assert ReminderService.validate_threshold(168) == Ok(168)
        assert ReminderService.validate_threshold(100) == Ok(100)

    def test_accepts_none_disabled(self) -> None:
        """validate_threshold accepts None (disabled)."""
        assert ReminderService.validate_threshold(None) == Ok(None)

    def test_rejects_zero(self) -> None:
        """validate_threshold rejects 0."""
        result = ReminderService.validate_threshold(0)
        assert isinstance(result, Err)
        assert isinstance(result.error, ReminderError)

    def test_rejects_greater_than_168(self) -> None:
        """validate_threshold rejects > 168."""
        result = ReminderService.validate_threshold(169)
        assert isinstance(result, Err)
        assert isinstance(result.error, ReminderError)

    def test_rejects_negative(self) -> None:
        """validate_threshold rejects negative values."""
        result = ReminderService.validate_threshold(-1)
        assert isinstance(result, Err)
        assert isinstance(result.error, ReminderError)


class TestSendReminder:
    """Tests for the async send_reminder method."""

    @pytest.mark.asyncio
    async def test_sends_message_when_threshold_exceeded(self) -> None:
        """send_reminder sends a message when should_send_reminder is True."""
        service = ReminderService(authorized_user_id=12345, threshold_hours=1)
        now = datetime(2024, 1, 15, 10, 0, 0)
        service.record_activity(now)
        # Manually set _last_input_time far enough back
        service._last_input_time = datetime(2024, 1, 15, 8, 0, 0)

        bot = AsyncMock()
        await service.send_reminder(bot)

        bot.send_message.assert_called_once()
        assert service._reminder_sent is True

    @pytest.mark.asyncio
    async def test_does_not_send_when_disabled(self) -> None:
        """send_reminder does not send when reminders are disabled."""
        service = ReminderService(authorized_user_id=12345, threshold_hours=None)
        service._last_input_time = datetime(2024, 1, 1, 0, 0, 0)

        bot = AsyncMock()
        await service.send_reminder(bot)

        bot.send_message.assert_not_called()


class TestUpdateThreshold:
    """Tests for update_threshold method."""

    def test_updates_threshold(self, service: ReminderService) -> None:
        """update_threshold updates the internal threshold value."""
        service.update_threshold(48)
        assert service._threshold_hours == 48

    def test_updates_to_none(self, service: ReminderService) -> None:
        """update_threshold can disable reminders by setting None."""
        service.update_threshold(None)
        assert service._threshold_hours is None
