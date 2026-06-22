"""Unit tests for MemoryService."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from diary_bot.llm_client import LLMClient, LLMError
from diary_bot.memory_service import MemoryService
from diary_bot.models import DiaryEntry, Err, Ok, Tone


def _make_diary_entry(entry_date: date, content: str = "A diary entry.") -> DiaryEntry:
    """Helper to create a DiaryEntry for testing."""
    return DiaryEntry(
        id=1,
        entry_date=entry_date,
        content=content,
        tone=Tone.REFLECTIVE,
        special_instructions=None,
        generated_at=datetime(2024, 1, 1, 22, 0, 0),
    )


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_diary_entry = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_llm():
    llm = AsyncMock(spec=LLMClient)
    llm.summarize_entry = AsyncMock(return_value=Ok("Had a productive day at work."))
    return llm


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def service(mock_repo, mock_llm):
    return MemoryService(repo=mock_repo, llm_client=mock_llm, authorized_user_id=12345)


class TestCheckAndSendMemory:
    """Tests for MemoryService.check_and_send_memory()."""

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_sends_message_when_entry_exists_7_days_ago(
        self, mock_date, service, mock_repo, mock_llm, mock_bot
    ):
        """check_and_send_memory sends message when entry exists 7 days ago."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target_date = today - timedelta(days=7)
        entry = _make_diary_entry(target_date, "Went hiking in the mountains.")

        async def get_entry(d):
            if d == target_date:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Enjoyed a mountain hike.")

        await service.check_and_send_memory(mock_bot)

        mock_llm.summarize_entry.assert_called_once_with("Went hiking in the mountains.")
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="\U0001f52e 1 week ago today: Enjoyed a mountain hike.",
        )

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_sends_message_when_entry_exists_14_days_ago_not_7(
        self, mock_date, service, mock_repo, mock_llm, mock_bot
    ):
        """check_and_send_memory sends message when entry exists 14 days ago (not 7)."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target_14 = today - timedelta(days=14)
        entry = _make_diary_entry(target_14, "Started a new book.")

        async def get_entry(d):
            if d == target_14:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Began reading a new novel.")

        await service.check_and_send_memory(mock_bot)

        mock_llm.summarize_entry.assert_called_once_with("Started a new book.")
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="\U0001f52e 2 weeks ago today: Began reading a new novel.",
        )

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_sends_nothing_when_no_matching_entries(
        self, mock_date, service, mock_repo, mock_bot
    ):
        """check_and_send_memory sends nothing when no matching entries exist."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        mock_repo.get_diary_entry.return_value = None

        await service.check_and_send_memory(mock_bot)

        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_only_sends_one_message_first_match_wins(
        self, mock_date, service, mock_repo, mock_llm, mock_bot
    ):
        """check_and_send_memory only sends one message even if multiple matches exist (first wins: 7 days)."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target_7 = today - timedelta(days=7)
        target_14 = today - timedelta(days=14)
        entry_7 = _make_diary_entry(target_7, "Entry from 7 days ago.")
        entry_14 = _make_diary_entry(target_14, "Entry from 14 days ago.")

        async def get_entry(d):
            if d == target_7:
                return entry_7
            if d == target_14:
                return entry_14
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Summary of 7 days ago.")

        await service.check_and_send_memory(mock_bot)

        # Only one message sent
        mock_bot.send_message.assert_called_once()
        # The 7-day match is used, not 14-day
        mock_llm.summarize_entry.assert_called_once_with("Entry from 7 days ago.")
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="\U0001f52e 1 week ago today: Summary of 7 days ago.",
        )

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_does_nothing_when_summarize_entry_fails(
        self, mock_date, service, mock_repo, mock_llm, mock_bot
    ):
        """check_and_send_memory does nothing when summarize_entry fails (graceful handling)."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target_7 = today - timedelta(days=7)
        entry = _make_diary_entry(target_7, "Some entry.")

        async def get_entry(d):
            if d == target_7:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Err(LLMError(message="API timeout"))

        await service.check_and_send_memory(mock_bot)

        # No message sent when LLM fails
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_label_1_week_for_7_days(self, mock_date, service, mock_repo, mock_llm, mock_bot):
        """Label is '1 week ago today' for 7 days."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target = today - timedelta(days=7)
        entry = _make_diary_entry(target)

        async def get_entry(d):
            if d == target:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Summary.")

        await service.check_and_send_memory(mock_bot)

        call_args = mock_bot.send_message.call_args
        assert "1 week ago today" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_label_2_weeks_for_14_days(self, mock_date, service, mock_repo, mock_llm, mock_bot):
        """Label is '2 weeks ago today' for 14 days."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target = today - timedelta(days=14)
        entry = _make_diary_entry(target)

        async def get_entry(d):
            if d == target:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Summary.")

        await service.check_and_send_memory(mock_bot)

        call_args = mock_bot.send_message.call_args
        assert "2 weeks ago today" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_label_3_weeks_for_21_days(self, mock_date, service, mock_repo, mock_llm, mock_bot):
        """Label is '3 weeks ago today' for 21 days."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target = today - timedelta(days=21)
        entry = _make_diary_entry(target)

        async def get_entry(d):
            if d == target:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Summary.")

        await service.check_and_send_memory(mock_bot)

        call_args = mock_bot.send_message.call_args
        assert "3 weeks ago today" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    @patch("diary_bot.memory_service.date")
    async def test_label_4_weeks_for_28_days(self, mock_date, service, mock_repo, mock_llm, mock_bot):
        """Label is '4 weeks ago today' for 28 days."""
        today = date(2024, 6, 15)
        mock_date.today.return_value = today

        target = today - timedelta(days=28)
        entry = _make_diary_entry(target)

        async def get_entry(d):
            if d == target:
                return entry
            return None

        mock_repo.get_diary_entry.side_effect = get_entry
        mock_llm.summarize_entry.return_value = Ok("Summary.")

        await service.check_and_send_memory(mock_bot)

        call_args = mock_bot.send_message.call_args
        assert "4 weeks ago today" in call_args.kwargs["text"]


class TestGetMatchingMemoryDates:
    """Tests for MemoryService.get_matching_memory_dates() static method."""

    def test_returns_empty_when_no_matches(self):
        current = date(2024, 6, 15)
        entry_dates = {date(2024, 6, 10), date(2024, 5, 1)}
        result = MemoryService.get_matching_memory_dates(current, entry_dates)
        assert result == []

    def test_returns_7_day_match(self):
        current = date(2024, 6, 15)
        target = current - timedelta(days=7)
        entry_dates = {target}
        result = MemoryService.get_matching_memory_dates(current, entry_dates)
        assert result == [(target, 7)]

    def test_returns_multiple_matches_in_order(self):
        current = date(2024, 6, 15)
        target_7 = current - timedelta(days=7)
        target_21 = current - timedelta(days=21)
        entry_dates = {target_7, target_21}
        result = MemoryService.get_matching_memory_dates(current, entry_dates)
        assert result == [(target_7, 7), (target_21, 21)]

    def test_returns_all_four_matches(self):
        current = date(2024, 6, 15)
        targets = {current - timedelta(days=d) for d in [7, 14, 21, 28]}
        result = MemoryService.get_matching_memory_dates(current, targets)
        assert len(result) == 4
        assert result[0] == (current - timedelta(days=7), 7)
        assert result[1] == (current - timedelta(days=14), 14)
        assert result[2] == (current - timedelta(days=21), 21)
        assert result[3] == (current - timedelta(days=28), 28)
