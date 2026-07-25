"""FastAPI dashboard compatibility router."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openswe_platform.api.deps import AuthContext, get_auth, get_db
from openswe_platform.api.routes_tasks import add_message, cancel_task, decide_approval
from openswe_platform.common.config import get_settings
from openswe_platform.common.enums import ApprovalStatus
from openswe_platform.common.models import Approval, Message, RunEvent, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/api", tags=["dashboard"])


async def _get_task_by_id_or_thread_id(
    db: AsyncSession, org_id: uuid.UUID, thread_id: str
) -> Task | None:
    result = await db.execute(
        select(Task).where(Task.org_id == org_id, Task.thread_id == thread_id)
    )
    task = result.scalars().first()
    if task:
        return task

    try:
        task_id = uuid.UUID(thread_id)
        task = await db.get(Task, task_id)
        if task and task.org_id == org_id:
            return task
    except ValueError:
        pass

    return None


class DashboardMessageRequest(BaseModel):
    content: str


@router.get("/me")
async def get_me(auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    return {
        "login": "moule3053",
        "email": "14330171+moule3053@users.noreply.github.com",
        "avatar_url": "https://github.com/moule3053.png",
        "is_admin": True,
        "slack_oauth_enabled": False,
    }


@router.get("/my-mapping")
async def get_my_mapping() -> dict[str, Any]:
    return {"login": "moule3053", "github_login": "moule3053"}


@router.get("/repos")
async def get_repos() -> dict[str, Any]:
    return {"repos": ["moule3053/open-swe"]}


@router.get("/options")
async def get_options() -> dict[str, Any]:
    settings = get_settings()
    default_model = settings.default_model or "google:gemini-3.5-flash"
    return {
        "models": [
            {
                "id": "google:gemini-3.5-flash",
                "label": "Gemini 3.5 Flash",
                "efforts": ["minimal", "low", "medium", "high"],
                "default_effort": "medium",
                "supports_images": True,
            },
            {
                "id": "google_genai:gemini-3.5-flash",
                "label": "Gemini 3.5 Flash (GenAI)",
                "efforts": ["minimal", "low", "medium", "high"],
                "default_effort": "medium",
                "supports_images": True,
            },
            {
                "id": "openai:gpt-4o",
                "label": "GPT-4o",
                "efforts": [],
                "default_effort": "",
                "supports_images": True,
            },
            {
                "id": "openai:gpt-4o-mini",
                "label": "GPT-4o Mini",
                "efforts": [],
                "default_effort": "",
                "supports_images": True,
            },
            {
                "id": "anthropic:claude-3-5-sonnet",
                "label": "Claude 3.5 Sonnet",
                "efforts": [],
                "default_effort": "",
                "supports_images": True,
            },
            {
                "id": "anthropic:claude-sonnet-5",
                "label": "Claude Sonnet 5",
                "efforts": ["low", "medium", "high", "xhigh", "max"],
                "default_effort": "high",
                "supports_images": True,
            },
            {
                "id": "openai:o1",
                "label": "o1",
                "efforts": ["low", "medium", "high"],
                "default_effort": "medium",
                "supports_images": False,
            },
        ],
        "default_agent_model": default_model,
        "default_agent_reasoning_effort": "medium",
        "default_agent_subagent_model": default_model,
        "default_agent_subagent_reasoning_effort": "medium",
    }


@router.get("/profile")
async def get_profile(auth: AuthContext = Depends(get_auth)) -> dict[str, Any]:
    return {
        "login": "moule3053",
        "email": "14330171+moule3053@users.noreply.github.com",
        "default_model": "gpt-4o",
        "reasoning_effort": "medium",
        "default_subagent_model": "gpt-4o",
        "subagent_reasoning_effort": "medium",
        "default_repo": None,
        "base_branch": "main",
        "branch_prefix": "open-swe/",
        "auto_fix_ci": False,
        "create_prs": True,
    }


def task_to_agent_thread(task: Task, db_messages: list[Message] | None = None) -> dict[str, Any]:
    messages = []
    if db_messages:
        for m in db_messages:
            author_role = (
                "user"
                if m.role == "user"
                else "agent"
                if m.role in {"assistant", "agent"}
                else "system"
            )
            messages.append(
                {
                    "id": str(m.message_id),
                    "author": {"name": author_role},
                    "timestamp": m.created_at.isoformat(),
                    "chunks": [{"kind": "text", "text": m.content}],
                }
            )

    is_resolved = task.status in {"succeeded", "failed", "cancelled"}
    return {
        "id": str(task.task_id),
        "title": task.title or f"Task on {task.repo or 'repository'}",
        "repo": task.repo.split("/")[-1] if task.repo else "",
        "repoFullName": task.repo or "",
        "branch": task.base_ref or "main",
        "model": task.model,
        "status": "running"
        if task.status in {"queued", "running"}
        else "paused"
        if task.status == "parked"
        else "completed"
        if task.status == "succeeded"
        else "failed",
        "viewed": True,
        "resolved": is_resolved,
        "createdAt": int(task.created_at.replace(tzinfo=UTC).timestamp() * 1000),
        "updatedAt": int(task.updated_at.replace(tzinfo=UTC).timestamp() * 1000),
        "messages": messages,
    }


@router.get("/threads/sidebar")
async def get_sidebar_threads(
    db: AsyncSession = Depends(get_db), auth: AuthContext = Depends(get_auth)
) -> dict[str, Any]:
    result = await db.execute(
        select(Task).where(Task.org_id == auth.org_id).order_by(Task.updated_at.desc())
    )
    tasks = list(result.scalars().all())

    active_items = []
    resolved_items = []
    for t in tasks:
        thread = task_to_agent_thread(t)
        if t.status in {"succeeded", "failed", "cancelled"}:
            resolved_items.append(thread)
        else:
            active_items.append(thread)

    return {
        "active": {"items": active_items, "limit": 100, "hasMore": False},
        "resolved": {"items": resolved_items, "limit": 100, "hasMore": False},
    }


@router.get("/threads/page")
async def get_threads_page(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    result = await db.execute(
        select(Task)
        .where(Task.org_id == auth.org_id)
        .order_by(Task.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    tasks = list(result.scalars().all())
    items = [task_to_agent_thread(t) for t in tasks]
    return {
        "items": items,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "hasMore": False,
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    msg_result = await db.execute(
        select(Message).where(Message.task_id == task.task_id).order_by(Message.seq)
    )
    db_messages = list(msg_result.scalars().all())
    return task_to_agent_thread(task, db_messages)


@router.get("/threads/{thread_id}/state")
async def get_thread_state(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)
    if task is None:
        return {"values": {"messages": []}, "next": []}

    msg_result = await db.execute(
        select(Message).where(Message.task_id == task.task_id).order_by(Message.seq)
    )
    db_messages = list(msg_result.scalars().all())

    messages = []
    for m in db_messages:
        messages.append(
            {
                "type": m.role
                if m.role in {"human", "ai", "system"}
                else "human"
                if m.role == "user"
                else "ai",
                "id": str(m.message_id),
                "content": m.content,
            }
        )

    return {
        "values": {"messages": messages},
        "next": [] if task.status in {"succeeded", "failed", "cancelled"} else ["agent"],
    }


@router.post("/threads/{thread_id}/history")
async def post_thread_history(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[dict[str, Any]]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)
    if task is None:
        return []

    msg_result = await db.execute(
        select(Message).where(Message.task_id == task.task_id).order_by(Message.seq)
    )
    db_messages = list(msg_result.scalars().all())

    messages = []
    for m in db_messages:
        messages.append(
            {
                "type": m.role
                if m.role in {"human", "ai", "system"}
                else "human"
                if m.role == "user"
                else "ai",
                "id": str(m.message_id),
                "content": m.content,
            }
        )

    return [{"values": {"messages": messages}, "checkpoint": {}}]


@router.post("/threads/{thread_id}/commands")
async def post_thread_commands(
    thread_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}

    method = body.get("method")
    params = body.get("params", {})
    run_input = params.get("input", {}) or {}

    content = ""
    messages = run_input.get("messages", [])
    if messages and isinstance(messages, list):
        content_raw = messages[-1].get("content") or ""
        if isinstance(content_raw, list):
            text_parts = []
            for block in content_raw:
                if isinstance(block, dict):
                    text_parts.append(block.get("text") or "")
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "".join(text_parts)
        else:
            content = str(content_raw)

    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    settings = get_settings()
    if task is None:
        from openswe_platform.api.routes_tasks import create_task

        task = await create_task(
            db,
            org_id=auth.org_id,
            user_id=auth.user_id,
            title=content[:100] if content else "New Chat Run",
            prompt=content,
            repo="moule3053/open-swe",
            base_ref="main",
            source="web_ui",
            source_ref=None,
            thread_id=thread_id,
            agent_type="coding",
            model=settings.default_model,
            sandbox_provider=settings.default_sandbox_provider,
            mcp_server_ids=[],
            mcp_mode="inherit",
            metadata={},
            platform_default_model=settings.default_model,
        )
        await db.commit()

    if content and method in {"run.start", "input.respond"}:
        await add_message(db, task_id=task.task_id, content=content, kind="user_guidance")
        await db.commit()

    return {
        "id": str(task.task_id),
        "thread_id": thread_id,
        "status": "running",
    }


@router.post("/threads/{thread_id}/messages")
async def post_thread_message(
    thread_id: str,
    body: DashboardMessageRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    if task is None or task.org_id != auth.org_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    await add_message(db, task_id=task.task_id, content=body.content, kind="user_guidance")
    await db.commit()

    msg_result = await db.execute(
        select(Message).where(Message.task_id == task.task_id).order_by(Message.seq)
    )
    db_messages = list(msg_result.scalars().all())
    return task_to_agent_thread(task, db_messages)


@router.post("/threads/{thread_id}/cancel")
async def post_cancel_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    if task is None or task.org_id != auth.org_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    await cancel_task(db, task_id=task.task_id, reason="user_requested")
    await db.commit()

    msg_result = await db.execute(
        select(Message).where(Message.task_id == task.task_id).order_by(Message.seq)
    )
    db_messages = list(msg_result.scalars().all())
    return task_to_agent_thread(task, db_messages)


@router.get("/threads/{thread_id}/stream")
async def stream_thread(
    thread_id: str,
    auth: AuthContext = Depends(get_auth),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    try:
        task_uuid = uuid.UUID(thread_id)
    except ValueError:
        task_uuid = None

    async def gen():
        try:
            last_seq = int(last_event_id or 0)
        except ValueError:
            last_seq = 0
        factory = __import__(
            "openswe_platform.common.db", fromlist=["get_session_factory"]
        ).get_session_factory()

        real_task_id = task_uuid
        while True:
            async with factory() as session:
                if real_task_id is None:
                    result = await session.execute(
                        select(Task).where(Task.org_id == auth.org_id, Task.thread_id == thread_id)
                    )
                    task = result.scalars().first()
                    if task:
                        real_task_id = task.task_id
                else:
                    task = await session.get(Task, real_task_id)

                if task is None or task.org_id != auth.org_id:
                    yield f"event: error\ndata: {json.dumps({'error': 'not_found'})}\n\n"
                    return

                result = await session.execute(
                    select(RunEvent)
                    .where(RunEvent.task_id == real_task_id, RunEvent.seq > last_seq)
                    .order_by(RunEvent.seq)
                    .limit(50)
                )
                events = list(result.scalars().all())
                for event in events:
                    last_seq = event.seq
                    data = {
                        "event_id": str(event.event_id),
                        "seq": event.seq,
                        "event_type": event.event_type,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    }
                    yield f"id: {event.seq}\nevent: run_event\ndata: {json.dumps(data)}\n\n"

                yield f"event: task_status\ndata: {json.dumps({'status': task.status})}\n\n"
                if task.status in {"succeeded", "failed", "cancelled"}:
                    return
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/workflow-approval/{thread_id}")
async def list_thread_workflow_approvals(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    if task is None or task.org_id != auth.org_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Approval).where(
            Approval.task_id == task.task_id, Approval.status == ApprovalStatus.PENDING.value
        )
    )
    approvals = list(result.scalars().all())

    return {
        "approvals": [
            {
                "approval_id": str(a.approval_id),
                "kind": a.kind,
                "status": a.status,
                "payload": a.payload,
                "created_at": a.created_at.isoformat(),
            }
            for a in approvals
        ]
    }


@router.post("/workflow-approval/{thread_id}/{fingerprint}/approve")
async def approve_workflow_push_fingerprint(
    thread_id: str,
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    if task is None or task.org_id != auth.org_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Approval).where(
            Approval.task_id == task.task_id, Approval.status == ApprovalStatus.PENDING.value
        )
    )
    approvals = list(result.scalars().all())
    target_approval = None
    for a in approvals:
        if a.payload.get("fingerprint") == fingerprint or str(a.approval_id) == fingerprint:
            target_approval = a
            break

    if target_approval is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Pending approval not found")

    await decide_approval(db, approval_id=target_approval.approval_id, decision="approved")
    await db.commit()
    return {"status": "approved", "fingerprint": fingerprint}


@router.post("/workflow-approval/{thread_id}/{fingerprint}/reject")
async def reject_workflow_push_fingerprint(
    thread_id: str,
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    task = await _get_task_by_id_or_thread_id(db, auth.org_id, thread_id)

    if task is None or task.org_id != auth.org_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Approval).where(
            Approval.task_id == task.task_id, Approval.status == ApprovalStatus.PENDING.value
        )
    )
    approvals = list(result.scalars().all())
    target_approval = None
    for a in approvals:
        if a.payload.get("fingerprint") == fingerprint or str(a.approval_id) == fingerprint:
            target_approval = a
            break

    if target_approval is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Pending approval not found")

    await decide_approval(db, approval_id=target_approval.approval_id, decision="rejected")
    await db.commit()
    return {"status": "rejected", "fingerprint": fingerprint}


@router.get("/threads/{thread_id}/pr-diff")
async def get_thread_pr_diff(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    return {
        "prNumber": 1,
        "baseSha": "base",
        "headSha": "head",
        "truncated": False,
        "files": [],
    }
