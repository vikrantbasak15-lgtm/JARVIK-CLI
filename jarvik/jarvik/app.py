"""
JARVIK — a terminal chat client for OpenRouter models.

Claude Code-style TUI: slash commands with tab-completion, persistent input
history, file context injection, shell execution, code-block extraction,
session save/load, themes, conversation compaction, usage & cost tracking,
and streaming replies with live stats.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.geometry import Offset
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Markdown, Static, TextArea

from . import config as cfg
from . import api
from .utils import (
    estimate_tokens,
    extract_code_blocks,
    format_cost,
    format_elapsed,
)

APP_VERSION = "2.0.0"

BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗██╗  ██╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██║ ██╔╝
     ██║███████║██████╔╝██║   ██║██║█████╔╝
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║██╔═██╗
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║██║  ██╗
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚═╝  ╚═╝
"""

HELP_TEXT = """\
### JARVIK commands

**Chat control**
| Command | Description |
|---|---|
| `/retry` | Regenerate the last reply |
| `/undo` | Remove the last exchange from context |
| `/stop` | Stop the current response (or press **Escape**) |
| `/clear` | Clear the conversation |
| `/compact` | Summarize + compress the conversation to free context |

**Model & account**
| Command | Description |
|---|---|
| `/model [name]` | Show current model, or switch |
| `/models [filter]` | Fetch the live model list from OpenRouter |
| `/system [prompt]` | Show or set the system prompt |
| `/temp [0.0-2.0]` | Show or set sampling temperature |
| `/maxtok [n]` | Show or set max reply tokens |
| `/keyinfo` | Show your OpenRouter credits & usage |
| `/apikey <key>` | Set / update your OpenRouter API key |

**Files & tools**
| Command | Description |
|---|---|
| `/read <path>` | Attach a local file as context for your next message |
| `/write <path> [n]` | Save the n-th (default last) code block to a file |
| `/run <shell cmd>` | Run a local shell command and show its output |
| `/multi` | Open a multiline editor for a long prompt |

**Sessions & output**
| Command | Description |
|---|---|
| `/save [name]` | Save the current conversation |
| `/load <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/sessions rm <name>` | Delete a saved session |
| `/export [path]` | Export the conversation as markdown |

**Info & settings**
| Command | Description |
|---|---|
| `/usage` | Tokens & cost totals for this session |
| `/tokens` | Approximate token count of the current context |
| `/theme [name]` | Switch theme: `blue`, `dark`, `matrix` |
| `/help` | Show this help |
| `/quit`, `/exit` | Exit JARVIK |

Shortcuts: **↑/↓** input history · **Tab** complete commands · **Ctrl+L** clear · **Esc** stop."""


# --------------------------------------------------------------------- CSS --
# All colors come from CSS variables set per-theme (see config.THEMES and
# JarvikApp.get_css_variables / _apply_theme).

CSS = """
Screen {
    background: $screen-bg;
    color: $screen-fg;
    scrollbar-color: $border $topbar-bg;
    scrollbar-color-hover: $accent $topbar-bg;
    scrollbar-color-active: $accent $topbar-bg;
    scrollbar-size: 1 1;
}

#topbar {
    dock: top;
    height: 3;
    background: $topbar-bg;
    color: $topbar-fg;
    content-align: center middle;
    text-style: bold;
    border-bottom: tall $border;
}

#statusbar {
    dock: top;
    height: 1;
    background: $topbar-bg;
    color: $topbar-fg;
    padding: 0 2;
}

#chat {
    background: $screen-bg;
    padding: 1 3;
}

.bubble {
    margin: 0 0 1 0;
    padding: 1 2;
    border: round $border;
    background: $asst-bg;
    width: 100%;
}

.bubble.user {
    border: round $user-border;
    background: $user-bg;
    color: $user-fg;
    margin-left: 6;
}

.bubble.assistant {
    border: round $asst-border;
    background: $asst-bg;
    color: $asst-fg;
    margin-right: 6;
}

.bubble.system {
    border: round $sys-border;
    background: $sys-bg;
    color: $sys-fg;
    margin-right: 6;
}

.bubble.tool {
    border: round $tool-border;
    background: $tool-bg;
    color: $tool-fg;
    margin-right: 6;
}

.bubble.banner {
    border: heavy $banner-border;
    background: $banner-bg;
    color: $screen-fg;
}

.bubble.banner .role-label {
    color: $topbar-fg;
}

.bubble.error {
    border: round $err-border;
    background: $err-bg;
    color: $err-fg;
    margin-right: 6;
}

.role-label {
    text-style: bold;
    color: $accent;
    margin-bottom: 0;
}

.bubble.user .role-label {
    color: $user-border;
}

.bubble.assistant .role-label {
    color: $accent;
}

.bubble.system .role-label {
    color: $sys-fg;
}

.bubble.tool .role-label {
    color: $tool-border;
}

.bubble.error .role-label {
    color: $err-border;
}

.bubble .dots-line {
    display: none;
    height: 1;
    color: $sys-fg;
    text-style: italic;
}

.bubble .dots-line.on {
    display: block;
}

#input-bar {
    dock: bottom;
    height: auto;
    background: $topbar-bg;
    border-top: tall $border;
    padding: 0 2;
}

#suggest {
    height: 1;
    color: $topbar-fg;
}

Input {
    background: $input-bg;
    color: $input-fg;
    border: round $input-border;
    padding: 0 1;
}

Input:focus {
    border: round $input-focus-border;
    background: $input-focus-bg;
}

Footer {
    background: $topbar-bg;
    color: $topbar-fg;
}

Footer > .footer--key {
    color: $accent;
    text-style: bold;
}

Footer > .footer--description {
    color: $topbar-fg;
}

MultiEditorScreen TextArea {
    background: $screen-bg;
    color: $screen-fg;
    border: round $input-border;
}

MultiEditorScreen TextArea:focus {
    border: round $input-focus-border;
}

MultiEditorScreen #multi-title {
    background: $topbar-bg;
    color: $topbar-fg;
    text-style: bold;
    padding: 0 2;
}
"""

