"""Main entry point for the Telegram Diary Bot.

Initializes all components, registers handlers with the Application,
sets up the scheduler, initializes the database, and starts long polling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load .env file from the project root (if it exists)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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

    # 2. Build the Telegram Application
    application = Application.builder().token(config.bot_token).build()

    # Store config and user_filter for post_init
    application.bot_data["_config"] = config
    application.bot_data["_user_filter"] = user_filter

    # Register post_init to do async setup
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    # Register handlers (sync registration)
    _register_handlers(application, user_filter)

    # 3. Start polling (handles signals and shutdown gracefully)
    logger.info("Starting bot polling...")
    application.run_polling()


async def _post_init(application: Application) -> None:
    """Async initialization that runs after the Application is built."""
    config = application.bot_data["_config"]

    # Initialize the database
    db = await init_db(config.database_path)
    logger.info("Database initialized at: %s", config.database_path)

    # Create services
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
        threshold_hours=None,
    )
    export_service = ExportService(repo)
    delete_service = DeleteService(repo)

    # Create scheduler service
    scheduler = AsyncIOScheduler()
    scheduler_service = SchedulerService(
        scheduler=scheduler,
        mood_service=mood_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        bot=application.bot,
    )

    # Store HandlerContext in bot_data
    handler_ctx = HandlerContext(
        input_service=input_service,
        diary_service=diary_service,
        export_service=export_service,
        delete_service=delete_service,
        scheduler_service=scheduler_service,
        repository=repo,
    )
    application.bot_data["handler_ctx"] = handler_ctx
    application.bot_data["_db"] = db
    application.bot_data["_scheduler"] = scheduler

    # Load user settings and configure scheduler
    user_settings = await repo.get_settings()
    if user_settings.inactivity_threshold_hours is not None:
        reminder_service.update_threshold(user_settings.inactivity_threshold_hours)

    scheduler.start()
    await scheduler_service.setup_schedules(user_settings)
    logger.info("Scheduler and services initialized.")


async def _post_shutdown(application: Application) -> None:
    """Clean up resources after the Application shuts down."""
    scheduler = application.bot_data.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)

    db = application.bot_data.get("_db")
    if db:
        await db.close()

    logger.info("Bot shut down gracefully.")


def _register_handlers(application: Application, user_filter) -> None:  # noqa: ANN001
    """Register all handlers with the Application."""
    application.add_handler(CommandHandler("start", handle_start, filters=user_filter))
    application.add_handler(CommandHandler("help", handle_help, filters=user_filter))
    application.add_handler(CommandHandler("diary", handle_diary_cmd, filters=user_filter))
    application.add_handler(CommandHandler("tone", handle_tone_cmd, filters=user_filter))
    application.add_handler(CommandHandler("week", handle_week_cmd, filters=user_filter))
    application.add_handler(CommandHandler("export", handle_export_cmd, filters=user_filter))
    application.add_handler(CommandHandler("delete", handle_delete_cmd, filters=user_filter))
    application.add_handler(CommandHandler("settings", handle_settings_cmd, filters=user_filter))

    application.add_handler(
        MessageHandler(
            user_filter & filters.TEXT & ~filters.COMMAND,
            _handle_text_with_awaiting_check,
        )
    )
    application.add_handler(MessageHandler(user_filter & filters.VOICE, handle_voice))
    application.add_handler(CallbackQueryHandler(handle_callback_query))


if __name__ == "__main__":
    main()
