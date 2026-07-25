"""Tests for the dashboard compatibility layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from openswe_platform.api.deps import AuthContext
from openswe_platform.api.routes_dashboard import (
    get_me,
    get_options,
    get_profile,
    get_sidebar_threads,
    task_to_agent_thread,
)
from openswe_platform.common.config import get_settings
from openswe_platform.common.models import Task


@pytest.mark.asyncio
async def test_get_me():
    auth = AuthContext(org_id=uuid.uuid4(), user_id=uuid.uuid4())
    res = await get_me(auth)
    assert res["login"] == "moule3053"
    assert res["is_admin"] is True


@pytest.mark.asyncio
async def test_get_options():
    res = await get_options()
    assert len(res["models"]) > 0
    assert res["default_agent_model"] == get_settings().default_model


@pytest.mark.asyncio
async def test_get_profile():
    auth = AuthContext(org_id=uuid.uuid4(), user_id=uuid.uuid4())
    res = await get_profile(auth)
    assert res["login"] == "moule3053"
    assert res["create_prs"] is True


def test_task_to_agent_thread():
    task = Task(
        task_id=uuid.uuid4(),
        title="Test Task",
        repo="acme/test-repo",
        base_ref="main",
        model="gpt-4o",
        status="queued",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    thread = task_to_agent_thread(task)
    assert thread["id"] == str(task.task_id)
    assert thread["title"] == "Test Task"
    assert thread["repo"] == "test-repo"
    assert thread["repoFullName"] == "acme/test-repo"
    assert thread["status"] == "running"
    assert thread["resolved"] is False


@pytest.mark.asyncio
async def test_get_sidebar_threads():
    db = AsyncMock()
    auth = AuthContext(org_id=uuid.uuid4(), user_id=uuid.uuid4())

    task1 = Task(
        task_id=uuid.uuid4(),
        title="Active Task",
        repo="acme/test-repo",
        base_ref="main",
        model="gpt-4o",
        status="queued",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    task2 = Task(
        task_id=uuid.uuid4(),
        title="Resolved Task",
        repo="acme/test-repo",
        base_ref="main",
        model="gpt-4o",
        status="succeeded",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [task1, task2]
    db.execute.return_value = mock_result

    res = await get_sidebar_threads(db, auth)
    assert "active" in res
    assert "resolved" in res
    assert len(res["active"]["items"]) == 1
    assert len(res["resolved"]["items"]) == 1
    assert res["active"]["items"][0]["title"] == "Active Task"
    assert res["resolved"]["items"][0]["title"] == "Resolved Task"
