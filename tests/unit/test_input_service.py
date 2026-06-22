"""Unit tests for InputService.store_text() and store_voice() methods.

Tests whitespace validation, successful storage, voice duration validation,
transcription flow, and error handling.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from diary_bot.input_service import InputError, InputService
from diary_bot.models import Err, Ok
from diary_bot.transcriber import TranscriptionError


@pytest.fixture
def mock_repo():
    """Create a mock Repository."""
    repo = MagicMock()
    repo.save_input = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_day_boundary():
    """Create a mock DayBoundaryService."""
    service = MagicMock()
    service.get_entry_date_async = AsyncMock(return_value=date(2024, 1, 15))
    return service


@pytest.fixture
def mock_transcriber():
    """Create a mock Transcriber."""
    transcriber = MagicMock()
    transcriber.transcribe = AsyncMock(return_value=Ok(value="Hello world"))
    return transcriber


@pytest.fixture
def input_service(mock_repo, mock_transcriber, mock_day_boundary):
    """Create an InputService with mocked dependencies."""
    return InputService(repo=mock_repo, transcriber=mock_transcriber, day_boundary=mock_day_boundary)


class TestStoreTextValidation:
    """Tests for whitespace/empty input rejection."""

    async def test_empty_string_rejected(self, input_service, mock_repo):
        """Empty string should be rejected without storing."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("", timestamp)

        assert isinstance(result, Err)
        assert "No text content detected" in result.error.message
        mock_repo.save_input.assert_not_called()

    async def test_whitespace_only_rejected(self, input_service, mock_repo):
        """Whitespace-only string should be rejected without storing."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("   ", timestamp)

        assert isinstance(result, Err)
        assert "No text content detected" in result.error.message
        mock_repo.save_input.assert_not_called()

    async def test_tabs_only_rejected(self, input_service, mock_repo):
        """Tabs-only string should be rejected without storing."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("\t\t\t", timestamp)

        assert isinstance(result, Err)
        assert "No text content detected" in result.error.message
        mock_repo.save_input.assert_not_called()

    async def test_newlines_only_rejected(self, input_service, mock_repo):
        """Newlines-only string should be rejected without storing."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("\n\n\n", timestamp)

        assert isinstance(result, Err)
        assert "No text content detected" in result.error.message
        mock_repo.save_input.assert_not_called()

    async def test_mixed_whitespace_rejected(self, input_service, mock_repo):
        """Mixed whitespace characters should be rejected without storing."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text(" \t \n \r ", timestamp)

        assert isinstance(result, Err)
        assert "No text content detected" in result.error.message
        mock_repo.save_input.assert_not_called()


class TestStoreTextSuccess:
    """Tests for successful text storage."""

    async def test_valid_text_stored_successfully(self, input_service, mock_repo, mock_day_boundary):
        """Valid text should be stored and return confirmation."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("Had a great morning walk", timestamp)

        assert isinstance(result, Ok)
        assert result.value == "✓ Noted"
        mock_day_boundary.get_entry_date_async.assert_called_once_with(timestamp)
        mock_repo.save_input.assert_called_once_with(
            entry_date=date(2024, 1, 15),
            text="Had a great morning walk",
            timestamp=timestamp,
            input_type="text",
        )

    async def test_text_with_leading_trailing_whitespace_stored(self, input_service, mock_repo):
        """Text with leading/trailing whitespace but non-empty content should be stored."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("  hello  ", timestamp)

        assert isinstance(result, Ok)
        assert result.value == "✓ Noted"
        # The original text (with whitespace) should be stored, not stripped
        mock_repo.save_input.assert_called_once_with(
            entry_date=date(2024, 1, 15),
            text="  hello  ",
            timestamp=timestamp,
            input_type="text",
        )

    async def test_single_character_stored(self, input_service, mock_repo):
        """Single non-whitespace character should be stored successfully."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

        result = await input_service.store_text("a", timestamp)

        assert isinstance(result, Ok)
        assert result.value == "✓ Noted"
        mock_repo.save_input.assert_called_once()


class TestStoreTextStorageFailure:
    """Tests for storage failure handling."""

    async def test_repository_exception_returns_error(self, input_service, mock_repo):
        """If Repository.save_input() raises, an Err should be returned."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        mock_repo.save_input = AsyncMock(side_effect=Exception("DB connection lost"))

        result = await input_service.store_text("Hello world", timestamp)

        assert isinstance(result, Err)
        assert "Failed to save" in result.error.message

    async def test_repository_exception_mentions_retry(self, input_service, mock_repo):
        """Error message should prompt the user to retry."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        mock_repo.save_input = AsyncMock(side_effect=RuntimeError("disk full"))

        result = await input_service.store_text("Important thought", timestamp)

        assert isinstance(result, Err)
        assert "try again" in result.error.message.lower()


class TestInputError:
    """Tests for the InputError type."""

    def test_input_error_message(self):
        """InputError should store the message."""
        err = InputError("something went wrong")
        assert err.message == "something went wrong"

    def test_input_error_equality(self):
        """InputErrors with same message should be equal."""
        err1 = InputError("test")
        err2 = InputError("test")
        assert err1 == err2

    def test_input_error_inequality(self):
        """InputErrors with different messages should not be equal."""
        err1 = InputError("test1")
        err2 = InputError("test2")
        assert err1 != err2

    def test_input_error_repr(self):
        """InputError should have a readable repr."""
        err = InputError("oops")
        assert "oops" in repr(err)


class TestStoreVoiceDurationValidation:
    """Tests for voice note duration validation."""

    async def test_duration_over_60_seconds_rejected(self, input_service, mock_repo, mock_transcriber):
        """Voice notes longer than 60 seconds should be rejected."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 100

        result = await input_service.store_voice(audio, duration=61, timestamp=timestamp)

        assert isinstance(result, Err)
        assert "too long" in result.error.message.lower()
        assert "60" in result.error.message
        mock_transcriber.transcribe.assert_not_called()
        mock_repo.save_input.assert_not_called()

    async def test_duration_exactly_60_accepted(self, input_service, mock_transcriber):
        """Voice notes at exactly 60 seconds should be accepted."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 100

        result = await input_service.store_voice(audio, duration=60, timestamp=timestamp)

        assert isinstance(result, Ok)
        mock_transcriber.transcribe.assert_called_once_with(audio)

    async def test_duration_1_second_accepted(self, input_service, mock_transcriber):
        """Short voice notes should be accepted."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 50

        result = await input_service.store_voice(audio, duration=1, timestamp=timestamp)

        assert isinstance(result, Ok)
        mock_transcriber.transcribe.assert_called_once_with(audio)


