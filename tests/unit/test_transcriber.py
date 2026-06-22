"""Unit tests for the Transcriber class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from diary_bot.models import Err, Ok
from diary_bot.transcriber import Transcriber, TranscriptionError


@pytest.fixture
def mock_groq_client():
    """Create a mock AsyncGroq client."""
    client = AsyncMock()
    return client


@pytest.fixture
def transcriber(mock_groq_client):
    """Create a Transcriber instance with a mocked Groq client."""
    return Transcriber(groq_client=mock_groq_client)


class TestTranscriber:
    """Tests for the Transcriber.transcribe() method."""

    async def test_successful_transcription(self, transcriber, mock_groq_client):
        """Should return Ok with transcribed text on success."""
        mock_response = MagicMock()
        mock_response.text = "Hello, this is a test transcription."
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await transcriber.transcribe(b"fake audio bytes")

        assert isinstance(result, Ok)
        assert result.value == "Hello, this is a test transcription."

    async def test_successful_transcription_calls_api_with_correct_model(
        self, transcriber, mock_groq_client
    ):
        """Should call the Groq API with the whisper-large-v3 model."""
        mock_response = MagicMock()
        mock_response.text = "transcribed"
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        await transcriber.transcribe(b"audio data")

        mock_groq_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_groq_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-large-v3"

    async def test_retry_on_first_failure_then_success(
        self, transcriber, mock_groq_client
    ):
        """Should retry once and return Ok if the second attempt succeeds."""
        mock_response = MagicMock()
        mock_response.text = "success on retry"
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            side_effect=[Exception("API error"), mock_response]
        )

        result = await transcriber.transcribe(b"audio bytes")

        assert isinstance(result, Ok)
        assert result.value == "success on retry"
        assert mock_groq_client.audio.transcriptions.create.call_count == 2

    async def test_returns_error_after_both_attempts_fail(
        self, transcriber, mock_groq_client
    ):
        """Should return Err with TranscriptionError if both attempts fail."""
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            side_effect=[Exception("first failure"), Exception("second failure")]
        )

        result = await transcriber.transcribe(b"audio bytes")

        assert isinstance(result, Err)
        assert isinstance(result.error, TranscriptionError)
        assert "second failure" in result.error.message

    async def test_error_message_contains_retry_info(
        self, transcriber, mock_groq_client
    ):
        """Error message should indicate the failure happened after retry."""
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            side_effect=Exception("timeout")
        )

        result = await transcriber.transcribe(b"audio bytes")

        assert isinstance(result, Err)
        assert "after retry" in result.error.message

    async def test_does_not_retry_on_success(self, transcriber, mock_groq_client):
        """Should only call the API once if the first attempt succeeds."""
        mock_response = MagicMock()
        mock_response.text = "first try success"
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await transcriber.transcribe(b"audio bytes")

        assert isinstance(result, Ok)
        assert mock_groq_client.audio.transcriptions.create.call_count == 1

    async def test_handles_empty_transcription_text(
        self, transcriber, mock_groq_client
    ):
        """Should return Ok with empty string if the API returns empty text."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await transcriber.transcribe(b"audio bytes")

        assert isinstance(result, Ok)
        assert result.value == ""

    async def test_file_tuple_passed_to_api(self, transcriber, mock_groq_client):
        """Should pass audio as a file tuple with .ogg extension."""
        mock_response = MagicMock()
        mock_response.text = "test"
        mock_groq_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        await transcriber.transcribe(b"audio content")

        call_kwargs = mock_groq_client.audio.transcriptions.create.call_args[1]
        file_arg = call_kwargs["file"]
        # file should be a tuple (filename, content)
        assert isinstance(file_arg, tuple)
        assert file_arg[0] == "audio.ogg"
        assert isinstance(file_arg[1], bytes)
