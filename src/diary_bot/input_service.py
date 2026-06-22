"""Input service for handling text and voice message storage.

Validates inputs and coordinates with Repository and DayBoundaryService
to persist user messages for the current day's entry.
"""

from __future__ import annotations

from datetime import datetime

from diary_bot.day_boundary import DayBoundaryService
from diary_bot.models import Err, Ok, Result
from diary_bot.repository import Repository
from diary_bot.transcriber import Transcriber

MAX_VOICE_DURATION_SECONDS = 60


class InputError:
    """Error type for input service operations."""

    def __init__(self, message: str) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"InputError({self.message!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InputError):
            return NotImplemented
        return self.message == other.message


class InputService:
    """Handles storing text and voice inputs for the current day.

    Validates input content, determines the correct entry date via
    DayBoundaryService, and persists through Repository.
    """

    def __init__(
        self,
        repo: Repository,
        transcriber: Transcriber,
        day_boundary: DayBoundaryService,
    ) -> None:
        self._repo = repo
        self._transcriber = transcriber
        self._day_boundary = day_boundary

    async def store_text(self, text: str, timestamp: datetime) -> Result[str, InputError]:
        """Store a text input. Returns confirmation or error.

        Validates that the text is not empty or whitespace-only before storing.
        Uses DayBoundaryService to determine the correct entry date, then
        persists via Repository.

        Args:
            text: The text message content from the user.
            timestamp: The timestamp of the message.

        Returns:
            Ok with a confirmation message on success, or
            Err with an InputError on validation failure or storage failure.
        """
        # Validate: reject empty or whitespace-only text
        if not text or not text.strip():
            return Err(InputError("No text content detected. Please send a non-empty message."))

        # Determine the entry date using day boundary logic
        entry_date = await self._day_boundary.get_entry_date_async(timestamp)

        # Persist the input via Repository
        try:
            await self._repo.save_input(
                entry_date=entry_date,
                text=text,
                timestamp=timestamp,
                input_type="text",
            )
        except Exception:
            return Err(InputError("Failed to save your message. Please try again."))

        return Ok("✓ Noted")

    async def store_voice(
        self, audio_bytes: bytes, duration: int, timestamp: datetime
    ) -> Result[str, InputError]:
        """Transcribe and store a voice input. Returns the transcription or error.

        Validates that the voice note is within the maximum allowed duration,
        transcribes the audio via the Transcriber, determines the correct entry
        date via DayBoundaryService, and persists the transcribed text through
        Repository.

        Args:
            audio_bytes: The raw audio data to transcribe.
            duration: Duration of the voice note in seconds.
            timestamp: The timestamp of the voice message.

        Returns:
            Ok with the transcribed text on success, or
            Err with an InputError on validation/transcription/storage failure.
        """
        # Validate: reject voice notes longer than 60 seconds
        if duration > MAX_VOICE_DURATION_SECONDS:
            return Err(
                InputError(
                    f"Voice note too long ({duration}s). "
                    f"Maximum allowed duration is {MAX_VOICE_DURATION_SECONDS} seconds."
                )
            )

        # Transcribe via Groq Whisper
        transcription_result = await self._transcriber.transcribe(audio_bytes)

        if isinstance(transcription_result, Err):
            return Err(
                InputError(
                    "Transcription failed. Please try sending your message as text instead."
                )
            )

        transcribed_text = transcription_result.value

        # Determine the entry date using day boundary logic
        entry_date = await self._day_boundary.get_entry_date_async(timestamp)

        # Persist the transcribed text via Repository
        try:
            await self._repo.save_input(
                entry_date=entry_date,
                text=transcribed_text,
                timestamp=timestamp,
                input_type="voice",
            )
        except Exception:
            return Err(InputError("Failed to save your voice note. Please try again."))

        return Ok(transcribed_text)
