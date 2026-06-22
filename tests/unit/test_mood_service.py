"""Unit tests for MoodService and validate_mood_times.

Tests send_check_in, record_response (within/outside 2-hour window),
expire_check_in, and validate_mood_times validation logic.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from diary_bot.models import CheckInStatus, Err, MoodCheckIn, Ok
from diary_bot.mood_service import MoodError, MoodService, validate_mood_times


@pytest.fixture
def mock_repo():
    """Create a mock Repository with mood-related methods."""
    repo = MagicMock()
    repo.save_mood_check_in = AsyncMock(return_value=1)
    repo.save_mood_response = AsyncMock()
    repo.get_pending_check_in = AsyncMock(return_value=None)
    repo.mark_check_in_expired = AsyncMock()
    repo.mark_check_in_responded = AsyncMock()
    return repo


@pytest.fixture
def mock_bot():
    """Create a mock Telegram Bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mood_service(mock_repo):
    """Create a MoodService with mocked repository."""
    return MoodService(repo=mock_repo, authorized_user_id=12345)


class TestSendCheckIn:
    """Tests for MoodService.send_check_in()."""

    async def test_creates_db_record(self, mood_service, mock_repo, mock_bot):
        """send_check_in should create a mood check-in record in the DB."""
        await mood_service.send_check_in(mock_bot)

        mock_repo.save_mood_check_in.assert_called_once()
        # Verify a datetime was passed
        call_args = mock_repo.save_mood_check_in.call_args[0]
        assert isinstance(call_args[0], datetime)

    async def test_sends_telegram_message(self, mood_service, mock_repo, mock_bot):
        """send_check_in should send a message asking how the user is feeling."""
        await mood_service.send_check_in(mock_bot)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 12345
        assert "feeling" in call_kwargs["text"].lower()

    async def test_returns_check_in_id(self, mood_service, mock_repo, mock_bot):
        """send_check_in should return the check-in ID for scheduling expiry."""
        mock_repo.save_mood_check_in = AsyncMock(return_value=42)

        result = await mood_service.send_check_in(mock_bot)

        assert result == 42


class TestRecordResponse:
    """Tests for MoodService.record_response()."""

    async def test_within_2_hours_saves_response(self, mood_service, mock_repo):
        """Response within 2 hours should be saved and check-in marked responded."""
        scheduled_at = datetime(2024, 1, 15, 9, 0, 0)
        check_in = MoodCheckIn(
            id=1, scheduled_at=scheduled_at, status=CheckInStatus.PENDING
        )
        mock_repo.get_pending_check_in = AsyncMock(return_value=check_in)

        response_time = scheduled_at + timedelta(hours=1)
        result = await mood_service.record_response(
            "Feeling great!", check_in_id=1, timestamp=response_time
        )

        assert isinstance(result, Ok)
        mock_repo.save_mood_response.assert_called_once_with(
            1, "Feeling great!", response_time, response_time.date()
        )
        mock_repo.mark_check_in_responded.assert_called_once_with(1)

    async def test_exactly_at_2_hours_saves_response(self, mood_service, mock_repo):
        """Response at exactly 2 hours should still be accepted."""
        scheduled_at = datetime(2024, 1, 15, 9, 0, 0)
        check_in = MoodCheckIn(
            id=1, scheduled_at=scheduled_at, status=CheckInStatus.PENDING
        )
        mock_repo.get_pending_check_in = AsyncMock(return_value=check_in)

        response_time = scheduled_at + timedelta(hours=2)
        result = await mood_service.record_response(
            "Doing okay", check_in_id=1, timestamp=response_time
        )

        assert isinstance(result, Ok)
        mock_repo.save_mood_response.assert_called_once()

    async def test_after_2_hours_returns_error(self, mood_service, mock_repo):
        """Response after 2 hours should be rejected."""
        scheduled_at = datetime(2024, 1, 15, 9, 0, 0)
        check_in = MoodCheckIn(
            id=1, scheduled_at=scheduled_at, status=CheckInStatus.PENDING
        )
        mock_repo.get_pending_check_in = AsyncMock(return_value=check_in)

        response_time = scheduled_at + timedelta(hours=2, seconds=1)
        result = await mood_service.record_response(
            "Too late", check_in_id=1, timestamp=response_time
        )

        assert isinstance(result, Err)
        assert "window" in result.error.message.lower() or "expired" in result.error.message.lower()
        mock_repo.save_mood_response.assert_not_called()
        mock_repo.mark_check_in_responded.assert_not_called()

    async def test_no_pending_check_in_returns_error(self, mood_service, mock_repo):
        """Response with no pending check-in should be rejected."""
        mock_repo.get_pending_check_in = AsyncMock(return_value=None)

        result = await mood_service.record_response(
            "Hello", check_in_id=1, timestamp=datetime(2024, 1, 15, 10, 0, 0)
        )

        assert isinstance(result, Err)
        assert "no pending" in result.error.message.lower()
        mock_repo.save_mood_response.assert_not_called()

    async def test_mismatched_check_in_id_returns_error(self, mood_service, mock_repo):
        """Response with a check-in ID that doesn't match the pending one should be rejected."""
        scheduled_at = datetime(2024, 1, 15, 9, 0, 0)
        check_in = MoodCheckIn(
            id=1, scheduled_at=scheduled_at, status=CheckInStatus.PENDING
        )
        mock_repo.get_pending_check_in = AsyncMock(return_value=check_in)

        result = await mood_service.record_response(
            "Hello", check_in_id=99, timestamp=scheduled_at + timedelta(minutes=30)
        )

        assert isinstance(result, Err)
        assert "no pending" in result.error.message.lower()


