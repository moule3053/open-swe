"""API FastAPI application."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from openswe_platform.api.routes_dashboard import router as dashboard_router
from openswe_platform.api.routes_mcp import router as mcp_router
from openswe_platform.api.routes_meta import router as meta_router
from openswe_platform.api.routes_tasks import router as tasks_router
from openswe_platform.common.config import get_settings
from openswe_platform.common.db import dispose_engine, get_session_factory
from openswe_platform.common.errors import PlatformError
from openswe_platform.common.messaging import NatsBus
from openswe_platform.common.outbox import outbox_supervisor_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    stop = asyncio.Event()
    app.state.nats = None

    def _set_connection(bus: NatsBus | None) -> None:
        app.state.nats = bus

    publisher_task = asyncio.create_task(
        outbox_supervisor_loop(
            get_session_factory(),
            nats_url=settings.nats_url,
            interval=settings.outbox_poll_interval_seconds,
            stop_event=stop,
            on_connection=_set_connection,
        )
    )

    yield

    stop.set()
    publisher_task.cancel()
    try:
        await publisher_task
    except asyncio.CancelledError:
        pass
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Open SWE API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_settings().cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PlatformError)
    async def platform_error_handler(_request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict())

    app.include_router(meta_router)
    app.include_router(tasks_router)
    app.include_router(mcp_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
