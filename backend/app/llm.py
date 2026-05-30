"""
LLM client factory — uses OpenRouter if OPENROUTER_API_KEY is set, otherwise Anthropic directly.
OpenRouter supports the Anthropic Python client via base_url redirect.
"""
import os
import anthropic

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_MODEL_DIRECT = "claude-sonnet-4-6"
_MODEL_OPENROUTER = "anthropic/claude-sonnet-4-6"


def get_client() -> anthropic.Anthropic:
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        return anthropic.Anthropic(
            api_key=openrouter_key,
            base_url=_OPENROUTER_BASE,
            default_headers={
                "HTTP-Referer": "https://soulens.vercel.app",
                "X-Title": "Soulens",
            },
        )
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def claude_model() -> str:
    return _MODEL_OPENROUTER if os.getenv("OPENROUTER_API_KEY") else _MODEL_DIRECT
