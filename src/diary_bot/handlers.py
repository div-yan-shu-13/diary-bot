"""Telegram command and message handlers for the Diary Bot.

Each handler is an async function that routes incoming Telegram updates
to the appropriate service layer. Services are accessed via bot_data
through the HandlerContext dataclass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from diary_bot.delete_service import DeleteService
from diary_bot.diary_service import DiaryService, GenerationStatus
from diary_bot.export_service import ExportService
from diary_bot.input_service import InputService
from diary_bot.models import Err, Ok, Tone
from diary_bot.repository import Repository
from diary_bot.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


@dataclass
class HandlerContext:
    """Holds references to all services needed by handlers.

    Stored in context.bot_data["handler_ctx"] so handlers can
    access services without global state.
    """

    input_service: InputService
    diary_service: DiaryService
    export_service: ExportService
    delete_service: DeleteService
    scheduler_service: SchedulerService
    repository: Repository


def _get_ctx(context: ContextTypes.DEFAULT_TYPE) -> HandlerContext:
    """Retrieve the HandlerContext from bot_data."""
    return context.bot_data["handler_ctx"]  # type: ignore[index]


# --- /start and /help ---


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the user starts the bot."""
    welcome = (
        "Welcome to your personal Diary Bot! 📔\n\n"
        "Send me text messages or voice notes (up to 60s) throughout the day, "
        "and I'll help you create a polished diary entry.\n\n"
        "Use /help to see all available commands."
    )
    await update.message.reply_text(welcome)  # type: ignore[union-attr]


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help text listing all available commands."""
    help_text = (
        "📖 *Available Commands*\n\n"
        "/diary — Generate today's diary entry\n"
        "/tone — View or set writing tone (poetic, casual, reflective)\n"
        "/week — Generate a weekly summary\n"
        "/export — Export all entries as JSON\n"
        "/delete — Delete entries\n"
        "/settings — View current settings\n"
        "/help — Show this help message\n\n"
        "💬 *How to use:*\n"
        "Just send me text messages or voice notes (up to 60s) anytime during the day. "
        "When you're ready, use /diary to generate your entry."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")  # type: ignore[union-attr]


# --- Text and Voice message handlers ---


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages by storing them via InputService."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    text = message.text or ""
    result = await ctx.input_service.store_text(text, message.date)

    if isinstance(result, Ok):
        await message.reply_text(result.value)
    else:
        # Error: either whitespace rejection or storage failure
        error_msg = result.error.message
        await message.reply_text(error_msg)

    # Reset inactivity timer on any user input (Req 6.4)
    await ctx.scheduler_service.reset_inactivity_timer()


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages by transcribing and storing them."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None or message.voice is None:
        return

    voice = message.voice
    duration = voice.duration

    # Download the voice file from Telegram
    voice_file = await voice.get_file()
    audio_buffer = BytesIO()
    await voice_file.download_to_memory(audio_buffer)
    audio_bytes = audio_buffer.getvalue()

    result = await ctx.input_service.store_voice(audio_bytes, duration, message.date)

    if isinstance(result, Ok):
        # Reply with the transcribed text so user can review
        await message.reply_text(f"🎤 Transcribed: {result.value}")
    else:
        await message.reply_text(result.error.message)

    # Reset inactivity timer on any user input (Req 6.4)
    await ctx.scheduler_service.reset_inactivity_timer()


# --- Command handlers ---


async def handle_diary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /diary command to initiate diary generation."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    state = await ctx.diary_service.initiate_generation(message.date)

    if state.status == GenerationStatus.NO_INPUTS:
        await message.reply_text("No inputs for today. Send me some messages first!")
        return

    # READY: ask for special instructions
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data="diary:special_yes"),
            InlineKeyboardButton("No, generate now", callback_data="diary:special_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Store entry_date in user_data for the callback
    if context.user_data is not None:
        context.user_data["diary_entry_date"] = state.entry_date.isoformat()

    await message.reply_text(
        "Ready to generate your diary entry. Any special instructions?",
        reply_markup=reply_markup,
    )


async def handle_tone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tone command — show current tone with inline buttons to change it."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    current_tone = await ctx.diary_service.get_tone()

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✓ ' if current_tone.value == 'poetic' else ''}Poetic",
                callback_data="tone:poetic",
            ),
            InlineKeyboardButton(
                f"{'✓ ' if current_tone.value == 'casual' else ''}Casual",
                callback_data="tone:casual",
            ),
            InlineKeyboardButton(
                f"{'✓ ' if current_tone.value == 'reflective' else ''}Reflective",
                callback_data="tone:reflective",
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        f"Current tone: *{current_tone.value}*\n\nTap to change:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def handle_week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /week command to generate a weekly summary."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    result = await ctx.diary_service.generate_weekly_summary()

    if isinstance(result, Ok):
        await message.reply_text(result.value)
    else:
        if result.error.code == "insufficient_data":
            await message.reply_text("Not enough data for weekly summary. Keep journaling!")
        else:
            await message.reply_text("Could not generate summary, try again later.")


async def handle_export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export command to export all entries as JSON."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    result = await ctx.export_service.export_all()

    if isinstance(result, Ok):
        document = BytesIO(result.value)
        document.name = "diary_export.json"
        await message.reply_document(document=document, filename="diary_export.json")
    else:
        await message.reply_text("No entries available to export.")


async def handle_delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command to present deletion options."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    reply_markup = await ctx.delete_service.initiate_delete()
    await message.reply_text("What would you like to delete?", reply_markup=reply_markup)


async def handle_settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command to display current configuration."""
    ctx = _get_ctx(context)
    message = update.message
    if message is None:
        return

    settings = await ctx.repository.get_settings()

    inactivity_str = (
        f"{settings.inactivity_threshold_hours}h"
        if settings.inactivity_threshold_hours is not None
        else "disabled"
    )
    memory_str = settings.memory_callback_time or "disabled"
    mood_times_str = ", ".join(settings.mood_check_in_times)

    text = (
        "⚙️ *Current Settings*\n\n"
        f"• Tone: {settings.tone.value}\n"
        f"• Timezone: {settings.timezone}\n"
        f"• Mood check-ins: {mood_times_str}\n"
        f"• Inactivity reminder: {inactivity_str}\n"
        f"• Memory callback: {memory_str}"
    )
    await message.reply_text(text, parse_mode="Markdown")


