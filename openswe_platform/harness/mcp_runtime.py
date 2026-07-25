"""Load MCP tools from task snapshot (harness-side)."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class McpTool:
    server_id: str
    server_name: str
    tool_name: str
    description: str = ""
    # callable placeholder for agent binding
    handler: Callable[..., Awaitable[str]] | None = None

    @property
    def namespaced(self) -> str:
        safe = self.server_name.replace("-", "_").replace(" ", "_")
        return f"mcp_{safe}_{self.tool_name}"


@dataclass
class McpSession:
    server_id: str
    name: str
    ok: bool
    tools: list[McpTool] = field(default_factory=list)
    error: str | None = None


def filter_tools(
    tool_names: list[str],
    *,
    allowlist: list[str],
    denylist: list[str],
) -> list[str]:
    names = list(tool_names)
    if allowlist:
        names = [n for n in names if n in allowlist]
    if denylist:
        names = [n for n in names if n not in denylist]
    return names


async def connect_mcp_servers(snapshot: list[dict[str, Any]]) -> list[McpSession]:
    """Connect configured MCP servers. fail_open for optional, tracked per session."""
    sessions: list[McpSession] = []
    for cfg in snapshot or []:
        server_id = str(cfg.get("mcp_server_id") or "")
        name = str(cfg.get("name") or "mcp")
        required = bool(cfg.get("required"))
        try:
            tools = await _probe_tools(cfg)
            allow = list(cfg.get("tool_allowlist") or [])
            deny = list(cfg.get("tool_denylist") or [])
            filtered = filter_tools(tools, allowlist=allow, denylist=deny)
            mcp_tools = [
                McpTool(
                    server_id=server_id,
                    server_name=name,
                    tool_name=t,
                    description=f"MCP tool {t} from {name}",
                    handler=_make_handler(cfg, t),
                )
                for t in filtered
            ]
            sessions.append(McpSession(server_id=server_id, name=name, ok=True, tools=mcp_tools))
        except Exception as exc:
            logger.exception("MCP connect failed for %s", name)
            sessions.append(
                McpSession(
                    server_id=server_id,
                    name=name,
                    ok=False,
                    error=str(exc),
                )
            )
            if required:
                raise
    return sessions


async def _probe_tools(cfg: dict[str, Any]) -> list[str]:
    """Best-effort tool discovery. Uses langchain-mcp-adapters when available."""
    transport = cfg.get("transport")
    url = cfg.get("url")
    if transport in {"sse", "streamable_http"} and url:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            from langchain_mcp_adapters.sessions import SSEConnection, StreamableHttpConnection

            headers = {}
            if cfg.get("headers_json"):
                headers = json.loads(cfg["headers_json"])
            if cfg.get("auth"):
                headers.setdefault("Authorization", f"Bearer {cfg['auth']}")

            server_key = str(cfg.get("name") or "server")
            if transport == "sse":
                connection = SSEConnection(
                    url=str(url),
                    transport="sse",
                    headers=headers,
                )
            else:
                connection = StreamableHttpConnection(
                    url=str(url),
                    transport="streamable_http",
                    headers=headers,
                )
            client = MultiServerMCPClient({server_key: connection})
            tools = await client.get_tools()
            return [getattr(t, "name", str(t)) for t in tools]
        except Exception as exc:
            logger.warning("langchain MCP probe failed: %s", exc)
            # treat remote as reachable with unknown tools — empty list still ok
            return []
    if transport == "stdio":
        # stdio servers discovered at connect time; empty until process start
        return []
    return []


def _make_handler(cfg: dict[str, Any], tool_name: str) -> Callable[..., Awaitable[str]]:
    async def _handler(**kwargs: Any) -> str:
        logger.info(
            "MCP tool call server=%s tool=%s kwargs_keys=%s",
            cfg.get("name"),
            tool_name,
            list(kwargs.keys()),
        )
        return json.dumps(
            {
                "ok": True,
                "server": cfg.get("name"),
                "tool": tool_name,
                "note": "MCP invocation stub — wire MultiServerMCPClient.call for production",
                "args": kwargs,
            }
        )

    return _handler
