"""Diary service for managing diary generation and tone preferences.

Orchestrates diary entry generation using collected inputs and LLM,
and manages user tone settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from diary_bot.day_boundary import DayBoundaryService
from diary_bot.models import Err, Ok, Result, Tone
from diary_bot.repository import Repository


@dataclass
class ToneError:
    """Error returned when an invalid tone value is provided."""

    message: str


@dataclass
class DiaryError:
    """Error returned during diary generation."""

    message: str
    code: str  # "no_inputs", "already_generated", "llm_failure"


class GenerationStatus(Enum):
    """Status indicating what should happen next in the diary generation flow."""

    READY = "ready"
    NO_INPUTS = "no_inputs"
    ALREADY_GENERATED = "already_generated"


@dataclass
class GenerationState:
    """State returned from initiate_generation indicating the next step.

    Attributes:
        status: The generation status.
        entry_date: The resolved entry date for diary generation.
        is_post_10pm: Whether the request was made after 10 PM.
    """

    status: GenerationStatus
    entry_date: date
    is_post_10pm: bool


class DiaryService:
    """Orchestrates diary generation and tone management."""

    _VALID_TONES = {tone.value for tone in Tone}

    def __init__(
        self,
        repo: Repository,
        llm_client: Any,
        day_boundary: DayBoundaryService,
    ) -> None:
        self._repo = repo
        self._llm_client = llm_client
        self._day_boundary = day_boundary

    async def initiate_generation(self, timestamp: datetime) -> GenerationState:
        """Start the diary generation flow. Returns state indicating next step.

        Determines the entry date, checks for post-10PM duplicate generation,
        and verifies that inputs exist for the target date.

        Args:
            timestamp: The current time when /diary was invoked.

        Returns:
            GenerationState indicating whether to proceed, or why not.
        """
        entry_date = await self._day_boundary.get_entry_date_async(timestamp)
        is_post_10pm = self._day_boundary.is_post_10pm(timestamp)

        # Post-10PM duplicate check (Req 11.6)
        if is_post_10pm:
            already_generated = await self._day_boundary.has_diary_been_generated_post_10pm(entry_date)
            if already_generated:
                return GenerationState(
                    status=GenerationStatus.ALREADY_GENERATED,
                    entry_date=entry_date,
                    is_post_10pm=is_post_10pm,
                )

        # Check if there are any inputs for the entry date (Req 3.5)
        inputs = await self._repo.get_inputs_for_date(entry_date)
        if not inputs:
            return GenerationState(
                status=GenerationStatus.NO_INPUTS,
                entry_date=entry_date,
                is_post_10pm=is_post_10pm,
            )

        # Ready for generation — handler will ask for special instructions
        return GenerationState(
            status=GenerationStatus.READY,
            entry_date=entry_date,
            is_post_10pm=is_post_10pm,
        )

    async def generate_entry(
        self, entry_date: date, special_instructions: str | None, tone: Tone
    ) -> Result[str, DiaryError]:
        """Generate diary from collected inputs using LLM.

        Gathers inputs and mood data for the date, calls the LLM, and
        persists the generated entry on success.

        Args:
            entry_date: The date to generate the diary for.
            special_instructions: Optional user guidance for the generation.
            tone: The writing tone to apply.

        Returns:
            Ok(str) with the generated diary content on success,
            Err(DiaryError) on failure.
        """
        inputs = await self._repo.get_inputs_for_date(entry_date)
        mood_data = await self._repo.get_mood_for_date(entry_date)

        llm_result = await self._llm_client.generate_diary(
            inputs, mood_data, tone, special_instructions
        )

        if isinstance(llm_result, Err):
            return Err(
                DiaryError(
                    message=f"Failed to generate diary: {llm_result.error.message}",
                    code="llm_failure",
                )
            )

        content = llm_result.value

        # Persist the diary entry (Req 3.6: INSERT OR REPLACE ensures uniqueness)
        await self._repo.save_diary_entry(
            entry_date, content, tone.value, special_instructions
        )

        # Mark diary generated for day boundary tracking (Req 11.2)
        await self._day_boundary.mark_diary_generated(entry_date, datetime.utcnow())

        return Ok(content)

    async def set_tone(self, tone_value: str) -> Result[Tone, ToneError]:
        """Set the user's tone preference.

        Validates that the provided value is one of the three valid tones
        (case-insensitive). Persists the choice and returns the resolved Tone.

        Args:
            tone_value: The tone string to set.

        Returns:
            Ok(Tone) on success, Err(ToneError) if the value is invalid.
        """
        normalized = tone_value.strip().lower()
        if normalized not in self._VALID_TONES:
            valid_options = ", ".join(sorted(self._VALID_TONES))
            return Err(
                ToneError(
                    message=f"Invalid tone '{tone_value}'. Valid options: {valid_options}"
                )
            )

        await self._repo.update_setting("tone", normalized)
        return Ok(Tone(normalized))

    async def generate_weekly_summary(self) -> Result[str, DiaryError]:
        """Generate weekly summary from past 7 days of entries.

        Calculates the 7-day date range (today and 6 days back), retrieves
        diary entries, checks the minimum data threshold, and calls the LLM.

        Returns:
            Ok(str) with the generated weekly summary content on success,
            Err(DiaryError) with code "insufficient_data" if fewer than 2 days have entries,
            Err(DiaryError) with code "llm_failure" if LLM generation fails.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=6)

        entries = await self._repo.get_entries_for_range(start_date, end_date)

        # Check minimum data threshold: need at least 2 days with entries
        unique_days = {entry.entry_date for entry in entries}
        if len(unique_days) < 2:
            return Err(
                DiaryError(
                    message="Insufficient data for weekly summary. Need at least 2 days with entries in the past 7 days.",
                    code="insufficient_data",
                )
            )

        llm_result = await self._llm_client.generate_weekly_summary(entries)

        if isinstance(llm_result, Err):
            return Err(
                DiaryError(
                    message=f"Failed to generate weekly summary: {llm_result.error.message}",
                    code="llm_failure",
                )
            )

        return Ok(llm_result.value)

    async def get_tone(self) -> Tone:
        """Get current tone, defaulting to 'reflective'.

        Returns:
            The user's configured Tone, or Tone.REFLECTIVE if not set.
        """
        settings = await self._repo.get_settings()
        return settings.tone
