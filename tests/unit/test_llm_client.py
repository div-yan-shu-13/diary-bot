"""Unit tests for LLMClient with mocked Groq API."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from diary_bot.llm_client import GeminiFallback, LLMClient, LLMError
from diary_bot.models import (
    DiaryEntry,
    Err,
    Input,
    InputType,
    MoodEntry,
    Ok,
    Tone,
)


# --- Fixtures ---


def _make_groq_response(content: str) -> MagicMock:
    """Create a mock Groq chat completion response."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_inputs() -> list[Input]:
    """Create sample inputs for testing."""
    return [
        Input(
            id=1,
            entry_date=date(2024, 1, 15),
            content="Had a great morning walk",
            timestamp=datetime(2024, 1, 15, 8, 30),
            input_type=InputType.TEXT,
        ),
        Input(
            id=2,
            entry_date=date(2024, 1, 15),
            content="Lunch with Sarah was wonderful",
            timestamp=datetime(2024, 1, 15, 12, 0),
            input_type=InputType.TEXT,
        ),
    ]


def _make_mood_data() -> list[MoodEntry]:
    """Create sample mood data for testing."""
    return [
        MoodEntry(
            id=1,
            check_in_id=1,
            content="Feeling energized and happy",
            timestamp=datetime(2024, 1, 15, 9, 0),
            entry_date=date(2024, 1, 15),
        ),
    ]


def _make_diary_entries() -> list[DiaryEntry]:
    """Create sample diary entries for testing."""
    return [
        DiaryEntry(
            id=1,
            entry_date=date(2024, 1, 14),
            content="Today was a peaceful day spent reading.",
            tone=Tone.REFLECTIVE,
            special_instructions=None,
            generated_at=datetime(2024, 1, 14, 22, 0),
        ),
        DiaryEntry(
            id=2,
            entry_date=date(2024, 1, 15),
            content="An exciting day full of discoveries.",
            tone=Tone.CASUAL,
            special_instructions=None,
            generated_at=datetime(2024, 1, 15, 22, 0),
        ),
    ]


@pytest.fixture
def mock_groq_client() -> AsyncMock:
    """Create a mock AsyncGroq client."""
    client = AsyncMock()
    client.chat = AsyncMock()
    client.chat.completions = AsyncMock()
    client.chat.completions.create = AsyncMock()
    return client


@pytest.fixture
def mock_fallback_client() -> AsyncMock:
    """Create a mock Gemini fallback client."""
    fallback = AsyncMock(spec=GeminiFallback)
    return fallback


# --- Tests: Successful diary generation ---


@pytest.mark.asyncio
async def test_generate_diary_success(mock_groq_client: AsyncMock) -> None:
    """Successful diary generation returns Ok with content."""
    expected_content = "Today was a wonderful day that began with a morning walk..."
    mock_groq_client.chat.completions.create.return_value = _make_groq_response(
        expected_content
    )

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=_make_mood_data(),
        tone=Tone.REFLECTIVE,
        special_instructions=None,
    )

    assert isinstance(result, Ok)
    assert result.value == expected_content
    mock_groq_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_diary_with_special_instructions(
    mock_groq_client: AsyncMock,
) -> None:
    """Diary generation incorporates special instructions into the prompt."""
    expected_content = "A day focused on gratitude..."
    mock_groq_client.chat.completions.create.return_value = _make_groq_response(
        expected_content
    )

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=_make_mood_data(),
        tone=Tone.POETIC,
        special_instructions="Focus on gratitude",
    )

    assert isinstance(result, Ok)
    assert result.value == expected_content
    # Verify the prompt includes the special instructions
    call_args = mock_groq_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert "Focus on gratitude" in prompt
    assert "poetic" in prompt


# --- Tests: Successful weekly summary ---


@pytest.mark.asyncio
async def test_generate_weekly_summary_success(mock_groq_client: AsyncMock) -> None:
    """Successful weekly summary returns Ok with content."""
    expected_content = (
        "**Recurring Themes**\nReading and nature...\n"
        "**Notable Events & Mood Patterns**\nHighly energized...\n"
        "**Overall Reflection**\nA balanced week..."
    )
    mock_groq_client.chat.completions.create.return_value = _make_groq_response(
        expected_content
    )

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_weekly_summary(entries=_make_diary_entries())

    assert isinstance(result, Ok)
    assert result.value == expected_content
    mock_groq_client.chat.completions.create.assert_called_once()


# --- Tests: Successful summarize_entry ---


