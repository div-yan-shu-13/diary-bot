"""Scheduler service for configuring periodic jobs.

Uses APScheduler's AsyncIOScheduler to manage mood check-in jobs,
memory callback jobs, and inactivity reminder jobs based on user settings.
"""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from diary_bot.diary_service import DiaryService
from diary_bot.memory_service import MemoryService
from diary_bot.models import UserSettings
from diary_bot.mood_service import MoodService
from diary_bot.reminder_service import ReminderService


class SchedulerService:
    """Manages scheduled jobs for the diary bot.

    Configures mood check-in jobs, memory callback job, and inactivity
    reminder job based on user settings via APScheduler.
    """

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        mood_service: MoodService,
        memory_service: MemoryService,
        reminder_service: ReminderService,
        diary_service: DiaryService,
        authorized_user_id: int,
        bot,  # noqa: ANN001
    ) -> None:
        """Initialize the scheduler service.

        Args:
            scheduler: APScheduler AsyncIOScheduler instance.
            mood_service: Service for mood check-in operations.
            memory_service: Service for memory callback operations.
            reminder_service: Service for inactivity reminder operations.
            diary_service: Service for diary generation operations.
            authorized_user_id: The user's Telegram ID for sending messages.
            bot: The Telegram Bot instance used to send messages.
        """
        self._scheduler = scheduler
        self._mood_service = mood_service
        self._memory_service = memory_service
        self._reminder_service = reminder_service
        self._diary_service = diary_service
        self._authorized_user_id = authorized_user_id
        self._bot = bot

    async def setup_schedules(self, user_settings: UserSettings) -> None:
        """Configure all scheduled jobs based on user settings.

        Removes any existing jobs first (clean slate), then adds:
        - Mood check-in jobs at configured times
        - Memory callback job if time is configured
        - Inactivity reminder job if threshold is configured

        Args:
            user_settings: The user's current settings.
        """
        # Remove all existing jobs for a clean slate
        self._scheduler.remove_all_jobs()

        # Add mood check-in jobs
        for idx, time_str in enumerate(user_settings.mood_check_in_times):
            hour, minute = time_str.split(":")
            self._scheduler.add_job(
                self._mood_service.send_check_in,
                trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                args=[self._bot],
                id=f"mood_check_in_{idx}",
            )

        # Add memory callback job if configured
        if user_settings.memory_callback_time is not None:
            hour, minute = user_settings.memory_callback_time.split(":")
            self._scheduler.add_job(
                self._memory_service.check_and_send_memory,
                trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                args=[self._bot],
                id="memory_callback",
            )

        # Add inactivity reminder job if threshold is configured
        if user_settings.inactivity_threshold_hours is not None:
            self._scheduler.add_job(
                self._reminder_service.send_reminder,
                trigger=IntervalTrigger(minutes=30),
                args=[self._bot],
                id="inactivity_reminder",
            )

        # Add auto-diary generation at 10:30 PM user's timezone
        self._scheduler.add_job(
            self._diary_service.auto_generate_diary,
            trigger=CronTrigger(hour=22, minute=30),
            args=[self._bot, self._authorized_user_id],
            id="auto_diary",
        )

    async def update_mood_times(self, times: list[str]) -> None:
        """Reconfigure mood check-in schedule.

        Removes existing mood jobs and adds new ones at the specified times.

        Args:
            times: List of time strings in "HH:MM" format.
        """
        # Remove existing mood jobs
        for idx in range(3):
            job_id = f"mood_check_in_{idx}"
            job = self._scheduler.get_job(job_id)
            if job is not None:
                self._scheduler.remove_job(job_id)

        # Add new mood jobs
        for idx, time_str in enumerate(times):
            hour, minute = time_str.split(":")
            self._scheduler.add_job(
                self._mood_service.send_check_in,
                trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                args=[self._bot],
                id=f"mood_check_in_{idx}",
            )

    async def reset_inactivity_timer(self) -> None:
        """Reset the inactivity reminder countdown.

        Records the current time as the latest user activity so the
        inactivity reminder timer starts fresh.
        """
        self._reminder_service.record_activity(datetime.utcnow())
