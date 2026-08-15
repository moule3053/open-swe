"""Tests for local development migration defaults."""

from unittest.mock import AsyncMock

import pytest

from alephat_platform.common.config import Settings
from alephat_platform.migrate import _sync_development_defaults


@pytest.mark.asyncio
async def test_sync_development_defaults_uses_compose_model_and_sandbox():
    connection = AsyncMock()
    settings = Settings(
        bootstrap_dev_defaults=True,
        default_org_id="00000000-0000-4000-8000-000000000001",
        default_model="google:gemini-3.5-flash",
        default_sandbox_provider="local",
    )

    await _sync_development_defaults(connection, settings)

    args = connection.execute.await_args.args
    assert args[2:] == ("google:gemini-3.5-flash", "local")


@pytest.mark.asyncio
async def test_sync_development_defaults_is_disabled_by_default():
    connection = AsyncMock()
    settings = Settings(bootstrap_dev_defaults=False)

    await _sync_development_defaults(connection, settings)

    connection.execute.assert_not_awaited()
