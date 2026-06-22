"""Transcriber module wrapping Groq Whisper API for voice-to-text conversion."""

import tempfile
from dataclasses import dataclass

from groq import AsyncGroq

from diary_bot.models import Err, Ok, Result


@dataclass
class TranscriptionError:
    """Error returned when audio transcription fails."""

    message: str


class Transcriber:
    """Wraps the Groq Whisper API to transcribe audio bytes to text."""

    def __init__(self, groq_client: AsyncGroq) -> None:
        self._client = groq_client

    async def transcribe(self, audio_bytes: bytes) -> Result[str, TranscriptionError]:
        """Transcribe audio bytes to text.

        Retries once on failure before returning an error.

        Args:
            audio_bytes: Raw audio data to transcribe.

        Returns:
            Ok with the transcribed text on success,
            Err with TranscriptionError if both attempts fail.
        """
        last_error: Exception | None = None

        for _ in range(2):  # Try up to 2 times (initial + 1 retry)
            try:
                text = await self._call_whisper(audio_bytes)
                return Ok(value=text)
            except Exception as e:
                last_error = e

        return Err(
            error=TranscriptionError(
                message=f"Transcription failed after retry: {last_error}"
            )
        )

    async def _call_whisper(self, audio_bytes: bytes) -> str:
        """Call the Groq Whisper API with audio bytes.

        Uses a temporary file since the Groq API expects a file-like object.
        """
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp.seek(0)

            transcription = await self._client.audio.transcriptions.create(
                file=("audio.ogg", tmp.read()),
                model="whisper-large-v3",
            )

        return transcription.text
