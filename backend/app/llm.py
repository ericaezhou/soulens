"""
LLM abstraction — uses OpenRouter (via openai SDK) if OPENROUTER_API_KEY is set,
otherwise calls Anthropic directly.

Usage:
    from app.llm import create_message
    text = create_message(content_blocks, max_tokens=4000)
"""
import os
import anthropic
from openai import OpenAI

_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_OPENROUTER_MODEL = "anthropic/claude-sonnet-4-6"


def _to_openai_content(blocks: list) -> list:
    """Convert Anthropic-format content blocks to OpenAI format."""
    out = []
    for b in blocks:
        if b.get("type") == "text":
            out.append({"type": "text", "text": b["text"]})
        elif b.get("type") == "image":
            src = b.get("source", {})
            if src.get("type") == "base64":
                out.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"},
                })
    return out


def create_message(content: list, max_tokens: int = 4000) -> str:
    """Call Claude and return the response text. Routes via OpenRouter if key is set."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    if openrouter_key:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
            default_headers={
                "HTTP-Referer": "https://soulens.vercel.app",
                "X-Title": "Soulens",
            },
        )
        response = client.chat.completions.create(
            model=_OPENROUTER_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": _to_openai_content(content)}],
        )
        return response.choices[0].message.content

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    resp = client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    return resp.content[0].text
