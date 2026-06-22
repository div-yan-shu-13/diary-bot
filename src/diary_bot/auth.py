"""Authorization middleware for the Telegram Diary Bot.

Filters incoming updates to accept only messages from the configured
AUTHORIZED_USER_ID. Non-matching user IDs are silently discarded.
"""

import logging

from telegram import Update

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Middleware that filters Telegram updates by user ID.

    Only updates from the authorized user are processed.
    All other updates are silently discarded without any response.
    """

    def __init__(self, authorized_user_id: int) -> None:
        """Initialize the auth middleware.

        Args:
            authorized_user_id: The Telegram user ID allowed to interact with the bot.
        """
        self.authorized_user_id = authorized_user_id

    async def check(self, update: Update) -> bool:
        """Check if the update is from the authorized user.

        Args:
            update: The incoming Telegram update.

        Returns:
            True if the update is from the authorized user, False otherwise.
            Returns False (discard) for updates without an effective user.
        """
        effective_user = update.effective_user

        if effective_user is None:
            logger.debug("Update discarded: no effective user present.")
            return False

        if effective_user.id != self.authorized_user_id:
            logger.debug(
                "Update discarded: user ID %d is not authorized.", effective_user.id
            )
            return False

        return True
