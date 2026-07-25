"""Health, sandbox catalog, settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openswe_platform.api.deps import AuthContext, get_auth, get_db
from openswe_platform.common.config import get_settings
from openswe_platform.common.enums import SandboxProvider
from openswe_platform.common.models import OrgSettings, UserSettings

router = APIRouter(tags=["meta"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
    return {"status": "ready"}


@router.get("/v1/sandbox-providers")
async def sandbox_providers(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    settings = get_settings()
    org = await db.get(OrgSettings, auth.org_id)
    enabled = (
        list(org.enabled_sandbox_providers)
        if org and org.enabled_sandbox_providers
        else [p.value for p in SandboxProvider]
    )
    default = org.default_sandbox_provider if org else settings.default_sandbox_provider
    items = []
    for p in SandboxProvider:
        items.append(
            {
                "id": p.value,
                "enabled": p.value in enabled,
                "default": p.value == default,
            }
        )
    return {"items": items, "default": default}


class MeSettingsPatch(BaseModel):
    preferred_model: str | None = None
    preferred_sandbox_provider: str | None = None
    default_mcp_server_ids: list[str] | None = None


@router.get("/v1/me/settings")
async def get_me_settings(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    row = await db.get(UserSettings, auth.user_id)
    if row is None:
        return {
            "preferred_model": None,
            "preferred_sandbox_provider": None,
            "default_mcp_server_ids": [],
        }
    return {
        "preferred_model": row.preferred_model,
        "preferred_sandbox_provider": row.preferred_sandbox_provider,
        "default_mcp_server_ids": [str(i) for i in (row.default_mcp_server_ids or [])],
    }


@router.patch("/v1/me/settings")
async def patch_me_settings(
    body: MeSettingsPatch,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    import uuid

    row = await db.get(UserSettings, auth.user_id)
    if row is None:
        row = UserSettings(user_id=auth.user_id)
        db.add(row)
    if body.preferred_model is not None:
        row.preferred_model = body.preferred_model
    if body.preferred_sandbox_provider is not None:
        row.preferred_sandbox_provider = body.preferred_sandbox_provider
    if body.default_mcp_server_ids is not None:
        row.default_mcp_server_ids = [uuid.UUID(i) for i in body.default_mcp_server_ids]
    await db.flush()
    return {
        "preferred_model": row.preferred_model,
        "preferred_sandbox_provider": row.preferred_sandbox_provider,
        "default_mcp_server_ids": [str(i) for i in (row.default_mcp_server_ids or [])],
    }


class OrgSettingsPatch(BaseModel):
    default_model: str | None = None
    default_sandbox_provider: str | None = None
    enabled_sandbox_providers: list[str] | None = None
    mcp_stdio_allowed: bool | None = None
    max_mcp_servers_per_run: int | None = None


@router.get("/v1/orgs/{org_id}/settings")
async def get_org_settings(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    if str(auth.org_id) != org_id:
        from openswe_platform.common.errors import ForbiddenError

        raise ForbiddenError()
    row = await db.get(OrgSettings, auth.org_id)
    if row is None:
        return {}
    return {
        "default_model": row.default_model,
        "default_sandbox_provider": row.default_sandbox_provider,
        "enabled_sandbox_providers": list(row.enabled_sandbox_providers or []),
        "mcp_stdio_allowed": row.mcp_stdio_allowed,
        "max_mcp_servers_per_run": row.max_mcp_servers_per_run,
    }


@router.patch("/v1/orgs/{org_id}/settings")
async def patch_org_settings(
    org_id: str,
    body: OrgSettingsPatch,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    if str(auth.org_id) != org_id:
        from openswe_platform.common.errors import ForbiddenError

        raise ForbiddenError()
    row = await db.get(OrgSettings, auth.org_id)
    if row is None:
        row = OrgSettings(org_id=auth.org_id)
        db.add(row)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    return {
        "default_model": row.default_model,
        "default_sandbox_provider": row.default_sandbox_provider,
        "enabled_sandbox_providers": list(row.enabled_sandbox_providers or []),
        "mcp_stdio_allowed": row.mcp_stdio_allowed,
        "max_mcp_servers_per_run": row.max_mcp_servers_per_run,
    }
