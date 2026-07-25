import pytest

from openswe_platform.common.config import clear_settings_cache
from openswe_platform.harness.llm_client import (
    DirectLLMClient,
    LiteLLMClient,
    make_llm_client,
    parse_model_id,
    resolve_llm_mode,
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_parse_model_id_provider_colon():
    p = parse_model_id("anthropic:claude-sonnet-4-20250514")
    assert p.provider == "anthropic"
    assert p.model == "claude-sonnet-4-20250514"


def test_parse_model_id_slash():
    p = parse_model_id("openai/gpt-4o-mini")
    assert p.provider == "openai"
    assert p.model == "gpt-4o-mini"


def test_parse_model_id_default_provider():
    p = parse_model_id("gpt-4o-mini", default_provider="openai")
    assert p.provider == "openai"
    assert p.model == "gpt-4o-mini"


def test_resolve_mode_direct_explicit(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "direct")
    monkeypatch.delenv("LITELLM_ENABLED", raising=False)
    clear_settings_cache()
    assert resolve_llm_mode() == "direct"


def test_resolve_mode_litellm_explicit(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "litellm")
    clear_settings_cache()
    assert resolve_llm_mode() == "litellm"


def test_resolve_mode_auto_prefers_direct_with_key(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setenv("LITELLM_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    clear_settings_cache()
    assert resolve_llm_mode() == "direct"


def test_resolve_mode_auto_litellm_when_enabled(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setenv("LITELLM_ENABLED", "true")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    clear_settings_cache()
    assert resolve_llm_mode() == "litellm"


def test_make_llm_client_direct(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "direct")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    clear_settings_cache()
    client = make_llm_client()
    assert isinstance(client, DirectLLMClient)


def test_make_llm_client_litellm(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "litellm")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    clear_settings_cache()
    client = make_llm_client()
    assert isinstance(client, LiteLLMClient)


@pytest.mark.asyncio
async def test_direct_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", "direct")
    clear_settings_cache()
    client = DirectLLMClient()
    client.openai_api_key = None
    with pytest.raises(RuntimeError, match="API key"):
        await client.chat_completions(
            model="openai:gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