THINKING_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

COMPACT_PROMPT = (
    "Summarize this conversation into a compact context so it can continue seamlessly. "
    "Capture: key decisions and facts, user preferences, open tasks, and any code or "
    "file paths that matter. Keep it under 600 words. Write it as terse context notes, "
    "not prose for a human."
)


def theme_variables(t: dict) -> dict[str, str]:
    """Convert a theme dict (underscore keys) to CSS variable names (dash keys)."""
    return {k.replace("_", "-"): v for k, v in t.items() if k != "label"}


class HistoryInput(Input):
    """Input with persistent up/down history and /command tab-completion."""

    def __init__(self, app_ref: "JarvikApp", **kwargs):
        super().__init__(**kwargs)
        self.jarvik = app_ref

    def _on_key(self, event) -> None:  # noqa: N802 (Textual private hook)
        key = event.key
        if key == "up":
            event.stop()
            event.prevent_default()
            self.jarvik.history_prev()
        elif key == "down":
            event.stop()
            event.prevent_default()
            self.jarvik.history_next()
        elif key == "tab":
            event.stop()
            event.prevent_default()
            self.jarvik.suggest_cycle()
        elif key == "right":
            # accept a command suggestion only when the cursor is at the end
            if self.jarvik.suggestion_active and self.cursor_position >= len(self.value):
                event.stop()
                event.prevent_default()
                self.jarvik.suggest_accept()


