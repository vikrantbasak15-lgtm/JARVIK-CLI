"""Minimal async OpenRouter client: streaming chat, usage accounting, credits."""

import json
from typing import AsyncIterator

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"


class OpenRouterError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jarvik-cli/jarvik",
        "X-Title": "JARVIK",
    }


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    usage: dict | None = None,
) -> AsyncIterator[str]:
    """Yield content chunks as they arrive from OpenRouter.

    If `usage` is a dict, it is updated in place with the provider-reported
    usage/cost object that OpenRouter attaches to the final SSE chunk.
    """
    if not api_key:
        raise OpenRouterError("No API key set. Use /apikey <key> to set one.")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", OPENROUTER_CHAT_URL, headers=_headers(api_key), json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                try:
                    err = json.loads(body).get("error", {}).get("message")
                except Exception:
                    err = None
                raise OpenRouterError(err or f"HTTP {resp.status_code}: {body.decode(errors='replace')[:300]}")

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if usage is not None and chunk.get("usage"):
                    usage.clear()
                    usage.update(chunk["usage"])
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content


async def chat_once(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, dict | None]:
    """Non-streaming completion. Returns (text, usage-or-None)."""
    if not api_key:
        raise OpenRouterError("No API key set. Use /apikey <key> to set one.")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(OPENROUTER_CHAT_URL, headers=_headers(api_key), json=payload)
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {}).get("message")
            except Exception:
                err = None
            raise OpenRouterError(err or f"HTTP {resp.status_code}")
        data = resp.json()
        text = ""
        choices = data.get("choices") or []
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
        return text, data.get("usage")


async def fetch_models(api_key: str = "") -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(OPENROUTER_MODELS_URL, headers=_headers(api_key))
        resp.raise_for_status()
        return resp.json().get("data", [])


async def fetch_credits(api_key: str) -> dict:
    """Return account credit/usage info: label, usage, limit, is_free_tier, rate_limit."""
    if not api_key:
        raise OpenRouterError("No API key set. Use /apikey <key> to set one.")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(OPENROUTER_CREDITS_URL, headers=_headers(api_key))
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {}).get("message")
            except Exception:
                err = None
            raise OpenRouterError(err or f"HTTP {resp.status_code}")
        return resp.json().get("data", {})
