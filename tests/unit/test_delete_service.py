"""Unit tests for DeleteService.

Tests initiate_delete keyboard, confirm_delete flows, and
get_confirmation_keyboard structure.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from diary_bot.delete_service import DeleteError, DeleteService
from diary_bot.models import Err, Ok


@pytest.fixture
def mock_repo():
    """Create a mock Repository."""
    repo = MagicMock()
    repo.delete_entries_by_date = AsyncMock(return_value=3)
    repo.delete_entries_by_range = AsyncMock(return_value=7)
    repo.delete_all_data = AsyncMock(return_value=15)
    return repo


@pytest.fixture
def delete_service(mock_repo):
    """Create a DeleteService with mocked repository."""
    return DeleteService(repo=mock_repo)


class TestInitiateDelete:
    """Tests for initiate_delete returning correct inline keyboard."""

    async def test_returns_inline_keyboard_with_3_buttons(self, delete_service):
        """initiate_delete should return an InlineKeyboardMarkup with 3 buttons."""
        markup = await delete_service.initiate_delete()

        # Each button is on its own row
        assert len(markup.inline_keyboard) == 3

    async def test_first_button_is_delete_by_date(self, delete_service):
        """First button should be 'Delete by date' with callback_data 'delete:by_date'."""
        markup = await delete_service.initiate_delete()

        button = markup.inline_keyboard[0][0]
        assert button.text == "Delete by date"
        assert button.callback_data == "delete:by_date"

    async def test_second_button_is_delete_date_range(self, delete_service):
        """Second button should be 'Delete date range' with callback_data 'delete:date_range'."""
        markup = await delete_service.initiate_delete()

        button = markup.inline_keyboard[1][0]
        assert button.text == "Delete date range"
        assert button.callback_data == "delete:date_range"

    async def test_third_button_is_delete_all(self, delete_service):
        """Third button should be 'Delete all data' with callback_data 'delete:all'."""
        markup = await delete_service.initiate_delete()

        button = markup.inline_keyboard[2][0]
        assert button.text == "Delete all data"
        assert button.callback_data == "delete:all"


class TestConfirmDeleteByDate:
    """Tests for confirm_delete with delete_type='by_date'."""

    async def test_calls_repo_with_correct_date(self, delete_service, mock_repo):
        """confirm_delete by_date should call repo.delete_entries_by_date with parsed date."""
        await delete_service.confirm_delete("by_date", "2024-03-15")

        mock_repo.delete_entries_by_date.assert_called_once_with(date(2024, 3, 15))

    async def test_returns_ok_with_count(self, delete_service, mock_repo):
        """confirm_delete by_date should return Ok with deleted count when entries found."""
        mock_repo.delete_entries_by_date = AsyncMock(return_value=5)

        result = await delete_service.confirm_delete("by_date", "2024-03-15")

        assert isinstance(result, Ok)
        assert "5" in result.value
        assert "deleted" in result.value.lower()


class TestConfirmDeleteDateRange:
    """Tests for confirm_delete with delete_type='date_range'."""

    async def test_calls_repo_with_correct_range(self, delete_service, mock_repo):
        """confirm_delete date_range should call repo.delete_entries_by_range with parsed dates."""
        await delete_service.confirm_delete("date_range", "2024-01-01:2024-01-31")

        mock_repo.delete_entries_by_range.assert_called_once_with(
            date(2024, 1, 1), date(2024, 1, 31)
        )

    async def test_returns_ok_with_count(self, delete_service, mock_repo):
        """confirm_delete date_range should return Ok with deleted count when entries found."""
        mock_repo.delete_entries_by_range = AsyncMock(return_value=12)

        result = await delete_service.confirm_delete("date_range", "2024-01-01:2024-01-31")

        assert isinstance(result, Ok)
        assert "12" in result.value
        assert "deleted" in result.value.lower()


class TestConfirmDeleteAll:
    """Tests for confirm_delete with delete_type='all'."""

    async def test_calls_repo_delete_all_data(self, delete_service, mock_repo):
        """confirm_delete all should call repo.delete_all_data."""
        await delete_service.confirm_delete("all", "")

        mock_repo.delete_all_data.assert_called_once()

    async def test_returns_ok_with_count(self, delete_service, mock_repo):
        """confirm_delete all should return Ok with deleted count when data exists."""
        mock_repo.delete_all_data = AsyncMock(return_value=42)

        result = await delete_service.confirm_delete("all", "")

        assert isinstance(result, Ok)
        assert "42" in result.value
        assert "deleted" in result.value.lower()


class TestConfirmDeleteNoEntries:
    """Tests for confirm_delete when no entries found (0 rows deleted)."""

    async def test_by_date_no_entries_returns_err(self, delete_service, mock_repo):
        """confirm_delete should return Err when repo returns 0 rows deleted."""
        mock_repo.delete_entries_by_date = AsyncMock(return_value=0)

        result = await delete_service.confirm_delete("by_date", "2024-06-01")

        assert isinstance(result, Err)
        assert "No entries found" in result.error.message

    async def test_date_range_no_entries_returns_err(self, delete_service, mock_repo):
        """confirm_delete date_range should return Err when no rows deleted."""
        mock_repo.delete_entries_by_range = AsyncMock(return_value=0)

        result = await delete_service.confirm_delete("date_range", "2024-06-01:2024-06-30")

        assert isinstance(result, Err)
        assert "No entries found" in result.error.message

    async def test_all_no_entries_returns_err(self, delete_service, mock_repo):
        """confirm_delete all should return Err when database is empty."""
        mock_repo.delete_all_data = AsyncMock(return_value=0)

        result = await delete_service.confirm_delete("all", "")

        assert isinstance(result, Err)
        assert "No entries found" in result.error.message


class TestGetConfirmationKeyboard:
    """Tests for get_confirmation_keyboard structure."""

    def test_returns_2_buttons(self, delete_service):
        """get_confirmation_keyboard should return markup with 2 buttons on one row."""
        markup = delete_service.get_confirmation_keyboard("by_date", "2024-03-15")

        assert len(markup.inline_keyboard) == 1  # one row
        assert len(markup.inline_keyboard[0]) == 2  # two buttons

    def test_confirm_button_text_and_callback(self, delete_service):
        """First button should be '✅ Confirm' with appropriate callback_data."""
        markup = delete_service.get_confirmation_keyboard("by_date", "2024-03-15")

        confirm_btn = markup.inline_keyboard[0][0]
        assert confirm_btn.text == "✅ Confirm"
        assert confirm_btn.callback_data == "confirm_delete:by_date:2024-03-15"

    def test_cancel_button_text_and_callback(self, delete_service):
        """Second button should be '❌ Cancel' with callback_data 'cancel_delete'."""
        markup = delete_service.get_confirmation_keyboard("by_date", "2024-03-15")

        cancel_btn = markup.inline_keyboard[0][1]
        assert cancel_btn.text == "❌ Cancel"
        assert cancel_btn.callback_data == "cancel_delete"

    def test_callback_data_includes_delete_type_and_target(self, delete_service):
        """Confirm callback_data should encode delete_type and target."""
        markup = delete_service.get_confirmation_keyboard("date_range", "2024-01-01:2024-01-31")

        confirm_btn = markup.inline_keyboard[0][0]
        assert confirm_btn.callback_data == "confirm_delete:date_range:2024-01-01:2024-01-31"


class TestDeleteError:
    """Tests for the DeleteError dataclass."""

    def test_message_field(self):
        """DeleteError should store the message."""
        err = DeleteError("something went wrong")
        assert err.message == "something went wrong"

    def test_equality(self):
        """DeleteErrors with same message should be equal."""
        err1 = DeleteError("test")
        err2 = DeleteError("test")
        assert err1 == err2
