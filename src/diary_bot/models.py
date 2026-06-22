"""Domain models for the Telegram Diary Bot.

Contains enums, dataclasses, and the Result type used across the application.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")


# --- Enums ---


class Tone(Enum):
    """Writing style applied to generated diary entries."""

    POETIC = "poetic"
    CASUAL = "casual"
    REFLECTIVE = "reflective"


class InputType(Enum):
    """Type of user input captured by the bot."""

    TEXT = "text"
    VOICE = "voice"


class CheckInStatus(Enum):
    """Status of a mood check-in."""

    PENDING = "pending"
    RESPONDED = "responded"
    EXPIRED = "expired"


# --- Dataclasses ---


@dataclass
class Input:
    """A text or voice input captured from the user."""

    id: int
    entry_date: date
    content: str
    timestamp: datetime
    input_type: InputType


@dataclass
class DiaryEntry:
    """A generated diary entry for a specific day."""

    id: int
    entry_date: date
    content: str
    tone: Tone
    special_instructions: str | None
    generated_at: datetime


@dataclass
class MoodCheckIn:
    """A scheduled mood check-in instance."""

    id: int
    scheduled_at: datetime
    status: CheckInStatus


@dataclass
class MoodEntry:
    """A user's response to a mood check-in."""

    id: int
    check_in_id: int
    content: str
    timestamp: datetime
    entry_date: date


@dataclass
class UserSettings:
    """User configuration for the bot."""

    tone: Tone
    timezone: str
    mood_check_in_times: list[str]  # HH:MM format
    inactivity_threshold_hours: int | None  # None = disabled
    memory_callback_time: str | None  # HH:MM format


# --- Result Type ---


@dataclass
class Ok(Generic[T]):
    """Represents a successful result containing a value."""

    value: T


@dataclass
class Err(Generic[E]):
    """Represents a failed result containing an error."""

    error: E


Result = Ok[T] | Err[E]
