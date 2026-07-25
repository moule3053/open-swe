import pytest

from openswe_platform.common.network_security import validate_remote_url


@pytest.mark.asyncio
async def test_blocks_private_mcp_address():
    with pytest.raises(ValueError, match="private or reserved"):
        await validate_remote_url("http://127.0.0.1:8080/mcp", allow_private=False)


@pytest.mark.asyncio
async def test_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        await validate_remote_url(
            "https://user:secret@example.com/mcp",
            allow_private=False,
            resolve=False,
        )


@pytest.mark.asyncio
async def test_private_network_policy_can_be_enabled():
    await validate_remote_url("http://127.0.0.1:8080/mcp", allow_private=True)
