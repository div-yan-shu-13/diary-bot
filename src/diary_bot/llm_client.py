"""LLM Client module for diary generation using Groq Cloud with optional Gemini fallback.

Provides methods for generating diary entries, weekly summaries, and one-sentence
summaries for memory callbacks. Implements retry-once logic and fallback handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from groq import AsyncGroq

from diary_bot.models import (
    DiaryEntry,
    Err,
    Input,
    MoodEntry,
    Ok,
    Result,
    Tone,
)


@dataclass
class LLMError:
    """Represents an error from the LLM service."""

    message: str


class GeminiFallback(Protocol):
    """Protocol for a Gemini fallback client."""

    async def generate(self, prompt: str) -> str:
        """Generate text from a prompt. Raises Exception on failure."""
        ...


class LLMClient:
    """Wraps Groq/Gemini APIs for text generation with retry and fallback."""

    def __init__(
        self,
        groq_client: AsyncGroq,
        fallback_client: GeminiFallback | None = None,
    ) -> None:
        self._groq = groq_client
        self._fallback = fallback_client

    async def generate_diary(
        self,
        inputs: list[Input],
        mood_data: list[MoodEntry],
        tone: Tone,
        special_instructions: str | None,
    ) -> Result[str, LLMError]:
        """Generate a diary entry from inputs.

        Builds a prompt incorporating tone, inputs, mood data, and special instructions,
        then calls the LLM with retry-once and optional Gemini fallback.
        """
        prompt = self._build_diary_prompt(inputs, mood_data, tone, special_instructions)
        return await self._call_with_retry_and_fallback(prompt)

    async def generate_weekly_summary(
        self, entries: list[DiaryEntry]
    ) -> Result[str, LLMError]:
        """Generate a weekly summary from past entries.

        The prompt requests recurring themes, notable events/mood patterns,
        and a brief overall reflection.
        """
        prompt = self._build_weekly_summary_prompt(entries)
        return await self._call_with_retry_and_fallback(prompt)

    async def summarize_entry(self, entry_text: str) -> Result[str, LLMError]:
        """Generate a one-sentence summary for memory callbacks."""
        prompt = self._build_summarize_prompt(entry_text)
        return await self._call_with_retry_and_fallback(prompt)

    # --- Private helpers ---

    async def _call_with_retry_and_fallback(
        self, prompt: str
    ) -> Result[str, LLMError]:
        """Call Groq with retry-once logic, then fall back to Gemini if configured."""
        # First attempt
        result = await self._call_groq(prompt)
        if isinstance(result, Ok):
            return result

        # Retry once
        result = await self._call_groq(prompt)
        if isinstance(result, Ok):
            return result

        # Fallback to Gemini if available
        if self._fallback is not None:
            fallback_result = await self._call_fallback(prompt)
            if isinstance(fallback_result, Ok):
                return fallback_result
            return fallback_result

        return result

    async def _call_groq(self, prompt: str) -> Result[str, LLMError]:
        """Make a single call to the Groq API."""
        try:
            response = await self._groq.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            if content is None:
                return Err(LLMError(message="LLM returned empty content"))
            return Ok(content)
        except Exception as e:
            return Err(LLMError(message=f"Groq API error: {e}"))

    async def _call_fallback(self, prompt: str) -> Result[str, LLMError]:
        """Make a call to the Gemini fallback client."""
        try:
            content = await self._fallback.generate(prompt)  # type: ignore[union-attr]
            return Ok(content)
        except Exception as e:
            return Err(LLMError(message=f"Gemini fallback error: {e}"))

    def _build_diary_prompt(
        self,
        inputs: list[Input],
        mood_data: list[MoodEntry],
        tone: Tone,
        special_instructions: str | None,
    ) -> str:
        """Build the prompt for diary generation."""
        parts: list[str] = []
        parts.append(
            f"You are a personal diary writer. Write a first-person diary entry in a {tone.value} tone.\n\n"
            "CRITICAL RULES:\n"
            "- ONLY write about what is explicitly mentioned in the inputs below.\n"
            "- Do NOT invent, assume, or hallucinate any details, events, people, or feelings that are not directly stated.\n"
            "- Do NOT add context, backstory, or speculation about what the user might have done.\n"
            "- If there is very little input, write a short entry. A single input means a short entry — that's fine.\n"
            "- Write as if YOU are the person (first person). The inputs are YOUR notes to yourself.\n"
            "- Keep it genuine and grounded in exactly what was shared."
        )

        if special_instructions:
            parts.append(f"\nSpecial instructions: {special_instructions}")

        parts.append("\n\nHere are the day's inputs in chronological order:")
        for inp in inputs:
            time_str = inp.timestamp.strftime("%H:%M")
            parts.append(f"- [{time_str}] ({inp.input_type.value}): {inp.content}")

        if mood_data:
            parts.append("\n\nMood check-in responses:")
            for mood in mood_data:
                time_str = mood.timestamp.strftime("%H:%M")
                parts.append(f"- [{time_str}]: {mood.content}")

        parts.append(
            "\n\nWrite the diary entry using ONLY the information above. "
            "Do not use bullet points; write in flowing prose. "
            "If there's only one input, keep the entry brief — a few sentences is perfectly fine."
        )
        return "\n".join(parts)

    def _build_weekly_summary_prompt(self, entries: list[DiaryEntry]) -> str:
        """Build the prompt for weekly summary generation."""
        parts: list[str] = []
        parts.append(
            "You are a personal journal analyst. Based on the following diary entries "
            "from the past week, generate a weekly summary with these sections:\n"
            "1. **Recurring Themes** - patterns or topics that appeared multiple times\n"
            "2. **Notable Events & Mood Patterns** - significant happenings and emotional trends\n"
            "3. **Overall Reflection** - a brief concluding thought about the week\n"
        )

        parts.append("Here are the diary entries:\n")
        for entry in entries:
            date_str = entry.entry_date.isoformat()
            parts.append(f"--- {date_str} ({entry.tone.value} tone) ---")
            parts.append(entry.content)
            parts.append("")

        parts.append("Write the weekly summary with the three labeled sections.")
        return "\n".join(parts)

    def _build_summarize_prompt(self, entry_text: str) -> str:
        """Build the prompt for a one-sentence summary."""
        return (
            "Summarize the following diary entry in exactly one sentence. "
            "Be concise but capture the essence of the day.\n\n"
            f"Diary entry:\n{entry_text}\n\n"
            "One-sentence summary:"
        )
