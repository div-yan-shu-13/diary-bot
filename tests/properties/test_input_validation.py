# Feature: telegram-diary-bot, Property 2: Whitespace Input Rejection
"""Property-based test for whitespace input rejection.

Validates: Requirements 1.5

For any string composed entirely of whitespace characters (spaces, tabs, newlines,
or combinations thereof), the input validation SHALL reject the string and the stored
input count SHALL remain unchanged.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from diary_bot.input_service import InputService
from diary_bot.models import Err, Ok


# Strategy: generate strings composed entirely of whitespace characters
whitespace_strings = st.text(
    alphabet=" \t\n\r\x0b\x0c",
    min_size=1,
)


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


@settings(max_examples=100)
@given(whitespace_input=whitespace_strings)
async def test_whitespace_only_input_rejected(whitespace_input: str) -> None:
    """Any string composed entirely of whitespace characters is rejected."""
    # **Validates: Requirements 1.5**
    mock_repo = MagicMock()
    mock_repo.save_input = AsyncMock(return_value=1)
    mock_day_boundary = MagicMock()
    mock_day_boundary.get_entry_date_async = AsyncMock(return_value=date(2024, 1, 15))
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe = AsyncMock(return_value=Ok(value="text"))

    service = InputService(repo=mock_repo, transcriber=mock_transcriber, day_boundary=mock_day_boundary)
    timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

    result = await service.store_text(whitespace_input, timestamp)

    # Whitespace-only input must be rejected
    assert isinstance(result, Err), (
        f"Expected Err for whitespace-only input {whitespace_input!r}, got {result}"
    )
    # Repository.save_input must never be called (stored input count unchanged)
    mock_repo.save_input.assert_not_called()


@settings(max_examples=100)
@given(whitespace_input=whitespace_strings)
async def test_whitespace_rejection_preserves_input_count(whitespace_input: str) -> None:
    """Stored input count remains unchanged after whitespace rejection."""
    # **Validates: Requirements 1.5**
    mock_repo = MagicMock()
    mock_repo.save_input = AsyncMock(return_value=1)
    mock_day_boundary = MagicMock()
    mock_day_boundary.get_entry_date_async = AsyncMock(return_value=date(2024, 1, 15))
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe = AsyncMock(return_value=Ok(value="text"))

    service = InputService(repo=mock_repo, transcriber=mock_transcriber, day_boundary=mock_day_boundary)
    timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

    await service.store_text(whitespace_input, timestamp)

    # Verify save_input was never called - the stored input count is unchanged
    assert mock_repo.save_input.call_count == 0, (
        f"save_input was called {mock_repo.save_input.call_count} times "
        f"for whitespace input {whitespace_input!r}"
    )


async def test_empty_string_rejected() -> None:
    """Empty string is also rejected as a boundary case of whitespace input."""
    # **Validates: Requirements 1.5**
    mock_repo = MagicMock()
    mock_repo.save_input = AsyncMock(return_value=1)
    mock_day_boundary = MagicMock()
    mock_day_boundary.get_entry_date_async = AsyncMock(return_value=date(2024, 1, 15))
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe = AsyncMock(return_value=Ok(value="text"))

    service = InputService(repo=mock_repo, transcriber=mock_transcriber, day_boundary=mock_day_boundary)
    timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

    result = await service.store_text("", timestamp)

    assert isinstance(result, Err), f"Expected Err for empty string, got {result}"
    mock_repo.save_input.assert_not_called()
