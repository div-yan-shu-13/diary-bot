"""Callback query and awaiting-text handlers for the Diary Bot.

Routes inline keyboard button presses to the appropriate service based
on callback_data prefixes, and handles follow-up text messages when the
bot is awaiting user input (special instructions, delete date, etc.).
"""

from __future__ import annotations

import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from diary_bot.models import Err, Ok

logger = logging.getLogger(__name__)


def _get_ctx(context: ContextTypes.DEFAULT_TYPE):
    """Retrieve the HandlerContext from bot_data."""
    return context.bot_data["handler_ctx"]


# --- Main callback query handler ---


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline button presses based on callback_data prefix.

    Handles:
    - diary:* — diary special instructions flow
    - delete:* — delete option selection
    - confirm_delete:* — confirmed deletion execution
    - cancel_delete — abort deletion
    - tone:* — tone selection via inline buttons
    """
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = query.data or ""

    if data.startswith("diary:"):
        await _handle_diary_callback(update, context, data)
    elif data.startswith("delete:"):
        await _handle_delete_callback(update, context, data)
    elif data.startswith("confirm_delete:"):
        await _handle_confirm_delete(update, context, data)
    elif data == "cancel_delete":
        await _handle_cancel_delete(update, context)
    elif data.startswith("tone:"):
        await _handle_tone_callback(update, context, data)
    else:
        logger.warning("Unhandled callback data: %s", data)


# --- Diary callbacks ---


async def _handle_diary_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle diary-related inline button callbacks.

    - diary:no_instructions — generate diary with no special instructions
    - diary:with_instructions — prompt user to send instructions as text
    """
    query = update.callback_query
    if query is None or query.message is None:
        return

    ctx = _get_ctx(context)

    if data == "diary:no_instructions":
        entry_date_str = (context.user_data or {}).get("diary_entry_date")
        if entry_date_str is None:
            await query.message.reply_text("Something went wrong. Please try /diary again.")
            return

        entry_date = date.fromisoformat(entry_date_str)
        tone = await ctx.diary_service.get_tone()
        result = await ctx.diary_service.generate_entry(entry_date, None, tone)

        if isinstance(result, Ok):
            await query.message.reply_text(result.value)
        else:
            await query.message.reply_text(
                "Could not generate your diary entry. Please try again later."
            )

    elif data == "diary:with_instructions":
        if context.user_data is not None:
            context.user_data["awaiting_instructions"] = True
        await query.message.reply_text(
            "Please send your special instructions as a text message."
        )

    # Also support the alternative callback data names from handlers.py
    elif data == "diary:special_no":
        # Alias for no_instructions
        entry_date_str = (context.user_data or {}).get("diary_entry_date")
        if entry_date_str is None:
            await query.message.reply_text("Something went wrong. Please try /diary again.")
            return

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
        # Alias for with_instructions
        if context.user_data is not None:
            context.user_data["awaiting_instructions"] = True
        await query.message.reply_text(
            "Please send your special instructions as a text message."
        )


# --- Delete callbacks ---


async def _handle_delete_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle delete option selection from inline keyboard.

    - delete:by_date — ask user to specify the date
    - delete:date_range — ask user to specify the range
    - delete:all — show confirmation keyboard immediately
    """
    query = update.callback_query
    if query is None or query.message is None:
        return

    ctx = _get_ctx(context)
    delete_type = data.split(":", 1)[1]

    if delete_type == "by_date":
        if context.user_data is not None:
            context.user_data["awaiting_delete_date"] = True
            context.user_data["delete_type"] = "by_date"
        await query.message.reply_text(
            "Please send the date (YYYY-MM-DD) for deletion."
        )

    elif delete_type == "date_range":
        if context.user_data is not None:
            context.user_data["awaiting_delete_range"] = True
            context.user_data["delete_type"] = "date_range"
        await query.message.reply_text(
            "Please send the date range as START:END (e.g., 2024-01-01:2024-01-31)"
        )

    elif delete_type == "all":
        confirm_keyboard = ctx.delete_service.get_confirmation_keyboard("all", "")
        await query.message.reply_text(
            "⚠️ This will delete ALL your data. Are you sure?",
            reply_markup=confirm_keyboard,
        )


# --- Confirm/Cancel delete callbacks ---


async def _handle_confirm_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Execute confirmed deletion.

    callback_data format: confirm_delete:{type}:{target}
    """
    query = update.callback_query
    if query is None or query.message is None:
        return

    ctx = _get_ctx(context)

    # Parse: "confirm_delete:{delete_type}:{target}"
    parts = data.split(":", 2)
    if len(parts) < 3:
        await query.message.edit_text("Invalid delete confirmation.")
        return

    delete_type = parts[1]
    target = parts[2]

    result = await ctx.delete_service.confirm_delete(delete_type, target)
    if isinstance(result, Ok):
        await query.message.edit_text(f"✓ {result.value}")
    else:
        await query.message.edit_text(result.error.message)


