"""FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from openswe_platform.common.config import get_settings
from openswe_platform.common.db import get_session_factory


@dataclass
class AuthContext:
    org_id: uuid.UUID
    user_id: uuid.UUID


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_auth(
    request: Request,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AuthContext:
    settings = get_settings()
    # Dev/auth-disabled: default identities. Production would validate JWT/session.
    org = x_org_id or settings.default_org_id
    user = x_user_id or settings.default_user_id
    return AuthContext(org_id=uuid.UUID(org), user_id=uuid.UUID(user))
