"""Reminder service for inactivity detection and notification.

Tracks user activity and sends a single reminder when the user
has been inactive beyond a configurable threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from diary_bot.models import Err, Ok, Result

# Valid threshold range: 1 hour to 7 days (168 hours)
MIN_THRESHOLD_HOURS = 1
MAX_THRESHOLD_HOURS = 168  # 7 days * 24 hours


class ReminderError:
    """Error type for reminder service operations."""

    def __init__(self, message: str) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"ReminderError({self.message!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ReminderError):
            return NotImplemented
        return self.message == other.message


class ReminderService:
    """Manages inactivity reminders for a single user.

    Tracks the last time the user sent input and determines when
    a reminder should be sent. Ensures at most one reminder per
    inactivity period — a new reminder is only sent after the user
    sends at least one new input following a previous reminder.

    State is held in-memory and resets on process restart.
    """

    def __init__(
        self,
        authorized_user_id: int,
        threshold_hours: int | None,
    ) -> None:
        """Initialize the reminder service.

        Args:
            authorized_user_id: Telegram user ID to send reminders to.
            threshold_hours: Hours of inactivity before a reminder is sent.
                             None means reminders are disabled.
        """
        self._user_id = authorized_user_id
        self._threshold_hours = threshold_hours
        self._last_input_time: datetime | None = None
        self._reminder_sent: bool = False

    def record_activity(self, timestamp: datetime) -> None:
        """Record that the user sent input at the given timestamp.

        Updates the last input time and resets the reminder_sent flag,
        allowing a new reminder to be sent after the next inactivity period.

        Args:
            timestamp: The time the user's input was received.
        """
        self._last_input_time = timestamp
        self._reminder_sent = False

    def should_send_reminder(self, current_time: datetime) -> bool:
        """Determine whether a reminder should be sent right now.

        Returns False if:
        - Reminders are disabled (threshold is None)
        - No activity has been recorded yet
        - A reminder was already sent this inactivity period
        - The inactivity threshold has not yet been exceeded

        Returns True only when the elapsed time since last input
        meets or exceeds the configured threshold.

        Args:
            current_time: The current time to check against.

        Returns:
            True if a reminder should be sent, False otherwise.
        """
        if self._threshold_hours is None:
            return False

        if self._last_input_time is None:
            return False

        if self._reminder_sent:
            return False

        elapsed = current_time - self._last_input_time
        threshold = timedelta(hours=self._threshold_hours)
        return elapsed >= threshold

    def mark_reminder_sent(self) -> None:
        """Mark that a reminder has been sent for the current inactivity period.

        Prevents additional reminders until the user sends new input.
        """
        self._reminder_sent = True

    async def send_reminder(self, bot) -> None:  # noqa: ANN001
        """Send a reminder message to the user if conditions are met.

        Checks should_send_reminder with the current time and, if True,
        sends a gentle nudge message via the bot and marks the reminder
        as sent.

        Args:
            bot: The Telegram Bot instance used to send messages.
        """
        current_time = datetime.now()
        if self.should_send_reminder(current_time):
            await bot.send_message(
                chat_id=self._user_id,
                text="Hey! It's been a while since your last entry. "
                "How about jotting down what's on your mind? 📝",
            )
            self.mark_reminder_sent()

    def update_threshold(self, hours: int | None) -> None:
        """Update the inactivity threshold.

        Args:
            hours: New threshold in hours, or None to disable reminders.
        """
        self._threshold_hours = hours

    @staticmethod
    def validate_threshold(value: int | None) -> Result[int | None, ReminderError]:
        """Validate a proposed inactivity threshold value.

        Args:
            value: Proposed threshold in hours, or None to disable.

        Returns:
            Ok with the value if valid, or Err with a ReminderError if invalid.
        """
        if value is None:
            return Ok(None)

        if value < MIN_THRESHOLD_HOURS or value > MAX_THRESHOLD_HOURS:
            return Err(
                ReminderError(
                    f"Inactivity threshold must be between {MIN_THRESHOLD_HOURS} "
                    f"and {MAX_THRESHOLD_HOURS} hours, or disabled. Got: {value}"
                )
            )

        return Ok(value)