# --- Callback query handler ---


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline button presses to the appropriate service."""
    ctx = _get_ctx(context)
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = query.data or ""

    if data.startswith("diary:"):
        await _handle_diary_callback(ctx, update, context, data)
    elif data.startswith("delete:") or data.startswith("confirm_delete:") or data == "cancel_delete":
        await _handle_delete_callback(ctx, update, context, data)
    else:
        logger.warning("Unhandled callback data: %s", data)


async def _handle_diary_callback(
    ctx: HandlerContext,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle diary-related inline button callbacks."""
    query = update.callback_query
    if query is None or query.message is None:
        return

    if data == "diary:special_no":
        # Generate without special instructions
        entry_date_str = (context.user_data or {}).get("diary_entry_date")
        if entry_date_str is None:
            await query.message.reply_text("Something went wrong. Please try /diary again.")
            return

        from datetime import date

        entry_date = date.fromisoformat(entry_date_str)
        tone = await ctx.diary_service.get_tone()
        result = await ctx.diary_service.generate_entry(entry_date, None, tone)

        if isinstance(result, Ok):
            await query.message.reply_text(result.value)
        else:
            await query.message.reply_text(
                "Could not generate your diary entry. Please try again later."
            )

    elif data == "diary:special_yes":
        # Ask user to type special instructions
        if context.user_data is not None:
            context.user_data["awaiting_special_instructions"] = True
        await query.message.reply_text(
            "Please type your special instructions for today's entry:"
        )


async def _handle_delete_callback(
    ctx: HandlerContext,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle delete-related inline button callbacks."""
    query = update.callback_query
    if query is None or query.message is None:
        return

    if data == "cancel_delete":
        await query.message.reply_text("Deletion cancelled. No data was deleted.")
        return

    if data.startswith("confirm_delete:"):
        # Execute the confirmed deletion
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.message.reply_text("Invalid delete confirmation.")
            return
        delete_type = parts[1]
        target = parts[2]

        result = await ctx.delete_service.confirm_delete(delete_type, target)
        if isinstance(result, Ok):
            await query.message.reply_text(f"✓ {result.value}")
        else:
            await query.message.reply_text(result.error.message)
        return

    if data.startswith("delete:"):
        # Show confirmation with the delete type
        delete_type = data.split(":", 1)[1]

        if delete_type == "all":
            # Show immediate confirmation for "delete all"
            confirm_keyboard = ctx.delete_service.get_confirmation_keyboard("all", "")
            await query.message.reply_text(
                "⚠️ This will permanently delete ALL your data. Are you sure?",
                reply_markup=confirm_keyboard,
            )
        elif delete_type == "by_date":
            # Ask user for date
            if context.user_data is not None:
                context.user_data["awaiting_delete_date"] = True
                context.user_data["delete_type"] = "by_date"
            await query.message.reply_text(
                "Please enter the date to delete (YYYY-MM-DD format):"
            )
        elif delete_type == "date_range":
            # Ask user for start date
            if context.user_data is not None:
                context.user_data["awaiting_delete_range"] = True
                context.user_data["delete_type"] = "date_range"
            await query.message.reply_text(
                "Please enter the date range to delete (format: YYYY-MM-DD to YYYY-MM-DD):"
            )
