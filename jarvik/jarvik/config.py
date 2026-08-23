"""Configuration and session persistence for JARVIK."""

import json
import os
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".jarvik"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "openai/gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": "You are JARVIK, a sharp, concise AI assistant running in a terminal. "
                      "Use markdown and fenced code blocks when sharing code.",
}

# A short curated list shown by /model with no args (fast to render, no network call needed)
SUGGESTED_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-3.5-haiku",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-chat",
    "mistralai/mistral-large",
    "qwen/qwen-2.5-72b-instruct",
]


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    ensure_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)  # keep the API key readable only by the owner
    except OSError:
        pass


def list_sessions() -> list[Path]:
    ensure_dirs()
    return sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def save_session(name: str, messages: list[dict]) -> Path:
    ensure_dirs()
    if not name:
        name = time.strftime("session-%Y%m%d-%H%M%S")
    if not name.endswith(".json"):
        name += ".json"
    path = SESSIONS_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"saved_at": time.time(), "messages": messages}, f, indent=2)
    return path


def load_session(name: str) -> list[dict]:
    if not name.endswith(".json"):
        name += ".json"
    path = SESSIONS_DIR / name
    if not path.exists():
        # allow loading by absolute/relative path too
        alt = Path(name)
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(name)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("messages", [])
