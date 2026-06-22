"""Unit tests for the AuthMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from diary_bot.auth import AuthMiddleware


@pytest.fixture
def auth_middleware():
    """Create an AuthMiddleware instance with a known authorized user ID."""
    return AuthMiddleware(authorized_user_id=123456789)


@pytest.mark.asyncio
async def test_check_authorized_user(auth_middleware):
    """Authorized user ID should return True."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789

    result = await auth_middleware.check(update)
    assert result is True


@pytest.mark.asyncio
async def test_check_unauthorized_user(auth_middleware):
    """Non-matching user ID should return False (silent discard)."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 987654321

    result = await auth_middleware.check(update)
    assert result is False


@pytest.mark.asyncio
async def test_check_no_effective_user(auth_middleware):
    """Update with no effective user should return False."""
    update = MagicMock()
    update.effective_user = None

    result = await auth_middleware.check(update)
    assert result is False


@pytest.mark.asyncio
async def test_check_different_unauthorized_ids(auth_middleware):
    """Multiple different unauthorized IDs should all return False."""
    for user_id in [0, 1, 999999999, -1, 123456790]:
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = user_id

        result = await auth_middleware.check(update)
        assert result is False, f"User ID {user_id} should not be authorized"
