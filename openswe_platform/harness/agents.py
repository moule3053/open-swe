"""Agent type registry — extensible Deep Agents / coding loop entrypoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from openswe_platform.harness.llm_client import LLMClient
from openswe_platform.harness.mcp_runtime import McpSession
from openswe_platform.harness.sandboxes import ExecResult, SandboxProviderBase, SandboxRef

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    success: bool
    final_message: str
    park: bool = False
    park_reason: str | None = None
    approval_payload: dict[str, Any] | None = None
    checkpoint_blob: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


@dataclass
class RunContext:
    org_id: str
    task_id: str
    run_id: str
    thread_id: str
    agent_type: str
    repo: str | None
    base_ref: str | None
    model: str
    prompt: str | None
    messages: list[dict[str, str]]
    sandbox_provider: str
    sandbox_id: str | None
    mcp_snapshot: list[dict[str, Any]]
    checkpoint: dict[str, Any] | None
    cancel_requested: bool = False


class AgentRunner(Protocol):
    async def run(
        self,
        ctx: RunContext,
        *,
        llm: LLMClient,
        sandbox: SandboxProviderBase,
        sandbox_ref: SandboxRef,
        mcp_sessions: list[McpSession],
        on_step: Any,
    ) -> AgentResult: ...


class CodingAgentRunner:
    """Minimal coding agent loop via LLM client + sandbox exec.

    Extensible: replace with deepagents.create_deep_agent wiring later.
    LLM may be LiteLLM (optional) or direct provider APIs.
    """

    async def run(
        self,
        ctx: RunContext,
        *,
        llm: LLMClient,
        sandbox: SandboxProviderBase,
        sandbox_ref: SandboxRef,
        mcp_sessions: list[McpSession],
        on_step: Any,
    ) -> AgentResult:
        step = int((ctx.checkpoint or {}).get("step", 0))
        history = list(ctx.messages)
        if not history and ctx.prompt:
            history = [{"role": "user", "content": ctx.prompt}]

        system = (
            "You are a remote coding agent. Work in the sandbox. "
            f"Repo: {ctx.repo or 'unspecified'}. Base ref: {ctx.base_ref or 'main'}. "
            "When you need a shell command, reply with a single line: RUN: <command>. "
            "When done, reply with DONE: <summary>. "
            "When you need plan approval, reply with PLAN: <plan text>. "
            "When you need a user answer, reply with QUESTION: <question>."
        )
        mcp_tool_names = [t.namespaced for s in mcp_sessions if s.ok for t in s.tools]
        if mcp_tool_names:
            system += f" Available MCP tools: {', '.join(mcp_tool_names[:20])}."

        max_steps = 8
        while step < max_steps:
            if ctx.cancel_requested:
                return AgentResult(
                    success=False,
                    final_message="cancelled",
                    error_code="cancelled",
                    checkpoint_blob={"step": step, "messages": history},
                )

            await on_step("model_started", {"step": step, "model": ctx.model})
            response = await llm.chat_completions(
                model=ctx.model,
                messages=[{"role": "system", "content": system}, *history],
            )
            content = llm.message_content(response)
            await on_step("model_finished", {"step": step, "chars": len(content)})
            history.append({"role": "assistant", "content": content})
            step += 1

            # Checkpoint after each model step
            blob = {"step": step, "messages": history}
            await on_step("checkpoint", blob)

            stripped = content.strip()
            if stripped.startswith("PLAN:"):
                plan = stripped[len("PLAN:") :].strip()
                return AgentResult(
                    success=False,
                    final_message=plan,
                    park=True,
                    park_reason="plan_approval",
                    approval_payload={"plan": plan},
                    checkpoint_blob=blob,
                )
            if stripped.startswith("QUESTION:"):
                q = stripped[len("QUESTION:") :].strip()
                return AgentResult(
                    success=False,
                    final_message=q,
                    park=True,
                    park_reason="agent_question",
                    checkpoint_blob=blob,
                )
            if stripped.startswith("DONE:"):
                return AgentResult(
                    success=True,
                    final_message=stripped[len("DONE:") :].strip(),
                    checkpoint_blob=blob,
                )
            if stripped.startswith("RUN:"):
                cmd = stripped[len("RUN:") :].strip()
                await on_step("tool_started", {"tool": "execute", "command": cmd})
                result: ExecResult = await sandbox.exec(sandbox_ref, cmd)
                await on_step(
                    "tool_finished",
                    {
                        "tool": "execute",
                        "exit_code": result.exit_code,
                        "stdout_preview": result.stdout[:500],
                    },
                )
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"Command exit={result.exit_code}\n"
                            f"stdout:\n{result.stdout[:4000]}\n"
                            f"stderr:\n{result.stderr[:2000]}"
                        ),
                    }
                )
                await on_step("checkpoint", {"step": step, "messages": history})
                continue

            # Free-form assistant text — treat as progress and continue once more
            history.append(
                {
                    "role": "user",
                    "content": (
                        "Continue. Use RUN:/DONE:/PLAN:/QUESTION: prefixes when taking action."
                    ),
                }
            )

        return AgentResult(
            success=False,
            final_message="max steps reached",
            error_code="max_steps",
            checkpoint_blob={"step": step, "messages": history},
        )


class ReviewerAgentRunner(CodingAgentRunner):
    """Reviewer agent — same loop, different system framing via prompt prefix."""

    async def run(self, ctx: RunContext, **kwargs: Any) -> AgentResult:
        ctx = RunContext(
            **{
                **ctx.__dict__,
                "prompt": (
                    f"[REVIEW MODE]\n{ctx.prompt or ''}\n"
                    "Review the change; finish with DONE: findings summary."
                ),
            }
        )
        return await super().run(ctx, **kwargs)


class AnalyzerAgentRunner(CodingAgentRunner):
    async def run(self, ctx: RunContext, **kwargs: Any) -> AgentResult:
        ctx = RunContext(
            **{
                **ctx.__dict__,
                "prompt": f"[ANALYZER MODE]\n{ctx.prompt or ''}\nFinish with DONE: style notes.",
            }
        )
        return await super().run(ctx, **kwargs)


class ChatAgentRunner(CodingAgentRunner):
    async def run(self, ctx: RunContext, **kwargs: Any) -> AgentResult:
        # single-turn style: ask model once via parent with low max by DONE instruction
        return await super().run(ctx, **kwargs)


REGISTRY: dict[str, AgentRunner] = {
    "coding": CodingAgentRunner(),
    "reviewer": ReviewerAgentRunner(),
    "analyzer": AnalyzerAgentRunner(),
    "chat": ChatAgentRunner(),
}


def get_agent(agent_type: str) -> AgentRunner:
    if agent_type not in REGISTRY:
        raise KeyError(agent_type)
    return REGISTRY[agent_type]