async def _handle_cancel_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Abort deletion and inform the user."""
    query = update.callback_query
    if query is None or query.message is None:
        return

    await query.message.edit_text("Deletion cancelled. No data was deleted.")


# --- Tone selection callback ---


async def _handle_tone_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle tone selection via inline buttons.

    callback_data format: tone:{value}
    """
    query = update.callback_query
    if query is None or query.message is None:
        return

    ctx = _get_ctx(context)
    tone_value = data.split(":", 1)[1]

    result = await ctx.diary_service.set_tone(tone_value)
    if isinstance(result, Ok):
        await query.message.edit_text(f"✓ Tone set to *{result.value.value}*", parse_mode="Markdown")
    else:
        await query.message.edit_text(result.error.message)


# --- Awaiting text handler ---


async def handle_awaiting_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages when the bot is awaiting follow-up input.

    Checks context.user_data for awaiting flags:
    - awaiting_instructions: user is providing special instructions for diary generation
    - awaiting_delete_date: user is providing a date for deletion
    - awaiting_delete_range: user is providing a date range for deletion

    Returns:
        None. If no awaiting state is active, this handler does nothing
        (returns early so the normal text handler can process the message).
    """
    user_data = context.user_data
    if user_data is None:
        return

    message = update.message
    if message is None or not message.text:
        return

    text = message.text.strip()
    ctx = _get_ctx(context)

    # --- Special instructions for diary generation ---
    if user_data.get("awaiting_instructions"):
        user_data["awaiting_instructions"] = False

        entry_date_str = user_data.get("diary_entry_date")
        if entry_date_str is None:
            await message.reply_text("Something went wrong. Please try /diary again.")
            return

        entry_date = date.fromisoformat(entry_date_str)
        tone = await ctx.diary_service.get_tone()
        result = await ctx.diary_service.generate_entry(entry_date, text, tone)

        if isinstance(result, Ok):
            await message.reply_text(result.value)
        else:
            await message.reply_text(
                "Could not generate your diary entry. Please try again later."
            )
        return

    # Also support the older flag name from handlers.py
    if user_data.get("awaiting_special_instructions"):
        user_data["awaiting_special_instructions"] = False

        entry_date_str = user_data.get("diary_entry_date")
        if entry_date_str is None:
            await message.reply_text("Something went wrong. Please try /diary again.")
            return

        entry_date = date.fromisoformat(entry_date_str)
        tone = await ctx.diary_service.get_tone()
        result = await ctx.diary_service.generate_entry(entry_date, text, tone)

        if isinstance(result, Ok):
            await message.reply_text(result.value)
        else:
            await message.reply_text(
                "Could not generate your diary entry. Please try again later."
            )
        return

    # --- Delete by date ---
    if user_data.get("awaiting_delete_date"):
        user_data["awaiting_delete_date"] = False

        try:
            date.fromisoformat(text)
        except ValueError:
            await message.reply_text(
                "Invalid date format. Please use YYYY-MM-DD (e.g., 2024-01-15)."
            )
            return

        confirm_keyboard = ctx.delete_service.get_confirmation_keyboard("by_date", text)
        await message.reply_text(
            f"Delete all entries for {text}?",
            reply_markup=confirm_keyboard,
        )
        return

    # --- Delete by date range ---
    if user_data.get("awaiting_delete_range"):
        user_data["awaiting_delete_range"] = False

        # Expect format: START:END or START to END
        range_text = text.replace(" to ", ":").replace(" ", "")
        parts = range_text.split(":")
        if len(parts) != 2:
            await message.reply_text(
                "Invalid format. Please use START:END (e.g., 2024-01-01:2024-01-31)."
            )
            return

        start_str, end_str = parts[0], parts[1]
        try:
            date.fromisoformat(start_str)
            date.fromisoformat(end_str)
        except ValueError:
            await message.reply_text(
                "Invalid date format. Please use YYYY-MM-DD:YYYY-MM-DD."
            )
            return

        target = f"{start_str}:{end_str}"
        confirm_keyboard = ctx.delete_service.get_confirmation_keyboard("date_range", target)
        await message.reply_text(
            f"Delete all entries from {start_str} to {end_str}?",
            reply_markup=confirm_keyboard,
        )
        return