class MultiEditorScreen(ModalScreen[str | None]):
    """Fullscreen multiline prompt editor. Ctrl+S sends, Escape cancels."""

    BINDINGS = [
        Binding("ctrl+s", "send", "Send"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield Static("MULTILINE EDITOR — Ctrl+S send · Escape cancel", id="multi-title")
        yield TextArea(self._initial, id="multi-text")
        yield Static("", id="multi-hint")

    def on_mount(self) -> None:
        self.query_one("#multi-text", TextArea).focus()

    def action_send(self) -> None:
        self.dismiss(self.query_one("#multi-text", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ChatBubble(Static):
    """A single message rendered as a rounded bubble with a role label.

    Bubbles slide + fade in on first show (directional: user from the right,
    everyone else from the left).
    """

    LABELS = {
        "user": "YOU",
        "assistant": "JARVIK",
        "system": "SYSTEM",
        "tool": "SHELL",
        "error": "ERROR",
    }

    shown: reactive[float] = reactive(1.0, init=False)
    shift_x: reactive[float] = reactive(0.0, init=False)

    def __init__(self, role: str, text: str, css_class: str | None = None):
        super().__init__()
        self.role = role
        self._text = text
        self.css_class = css_class or role
        self._entrance_done = False

    def compose(self) -> ComposeResult:
        yield Static(f"[b]{self._label()}[/b]", classes="role-label", markup=True)
        yield Markdown(self._text, id="md")
        yield Static("", classes="dots-line")

    def on_mount(self) -> None:
        self.add_class("bubble")
        self.add_class(self.css_class)
        # start hidden so there's no flash before the entrance animation runs
        if not self._entrance_done:
            self.styles.opacity = 0.0
            self.styles.offset = Offset(16 if self.css_class == "user" else -16, 0)
            # safety net in case on_show never fires
            self.call_after_refresh(self._enter)

    def on_show(self) -> None:
        self._enter()

    def _enter(self) -> None:
        if self._entrance_done:
            return
        self._entrance_done = True
        self.shown = 0.0
        self.shift_x = 16.0 if self.css_class == "user" else -16.0
        self.animate("shown", 1.0, duration=0.22, easing="out_cubic")
        self.animate("shift_x", 0.0, duration=0.3, easing="out_cubic")

    def watch_shown(self, shown: float) -> None:
        self.styles.opacity = max(0.0, min(1.0, shown))

    def watch_shift_x(self, shift_x: float) -> None:
        self.styles.offset = Offset(round(shift_x), 0)

    def _label(self) -> str:
        return self.LABELS.get(self.css_class, self.role)

    async def update_text(self, text: str) -> None:
        self._text = text
        try:
            await self.query_one("#md", Markdown).update(text)
        except Exception:
            pass

    def set_meta(self, meta: str) -> None:
        """Append a stats suffix to the role label (e.g. 'JARVIK · 2.1s · 340 tok')."""
        try:
            self.query_one(".role-label", Static).update(f"[b]{self._label()}[/b] [i]{meta}[/i]")
        except Exception:
            pass

    def set_dots(self, on: bool, frame: int = 0) -> None:
        """Show/hide the animated 'thinking' line under the message."""
        try:
            dots = self.query_one(".dots-line", Static)
        except Exception:
            return
        if on:
            dots.add_class("on")
            dots.update(f"{THINKING_FRAMES[frame % len(THINKING_FRAMES)]} thinking…")
        else:
            dots.remove_class("on")
            dots.update("")


class JarvikApp(App):
    CSS = CSS
    TITLE = "JARVIK"

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "stop_generation", "Stop", show=False),
    ]

    generating: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        # load config BEFORE super().__init__() — App.__init__ calls
        # get_css_variables(), which reads the theme from self.config
        self.config = cfg.load_config()
        super().__init__()
        self.messages: list[dict] = [
            {"role": "system", "content": self.config["system_prompt"]}
        ]
        self.pending_context: list[str] = []
        self._last_assistant_text = ""
        self._stream_start = 0.0

        # animation state (spinner / thinking dots)
        self._spin_idx = 0
        self._spin_timer = None
        self._think_bubble = None

        # usage / cost tracking (provider-reported)
        self.totals = {"prompt": 0, "completion": 0, "cost": 0.0, "requests": 0}
        self._last_usage: dict = {}

        # command aliases -> canonical
        self.aliases = {
            "/?": "/help",
            "/h": "/help",
            "/m": "/model",
            "/t": "/theme",
            "/k": "/keyinfo",
            "/q": "/quit",
        }

        # input history
        self.history: list[str] = cfg.load_history()
        self._hist_idx = len(self.history)
        self._hist_draft = ""

        # /command suggestions
        self._all_commands = sorted(
            set(
                [
                    "/help", "/apikey", "/model", "/models", "/system", "/temp",
                    "/maxtok", "/read", "/write", "/run", "/clear", "/save",
                    "/load", "/sessions", "/tokens", "/quit", "/exit",
                    "/retry", "/undo", "/compact", "/export", "/keyinfo",
                    "/usage", "/theme", "/multi",
                ]
                + list(self.aliases)
            )
        )
        self._suggestions: list[str] = []
        self._sugg_idx = 0

    # ----------------------------------------------------- css variables ----

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        theme = cfg.THEMES.get(self.config.get("theme"), cfg.THEMES[cfg.DEFAULT_THEME])
        variables.update(theme_variables(theme))
        return variables

    # ---------------------------------------------------------- layout ----

    def compose(self) -> ComposeResult:
        yield Static(self._topbar_text(), id="topbar")
        yield Static(self._statusbar_text(), id="statusbar")
        yield VerticalScroll(id="chat")
        yield Container(
            HistoryInput(
                self,
                placeholder="Message JARVIK…  (↑ history · Tab complete · /help)",
                id="input",
            ),
            Static("", id="suggest"),
            id="input-bar",
        )
        yield Footer()

    def _topbar_text(self) -> str:
        key_state = "key set" if self.config.get("api_key") else "no key -- /apikey"
        return f"JARVIK v{APP_VERSION}  |  {key_state}"

    def _statusbar_text(self) -> str:
        model = self.config.get("model", "?")
        theme = self.config.get("theme", cfg.DEFAULT_THEME)
        temp = self.config.get("temperature", 0.7)
        est = sum(estimate_tokens(m["content"]) for m in self.messages)
        cost = format_cost(self.totals["cost"]) if self.totals["requests"] else "$0"
        spin = f"{THINKING_FRAMES[self._spin_idx % len(THINKING_FRAMES)]}  " if self.generating else ""
        return (
            f"{spin}{model}  ·  temp {temp}  ·  ~{est} tok ctx  ·  "
            f"{self.totals['requests']} req  ·  {cost}  ·  theme: {theme}"
        )

    def refresh_topbar(self) -> None:
        self.query_one("#topbar", Static).update(self._topbar_text())

    def refresh_statusbar(self) -> None:
        self.query_one("#statusbar", Static).update(self._statusbar_text())

    def on_mount(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        intro = f"```\n{BANNER.strip(chr(10))}\n```\n\n" \
                "Welcome to **JARVIK** - your terminal AI.\n\n" \
                "Type a message to chat, or `/help` to see everything I can do."
        if not self.config.get("api_key"):
            intro += "\n\n**No OpenRouter API key set.** Run `/apikey sk-or-...` to get started."
        chat.mount(ChatBubble("system", intro, "banner"))
        self.query_one("#input", HistoryInput).focus()

    # -------------------------------------------------------- utilities ----

    async def add_bubble(self, role: str, text: str, css_class: str | None = None) -> ChatBubble:
        chat = self.query_one("#chat", VerticalScroll)
        bubble = ChatBubble(role, text, css_class)
        await chat.mount(bubble)
        if role == "assistant" and self.generating:
            bubble.set_dots(True, self._spin_idx)
        chat.scroll_end(duration=0.25, easing="out_cubic")
        return bubble

    def _apply_theme(self) -> None:
        theme = cfg.THEMES.get(self.config.get("theme"), cfg.THEMES[cfg.DEFAULT_THEME])
        self.stylesheet.set_variables(theme_variables(theme))
        self.refresh_css()

    def _remember_input(self, text: str) -> None:
        cfg.append_history(text)
        self.history = cfg.load_history()
        self._hist_idx = len(self.history)

    # ------------------------------------------------- history / suggest ----

    def history_prev(self) -> None:
        inp = self.query_one("#input", HistoryInput)
        if not self.history:
            return
        if self._hist_idx == len(self.history):
            self._hist_draft = inp.value
        if self._hist_idx > 0:
            self._hist_idx -= 1
            inp.value = self.history[self._hist_idx]
            inp.cursor_position = len(inp.value)

    def history_next(self) -> None:
        inp = self.query_one("#input", HistoryInput)
        if self._hist_idx < len(self.history):
            self._hist_idx += 1
            if self._hist_idx == len(self.history):
                inp.value = self._hist_draft
            else:
                inp.value = self.history[self._hist_idx]
            inp.cursor_position = len(inp.value)

    @property
    def suggestion_active(self) -> bool:
        return bool(self._suggestions)

    def suggest_cycle(self) -> None:
        inp = self.query_one("#input", HistoryInput)
        if not self._suggestions:
            return
        inp.value = self._suggestions[self._sugg_idx]
        inp.cursor_position = len(inp.value)
        self._sugg_idx = (self._sugg_idx + 1) % len(self._suggestions)

    def suggest_accept(self) -> None:
        inp = self.query_one("#input", HistoryInput)
        if not self._suggestions:
            return
        inp.value = self._suggestions[self._sugg_idx] + " "
        inp.cursor_position = len(inp.value)

    def _update_suggestions(self, text: str) -> None:
        widget = self.query_one("#suggest", Static)
        if not text.startswith("/") or " " in text:
            self._suggestions = []
            self._sugg_idx = 0
            widget.update("")
            return
        self._suggestions = [
            c for c in self._all_commands if c.startswith(text) and c != text
        ][:8]
        self._sugg_idx = 0
        if self._suggestions:
            widget.update("[b]Tab[/b]  " + "   ".join(self._suggestions))
        else:
            widget.update("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input":
            self._update_suggestions(event.value)

    # ------------------------------------------------------------ input ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self._update_suggestions("")

        if text.startswith("/"):
            await self.handle_command(text)
            self._remember_input(text)
            return

        if self.generating:
            await self.add_bubble("system", "Still generating - press **Escape** to stop first.", "system")
            return

        # fold in any pending file context
        full_text = text
        if self.pending_context:
            ctx = "\n\n".join(self.pending_context)
            full_text = f"{ctx}\n\n{text}"
            self.pending_context.clear()

        await self.add_bubble("user", text, "user")
        self.messages.append({"role": "user", "content": full_text})
        self._remember_input(text)
        self.refresh_statusbar()
        self.run_generation()

    # ------------------------------------------------------- generation ----

    @work(exclusive=True, group="stream")
    async def run_generation(self) -> None:
        if self._spin_timer is None:
            self._spin_timer = self.set_interval(0.1, self._tick_thinking, pause=True)
        self.generating = True
        bubble = await self.add_bubble("assistant", "▌", "assistant")
        self._think_bubble = bubble
        acc = ""
        last_update = 0.0
        self._stream_start = time.monotonic()
        usage: dict = {}
        try:
            async for chunk in api.stream_chat(
                api_key=self.config["api_key"],
                model=self.config["model"],
                messages=self.messages,
                temperature=float(self.config.get("temperature", 0.7)),
                max_tokens=int(self.config.get("max_tokens", 4096)),
                usage=usage,
            ):
                acc += chunk
                now = time.monotonic()
                if now - last_update > 0.05:  # throttle re-render for smoothness
                    await bubble.update_text(acc + " ▌")
                    last_update = now

            self._last_usage = usage
            elapsed = time.monotonic() - self._stream_start
            n_tok = usage.get("completion_tokens") or max(1, len(acc) // 4)
            tps = n_tok / elapsed if elapsed > 0 else 0.0
            cost = usage.get("cost")
            meta = f"· {format_elapsed(elapsed)} · {n_tok} tok · {tps:.0f} tok/s"
            if cost is not None:
                meta += f" · {format_cost(cost)}"
                self.totals["cost"] += float(cost)
            if usage:
                self.totals["prompt"] += int(usage.get("prompt_tokens") or 0)
                self.totals["completion"] += int(usage.get("completion_tokens") or 0)
                self.totals["requests"] += 1

            await bubble.update_text(acc if acc else "*(empty response)*")
            bubble.set_meta(meta)
            self.messages.append({"role": "assistant", "content": acc})
            self._last_assistant_text = acc
        except api.OpenRouterError as e:
            await bubble.update_text(f"**Error:** {e}")
            bubble.remove_class("assistant")
            bubble.add_class("error")
        except asyncio.CancelledError:
            await bubble.update_text(acc + "\n\n*(stopped)*")
            if acc:
                self.messages.append({"role": "assistant", "content": acc})
        except Exception as e:  # noqa: BLE001
            await bubble.update_text(f"**Unexpected error:** {e}")
            bubble.remove_class("assistant")
            bubble.add_class("error")
        finally:
            if self._think_bubble is not None:
                try:
                    self._think_bubble.set_dots(False)
                except Exception:  # noqa: BLE001
                    pass
                self._think_bubble = None
            self.generating = False
            self.refresh_statusbar()
            self.query_one("#chat", VerticalScroll).scroll_end(duration=0.25, easing="out_cubic")

    def action_stop_generation(self) -> None:
        if self.generating:
            for w in self.workers:
                if w.group == "stream":
                    w.cancel()

    def watch_generating(self, generating: bool) -> None:
        if generating:
            self._spin_idx = 0
            if self._spin_timer is not None:
                self._spin_timer.resume()
        else:
            if self._spin_timer is not None:
                self._spin_timer.pause()

    def _tick_thinking(self) -> None:
        self._spin_idx = (self._spin_idx + 1) % len(THINKING_FRAMES)
        if self.generating:
            self.refresh_statusbar()
            if self._think_bubble is not None:
                try:
                    self._think_bubble.set_dots(True, self._spin_idx)
                except Exception:  # noqa: BLE001
                    pass

    def action_clear_chat(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self.messages = [{"role": "system", "content": self.config["system_prompt"]}]

    # ------------------------------------------------------- commands ----

    async def handle_command(self, raw: str) -> None:
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        cmd = self.aliases.get(cmd, cmd)

        if cmd == "/stop":
            self.action_stop_generation()
            return

        handlers = {
            "/help": self.cmd_help,
            "/apikey": self.cmd_apikey,
            "/model": self.cmd_model,
            "/models": self.cmd_models,
            "/system": self.cmd_system,
            "/temp": self.cmd_temp,
            "/maxtok": self.cmd_maxtok,
            "/read": self.cmd_read,
            "/write": self.cmd_write,
            "/run": self.cmd_run,
            "/clear": self.cmd_clear,
            "/save": self.cmd_save,
            "/load": self.cmd_load,
            "/sessions": self.cmd_sessions,
            "/tokens": self.cmd_tokens,
            "/retry": self.cmd_retry,
            "/undo": self.cmd_undo,
            "/compact": self.cmd_compact,
            "/export": self.cmd_export,
            "/keyinfo": self.cmd_keyinfo,
            "/usage": self.cmd_usage,
            "/theme": self.cmd_theme,
            "/multi": self.cmd_multi,
            "/quit": self.cmd_quit,
            "/exit": self.cmd_quit,
        }
        handler = handlers.get(cmd)
        if not handler:
            await self.add_bubble("system", f"Unknown command `{cmd}`. Try `/help`.", "error")
            return
        await handler(arg)

    async def cmd_help(self, arg: str) -> None:
        await self.add_bubble("system", HELP_TEXT, "system")

    async def cmd_apikey(self, arg: str) -> None:
        key = arg.strip()
        if not key:
            await self.add_bubble("system", "Usage: `/apikey sk-or-v1-...`", "error")
            return
        self.config["api_key"] = key
        cfg.save_config(self.config)
        self.refresh_topbar()
        await self.add_bubble("system", "API key saved to `~/.jarvik/config.json`.", "system")
        # validate against the API
        try:
            data = await api.fetch_credits(key)
            label = data.get("label") or "unlabeled key"
            usage = float(data.get("usage") or 0.0)
            limit = float(data.get("limit") or 0.0)
            left = limit - usage
            await self.add_bubble(
                "system",
                f"Key valid — `{label}`\n\nUsed **${usage:.2f}** of **${limit:.2f}** "
                f"(remaining **${left:.2f}**).",
                "tool",
            )
        except Exception as e:  # noqa: BLE001
            await self.add_bubble(
                "system",
                f"Could not validate key ({e}) — it was still saved.",
                "error",
            )

    async def cmd_keyinfo(self, arg: str) -> None:
        if not self.config.get("api_key"):
            await self.add_bubble("system", "No API key set. Use `/apikey <key>`.", "error")
            return
        await self.add_bubble("system", "Fetching account info from OpenRouter…", "system")
        try:
            data = await api.fetch_credits(self.config["api_key"])
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not fetch account info: {e}", "error")
            return
        label = data.get("label") or "unlabeled key"
        usage = float(data.get("usage") or 0.0)
        limit = float(data.get("limit") or 0.0)
        left = limit - usage
        free = data.get("is_free_tier")
        bar_w = 24
        frac = min(1.0, usage / limit) if limit > 0 else 0.0
        filled = int(frac * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        await self.add_bubble(
            "system",
            f"**OpenRouter account** — `{label}`\n\n"
            f"`{bar}` {frac * 100:.1f}% used\n\n"
            f"- Spent: **${usage:.2f}**\n"
            f"- Limit: **${limit:.2f}**\n"
            f"- Remaining: **${left:.2f}**\n"
            f"- Free tier: {free}",
            "tool",
        )

    async def cmd_model(self, arg: str) -> None:
        if not arg:
            listing = "\n".join(f"- `{m}`" for m in cfg.SUGGESTED_MODELS)
            await self.add_bubble(
                "system",
                f"**Current model:** `{self.config['model']}`\n\n**Suggestions** "
                f"(use `/model <name>` to switch, `/models` for the full live list):\n\n{listing}",
                "system",
            )
            return
        self.config["model"] = arg.strip()
        cfg.save_config(self.config)
        self.refresh_topbar()
        self.refresh_statusbar()
        await self.add_bubble("system", f"Switched model to `{self.config['model']}`.", "system")

    async def cmd_models(self, arg: str) -> None:
        await self.add_bubble("system", "Fetching live model list from OpenRouter…", "system")
        try:
            models = await api.fetch_models(self.config.get("api_key", ""))
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not fetch models: {e}", "error")
            return
        names = [m.get("id", "?") for m in models]
        filt = [n for n in names if arg.lower() in n.lower()] if arg else names
        shown = filt[:40]
        text = f"**{len(filt)} models found**" + (f" matching `{arg}`" if arg else "") + \
               " (showing up to 40):\n\n" + "\n".join(f"- `{n}`" for n in shown)
        await self.add_bubble("system", text, "system")

    async def cmd_system(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", f"**Current system prompt:**\n\n{self.config['system_prompt']}", "system")
            return
        self.config["system_prompt"] = arg
        cfg.save_config(self.config)
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = arg
        else:
            self.messages.insert(0, {"role": "system", "content": arg})
        await self.add_bubble("system", "System prompt updated.", "system")

    async def cmd_temp(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", f"Current temperature: `{self.config.get('temperature')}`", "system")
            return
        try:
            t = float(arg)
            assert 0.0 <= t <= 2.0
        except (ValueError, AssertionError):
            await self.add_bubble("system", "Usage: `/temp 0.7` (range 0.0–2.0)", "error")
            return
        self.config["temperature"] = t
        cfg.save_config(self.config)
        self.refresh_statusbar()
        await self.add_bubble("system", f"Temperature set to `{t}`.", "system")

    async def cmd_maxtok(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", f"Max reply tokens: `{self.config.get('max_tokens')}`", "system")
            return
        try:
            n = int(arg)
            assert 16 <= n <= 200_000
        except (ValueError, AssertionError):
            await self.add_bubble("system", "Usage: `/maxtok 4096` (16–200000)", "error")
            return
        self.config["max_tokens"] = n
        cfg.save_config(self.config)
        await self.add_bubble("system", f"Max reply tokens set to `{n}`.", "system")

    async def cmd_read(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", "Usage: `/read path/to/file.py`", "error")
            return
        path = Path(arg.strip()).expanduser()
        if not path.exists() or not path.is_file():
            await self.add_bubble("system", f"File not found: `{path}`", "error")
            return
        try:
            content = path.read_text(errors="replace")
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not read file: {e}", "error")
            return
        if len(content) > 60_000:
            content = content[:60_000] + "\n... (truncated)"
        block = f"Context from file `{path.name}`:\n```\n{content}\n```"
        self.pending_context.append(block)
        await self.add_bubble(
            "system",
            f"Attached `{path}` ({len(content)} chars) - it will be sent with your next message.",
            "tool",
        )

    async def cmd_write(self, arg: str) -> None:
        if not self._last_assistant_text:
            await self.add_bubble("system", "No previous reply to extract code from yet.", "error")
            return
        bits = arg.split()
        if not bits:
            await self.add_bubble("system", "Usage: `/write path/to/file.py [block_number]`", "error")
            return
        path = Path(bits[0]).expanduser()
        try:
            idx = int(bits[1]) - 1 if len(bits) > 1 else -1
        except ValueError:
            await self.add_bubble("system", f"`{bits[1]}` is not a number. Usage: `/write path [n]`", "error")
            return
        blocks = extract_code_blocks(self._last_assistant_text)
        if not blocks:
            await self.add_bubble("system", "No code blocks found in the last reply.", "error")
            return
        try:
            _, code = blocks[idx]
        except IndexError:
            await self.add_bubble("system", f"Only {len(blocks)} code block(s) in the last reply.", "error")
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not write file: {e}", "error")
            return
        await self.add_bubble("system", f"Wrote {len(code)} chars to `{path}`.", "tool")

    async def cmd_run(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", "Usage: `/run <shell command>`", "error")
            return
        await self.add_bubble("tool", f"$ {arg}", "tool")
        try:
            # run off the UI thread so long commands don't freeze the app
            result = await asyncio.to_thread(
                subprocess.run, arg,
                shell=True, capture_output=True, text=True, timeout=60,
            )
            out = (result.stdout or "") + (result.stderr or "")
            out = out.strip() or "(no output)"
            if len(out) > 4000:
                out = out[:4000] + "\n... (truncated)"
            await self.add_bubble("tool", f"```\n{out}\n```\nexit code: `{result.returncode}`", "tool")
        except subprocess.TimeoutExpired:
            await self.add_bubble("system", "Command timed out after 60s.", "error")
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Failed to run command: {e}", "error")

    async def cmd_clear(self, arg: str) -> None:
        self.action_clear_chat()
        await self.add_bubble("system", "Conversation cleared.", "system")
        self.refresh_statusbar()

    async def cmd_save(self, arg: str) -> None:
        path = cfg.save_session(arg.strip(), self.messages)
        await self.add_bubble("system", f"Session saved to `{path}`.", "tool")

    async def cmd_load(self, arg: str) -> None:
        if not arg:
            await self.add_bubble("system", "Usage: `/load <session-name>`", "error")
            return
        try:
            messages = cfg.load_session(arg.strip())
        except FileNotFoundError:
            await self.add_bubble("system", f"No session named `{arg}` found. See `/sessions`.", "error")
            return
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not load session: {e}", "error")
            return
        self.action_clear_chat()
        self.messages = messages or self.messages
        chat = self.query_one("#chat", VerticalScroll)
        for m in self.messages:
            if m["role"] == "system":
                continue
            css_class = "user" if m["role"] == "user" else "assistant"
            await chat.mount(ChatBubble(m["role"], m["content"], css_class))
        await self.add_bubble("system", f"Loaded session `{arg}`.", "system")
        self.refresh_statusbar()

    async def cmd_sessions(self, arg: str) -> None:
        arg = arg.strip()
        if arg.lower().startswith("rm "):
            name = arg[3:].strip()
            if not name:
                await self.add_bubble("system", "Usage: `/sessions rm <name>`", "error")
                return
            if cfg.delete_session(name):
                await self.add_bubble("system", f"Deleted session `{name}`.", "tool")
            else:
                await self.add_bubble("system", f"No session named `{name}`.", "error")
            return
        sessions = cfg.list_sessions()
        if not sessions:
            await self.add_bubble("system", "No saved sessions yet. Use `/save` to create one.", "system")
            return
        lines = []
        for p in sessions[:30]:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- `{p.stem}` — *{mtime}*")
        await self.add_bubble("system", "**Saved sessions** (newest first):\n\n" + "\n".join(lines), "system")

    async def cmd_tokens(self, arg: str) -> None:
        total = sum(estimate_tokens(m["content"]) for m in self.messages)
        actual = ""
        if self.totals["prompt"]:
            actual = (
                f"\n\nLast reply actual usage: **{self._last_usage.get('prompt_tokens', '?')}** prompt + "
                f"**{self._last_usage.get('completion_tokens', '?')}** completion tokens."
            )
        await self.add_bubble(
            "system",
            f"Approx. **{total}** tokens in context across **{len(self.messages)}** messages "
            f"(rough estimate, not billing-accurate).{actual}",
            "system",
        )

    async def cmd_usage(self, arg: str) -> None:
        t = self.totals
        if not t["requests"]:
            await self.add_bubble("system", "No usage yet in this session.", "system")
            return
        await self.add_bubble(
            "system",
            f"**Session usage**\n\n"
            f"- Requests: **{t['requests']}**\n"
            f"- Prompt tokens: **{t['prompt']:,}**\n"
            f"- Completion tokens: **{t['completion']:,}**\n"
            f"- Total cost: **{format_cost(t['cost'])}**\n\n"
            f"Model: `{self.config['model']}` — figures are provider-reported.",
            "tool",
        )

    async def cmd_retry(self, arg: str) -> None:
        if self.generating:
            await self.add_bubble("system", "Still generating - press **Escape** to stop first.", "system")
            return
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages.pop()
        if not self.messages or self.messages[-1]["role"] != "user":
            await self.add_bubble("system", "Nothing to retry - the last message isn't yours.", "error")
            return
        await self.add_bubble("system", "Regenerating…", "system")
        self.run_generation()

    async def cmd_undo(self, arg: str) -> None:
        if self.generating:
            await self.add_bubble("system", "Still generating - press **Escape** to stop first.", "system")
            return
        removed = 0
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages.pop()
            removed += 1
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
            removed += 1
        if not removed:
            await self.add_bubble("system", "Nothing to undo.", "error")
            return
        chat = self.query_one("#chat", VerticalScroll)
        children = list(chat.children)
        for node in children[-removed:]:
            node.remove()
        await self.add_bubble("system", "Removed the last exchange from context.", "system")
        self.refresh_statusbar()

    async def cmd_compact(self, arg: str) -> None:
        if self.generating:
            await self.add_bubble("system", "Still generating - press **Escape** to stop first.", "system")
            return
        if len(self.messages) < 3:
            await self.add_bubble("system", "Conversation is already tiny - nothing to compact.", "system")
            return
        if not self.config.get("api_key"):
            await self.add_bubble("system", "No API key set. Use `/apikey <key>`.", "error")
            return
        await self.add_bubble("system", "Compacting conversation…", "system")
        try:
            summary, usage = await api.chat_once(
                api_key=self.config["api_key"],
                model=self.config["model"],
                messages=[*self.messages, {"role": "user", "content": COMPACT_PROMPT}],
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Compact failed: {e}", "error")
            return
        before = sum(estimate_tokens(m["content"]) for m in self.messages)
        self.messages = [
            {"role": "system", "content": self.config["system_prompt"]},
            {"role": "user", "content": f"[Context summary of our conversation so far]\n\n{summary}"},
            {"role": "assistant", "content": "Understood - context loaded. Continue whenever you're ready."},
        ]
        after = sum(estimate_tokens(m["content"]) for m in self.messages)
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        await self.add_bubble(
            "system",
            f"**Compacted.** ~{before} → ~{after} estimated tokens.\n\n"
            "Tip: `/export pre-compact.md` next time before compacting keeps a full transcript.",
            "tool",
        )
        self.refresh_statusbar()

    async def cmd_export(self, arg: str) -> None:
        path = Path(arg.strip()).expanduser() if arg.strip() else \
            Path(f"jarvik-chat-{time.strftime('%Y%m%d-%H%M%S')}.md")
        lines = [
            "# JARVIK chat export",
            "",
            f"- Model: `{self.config.get('model')}`",
            f"- Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Messages: {len(self.messages)}",
            "",
            "---",
            "",
        ]
        for m in self.messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                lines.append(f"> **system:** {content}\n")
            elif role == "user":
                lines.append(f"## 🧑 You\n\n{content}\n")
            else:
                lines.append(f"## 🤖 JARVIK\n\n{content}\n")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            await self.add_bubble("system", f"Could not export: {e}", "error")
            return
        await self.add_bubble("system", f"Exported {len(self.messages)} messages to `{path}`.", "tool")

    async def cmd_theme(self, arg: str) -> None:
        arg = arg.strip().lower()
        if not arg:
            listing = "\n".join(
                f"- **`{k}`** — {v['label']}" + (" *(current)*" if k == self.config.get("theme") else "")
                for k, v in cfg.THEMES.items()
            )
            await self.add_bubble("system", f"**Themes** (use `/theme <name>`):\n\n{listing}", "system")
            return
        if arg not in cfg.THEMES:
            await self.add_bubble(
                "system",
                f"Unknown theme `{arg}`. Available: {', '.join(f'`{k}`' for k in cfg.THEMES)}",
                "error",
            )
            return
        self.config["theme"] = arg
        cfg.save_config(self.config)
        self._apply_theme()
        self.refresh_topbar()
        self.refresh_statusbar()
        await self.add_bubble("system", f"Theme switched to **{cfg.THEMES[arg]['label']}**.", "system")

    @work(group="editor", exclusive=True)
    async def _open_multi_editor(self) -> str | None:
        # push_screen_wait must run inside a worker (Textual requirement)
        return await self.push_screen_wait(MultiEditorScreen(""))

    async def cmd_multi(self, arg: str) -> None:
        result = await self._open_multi_editor().wait()
        if result is None or not result.strip():
            await self.add_bubble("system", "Editor closed without sending.", "system")
            return
        text = result.strip()
        self._remember_input(text.splitlines()[0][:120])
        if self.generating:
            await self.add_bubble("system", "Still generating - press **Escape** to stop first.", "system")
            return
        full_text = text
        if self.pending_context:
            ctx = "\n\n".join(self.pending_context)
            full_text = f"{ctx}\n\n{text}"
            self.pending_context.clear()
        await self.add_bubble("user", text, "user")
        self.messages.append({"role": "user", "content": full_text})
        self.refresh_statusbar()
        self.run_generation()

    async def cmd_quit(self, arg: str) -> None:
        self.exit()


def main() -> None:
    JarvikApp().run()


if __name__ == "__main__":
    main()
