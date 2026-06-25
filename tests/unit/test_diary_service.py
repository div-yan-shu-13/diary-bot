"""Unit tests for DiaryService.set_tone() and get_tone() methods.

Tests tone validation, persistence, case insensitivity, and default behavior.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from diary_bot.diary_service import DiaryService, ToneError
from diary_bot.models import Err, Ok, Tone, UserSettings


@pytest.fixture
def mock_repo():
    """Create a mock Repository."""
    repo = MagicMock()
    repo.update_setting = AsyncMock()
    repo.get_settings = AsyncMock(
        return_value=UserSettings(
            tone=Tone.REFLECTIVE,
            timezone="UTC",
            mood_check_in_times=["09:00", "13:00", "18:00"],
            inactivity_threshold_hours=24,
            memory_callback_time="10:00",
        )
    )
    return repo


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    return MagicMock()


@pytest.fixture
def mock_day_boundary():
    """Create a mock DayBoundaryService."""
    return MagicMock()


@pytest.fixture
def diary_service(mock_repo, mock_llm_client, mock_day_boundary):
    """Create a DiaryService with mocked dependencies."""
    return DiaryService(repo=mock_repo, llm_client=mock_llm_client, day_boundary=mock_day_boundary)


class TestSetToneValid:
    """Tests for setting valid tone values."""

    async def test_set_tone_poetic(self, diary_service, mock_repo):
        """Setting 'poetic' returns Ok(Tone.POETIC) and persists."""
        result = await diary_service.set_tone("poetic")

        assert isinstance(result, Ok)
        assert result.value == Tone.POETIC
        mock_repo.update_setting.assert_called_once_with("tone", "poetic")

    async def test_set_tone_casual(self, diary_service, mock_repo):
        """Setting 'casual' returns Ok(Tone.CASUAL) and persists."""
        result = await diary_service.set_tone("casual")

        assert isinstance(result, Ok)
        assert result.value == Tone.CASUAL
        mock_repo.update_setting.assert_called_once_with("tone", "casual")

    async def test_set_tone_reflective(self, diary_service, mock_repo):
        """Setting 'reflective' returns Ok(Tone.REFLECTIVE) and persists."""
        result = await diary_service.set_tone("reflective")

        assert isinstance(result, Ok)
        assert result.value == Tone.REFLECTIVE
        mock_repo.update_setting.assert_called_once_with("tone", "reflective")

    async def test_set_tone_uppercase(self, diary_service, mock_repo):
        """Setting 'POETIC' (uppercase) returns Ok(Tone.POETIC) — case insensitive."""
        result = await diary_service.set_tone("POETIC")

        assert isinstance(result, Ok)
        assert result.value == Tone.POETIC
        mock_repo.update_setting.assert_called_once_with("tone", "poetic")

    async def test_set_tone_mixed_case(self, diary_service, mock_repo):
        """Setting 'Casual' (mixed case) returns Ok(Tone.CASUAL)."""
        result = await diary_service.set_tone("Casual")

        assert isinstance(result, Ok)
        assert result.value == Tone.CASUAL
        mock_repo.update_setting.assert_called_once_with("tone", "casual")


class TestSetToneInvalid:
    """Tests for setting invalid tone values."""

    async def test_set_tone_invalid_string(self, diary_service, mock_repo):
        """Setting 'invalid' returns Err(ToneError) with valid options listed."""
        result = await diary_service.set_tone("invalid")

        assert isinstance(result, Err)
        assert isinstance(result.error, ToneError)
        assert "casual" in result.error.message
        assert "poetic" in result.error.message
        assert "reflective" in result.error.message
        mock_repo.update_setting.assert_not_called()

    async def test_set_tone_empty_string(self, diary_service, mock_repo):
        """Setting empty string returns Err(ToneError)."""
        result = await diary_service.set_tone("")

        assert isinstance(result, Err)
        assert isinstance(result.error, ToneError)
        mock_repo.update_setting.assert_not_called()


class TestGetTone:
    """Tests for retrieving the current tone."""

    async def test_get_tone_default_reflective(self, diary_service):
        """get_tone returns REFLECTIVE when no tone has been set (default)."""
        tone = await diary_service.get_tone()

        assert tone == Tone.REFLECTIVE

    async def test_get_tone_returns_previously_set_tone(self, diary_service, mock_repo):
        """get_tone returns the tone stored in settings."""
        mock_repo.get_settings = AsyncMock(
            return_value=UserSettings(
                tone=Tone.POETIC,
                timezone="UTC",
                mood_check_in_times=["09:00", "13:00", "18:00"],
                inactivity_threshold_hours=24,
                memory_callback_time="10:00",
            )
        )

        tone = await diary_service.get_tone()

        assert tone == Tone.POETIC


# --- Tests for initiate_generation() and generate_entry() ---

from datetime import date, datetime
from unittest.mock import patch

from diary_bot.diary_service import DiaryError, GenerationState, GenerationStatus
from diary_bot.models import Input, InputType, MoodEntry


@pytest.fixture
def mock_repo_generation():
    """Create a mock Repository with generation-related methods."""
    repo = MagicMock()
    repo.update_setting = AsyncMock()
    repo.get_settings = AsyncMock(
        return_value=UserSettings(
            tone=Tone.REFLECTIVE,
            timezone="UTC",
            mood_check_in_times=["09:00", "13:00", "18:00"],
            inactivity_threshold_hours=24,
            memory_callback_time="10:00",
        )
    )
    repo.get_inputs_for_date = AsyncMock(return_value=[])
    repo.get_mood_for_date = AsyncMock(return_value=[])
    repo.save_diary_entry = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_day_boundary_generation():
    """Create a mock DayBoundaryService with generation-related methods."""
    boundary = MagicMock()
    boundary.get_entry_date_async = AsyncMock(return_value=date(2024, 1, 15))
    boundary.mark_diary_generated = AsyncMock()
    return boundary


@pytest.fixture
def mock_llm_client_generation():
    """Create a mock LLM client for generation tests."""
    client = MagicMock()
    client.generate_diary = AsyncMock(return_value=Ok("Today was a wonderful day..."))
    return client


@pytest.fixture
def diary_service_generation(mock_repo_generation, mock_llm_client_generation, mock_day_boundary_generation):
    """Create a DiaryService with generation-capable mocks."""
    return DiaryService(
        repo=mock_repo_generation,
        llm_client=mock_llm_client_generation,
        day_boundary=mock_day_boundary_generation,
    )


class TestInitiateGenerationNoInputs:
    """Tests for initiate_generation when no inputs exist."""

    async def test_returns_no_inputs_state(self, diary_service_generation, mock_repo_generation):
        """When no inputs exist for the entry date, returns NO_INPUTS state."""
        mock_repo_generation.get_inputs_for_date.return_value = []
        timestamp = datetime(2024, 1, 15, 14, 0, 0)

        state = await diary_service_generation.initiate_generation(timestamp)

        assert state.status == GenerationStatus.NO_INPUTS
        assert state.entry_date == date(2024, 1, 15)

    async def test_no_inputs_still_resolves_entry_date(
        self, diary_service_generation, mock_day_boundary_generation
    ):
        """Even with no inputs, the entry date is correctly resolved."""
        mock_day_boundary_generation.get_entry_date_async.return_value = date(2024, 1, 16)
        timestamp = datetime(2024, 1, 15, 23, 0, 0)

        state = await diary_service_generation.initiate_generation(timestamp)

        assert state.entry_date == date(2024, 1, 16)
        mock_day_boundary_generation.get_entry_date_async.assert_called_once_with(timestamp)


class TestInitiateGenerationReady:
    """Tests for initiate_generation when inputs exist (ready state)."""

    async def test_returns_ready_when_inputs_exist(
        self, diary_service_generation, mock_repo_generation
    ):
        """When inputs exist for the date, returns READY state."""
        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="Morning walk", timestamp=datetime(2024, 1, 15, 8, 0), input_type=InputType.TEXT)
        ]
        timestamp = datetime(2024, 1, 15, 14, 0, 0)

        state = await diary_service_generation.initiate_generation(timestamp)

        assert state.status == GenerationStatus.READY
        assert state.entry_date == date(2024, 1, 15)

    async def test_can_always_regenerate(
        self, diary_service_generation, mock_day_boundary_generation, mock_repo_generation
    ):
        """Diary can always be regenerated — no duplicate prevention."""
        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="Late dinner", timestamp=datetime(2024, 1, 15, 21, 0), input_type=InputType.TEXT)
        ]
        timestamp = datetime(2024, 1, 15, 22, 30, 0)

        state = await diary_service_generation.initiate_generation(timestamp)

        assert state.status == GenerationStatus.READY


class TestGenerateEntrySuccess:
    """Tests for generate_entry on successful generation."""

    async def test_calls_llm_with_correct_inputs(
        self, diary_service_generation, mock_repo_generation, mock_llm_client_generation
    ):
        """generate_entry passes inputs, mood, tone, and instructions to LLM."""
        inputs = [
            Input(id=1, entry_date=date(2024, 1, 15), content="Good morning", timestamp=datetime(2024, 1, 15, 8, 0), input_type=InputType.TEXT),
            Input(id=2, entry_date=date(2024, 1, 15), content="Lunch was great", timestamp=datetime(2024, 1, 15, 12, 0), input_type=InputType.TEXT),
        ]
        mood_data = [
            MoodEntry(id=1, check_in_id=1, content="Feeling great", timestamp=datetime(2024, 1, 15, 9, 0), entry_date=date(2024, 1, 15))
        ]
        mock_repo_generation.get_inputs_for_date.return_value = inputs
        mock_repo_generation.get_mood_for_date.return_value = mood_data

        await diary_service_generation.generate_entry(
            date(2024, 1, 15), "Focus on food", Tone.CASUAL
        )

        mock_llm_client_generation.generate_diary.assert_called_once_with(
            inputs, mood_data, Tone.CASUAL, "Focus on food"
        )

    async def test_saves_diary_entry_on_success(
        self, diary_service_generation, mock_repo_generation, mock_llm_client_generation
    ):
        """generate_entry saves the generated content to the repository."""
        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="test", timestamp=datetime(2024, 1, 15, 10, 0), input_type=InputType.TEXT)
        ]
        mock_llm_client_generation.generate_diary.return_value = Ok("A beautiful diary entry.")

        result = await diary_service_generation.generate_entry(
            date(2024, 1, 15), "Be poetic", Tone.POETIC
        )

        assert isinstance(result, Ok)
        assert result.value == "A beautiful diary entry."
        mock_repo_generation.save_diary_entry.assert_called_once_with(
            date(2024, 1, 15), "A beautiful diary entry.", "poetic", "Be poetic"
        )

    async def test_marks_diary_generated_on_success(
        self, diary_service_generation, mock_repo_generation, mock_day_boundary_generation, mock_llm_client_generation
    ):
        """generate_entry calls mark_diary_generated after successful generation."""
        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="test", timestamp=datetime(2024, 1, 15, 10, 0), input_type=InputType.TEXT)
        ]
        mock_llm_client_generation.generate_diary.return_value = Ok("Diary content")

        with patch("diary_bot.diary_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 1, 15, 22, 0, 0)
            await diary_service_generation.generate_entry(
                date(2024, 1, 15), None, Tone.REFLECTIVE
            )

        mock_day_boundary_generation.mark_diary_generated.assert_called_once_with(
            date(2024, 1, 15), datetime(2024, 1, 15, 22, 0, 0)
        )


class TestGenerateEntryFailure:
    """Tests for generate_entry when LLM fails."""

    async def test_returns_err_when_llm_fails(
        self, diary_service_generation, mock_repo_generation, mock_llm_client_generation
    ):
        """generate_entry returns Err(DiaryError) when LLM returns an error."""
        from diary_bot.llm_client import LLMError

        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="test", timestamp=datetime(2024, 1, 15, 10, 0), input_type=InputType.TEXT)
        ]
        mock_llm_client_generation.generate_diary.return_value = Err(
            LLMError(message="Service unavailable")
        )

        result = await diary_service_generation.generate_entry(
            date(2024, 1, 15), None, Tone.REFLECTIVE
        )

        assert isinstance(result, Err)
        assert isinstance(result.error, DiaryError)
        assert result.error.code == "llm_failure"
        assert "Service unavailable" in result.error.message

    async def test_does_not_save_when_llm_fails(
        self, diary_service_generation, mock_repo_generation, mock_llm_client_generation
    ):
        """generate_entry does not persist anything when LLM fails."""
        from diary_bot.llm_client import LLMError

        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="test", timestamp=datetime(2024, 1, 15, 10, 0), input_type=InputType.TEXT)
        ]
        mock_llm_client_generation.generate_diary.return_value = Err(
            LLMError(message="timeout")
        )

        await diary_service_generation.generate_entry(
            date(2024, 1, 15), "instructions", Tone.CASUAL
        )

        mock_repo_generation.save_diary_entry.assert_not_called()


class TestGenerateEntryNoSpecialInstructions:
    """Tests for generate_entry with no special instructions."""

    async def test_passes_none_for_no_special_instructions(
        self, diary_service_generation, mock_repo_generation, mock_llm_client_generation
    ):
        """generate_entry passes None to LLM when no special instructions provided."""
        mock_repo_generation.get_inputs_for_date.return_value = [
            Input(id=1, entry_date=date(2024, 1, 15), content="hello", timestamp=datetime(2024, 1, 15, 10, 0), input_type=InputType.TEXT)
        ]
        mock_llm_client_generation.generate_diary.return_value = Ok("Entry content")

        await diary_service_generation.generate_entry(
            date(2024, 1, 15), None, Tone.REFLECTIVE
        )

        mock_llm_client_generation.generate_diary.assert_called_once_with(
            mock_repo_generation.get_inputs_for_date.return_value,
            mock_repo_generation.get_mood_for_date.return_value,
            Tone.REFLECTIVE,
            None,
        )


# --- Tests for generate_weekly_summary() ---

from datetime import timedelta

from diary_bot.llm_client import LLMError as LLMClientError


@pytest.fixture
def mock_repo_weekly():
    """Create a mock Repository for weekly summary tests."""
    repo = MagicMock()
    repo.get_entries_for_range = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_llm_client_weekly():
    """Create a mock LLM client for weekly summary tests."""
    client = MagicMock()
    client.generate_weekly_summary = AsyncMock(
        return_value=Ok("## Recurring Themes\n...\n## Notable Events\n...\n## Overall Reflection\n...")
    )
    return client


@pytest.fixture
def mock_day_boundary_weekly():
    """Create a mock DayBoundaryService for weekly summary tests."""
    return MagicMock()


@pytest.fixture
def diary_service_weekly(mock_repo_weekly, mock_llm_client_weekly, mock_day_boundary_weekly):
    """Create a DiaryService for weekly summary tests."""
    return DiaryService(
        repo=mock_repo_weekly,
        llm_client=mock_llm_client_weekly,
        day_boundary=mock_day_boundary_weekly,
    )


class TestGenerateWeeklySummarySuccess:
    """Tests for generate_weekly_summary with sufficient data."""

    async def test_returns_ok_with_content_when_enough_entries(
        self, diary_service_weekly, mock_repo_weekly, mock_llm_client_weekly
    ):
        """generate_weekly_summary returns Ok with content when >= 2 days of entries exist."""
        from diary_bot.models import DiaryEntry, Tone

        today = date.today()
        entries = [
            DiaryEntry(
                id=1,
                entry_date=today - timedelta(days=2),
                content="Monday's diary entry.",
                tone=Tone.REFLECTIVE,
                special_instructions=None,
                generated_at=datetime(2024, 1, 13, 22, 0, 0),
            ),
            DiaryEntry(
                id=2,
                entry_date=today - timedelta(days=1),
                content="Tuesday's diary entry.",
                tone=Tone.CASUAL,
                special_instructions=None,
                generated_at=datetime(2024, 1, 14, 22, 0, 0),
            ),
        ]
        mock_repo_weekly.get_entries_for_range.return_value = entries
        expected_summary = "## Recurring Themes\nWork and health\n## Notable Events\nGot promoted\n## Overall Reflection\nA good week."
        mock_llm_client_weekly.generate_weekly_summary.return_value = Ok(expected_summary)

        result = await diary_service_weekly.generate_weekly_summary()

        assert isinstance(result, Ok)
        assert result.value == expected_summary
        mock_llm_client_weekly.generate_weekly_summary.assert_called_once_with(entries)

    async def test_queries_correct_7_day_date_range(
        self, diary_service_weekly, mock_repo_weekly, mock_llm_client_weekly
    ):
        """generate_weekly_summary queries from today - 6 days to today (7 total days)."""
        from diary_bot.models import DiaryEntry, Tone

        today = date.today()
        expected_start = today - timedelta(days=6)
        expected_end = today

        # Provide entries so the method doesn't short-circuit
        entries = [
            DiaryEntry(
                id=1,
                entry_date=today - timedelta(days=3),
                content="Entry A",
                tone=Tone.REFLECTIVE,
                special_instructions=None,
                generated_at=datetime(2024, 1, 12, 22, 0, 0),
            ),
            DiaryEntry(
                id=2,
                entry_date=today - timedelta(days=1),
                content="Entry B",
                tone=Tone.REFLECTIVE,
                special_instructions=None,
                generated_at=datetime(2024, 1, 14, 22, 0, 0),
            ),
        ]
        mock_repo_weekly.get_entries_for_range.return_value = entries

        await diary_service_weekly.generate_weekly_summary()

        mock_repo_weekly.get_entries_for_range.assert_called_once_with(expected_start, expected_end)


class TestGenerateWeeklySummaryInsufficientData:
    """Tests for generate_weekly_summary with insufficient data."""

    async def test_returns_insufficient_data_when_less_than_2_days(
        self, diary_service_weekly, mock_repo_weekly, mock_llm_client_weekly
    ):
        """generate_weekly_summary returns Err with code 'insufficient_data' when < 2 days exist."""
        from diary_bot.models import DiaryEntry, Tone

        today = date.today()
        # Only 1 day has entries
        entries = [
            DiaryEntry(
                id=1,
                entry_date=today - timedelta(days=1),
                content="Only one day of data.",
                tone=Tone.REFLECTIVE,
                special_instructions=None,
                generated_at=datetime(2024, 1, 14, 22, 0, 0),
            ),
        ]
        mock_repo_weekly.get_entries_for_range.return_value = entries

        result = await diary_service_weekly.generate_weekly_summary()

        assert isinstance(result, Err)
        assert isinstance(result.error, DiaryError)
        assert result.error.code == "insufficient_data"
        mock_llm_client_weekly.generate_weekly_summary.assert_not_called()

    async def test_returns_insufficient_data_when_zero_entries(
        self, diary_service_weekly, mock_repo_weekly, mock_llm_client_weekly
    ):
        """generate_weekly_summary returns Err with code 'insufficient_data' when 0 entries exist."""
        mock_repo_weekly.get_entries_for_range.return_value = []

        result = await diary_service_weekly.generate_weekly_summary()

        assert isinstance(result, Err)
        assert isinstance(result.error, DiaryError)
        assert result.error.code == "insufficient_data"
        mock_llm_client_weekly.generate_weekly_summary.assert_not_called()


class TestGenerateWeeklySummaryLLMFailure:
    """Tests for generate_weekly_summary when LLM fails."""

    async def test_returns_llm_failure_when_llm_fails(
        self, diary_service_weekly, mock_repo_weekly, mock_llm_client_weekly
    ):
        """generate_weekly_summary returns Err with code 'llm_failure' when LLM fails."""
        from diary_bot.models import DiaryEntry, Tone

        today = date.today()
        entries = [
            DiaryEntry(
                id=1,
                entry_date=today - timedelta(days=3),
                content="Entry A",
                tone=Tone.REFLECTIVE,
                special_instructions=None,
                generated_at=datetime(2024, 1, 12, 22, 0, 0),
            ),
            DiaryEntry(
                id=2,
                entry_date=today - timedelta(days=1),
                content="Entry B",
                tone=Tone.CASUAL,
                special_instructions=None,
                generated_at=datetime(2024, 1, 14, 22, 0, 0),
            ),
        ]
        mock_repo_weekly.get_entries_for_range.return_value = entries
        mock_llm_client_weekly.generate_weekly_summary.return_value = Err(
            LLMClientError(message="Service unavailable")
        )

        result = await diary_service_weekly.generate_weekly_summary()

        assert isinstance(result, Err)
        assert isinstance(result.error, DiaryError)
        assert result.error.code == "llm_failure"
        assert "Service unavailable" in result.error.message