class TestStoreVoiceSuccess:
    """Tests for successful voice transcription and storage."""

    async def test_successful_transcription_stored(
        self, input_service, mock_repo, mock_transcriber, mock_day_boundary
    ):
        """Successful transcription should be stored with input_type='voice'."""
        timestamp = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        audio = b"\x00" * 200
        mock_transcriber.transcribe = AsyncMock(return_value=Ok(value="Meeting at 3pm"))

        result = await input_service.store_voice(audio, duration=10, timestamp=timestamp)

        assert isinstance(result, Ok)
        assert result.value == "Meeting at 3pm"
        mock_day_boundary.get_entry_date_async.assert_called_once_with(timestamp)
        mock_repo.save_input.assert_called_once_with(
            entry_date=date(2024, 1, 15),
            text="Meeting at 3pm",
            timestamp=timestamp,
            input_type="voice",
        )

    async def test_returns_transcribed_text(self, input_service, mock_transcriber):
        """store_voice should return the transcribed text to the caller."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 100
        mock_transcriber.transcribe = AsyncMock(
            return_value=Ok(value="Had a wonderful lunch with colleagues")
        )

        result = await input_service.store_voice(audio, duration=30, timestamp=timestamp)

        assert isinstance(result, Ok)
        assert result.value == "Had a wonderful lunch with colleagues"


class TestStoreVoiceTranscriptionFailure:
    """Tests for transcription failure handling."""

    async def test_transcription_failure_returns_error(
        self, input_service, mock_repo, mock_transcriber
    ):
        """If transcription fails, an Err with a user-friendly message should be returned."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 100
        mock_transcriber.transcribe = AsyncMock(
            return_value=Err(error=TranscriptionError(message="API timeout"))
        )

        result = await input_service.store_voice(audio, duration=30, timestamp=timestamp)

        assert isinstance(result, Err)
        assert "transcription failed" in result.error.message.lower()
        assert "text" in result.error.message.lower()  # suggests sending as text
        mock_repo.save_input.assert_not_called()


class TestStoreVoiceStorageFailure:
    """Tests for storage failure after successful transcription."""

    async def test_storage_failure_returns_error(self, input_service, mock_repo, mock_transcriber):
        """If Repository.save_input() raises after transcription, an Err should be returned."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        audio = b"\x00" * 100
        mock_transcriber.transcribe = AsyncMock(return_value=Ok(value="Some text"))
        mock_repo.save_input = AsyncMock(side_effect=Exception("DB error"))

        result = await input_service.store_voice(audio, duration=15, timestamp=timestamp)

        assert isinstance(result, Err)
        assert "failed to save" in result.error.message.lower()