class TestExpireCheckIn:
    """Tests for MoodService.expire_check_in()."""

    async def test_marks_check_in_as_expired(self, mood_service, mock_repo):
        """expire_check_in should call repo.mark_check_in_expired with the correct ID."""
        await mood_service.expire_check_in(check_in_id=5)

        mock_repo.mark_check_in_expired.assert_called_once_with(5)


class TestValidateMoodTimes:
    """Tests for validate_mood_times()."""

    def test_valid_3_times_with_2h_spacing_in_range(self):
        """Valid times: 3 times between 08:00-22:00 with >= 2h spacing."""
        result = validate_mood_times(["09:00", "13:00", "18:00"])

        assert isinstance(result, Ok)
        assert result.value == ["09:00", "13:00", "18:00"]

    def test_valid_times_are_sorted(self):
        """Times should be returned sorted regardless of input order."""
        result = validate_mood_times(["18:00", "09:00", "13:00"])

        assert isinstance(result, Ok)
        assert result.value == ["09:00", "13:00", "18:00"]

    def test_valid_boundary_times(self):
        """08:00 and 22:00 are valid boundary values."""
        result = validate_mood_times(["08:00", "10:00", "12:00"])

        assert isinstance(result, Ok)
        assert result.value == ["08:00", "10:00", "12:00"]

    def test_rejects_fewer_than_3_times(self):
        """Fewer than 3 times should be rejected."""
        result = validate_mood_times(["09:00", "13:00"])

        assert isinstance(result, Err)
        assert "3" in result.error.message

    def test_rejects_more_than_3_times(self):
        """More than 3 times should be rejected."""
        result = validate_mood_times(["09:00", "11:00", "14:00", "18:00"])

        assert isinstance(result, Err)
        assert "3" in result.error.message

    def test_rejects_empty_list(self):
        """Empty list should be rejected."""
        result = validate_mood_times([])

        assert isinstance(result, Err)
        assert "3" in result.error.message

    def test_rejects_time_before_0800(self):
        """Times before 08:00 should be rejected."""
        result = validate_mood_times(["07:59", "10:00", "14:00"])

        assert isinstance(result, Err)
        assert "outside" in result.error.message.lower() or "range" in result.error.message.lower()

    def test_rejects_time_after_2200(self):
        """Times after 22:00 should be rejected."""
        result = validate_mood_times(["09:00", "13:00", "22:01"])

        assert isinstance(result, Err)
        assert "outside" in result.error.message.lower() or "range" in result.error.message.lower()

    def test_rejects_spacing_less_than_2_hours(self):
        """Times with less than 2 hours spacing should be rejected."""
        result = validate_mood_times(["09:00", "10:30", "14:00"])

        assert isinstance(result, Err)
        assert "spacing" in result.error.message.lower()

    def test_rejects_identical_times(self):
        """Identical times should be rejected (0 spacing)."""
        result = validate_mood_times(["09:00", "09:00", "14:00"])

        assert isinstance(result, Err)
        assert "spacing" in result.error.message.lower()

    def test_exact_2_hour_spacing_accepted(self):
        """Exactly 2 hours of spacing should be accepted."""
        result = validate_mood_times(["08:00", "10:00", "12:00"])

        assert isinstance(result, Ok)
        assert result.value == ["08:00", "10:00", "12:00"]

    def test_invalid_time_format_rejected(self):
        """Invalid time format strings should be rejected."""
        result = validate_mood_times(["9am", "13:00", "18:00"])

        assert isinstance(result, Err)
        assert "format" in result.error.message.lower()


class TestMoodError:
    """Tests for the MoodError type."""

    def test_mood_error_message(self):
        """MoodError should store the message."""
        err = MoodError("something went wrong")
        assert err.message == "something went wrong"

    def test_mood_error_equality(self):
        """MoodErrors with same message should be equal."""
        err1 = MoodError("test")
        err2 = MoodError("test")
        assert err1 == err2

    def test_mood_error_repr(self):
        """MoodError should have a readable repr."""
        err = MoodError("oops")
        assert "oops" in repr(err)
