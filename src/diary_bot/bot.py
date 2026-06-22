"""Main entry point for the Telegram Diary Bot.

Initializes all components, registers handlers with the Application,
sets up the scheduler, initializes the database, and starts long polling.
"""

from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import AsyncGroq
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from diary_bot.callback_handlers import handle_awaiting_text, handle_callback_query
from diary_bot.config import load_config
from diary_bot.database import init_db
from diary_bot.day_boundary import DayBoundaryService
from diary_bot.delete_service import DeleteService
from diary_bot.diary_service import DiaryService
from diary_bot.export_service import ExportService
from diary_bot.handlers import (
    HandlerContext,
    handle_delete_cmd,
    handle_diary_cmd,
    handle_export_cmd,
    handle_help,
    handle_settings_cmd,
    handle_start,
    handle_text,
    handle_tone_cmd,
    handle_voice,
    handle_week_cmd,
)
from diary_bot.input_service import InputService
from diary_bot.llm_client import LLMClient
from diary_bot.memory_service import MemoryService
from diary_bot.mood_service import MoodService
from diary_bot.reminder_service import ReminderService
from diary_bot.repository import Repository
from diary_bot.scheduler_service import SchedulerService
from diary_bot.transcriber import Transcriber

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _is_awaiting(user_data: dict | None) -> bool:
    """Check if the user is in an awaiting state for follow-up text input."""
    if user_data is None:
        return False
    return bool(
        user_data.get("awaiting_instructions")
        or user_data.get("awaiting_special_instructions")
        or user_data.get("awaiting_delete_date")
        or user_data.get("awaiting_delete_range")
    )


async def _handle_text_with_awaiting_check(update, context) -> None:  # noqa: ANN001
    """Wrapper that checks awaiting state before routing to normal text handler.

    If the user is in an awaiting state (e.g., typing special instructions or
    a delete date), routes to handle_awaiting_text. Otherwise routes to the
    normal handle_text handler which stores the message as input.

    Also resets the inactivity timer on any text input (Req 6.4).
    """
    user_data = context.user_data
    if _is_awaiting(user_data):
        await handle_awaiting_text(update, context)
    else:
        await handle_text(update, context)


def main() -> None:
    """Initialize all components and start the bot."""
    # 1. Load configuration (raises RuntimeError if AUTHORIZED_USER_ID missing)
    config = load_config()
    logger.info("Configuration loaded. Authorized user: %d", config.authorized_user_id)

    # Build the user filter for authorization (Req 13.1, 13.2)
    user_filter = filters.User(user_id=config.authorized_user_id)

    # 2. Run async initialization and start polling
    asyncio.run(_async_main(config, user_filter))


async def _async_main(config, user_filter) -> None:  # noqa: ANN001
    """Async initialization and bot startup."""
    # 2. Initialize the database
    db = await init_db(config.database_path)
    logger.info("Database initialized at: %s", config.database_path)

    # 3. Create services
    timezone = ZoneInfo(config.timezone)
    groq_client = AsyncGroq(api_key=config.groq_api_key)

    repo = Repository(db)
    transcriber = Transcriber(groq_client)
    llm_client = LLMClient(groq_client)
    day_boundary = DayBoundaryService(repo, timezone)
    input_service = InputService(repo, transcriber, day_boundary)
    diary_service = DiaryService(repo, llm_client, day_boundary)
    mood_service = MoodService(repo, config.authorized_user_id)
    memory_service = MemoryService(repo, llm_client, config.authorized_user_id)
    reminder_service = ReminderService(
        authorized_user_id=config.authorized_user_id,
        threshold_hours=None,  # Will be set from user settings
    )
    export_service = ExportService(repo)
    delete_service = DeleteService(repo)

    # 4. Build the Telegram Application
    application = Application.builder().token(config.bot_token).build()

    # 5. Create scheduler service (needs the bot instance)
    scheduler = AsyncIOScheduler()
    scheduler_service = SchedulerService(
        scheduler=scheduler,
        mood_service=mood_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        bot=application.bot,
    )

    # 6. Store HandlerContext in bot_data
    handler_ctx = HandlerContext(
        input_service=input_service,
        diary_service=diary_service,
        export_service=export_service,
        delete_service=delete_service,
        scheduler_service=scheduler_service,
        repository=repo,
    )
    application.bot_data["handler_ctx"] = handler_ctx

    # 7. Register command handlers (with user authorization filter)
    application.add_handler(
        CommandHandler("start", handle_start, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("help", handle_help, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("diary", handle_diary_cmd, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("tone", handle_tone_cmd, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("week", handle_week_cmd, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("export", handle_export_cmd, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("delete", handle_delete_cmd, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("settings", handle_settings_cmd, filters=user_filter)
    )

    # 8. Register message handlers
    # Text handler checks awaiting state first, then falls through to normal handling
    application.add_handler(
        MessageHandler(
            user_filter & filters.TEXT & ~filters.COMMAND,
            _handle_text_with_awaiting_check,
        )
    )

    # Voice handler
    application.add_handler(
        MessageHandler(user_filter & filters.VOICE, handle_voice)
    )

    # Callback query handler (inline buttons)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # 9. Load user settings and configure scheduler
    user_settings = await repo.get_settings()

    # Update reminder service with stored threshold
    if user_settings.inactivity_threshold_hours is not None:
        reminder_service.update_threshold(user_settings.inactivity_threshold_hours)

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started.")

    # Set up scheduled jobs from user settings
    await scheduler_service.setup_schedules(user_settings)
    logger.info("Scheduled jobs configured.")

    # 10. Start long polling
    logger.info("Starting bot polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Keep running until interrupted
    try:
        # Block until a stop signal is received
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await db.close()
        logger.info("Bot shut down gracefully.")


if __name__ == "__main__":
    main()
