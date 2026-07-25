import uuid

import pytest

from openswe_platform.common.enums import AgentType, McpMode, SandboxProvider
from openswe_platform.common.errors import PlatformError
from openswe_platform.common.resolution import (
    resolve_mcp_ids,
    resolve_model,
    resolve_sandbox_provider,
)


def test_model_resolution_order():
    assert (
        resolve_model(
            request_model="a",
            user_preferred="b",
            org_default="c",
            platform_default="d",
        )
        == "a"
    )
    assert (
        resolve_model(
            request_model=None,
            user_preferred="b",
            org_default="c",
            platform_default="d",
        )
        == "b"
    )
    assert (
        resolve_model(
            request_model=None,
            user_preferred=None,
            org_default=None,
            platform_default="d",
        )
        == "d"
    )


def test_sandbox_default_daytona():
    p = resolve_sandbox_provider(
        request_provider=None,
        user_preferred=None,
        org_default=None,
        enabled=["daytona", "agent_sandbox", "opensandbox"],
    )
    assert p == SandboxProvider.DAYTONA


def test_sandbox_user_select_opensandbox():
    p = resolve_sandbox_provider(
        request_provider="opensandbox",
        user_preferred="daytona",
        org_default="daytona",
        enabled=["daytona", "agent_sandbox", "opensandbox"],
    )
    assert p == SandboxProvider.OPENSANDBOX


def test_sandbox_disabled():
    with pytest.raises(PlatformError) as ei:
        resolve_sandbox_provider(
            request_provider="agent_sandbox",
            user_preferred=None,
            org_default=None,
            enabled=["daytona"],
        )
    assert ei.value.error_code == "sandbox_provider_disabled"


def test_mcp_inherit_and_required():
    u1, u2, req = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ids = resolve_mcp_ids(
        mode=McpMode.INHERIT,
        request_ids=None,
        user_defaults=[u1],
        org_required=[req],
        visible_enabled={u1, u2, req},
        agent_type=AgentType.CODING,
        server_agent_types={u1: [], u2: ["chat"], req: ["coding"]},
        max_servers=10,
    )
    assert ids[0] == req
    assert u1 in ids
    assert u2 not in ids


def test_mcp_replace_visibility():
    u1 = uuid.uuid4()
    with pytest.raises(PlatformError):
        resolve_mcp_ids(
            mode=McpMode.REPLACE,
            request_ids=[u1],
            user_defaults=[],
            org_required=[],
            visible_enabled=set(),
            agent_type="coding",
            server_agent_types={},
            max_servers=10,
        )
