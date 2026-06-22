"""Configuration module that loads environment variables for the diary bot.

Raises RuntimeError at import/load time if AUTHORIZED_USER_ID is not set or empty.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    bot_token: str
    groq_api_key: str
    authorized_user_id: int
    database_path: str
    timezone: str


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config: The validated configuration object.

    Raises:
        RuntimeError: If AUTHORIZED_USER_ID is not set or empty.
    """
    authorized_user_id_raw = os.environ.get("AUTHORIZED_USER_ID", "").strip()

    if not authorized_user_id_raw:
        raise RuntimeError(
            "AUTHORIZED_USER_ID environment variable is not set or is empty. "
            "The bot cannot start without a configured authorized user."
        )

    try:
        authorized_user_id = int(authorized_user_id_raw)
    except ValueError:
        raise RuntimeError(
            f"AUTHORIZED_USER_ID must be a valid integer, got: '{authorized_user_id_raw}'"
        )

    return Config(
        bot_token=os.environ.get("BOT_TOKEN", ""),
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        authorized_user_id=authorized_user_id,
        database_path=os.environ.get("DATABASE_PATH", "diary_bot.db"),
        timezone=os.environ.get("TIMEZONE", "UTC"),
    )
