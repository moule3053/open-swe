import base64
import json
from typing import Any, cast

import httpx
import pytest
from deepagents.backends.protocol import FILE_NOT_FOUND, INVALID_PATH
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from openswe_platform.harness import agents
from openswe_platform.harness.agent_sandbox_backend import AgentSandboxBackend
from openswe_platform.harness.agents import RunContext, get_agent
from openswe_platform.harness.sandboxes import AgentSandboxProvider, SandboxRef


@pytest.mark.asyncio
async def test_execute_uses_shell_and_preserves_stdout_and_stderr():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"exit_code": 7, "stdout": "output\n", "stderr": "failure\n"},
        )

    backend = AgentSandboxBackend(
        "sandbox-1",
        "http://sandbox.test:8888",
        transport=httpx.MockTransport(handler),
    )

    result = await backend.aexecute("printf 'hello'\necho done")

    assert result.exit_code == 7
    assert result.output == "output\nfailure\n"
    assert json.loads(requests[0].content) == {
        "command": "/bin/sh -lc 'printf '\"'\"'hello'\"'\"'\necho done'"
    }


@pytest.mark.asyncio
async def test_file_transfer_is_confined_to_runtime_workspace():
    uploaded: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/execute":
            return httpx.Response(200, json={"exit_code": 0, "stdout": "", "stderr": ""})
        if request.url.path == "/upload":
            uploaded.append(request.content)
            return httpx.Response(200, json={"message": "uploaded"})
        if request.url.path.startswith("/download/"):
            return httpx.Response(200, content=b"saved content")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    backend = AgentSandboxBackend(
        "sandbox-1",
        "http://sandbox.test:8888",
        transport=httpx.MockTransport(handler),
    )

    upload = await backend.aupload_files([("/nested/file.txt", b"saved content")])
    download = await backend.adownload_files([("/app/nested/file.txt")])

    assert upload[0].error is None
    assert b'filename="nested/file.txt"' in uploaded[0]
    assert download[0].content == b"saved content"
    assert download[0].error is None


@pytest.mark.asyncio
async def test_file_transfer_normalizes_errors():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    backend = AgentSandboxBackend(
        "sandbox-1",
        "http://sandbox.test:8888",
        transport=httpx.MockTransport(handler),
    )

    missing = await backend.adownload_files(["/missing.txt"])
    invalid = await backend.adownload_files(["relative.txt"])

    assert missing[0].error == FILE_NOT_FOUND
    assert invalid[0].error == INVALID_PATH


@pytest.mark.asyncio
async def test_large_edit_keeps_temporary_files_in_workspace():
    uploads: list[bytes] = []
    commands: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload":
            uploads.append(request.content)
            return httpx.Response(200, json={"message": "uploaded"})
        if request.url.path == "/execute":
            command = json.loads(request.content)["command"]
            commands.append(command)
            stdout = '{"count": 1}' if "mkdir -p" not in command else ""
            return httpx.Response(200, json={"exit_code": 0, "stdout": stdout, "stderr": ""})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    backend = AgentSandboxBackend(
        "sandbox-1",
        "http://sandbox.test:8888",
        transport=httpx.MockTransport(handler),
    )

    result = await backend.aedit("/large.txt", "x" * 30_000, "y" * 30_000)

    assert result.error is None
    assert result.path == "/large.txt"
    assert len(uploads) == 2
    assert all(b'filename=".deepagents-tmp/edit-' in upload for upload in uploads)
    workspace_prefix = base64.b64encode(b"/app/.deepagents-tmp/").decode().rstrip("=")
    assert any(workspace_prefix in command for command in commands)
    assert not any("/tmp/.deepagents_edit_" in command for command in commands)


@pytest.mark.asyncio
async def test_resolved_agent_sandbox_has_deep_agents_backend(monkeypatch):
    provider = AgentSandboxProvider()

    async def kube_request(_method: str, path: str, **_kwargs: object) -> dict[str, object]:
        assert path.endswith("/sandboxes/sandbox-1")
        return {
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "serviceFQDN": "sandbox-1.alephat-sandboxes.svc.cluster.local",
            }
        }

    monkeypatch.setattr(provider, "_request", kube_request)

    ref = await provider._resolve_ref(SandboxRef(provider="agent_sandbox", sandbox_id="sandbox-1"))

    assert isinstance(ref.handle, AgentSandboxBackend)
    assert ref.handle.id == "sandbox-1"
    assert ref.handle.workspace == "/app"


@pytest.mark.asyncio
async def test_agent_sandbox_executes_through_deep_agents_runtime(monkeypatch):
    executed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        executed.append(payload["command"])
        return httpx.Response(200, json={"exit_code": 0, "stdout": "ok\n", "stderr": ""})

    class FakeModel(FakeMessagesListChatModel):
        def bind_tools(self, *_args, **_kwargs):
            return self

    model = FakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute",
                        "args": {"command": "printf deep-agent-ok"},
                        "id": "execute-1",
                    }
                ],
            ),
            AIMessage(content="deep agent complete"),
        ]
    )
    monkeypatch.setattr(agents, "_make_deep_agent_model", lambda *_args, **_kwargs: model)
    backend = AgentSandboxBackend(
        "sandbox-1",
        "http://sandbox.test:8888",
        transport=httpx.MockTransport(handler),
    )
    context = RunContext(
        org_id="org",
        task_id="task",
        run_id="run",
        thread_id="thread",
        agent_type="coding",
        repo=None,
        base_ref="main",
        model="fake:model",
        prompt="run the command",
        messages=[],
        sandbox_provider="agent_sandbox",
        sandbox_id="sandbox-1",
        mcp_snapshot=[],
        checkpoint=None,
    )
    events: list[str] = []

    async def on_step(event_type: str, _payload: dict):
        events.append(event_type)

    async def on_boundary():
        return []

    result = await get_agent("coding").run(
        context,
        llm=cast(Any, None),
        sandbox=cast(Any, None),
        sandbox_ref=SandboxRef(
            provider="agent_sandbox",
            sandbox_id="sandbox-1",
            handle=backend,
        ),
        mcp_sessions=[],
        on_step=on_step,
        on_boundary=on_boundary,
    )

    assert result.success
    assert result.final_message == "deep agent complete"
    assert result.checkpoint_blob["runtime"] == "deepagents"
    assert executed == ["/bin/sh -lc 'printf deep-agent-ok'"]
    assert "tool_started" in events
