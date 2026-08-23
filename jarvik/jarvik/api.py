"""Minimal async OpenRouter client with streaming chat completions."""

import json
from typing import AsyncIterator

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"


class OpenRouterError(Exception):
    pass


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    """Yield content chunks as they arrive from OpenRouter."""
    if not api_key:
        raise OpenRouterError("No API key set. Use /apikey <key> to set one.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jarvik-cli/jarvik",
        "X-Title": "JARVIK",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", OPENROUTER_CHAT_URL, headers=headers, json=payload) as resp:
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
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content


async def fetch_models(api_key: str = "") -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])


async def check_key(api_key: str) -> dict:
    """Validate a key and return account/usage info."""
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(OPENROUTER_KEY_URL, headers=headers)
        if resp.status_code != 200:
            raise OpenRouterError(f"Key check failed (HTTP {resp.status_code})")
        return resp.json().get("data", {})
