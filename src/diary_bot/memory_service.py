"""Memory Callback Service for the Telegram Diary Bot.

Checks for diary entries from 7, 14, 21, or 28 days ago and sends
a one-sentence summary to the user if found.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from telegram import Bot

from diary_bot.llm_client import LLMClient
from diary_bot.models import Err, Ok
from diary_bot.repository import Repository

logger = logging.getLogger(__name__)

# Offsets to check, in order of priority
_MEMORY_OFFSETS_DAYS = [7, 14, 21, 28]

# Human-readable labels for each offset
_OFFSET_LABELS = {
    7: "1 week ago today",
    14: "2 weeks ago today",
    21: "3 weeks ago today",
    28: "4 weeks ago today",
}


class MemoryService:
    """Checks for and delivers 'on this day' memory messages."""

    def __init__(
        self,
        repo: Repository,
        llm_client: LLMClient,
        authorized_user_id: int,
    ) -> None:
        self._repo = repo
        self._llm_client = llm_client
        self._authorized_user_id = authorized_user_id

    async def check_and_send_memory(self, bot: Bot) -> None:
        """Check for past entries on this date and send a summary if found.

        Checks for diary entries at 7, 14, 21, and 28 days ago (in that order).
        Sends only ONE memory per day — the first match found.
        If no matches exist, does nothing.
        """
        today = date.today()

        for offset_days in _MEMORY_OFFSETS_DAYS:
            target_date = today - timedelta(days=offset_days)
            entry = await self._repo.get_diary_entry(target_date)

            if entry is not None:
                # Generate a one-sentence summary
                result = await self._llm_client.summarize_entry(entry.content)

                if isinstance(result, Err):
                    logger.warning(
                        "Failed to summarize entry for %s: %s",
                        target_date.isoformat(),
                        result.error.message,
                    )
                    return

                summary = result.value
                label = _OFFSET_LABELS[offset_days]
                message = f"\U0001f52e {label}: {summary}"

                await bot.send_message(
                    chat_id=self._authorized_user_id,
                    text=message,
                )
                return  # Only send one memory per day

    @staticmethod
    def get_matching_memory_dates(
        current_date: date, entry_dates: set[date]
    ) -> list[tuple[date, int]]:
        """Return matching dates with their offsets in days.

        Checks 7, 14, 21, 28 days before current_date against entry_dates.
        Returns a list of (matched_date, offset_days) tuples for each match found.
        """
        matches: list[tuple[date, int]] = []
        for offset_days in _MEMORY_OFFSETS_DAYS:
            target = current_date - timedelta(days=offset_days)
            if target in entry_dates:
                matches.append((target, offset_days))
        return matches
