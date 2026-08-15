from pathlib import Path

import pytest

from alephat_platform.common.enums import SandboxProvider
from alephat_platform.harness.sandboxes import get_sandbox_provider


@pytest.mark.parametrize(
    "name",
    [
        SandboxProvider.DAYTONA.value,
        SandboxProvider.AGENT_SANDBOX.value,
        SandboxProvider.OPENSANDBOX.value,
        SandboxProvider.LOCAL.value,
    ],
)
def test_providers_registered(name):
    p = get_sandbox_provider(name)
    assert p.name == name


def test_unknown_provider():
    with pytest.raises(ValueError):
        get_sandbox_provider("modal")


@pytest.mark.asyncio
async def test_local_provider_exec():
    p = get_sandbox_provider(SandboxProvider.LOCAL.value)
    ref = await p.create(task_id="test-task-12345")
    assert ref.provider == "local"
    assert ref.sandbox_id.startswith("local-test-tas")

    res = await p.exec(ref, "echo hello_local")
    assert res.exit_code == 0
    assert "hello_local" in res.stdout

    conn_ref = await p.connect(ref.sandbox_id)
    assert conn_ref.sandbox_id == ref.sandbox_id

    await p.stop(ref)
    await p.delete(ref)


@pytest.mark.asyncio
async def test_local_provider_uses_an_isolated_persistent_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    p = get_sandbox_provider(SandboxProvider.LOCAL.value)

    ref = await p.create(task_id="isolated-task")
    first_pwd = await p.exec(ref, "pwd")
    connected = await p.connect(ref.sandbox_id)
    second_pwd = await p.exec(connected, "pwd")

    expected = tmp_path / ref.sandbox_id
    assert Path(first_pwd.stdout.strip()) == expected
    assert Path(second_pwd.stdout.strip()) == expected
    assert ref.metadata["root_dir"] == str(expected)


@pytest.mark.asyncio
async def test_local_provider_rejects_unsafe_sandbox_id():
    p = get_sandbox_provider(SandboxProvider.LOCAL.value)

    with pytest.raises(ValueError, match="Invalid local sandbox id"):
        await p.connect("../outside")
