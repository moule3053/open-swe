"""Pluggable sandbox providers: daytona, agent_sandbox, opensandbox."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from openswe_platform.common.config import get_settings
from openswe_platform.common.enums import SandboxProvider

logger = logging.getLogger(__name__)


@dataclass
class SandboxRef:
    provider: str
    sandbox_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # optional live handle for providers that keep client objects
    handle: Any = None


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str = ""


class SandboxProviderBase(ABC):
    name: str

    @abstractmethod
    async def create(
        self, *, task_id: str, metadata: dict[str, Any] | None = None
    ) -> SandboxRef: ...

    @abstractmethod
    async def connect(self, sandbox_id: str) -> SandboxRef: ...

    @abstractmethod
    async def exec(self, ref: SandboxRef, command: str, timeout: int = 120) -> ExecResult: ...

    @abstractmethod
    async def stop(self, ref: SandboxRef) -> None: ...

    @abstractmethod
    async def delete(self, ref: SandboxRef) -> None: ...


class DaytonaProvider(SandboxProviderBase):
    name = SandboxProvider.DAYTONA.value

    async def create(self, *, task_id: str, metadata: dict[str, Any] | None = None) -> SandboxRef:
        settings = get_settings()
        if not settings.daytona_api_key:
            if not settings.allow_stub_sandboxes:
                raise RuntimeError("DAYTONA_API_KEY is required for the Daytona provider")
            sid = f"daytona-stub-{task_id[:8]}-{uuid.uuid4().hex[:8]}"
            logger.warning("Explicit local stub sandbox enabled: %s", sid)
            return SandboxRef(provider=self.name, sandbox_id=sid, metadata={"stub": True})
        try:
            from agent.integrations.daytona import create_daytona_sandbox

            backend = await asyncio.to_thread(create_daytona_sandbox, None)
            sid = (
                getattr(backend, "id", None)
                or getattr(backend, "sandbox_id", None)
                or str(uuid.uuid4())
            )
            return SandboxRef(
                provider=self.name,
                sandbox_id=str(sid),
                metadata=metadata or {},
                handle=backend,
            )
        except Exception:
            if not settings.allow_stub_sandboxes:
                raise
            logger.exception("Daytona create failed; explicit stub fallback enabled")
            return SandboxRef(
                provider=self.name,
                sandbox_id=f"daytona-stub-{uuid.uuid4().hex[:12]}",
                metadata={"stub": True},
            )

    async def connect(self, sandbox_id: str) -> SandboxRef:
        settings = get_settings()
        if not settings.daytona_api_key or sandbox_id.startswith("daytona-stub-"):
            return SandboxRef(provider=self.name, sandbox_id=sandbox_id, metadata={"stub": True})
        try:
            from agent.integrations.daytona import create_daytona_sandbox

            backend = await asyncio.to_thread(create_daytona_sandbox, sandbox_id)
            return SandboxRef(provider=self.name, sandbox_id=sandbox_id, handle=backend)
        except Exception:
            logger.exception("Daytona connect failed")
            raise

    async def exec(self, ref: SandboxRef, command: str, timeout: int = 120) -> ExecResult:
        if ref.metadata.get("stub") or ref.handle is None:
            return ExecResult(exit_code=0, stdout=f"[stub:{ref.sandbox_id}] ran: {command}\n")
        # DaytonaSandbox typically exposes execute / run
        handle = ref.handle
        if hasattr(handle, "execute"):
            result = await asyncio.to_thread(handle.execute, command, timeout=timeout)
            return ExecResult(
                exit_code=getattr(result, "exit_code", 0) or 0,
                stdout=str(getattr(result, "output", getattr(result, "stdout", result)) or ""),
                stderr=str(getattr(result, "stderr", "") or ""),
            )
        return ExecResult(exit_code=0, stdout=str(handle))

    async def stop(self, ref: SandboxRef) -> None:
        logger.info("stop sandbox %s/%s", ref.provider, ref.sandbox_id)

    async def delete(self, ref: SandboxRef) -> None:
        logger.info("delete sandbox %s/%s", ref.provider, ref.sandbox_id)


class AgentSandboxProvider(SandboxProviderBase):
    """kubernetes-sigs/agent-sandbox integration (stub-capable)."""

    name = SandboxProvider.AGENT_SANDBOX.value

    async def create(self, *, task_id: str, metadata: dict[str, Any] | None = None) -> SandboxRef:
        if not get_settings().allow_stub_sandboxes:
            raise RuntimeError(
                "agent_sandbox needs a cluster adapter; set ALLOW_STUB_SANDBOXES=true only for local UI testing"
            )
        namespace = os.environ.get("AGENT_SANDBOX_NAMESPACE", "agent-sandboxes")
        sid = f"asb-{task_id[:8]}-{uuid.uuid4().hex[:8]}"
        logger.info("agent_sandbox create %s in ns %s", sid, namespace)
        return SandboxRef(
            provider=self.name,
            sandbox_id=sid,
            metadata={"namespace": namespace, "stub": True, **(metadata or {})},
        )

    async def connect(self, sandbox_id: str) -> SandboxRef:
        if not get_settings().allow_stub_sandboxes:
            raise RuntimeError("agent_sandbox reconnect is unavailable without a cluster adapter")
        namespace = os.environ.get("AGENT_SANDBOX_NAMESPACE", "agent-sandboxes")
        return SandboxRef(
            provider=self.name,
            sandbox_id=sandbox_id,
            metadata={"namespace": namespace, "stub": True},
        )

    async def exec(self, ref: SandboxRef, command: str, timeout: int = 120) -> ExecResult:
        return ExecResult(
            exit_code=0,
            stdout=f"[agent_sandbox:{ref.sandbox_id}] ran: {command}\n",
        )

    async def stop(self, ref: SandboxRef) -> None:
        logger.info("agent_sandbox stop %s", ref.sandbox_id)

    async def delete(self, ref: SandboxRef) -> None:
        logger.info("agent_sandbox delete %s", ref.sandbox_id)


class OpenSandboxProvider(SandboxProviderBase):
    """OpenSandbox control-plane integration (stub-capable)."""

    name = SandboxProvider.OPENSANDBOX.value

    async def create(self, *, task_id: str, metadata: dict[str, Any] | None = None) -> SandboxRef:
        settings = get_settings()
        base = settings.opensandbox_base_url
        sid = f"osb-{task_id[:8]}-{uuid.uuid4().hex[:8]}"
        if not base:
            if not settings.allow_stub_sandboxes:
                raise RuntimeError("OPENSANDBOX_BASE_URL is required for the OpenSandbox provider")
            logger.warning("Explicit local stub sandbox enabled: %s", sid)
            return SandboxRef(
                provider=self.name, sandbox_id=sid, metadata={"stub": True, **(metadata or {})}
            )
        raise RuntimeError("OpenSandbox API adapter is not configured for this deployment")

    async def connect(self, sandbox_id: str) -> SandboxRef:
        settings = get_settings()
        if not settings.allow_stub_sandboxes:
            raise RuntimeError("OpenSandbox reconnect is unavailable without an API adapter")
        return SandboxRef(
            provider=self.name,
            sandbox_id=sandbox_id,
            metadata={"base_url": settings.opensandbox_base_url, "stub": True},
        )

    async def exec(self, ref: SandboxRef, command: str, timeout: int = 120) -> ExecResult:
        return ExecResult(
            exit_code=0,
            stdout=f"[opensandbox:{ref.sandbox_id}] ran: {command}\n",
        )

    async def stop(self, ref: SandboxRef) -> None:
        logger.info("opensandbox stop %s", ref.sandbox_id)

    async def delete(self, ref: SandboxRef) -> None:
        logger.info("opensandbox delete %s", ref.sandbox_id)


_REGISTRY: dict[str, SandboxProviderBase] = {
    SandboxProvider.DAYTONA.value: DaytonaProvider(),
    SandboxProvider.AGENT_SANDBOX.value: AgentSandboxProvider(),
    SandboxProvider.OPENSANDBOX.value: OpenSandboxProvider(),
}


def get_sandbox_provider(name: str) -> SandboxProviderBase:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown sandbox provider: {name}") from exc
