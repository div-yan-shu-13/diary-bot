"""Unit tests for the configuration module."""

import os
import pytest

from diary_bot.config import load_config


class TestLoadConfig:
    """Tests for load_config function."""

    def test_raises_when_authorized_user_id_not_set(self, monkeypatch):
        """Startup fails if AUTHORIZED_USER_ID is not set."""
        monkeypatch.delenv("AUTHORIZED_USER_ID", raising=False)
        with pytest.raises(RuntimeError, match="AUTHORIZED_USER_ID"):
            load_config()

    def test_raises_when_authorized_user_id_empty(self, monkeypatch):
        """Startup fails if AUTHORIZED_USER_ID is empty string."""
        monkeypatch.setenv("AUTHORIZED_USER_ID", "")
        with pytest.raises(RuntimeError, match="AUTHORIZED_USER_ID"):
            load_config()

    def test_raises_when_authorized_user_id_whitespace_only(self, monkeypatch):
        """Startup fails if AUTHORIZED_USER_ID is only whitespace."""
        monkeypatch.setenv("AUTHORIZED_USER_ID", "   ")
        with pytest.raises(RuntimeError, match="AUTHORIZED_USER_ID"):
            load_config()

    def test_raises_when_authorized_user_id_not_integer(self, monkeypatch):
        """Startup fails if AUTHORIZED_USER_ID is not a valid integer."""
        monkeypatch.setenv("AUTHORIZED_USER_ID", "not_a_number")
        with pytest.raises(RuntimeError, match="valid integer"):
            load_config()

    def test_loads_config_with_valid_authorized_user_id(self, monkeypatch):
        """Config loads successfully with a valid AUTHORIZED_USER_ID."""
        monkeypatch.setenv("AUTHORIZED_USER_ID", "123456789")
        monkeypatch.setenv("BOT_TOKEN", "test-token")
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
        monkeypatch.setenv("TIMEZONE", "Asia/Kolkata")

        config = load_config()

        assert config.authorized_user_id == 123456789
        assert config.bot_token == "test-token"
        assert config.groq_api_key == "test-key"
        assert config.database_path == "/tmp/test.db"
        assert config.timezone == "Asia/Kolkata"

    def test_defaults_when_optional_vars_missing(self, monkeypatch):
        """Optional env vars use sensible defaults."""
        monkeypatch.setenv("AUTHORIZED_USER_ID", "999")
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        monkeypatch.delenv("TIMEZONE", raising=False)

        config = load_config()

        assert config.authorized_user_id == 999
        assert config.bot_token == ""
        assert config.groq_api_key == ""
        assert config.database_path == "diary_bot.db"
        assert config.timezone == "UTC"
