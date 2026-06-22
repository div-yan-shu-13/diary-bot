"""Delete service for the Telegram Diary Bot.

Provides data deletion with inline keyboard confirmation flow.
"""

from dataclasses import dataclass
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from diary_bot.models import Err, Ok, Result
from diary_bot.repository import Repository


@dataclass
class DeleteError:
    """Represents an error during a delete operation."""

    message: str


class DeleteService:
    """Handles data deletion with inline keyboard confirmation flow."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def initiate_delete(self) -> InlineKeyboardMarkup:
        """Return inline keyboard with deletion options.

        Presents three buttons: Delete by date, Delete date range, Delete all data.
        """
        keyboard = [
            [InlineKeyboardButton("Delete by date", callback_data="delete:by_date")],
            [InlineKeyboardButton("Delete date range", callback_data="delete:date_range")],
            [InlineKeyboardButton("Delete all data", callback_data="delete:all")],
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_confirmation_keyboard(self, delete_type: str, target: str) -> InlineKeyboardMarkup:
        """Return inline keyboard with Confirm and Cancel buttons.

        Args:
            delete_type: One of "by_date", "date_range", "all".
            target: The target specification (date, range, or empty for all).
        """
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data=f"confirm_delete:{delete_type}:{target}",
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="cancel_delete",
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def confirm_delete(self, delete_type: str, target: str) -> Result[str, DeleteError]:
        """Execute confirmed deletion.

        Args:
            delete_type: One of "by_date", "date_range", "all".
            target: For "by_date": ISO date string. For "date_range": "start:end" ISO dates.
                    For "all": ignored.

        Returns:
            Ok with success message including count, or Err if no entries found.
        """
        if delete_type == "by_date":
            target_date = date.fromisoformat(target)
            count = await self._repo.delete_entries_by_date(target_date)
        elif delete_type == "date_range":
            start_str, end_str = target.split(":")
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
            count = await self._repo.delete_entries_by_range(start_date, end_date)
        elif delete_type == "all":
            count = await self._repo.delete_all_data()
        else:
            return Err(DeleteError(f"Unknown delete type: {delete_type}"))

        if count == 0:
            return Err(DeleteError("No entries found for the specified period."))

        return Ok(f"Successfully deleted {count} records.")
