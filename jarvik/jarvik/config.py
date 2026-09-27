"""Configuration, themes, and session persistence for JARVIK."""

import json
import os
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("JARVIK_HOME", str(Path.home() / ".jarvik")))
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
HISTORY_FILE = CONFIG_DIR / "history.json"

# v1 configs shipped with theme "blue"; v2 defaults to "dark".
# load_config() migrates old saved configs to the new default exactly once.
CONFIG_VERSION = 2

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "openai/gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "theme": "dark",
    "config_version": CONFIG_VERSION,
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

# ---------------------------------------------------------------------------
# Themes: topbar / border / accent colors per scheme.
# Each key maps to CSS classes used by app.py.
# ---------------------------------------------------------------------------
THEMES = {
    "blue": {
        "label": "Blue (default)",
        "screen_bg": "#040912",
        "screen_fg": "#dce9ff",
        "topbar_bg": "#081b36",
        "topbar_fg": "#7fc0ff",
        "border": "#2f6fce",
        "accent": "#4da3ff",
        "user_border": "#3a7bdb",
        "user_bg": "#0d2246",
        "user_fg": "#f0f6ff",
        "asst_border": "#1c4a8c",
        "asst_bg": "#05101f",
        "asst_fg": "#dbe8ff",
        "sys_border": "#294159",
        "sys_bg": "#0a1622",
        "sys_fg": "#93a8c2",
        "tool_border": "#2e8f63",
        "tool_bg": "#061913",
        "tool_fg": "#b7ecd3",
        "err_border": "#d1483a",
        "err_bg": "#240b0a",
        "err_fg": "#ffb9ae",
        "input_bg": "#0d2246",
        "input_fg": "#f0f6ff",
        "input_border": "#3a7bdb",
        "input_focus_border": "#58a6ff",
        "input_focus_bg": "#102a54",
        "banner_border": "#4da3ff",
        "banner_bg": "#071a33",
    },
    "dark": {
        "label": "Midnight Indigo",
        "screen_bg": "#08080d",
        "screen_fg": "#dedee8",
        "topbar_bg": "#12121c",
        "topbar_fg": "#c3c3d8",
        "border": "#2c2c3e",
        "accent": "#a08fff",
        "user_border": "#7a6fd0",
        "user_bg": "#1b1b2a",
        "user_fg": "#eeeef8",
        "asst_border": "#3d3d55",
        "asst_bg": "#0e0e18",
        "asst_fg": "#d4d4e4",
        "sys_border": "#2e2e40",
        "sys_bg": "#11111c",
        "sys_fg": "#9090a8",
        "tool_border": "#3f8e68",
        "tool_bg": "#0c1712",
        "tool_fg": "#b8e4cd",
        "err_border": "#b0453c",
        "err_bg": "#1e0d0c",
        "err_fg": "#f0aca3",
        "input_bg": "#1b1b2a",
        "input_fg": "#eeeef8",
        "input_border": "#7a6fd0",
        "input_focus_border": "#a89bff",
        "input_focus_bg": "#232338",
        "banner_border": "#8b7cf7",
        "banner_bg": "#12121f",
    },
    "matrix": {
        "label": "Matrix Green",
        "screen_bg": "#000d00",
        "screen_fg": "#b8ffcc",
        "topbar_bg": "#02200a",
        "topbar_fg": "#6dff9e",
        "border": "#116622",
        "accent": "#33ff77",
        "user_border": "#1f9a3d",
        "user_bg": "#03260d",
        "user_fg": "#d6ffe2",
        "asst_border": "#17802e",
        "asst_bg": "#011a06",
        "asst_fg": "#aef5c4",
        "sys_border": "#14521f",
        "sys_bg": "#021806",
        "sys_fg": "#77b58a",
        "tool_border": "#2e8f63",
        "tool_bg": "#061913",
        "tool_fg": "#b7ecd3",
        "err_border": "#a03028",
        "err_bg": "#1e0806",
        "err_fg": "#ffaba0",
        "input_bg": "#03260d",
        "input_fg": "#d6ffe2",
        "input_border": "#1f9a3d",
        "input_focus_border": "#33ff77",
        "input_focus_bg": "#053a12",
        "banner_border": "#33ff77",
        "banner_bg": "#032b0e",
    },
}
DEFAULT_THEME = "dark"


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
    except (json.JSONDecodeError, OSError):
        data = {}
        merged = dict(DEFAULT_CONFIG)
    # one-time migration: v1 saved configs started on "blue" -> move to dark
    if isinstance(data, dict) and data.get("config_version", 1) < CONFIG_VERSION:
        if merged.get("theme") == "blue":
            merged["theme"] = DEFAULT_THEME
        merged["config_version"] = CONFIG_VERSION
        save_config(merged)
    return merged


def save_config(config: dict) -> None:
    ensure_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)  # keep the API key readable only by the owner
    except OSError:
        pass


# ------------------------------------------------------------- history ----

def load_history() -> list[str]:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data if isinstance(x, str)]
    except (json.JSONDecodeError, OSError):
        return []


def append_history(entry: str) -> None:
    """Append one entry to the persistent input history (cap 500, dedup adjacent)."""
    ensure_dirs()
    items = load_history()
    if items and items[-1] == entry:
        return
    items.append(entry)
    items = items[-500:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f)
    except OSError:
        pass


# ------------------------------------------------------------ sessions ----

def list_sessions() -> list[Path]:
    ensure_dirs()
    return sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def session_path(name: str) -> Path:
    if not name.endswith(".json"):
        name += ".json"
    return SESSIONS_DIR / name


def delete_session(name: str) -> bool:
    path = session_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def save_session(name: str, messages: list[dict]) -> Path:
    ensure_dirs()
    if not name:
        name = time.strftime("session-%Y%m%d-%H%M%S")
    path = session_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"saved_at": time.time(), "messages": messages}, f, indent=2)
    return path


def load_session(name: str) -> list[dict]:
    path = session_path(name)
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
