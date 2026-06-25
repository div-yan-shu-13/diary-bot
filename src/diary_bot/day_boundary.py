"""Day boundary service for managing entry date assignment.

The "day" runs from 3:00 AM to 2:59 AM the next morning. This means:
- Messages sent between midnight and 2:59 AM count as the PREVIOUS day.
- The new day starts at 3:00 AM.

Inputs ALWAYS stay in the same day regardless of whether a diary has been
generated. The auto-diary at 10:30 PM only includes inputs up to that point,
but manual /diary always includes ALL inputs for the day.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from diary_bot.repository import Repository


class DayBoundaryService:
    """Encapsulates day boundary logic for input date assignment.

    Rules:
    - The "day" starts at 3:00 AM and ends at 2:59 AM the next morning.
    - Messages between midnight and 2:59 AM belong to the PREVIOUS calendar day.
    - Inputs NEVER shift to the next day. They always belong to their logical date.
    """

    _DAY_START_HOUR = 3  # 3:00 AM — when the new "day" begins

    def __init__(self, repo: Repository, timezone: ZoneInfo) -> None:
        self._repo = repo
        self._timezone = timezone

    def _get_logical_date(self, timestamp: datetime) -> date:
        """Get the logical diary date for a timestamp.

        If it's before 3 AM, the timestamp belongs to the previous calendar day.
        Otherwise it belongs to the current calendar day.
        """
        local_time = timestamp.astimezone(self._timezone)
        if local_time.hour < self._DAY_START_HOUR:
            return local_time.date() - timedelta(days=1)
        return local_time.date()

    def get_entry_date(self, timestamp: datetime) -> date:
        """Determine the entry date for a given timestamp.

        Args:
            timestamp: The datetime of the input (should be timezone-aware or UTC).

        Returns:
            The logical calendar date the input should be associated with.
        """
        return self._get_logical_date(timestamp)

    async def get_entry_date_async(self, timestamp: datetime) -> date:
        """Determine the entry date for a given timestamp (async version).

        No day-shifting logic — always returns the logical date based on 3 AM boundary.

        Args:
            timestamp: The datetime of the input.

        Returns:
            The calendar date the input should be associated with.
        """
        return self._get_logical_date(timestamp)

    async def mark_diary_generated(self, entry_date: date, timestamp: datetime) -> None:
        """Record that a diary was generated.

        Stores the generation timestamp for tracking purposes.
        Does NOT shift inputs to the next day.

        Args:
            entry_date: The date of the diary entry being generated.
            timestamp: When the diary generation occurred.
        """
        await self._repo.save_day_boundary_state(
            entry_date=entry_date,
            diary_generated_at=timestamp,
            next_day_active=False,  # Never shift inputs
        )
