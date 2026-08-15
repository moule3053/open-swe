"""Back-compat re-export — prefer ``alephat_platform.harness.llm_client``."""

from alephat_platform.harness.llm_client import (  # noqa: F401
    DirectLLMClient,
    LiteLLMClient,
    make_llm_client,
    parse_model_id,
    resolve_llm_mode,
)
