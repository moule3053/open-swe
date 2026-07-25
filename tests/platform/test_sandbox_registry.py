import pytest

from openswe_platform.common.enums import SandboxProvider
from openswe_platform.harness.sandboxes import get_sandbox_provider


@pytest.mark.parametrize(
    "name",
    [
        SandboxProvider.DAYTONA.value,
        SandboxProvider.AGENT_SANDBOX.value,
        SandboxProvider.OPENSANDBOX.value,
    ],
)
def test_providers_registered(name):
    p = get_sandbox_provider(name)
    assert p.name == name


def test_unknown_provider():
    with pytest.raises(ValueError):
        get_sandbox_provider("modal")
