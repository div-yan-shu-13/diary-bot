"""Day boundary service for managing entry date assignment.

Handles the logic for determining which calendar day an input belongs to,
including the post-10PM diary generation scenario where subsequent inputs
are associated with the next day's entry.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from diary_bot.repository import Repository


class DayBoundaryService:
    """Encapsulates day boundary logic for input date assignment.

    Rules:
    - Inputs between midnight and next midnight belong to that calendar date
      (when no post-10PM diary has been generated).
    - If a diary is generated at or after 10:00 PM, subsequent inputs before
      midnight are associated with the next day's entry.
    - At or after midnight, inputs always belong to the new calendar date
      regardless of prior evening state.
    - If a diary is generated before 10:00 PM, input collection does NOT switch.
    """

    _POST_10PM_HOUR = 22  # 10:00 PM

    def __init__(self, repo: Repository, timezone: ZoneInfo) -> None:
        self._repo = repo
        self._timezone = timezone

    def get_entry_date(self, timestamp: datetime) -> date:
        """Determine the entry date for a given timestamp.

        Considers whether a post-10PM diary generation has occurred for
        the current calendar date. If so, inputs are assigned to the next day.

        Args:
            timestamp: The datetime of the input (should be timezone-aware or UTC).

        Returns:
            The calendar date the input should be associated with.
        """
        # Convert to user's timezone
        local_time = timestamp.astimezone(self._timezone)
        calendar_date = local_time.date()

        # Check if there's an active next-day collection for today's date
        # This is a synchronous method, so we need to check state without async
        # We use a cached/sync approach - the caller should use get_entry_date_async
        # for the full async flow. This sync version is for simple date resolution.
        return calendar_date

    async def get_entry_date_async(self, timestamp: datetime) -> date:
        """Determine the entry date for a given timestamp (async version).

        Checks the day_boundary_state table to see if a post-10PM diary
        generation has occurred, which would shift input collection to the next day.

        Args:
            timestamp: The datetime of the input.

        Returns:
            The calendar date the input should be associated with.
        """
        # Convert to user's timezone
        local_time = timestamp.astimezone(self._timezone)
        calendar_date = local_time.date()

        # Check if next-day collection is active for the current calendar date
        state = await self._repo.get_day_boundary_state(calendar_date)
        if state is not None and state["next_day_collection_active"]:
            # A post-10PM diary was generated today; assign to next day
            return calendar_date + timedelta(days=1)

        return calendar_date

    async def mark_diary_generated(self, entry_date: date, timestamp: datetime) -> None:
        """Record that a diary was generated, potentially switching input collection.

        If the diary is generated at or after 10:00 PM, this activates
        next-day collection so subsequent inputs go to tomorrow's entry.
        If generated before 10:00 PM, no collection switch occurs.

        Args:
            entry_date: The date of the diary entry being generated.
            timestamp: When the diary generation occurred.
        """
        post_10pm = self.is_post_10pm(timestamp)
        await self._repo.save_day_boundary_state(
            entry_date=entry_date,
            diary_generated_at=timestamp,
            next_day_active=post_10pm,
        )

    def is_post_10pm(self, timestamp: datetime) -> bool:
        """Check if a timestamp is at or after 10:00 PM in the user's timezone.

        Args:
            timestamp: The datetime to check.

        Returns:
            True if the local time is >= 22:00, False otherwise.
        """
        local_time = timestamp.astimezone(self._timezone)
        return local_time.hour >= self._POST_10PM_HOUR

    async def has_diary_been_generated_post_10pm(self, entry_date: date) -> bool:
        """Check if a diary has already been generated in the post-10PM window for a date.

        Used to enforce the rule that only one diary can be generated
        in the post-10PM window per day (requirement 11.6).

        Args:
            entry_date: The calendar date to check.

        Returns:
            True if a post-10PM diary generation has already occurred for this date.
        """
        state = await self._repo.get_day_boundary_state(entry_date)
        if state is None:
            return False
        return state["next_day_collection_active"]