@pytest.mark.asyncio
async def test_summarize_entry_success(mock_groq_client: AsyncMock) -> None:
    """Successful summarize_entry returns Ok with one-sentence summary."""
    expected_summary = "A peaceful day spent reading and reflecting on life."
    mock_groq_client.chat.completions.create.return_value = _make_groq_response(
        expected_summary
    )

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.summarize_entry(
        entry_text="Today was a peaceful day spent reading by the window..."
    )

    assert isinstance(result, Ok)
    assert result.value == expected_summary
    mock_groq_client.chat.completions.create.assert_called_once()


# --- Tests: Retry-once on first failure then success ---


@pytest.mark.asyncio
async def test_retry_once_on_first_failure_then_success(
    mock_groq_client: AsyncMock,
) -> None:
    """Retry-once: first call fails, second call succeeds."""
    expected_content = "Today was great!"
    mock_groq_client.chat.completions.create.side_effect = [
        Exception("Temporary network error"),
        _make_groq_response(expected_content),
    ]

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.CASUAL,
        special_instructions=None,
    )

    assert isinstance(result, Ok)
    assert result.value == expected_content
    assert mock_groq_client.chat.completions.create.call_count == 2


# --- Tests: Both retries fail returns Err ---


@pytest.mark.asyncio
async def test_both_retries_fail_returns_err(mock_groq_client: AsyncMock) -> None:
    """Both retries fail returns Err with LLMError when no fallback configured."""
    mock_groq_client.chat.completions.create.side_effect = Exception("Service down")

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.REFLECTIVE,
        special_instructions=None,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert "Groq API error" in result.error.message
    assert mock_groq_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_both_retries_fail_weekly_summary(mock_groq_client: AsyncMock) -> None:
    """Both retries fail for weekly summary returns Err."""
    mock_groq_client.chat.completions.create.side_effect = Exception("Timeout")

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_weekly_summary(entries=_make_diary_entries())

    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert mock_groq_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_both_retries_fail_summarize_entry(mock_groq_client: AsyncMock) -> None:
    """Both retries fail for summarize_entry returns Err."""
    mock_groq_client.chat.completions.create.side_effect = Exception("Rate limited")

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.summarize_entry(entry_text="Some diary text")

    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert mock_groq_client.chat.completions.create.call_count == 2


# --- Tests: Fallback to Gemini when Groq fails ---


@pytest.mark.asyncio
async def test_fallback_to_gemini_when_groq_fails(
    mock_groq_client: AsyncMock, mock_fallback_client: AsyncMock
) -> None:
    """Fallback to Gemini when both Groq retries fail and fallback is configured."""
    expected_content = "Gemini generated diary entry."
    mock_groq_client.chat.completions.create.side_effect = Exception("Groq is down")
    mock_fallback_client.generate.return_value = expected_content

    client = LLMClient(
        groq_client=mock_groq_client, fallback_client=mock_fallback_client
    )
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.CASUAL,
        special_instructions=None,
    )

    assert isinstance(result, Ok)
    assert result.value == expected_content
    assert mock_groq_client.chat.completions.create.call_count == 2
    mock_fallback_client.generate.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_gemini_also_fails(
    mock_groq_client: AsyncMock, mock_fallback_client: AsyncMock
) -> None:
    """When both Groq and Gemini fallback fail, returns Err."""
    mock_groq_client.chat.completions.create.side_effect = Exception("Groq is down")
    mock_fallback_client.generate.side_effect = Exception("Gemini also down")

    client = LLMClient(
        groq_client=mock_groq_client, fallback_client=mock_fallback_client
    )
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.REFLECTIVE,
        special_instructions=None,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert "Gemini fallback error" in result.error.message


# --- Tests: No fallback attempt when fallback not configured ---


@pytest.mark.asyncio
async def test_no_fallback_when_not_configured(mock_groq_client: AsyncMock) -> None:
    """No fallback attempt when fallback_client is None."""
    mock_groq_client.chat.completions.create.side_effect = Exception("Service error")

    client = LLMClient(groq_client=mock_groq_client, fallback_client=None)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.REFLECTIVE,
        special_instructions=None,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert "Groq API error" in result.error.message
    # Only 2 calls (initial + retry), no fallback
    assert mock_groq_client.chat.completions.create.call_count == 2


# --- Tests: Edge cases ---


@pytest.mark.asyncio
async def test_generate_diary_empty_content_from_llm(
    mock_groq_client: AsyncMock,
) -> None:
    """LLM returning None content is treated as an error."""
    message = MagicMock()
    message.content = None
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    mock_groq_client.chat.completions.create.return_value = response

    client = LLMClient(groq_client=mock_groq_client)
    result = await client.generate_diary(
        inputs=_make_inputs(),
        mood_data=[],
        tone=Tone.CASUAL,
        special_instructions=None,
    )

    # None content on first try triggers retry
    # Both return None so result is Err
    assert isinstance(result, Err)
    assert "empty content" in result.error.message
