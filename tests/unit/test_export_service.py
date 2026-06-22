"""Unit tests for the ExportService class."""

import json
from datetime import date, datetime

import pytest

from diary_bot.database import init_db
from diary_bot.export_service import ExportError, ExportService
from diary_bot.models import Err, Ok
from diary_bot.repository import Repository


@pytest.fixture
async def repo():
    """Create a Repository backed by an in-memory database."""
    db = await init_db(":memory:")
    repository = Repository(db)
    yield repository
    await db.close()


@pytest.fixture
def export_service(repo: Repository) -> ExportService:
    """Create an ExportService with the test repository."""
    return ExportService(repo)


class TestExportAll:
    async def test_returns_ok_with_valid_json_bytes_when_entries_exist(
        self, repo: Repository, export_service: ExportService
    ):
        """export_all returns Ok with valid JSON bytes when entries exist."""
        await repo.save_input(date(2024, 1, 15), "Morning walk", datetime(2024, 1, 15, 8, 0), "text")
        await repo.save_diary_entry(date(2024, 1, 15), "Great day", "reflective")

        result = await export_service.export_all()

        assert isinstance(result, Ok)
        # Verify the bytes are valid JSON
        data = json.loads(result.value)
        assert isinstance(data, dict)
        assert "entries" in data
        assert len(data["entries"]) == 1

    async def test_json_contains_export_date_field(
        self, repo: Repository, export_service: ExportService
    ):
        """export_all JSON contains export_date field."""
        await repo.save_input(date(2024, 1, 15), "Hello", datetime(2024, 1, 15, 10, 0), "text")

        result = await export_service.export_all()

        assert isinstance(result, Ok)
        data = json.loads(result.value)
        assert "export_date" in data
        # Verify it's a valid ISO datetime string
        export_date = datetime.fromisoformat(data["export_date"])
        assert export_date is not None

    async def test_json_entries_ordered_by_date_ascending(
        self, repo: Repository, export_service: ExportService
    ):
        """export_all JSON entries are ordered by date ascending."""
        # Insert in reverse order to test ordering
        await repo.save_input(date(2024, 1, 17), "Day 3", datetime(2024, 1, 17, 10, 0), "text")
        await repo.save_input(date(2024, 1, 15), "Day 1", datetime(2024, 1, 15, 10, 0), "text")
        await repo.save_input(date(2024, 1, 16), "Day 2", datetime(2024, 1, 16, 10, 0), "text")

        result = await export_service.export_all()

        assert isinstance(result, Ok)
        data = json.loads(result.value)
        dates = [entry["date"] for entry in data["entries"]]
        assert dates == ["2024-01-15", "2024-01-16", "2024-01-17"]

    async def test_returns_err_export_error_when_no_entries(
        self, export_service: ExportService
    ):
        """export_all returns Err(ExportError) when no entries exist."""
        result = await export_service.export_all()

        assert isinstance(result, Err)
        assert isinstance(result.error, ExportError)
        assert result.error.message == "No entries available to export."

    async def test_json_includes_inputs_mood_responses_and_generated_diary(
        self, repo: Repository, export_service: ExportService
    ):
        """export_all JSON includes inputs, mood_responses, and generated_diary for each date."""
        entry_date = date(2024, 1, 15)
        await repo.save_input(entry_date, "Morning walk", datetime(2024, 1, 15, 8, 0), "text")
        await repo.save_input(entry_date, "Voice note", datetime(2024, 1, 15, 12, 0), "voice")
        await repo.save_diary_entry(entry_date, "A beautiful day unfolded", "poetic")

        check_in_id = await repo.save_mood_check_in(datetime(2024, 1, 15, 9, 0))
        await repo.save_mood_response(
            check_in_id, "Feeling great", datetime(2024, 1, 15, 9, 5), entry_date
        )

        result = await export_service.export_all()

        assert isinstance(result, Ok)
        data = json.loads(result.value)
        entry = data["entries"][0]

        # Verify inputs
        assert len(entry["inputs"]) == 2
        assert entry["inputs"][0]["content"] == "Morning walk"
        assert entry["inputs"][0]["type"] == "text"
        assert entry["inputs"][1]["content"] == "Voice note"
        assert entry["inputs"][1]["type"] == "voice"

        # Verify mood_responses
        assert len(entry["mood_responses"]) == 1
        assert entry["mood_responses"][0]["content"] == "Feeling great"
        assert "timestamp" in entry["mood_responses"][0]

        # Verify generated_diary
        assert entry["generated_diary"] is not None
        assert entry["generated_diary"]["content"] == "A beautiful day unfolded"
        assert entry["generated_diary"]["tone"] == "poetic"
        assert "generated_at" in entry["generated_diary"]
