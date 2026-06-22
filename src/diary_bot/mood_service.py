"""Mood service for managing mood check-ins and responses.

Handles sending mood check-in messages, recording user responses within
the 2-hour window, expiring missed check-ins, and validating mood
check-in time configurations.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from diary_bot.models import Err, MoodCheckIn, Ok, Result
from diary_bot.repository import Repository


MOOD_RESPONSE_WINDOW_HOURS = 2
REQUIRED_CHECK_IN_COUNT = 3
MIN_HOUR = 8   # 08:00
MAX_HOUR = 22  # 22:00
MIN_SPACING_HOURS = 2


class MoodError:
    """Error type for mood service operations."""

    def __init__(self, message: str) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"MoodError({self.message!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MoodError):
            return NotImplemented
        return self.message == other.message


class MoodService:
    """Manages mood check-ins and responses.

    Coordinates with Repository to persist mood data and with the Telegram
    Bot to send check-in messages to the user.
    """

    def __init__(self, repo: Repository, authorized_user_id: int) -> None:
        self._repo = repo
        self._user_id = authorized_user_id

    async def send_check_in(self, bot) -> int:
        """Send a mood check-in message to the user.

        Creates a mood check-in record in the database, sends a message
        asking the user how they're feeling, and returns the check-in ID
        for scheduling the expiry.

        Args:
            bot: The Telegram Bot instance used to send messages.

        Returns:
            The check-in ID for use in scheduling expiry.
        """
        now = datetime.utcnow()
        check_in_id = await self._repo.save_mood_check_in(now)
        await bot.send_message(
            chat_id=self._user_id,
            text="How are you feeling right now?",
        )
        return check_in_id

    async def record_response(
        self, text: str, check_in_id: int, timestamp: datetime
    ) -> Result[str, MoodError]:
        """Store a mood response linked to a specific check-in.

        Validates that the check-in exists and the response is within the
        2-hour window. If valid, saves the mood response and marks the
        check-in as responded.

        Args:
            text: The mood response text from the user.
            check_in_id: The ID of the check-in being responded to.
            timestamp: The timestamp of the user's response.

        Returns:
            Ok with confirmation on success, or Err with MoodError if the
            window has passed or no pending check-in exists.
        """
        check_in: MoodCheckIn | None = await self._repo.get_pending_check_in()

        if check_in is None or check_in.id != check_in_id:
            return Err(MoodError("No pending check-in found."))

        # Validate 2-hour response window
        window = timedelta(hours=MOOD_RESPONSE_WINDOW_HOURS)
        if timestamp - check_in.scheduled_at > window:
            return Err(
                MoodError("Response window has passed. Check-in expired after 2 hours.")
            )

        # Determine entry date from the response timestamp
        entry_date = timestamp.date()

        # Save response and mark check-in as responded
        await self._repo.save_mood_response(check_in_id, text, timestamp, entry_date)
        await self._repo.mark_check_in_responded(check_in_id)

        return Ok("Mood recorded. Thank you!")

    async def expire_check_in(self, check_in_id: int) -> None:
        """Mark a check-in as missed after the 2-hour window.

        Args:
            check_in_id: The ID of the check-in to expire.
        """
        await self._repo.mark_check_in_expired(check_in_id)


def validate_mood_times(times: list[str]) -> Result[list[str], MoodError]:
    """Validate mood check-in times configuration.

    Validates that exactly 3 times are provided, all are between 08:00 and
    22:00, and there is a minimum 2-hour spacing between each adjacent time
    when sorted.

    Args:
        times: List of time strings in HH:MM format.

    Returns:
        Ok with sorted list of valid times, or Err with explanation.
    """
    # Validate exactly 3 times
    if len(times) != REQUIRED_CHECK_IN_COUNT:
        return Err(
            MoodError(
                f"Exactly {REQUIRED_CHECK_IN_COUNT} check-in times are required, "
                f"got {len(times)}."
            )
        )

    # Parse and validate each time
    parsed_minutes: list[int] = []
    for t in times:
        try:
            parts = t.split(":")
            if len(parts) != 2:
                raise ValueError("Invalid format")
            hour = int(parts[0])
            minute = int(parts[1])
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError("Out of range")
        except (ValueError, IndexError):
            return Err(MoodError(f"Invalid time format: '{t}'. Use HH:MM format."))

        # Validate range 08:00–22:00
        total_minutes = hour * 60 + minute
        if total_minutes < MIN_HOUR * 60 or total_minutes > MAX_HOUR * 60:
            return Err(
                MoodError(
                    f"Time '{t}' is outside the allowed range (08:00–22:00)."
                )
            )

        parsed_minutes.append(total_minutes)

    # Sort times and check spacing
    sorted_indices = sorted(range(len(parsed_minutes)), key=lambda i: parsed_minutes[i])
    sorted_minutes = [parsed_minutes[i] for i in sorted_indices]
    sorted_times = [times[i] for i in sorted_indices]

    for i in range(1, len(sorted_minutes)):
        spacing = sorted_minutes[i] - sorted_minutes[i - 1]
        if spacing < MIN_SPACING_HOURS * 60:
            return Err(
                MoodError(
                    f"Insufficient spacing between '{sorted_times[i - 1]}' and "
                    f"'{sorted_times[i]}'. Minimum 2 hours required."
                )
            )

    return Ok(sorted_times)
