"""
JARVIK — a blue-themed terminal chat client for OpenRouter models.

Inspired by Claude Code: slash commands, file context injection, shell
execution, code-block extraction, session save/load, and streaming replies.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Input, Markdown, Static

from . import config as cfg
from . import api
from .utils import extract_code_blocks, estimate_tokens, truncate

APP_VERSION = "1.0.0"

BANNER = r"""
  ###   ###   ####   #   #  #####  #   #
    #  #   #  #   #  #   #    #    #  #
    #  #   #  #   #  #   #    #    # #
    #  #####  ####   #   #    #    ##
    #  #   #  #  #   #   #    #    # #
#   #  #   #  #   #   # #     #    #  #
 ###   #   #  #   #    #    #####  #   #
"""

HELP_TEXT = """\
### JARVIK commands

| Command | Description |
|---|---|
| `/help` | Show this help |
| `/apikey <key>` | Set / update your OpenRouter API key |
| `/model [name]` | Show current model, list suggestions, or switch model |
| `/models` | Fetch the live model list from OpenRouter |
| `/system <prompt>` | Set the system prompt |
| `/temp <0.0-2.0>` | Set sampling temperature |
| `/read <path>` | Attach a local file's contents as context for your next message |
| `/write <path> [n]` | Save the n-th (default last) code block from the last reply to a file |
| `/run <shell cmd>` | Run a local shell command and show its output |
| `/clear` | Clear the conversation |
| `/save [name]` | Save the current conversation to a session file |
| `/load <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/tokens` | Show an approximate token usage count |
| `/quit`, `/exit` | Exit JARVIK |

Press **Escape** to stop a response that's generating.
Press **Ctrl+L** to clear the screen. **Ctrl+C** to quit.
"""

BLUE_CSS = """
Screen {
    background: #040912;
    color: #dce9ff;
    scrollbar-color: #2f6fce #0a1730;
    scrollbar-color-hover: #4da3ff #0a1730;
    scrollbar-color-active: #6fb3ff #0a1730;
    scrollbar-size: 1 1;
}

#topbar {
    dock: top;
    height: 3;
    background: #081b36;
    color: #7fc0ff;
    content-align: center middle;
    text-style: bold;
    border-bottom: tall #2f6fce;
}

#chat {
    background: #040912;
    padding: 1 3;
}

.bubble {
    margin: 0 0 1 0;
    padding: 1 2;
    border: round #163361;
    background: #071429;
    width: 100%;
}

.bubble.user {
    border: round #3a7bdb;
    background: #0d2246;
    color: #f0f6ff;
    margin-left: 6;
}

.bubble.assistant {
    border: round #1c4a8c;
    background: #05101f;
    color: #dbe8ff;
    margin-right: 6;
}

.bubble.system {
    border: round #294159;
    background: #0a1622;
    color: #93a8c2;
    margin-right: 6;
}

.bubble.tool {
    border: round #2e8f63;
    background: #061913;
    color: #b7ecd3;
    margin-right: 6;
}

.bubble.banner {
    border: heavy #4da3ff;
    background: #071a33;
    color: #eaf3ff;
}

.bubble.banner .role-label {
    color: #7fc0ff;
}

.bubble.error {
    border: round #d1483a;
    background: #240b0a;
    color: #ffb9ae;
    margin-right: 6;
}

.role-label {
    text-style: bold;
    color: #4da3ff;
    margin-bottom: 0;
}

.bubble.user .role-label {
    color: #9dcbff;
}

.bubble.assistant .role-label {
    color: #58a6ff;
}

.bubble.system .role-label {
    color: #6f88a6;
}

.bubble.tool .role-label {
    color: #4fd693;
}

.bubble.error .role-label {
    color: #ff8f82;
}

#input-bar {
    dock: bottom;
    height: auto;
    background: #081b36;
    border-top: tall #2f6fce;
    padding: 1 2;
}

Input {
    background: #0d2246;
    color: #f0f6ff;
    border: round #3a7bdb;
    padding: 0 1;
}

Input:focus {
    border: round #58a6ff;
    background: #102a54;
}

Footer {
    background: #081b36;
    color: #6fb3ff;
}

Footer > .footer--key {
    color: #58a6ff;
    text-style: bold;
}

Footer > .footer--description {
    color: #7fa8d9;
}
"""


class ChatBubble(Static):
    """A single message rendered as a rounded bubble with a role label."""

    def __init__(self, role: str, text: str, css_class: str | None = None):
        super().__init__()
        self.role = role
        self._text = text
        self.css_class = css_class or role

    def compose(self) -> ComposeResult:
        label = {
            "user": "YOU",
            "assistant": "JARVIK",
            "system": "SYSTEM",
            "tool": "SHELL",
            "error": "ERROR",
        }.get(self.css_class, self.role)
        yield Static(f"[b]{label}[/b]", classes="role-label", markup=True)
        yield Markdown(self._text, id="md")

    def on_mount(self) -> None:
        self.add_class("bubble")
        self.add_class(self.css_class)

    async def update_text(self, text: str) -> None:
        self._text = text
        try:
            await self.query_one("#md", Markdown).update(text)
        except Exception:
            pass


class JarvikApp(App):
    CSS = BLUE_CSS
    TITLE = "JARVIK"

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "stop_generation", "Stop"),
    ]

    generating: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.config = cfg.load_config()
        self.messages: list[dict] = [
            {"role": "system", "content": self.config["system_prompt"]}
        ]
        self.pending_context: list[str] = []
        self._current_worker = None
        self._last_assistant_text = ""

    # ---------------------------------------------------------- layout ----

    def compose(self) -> ComposeResult:
        yield Static(self._topbar_text(), id="topbar")
        yield VerticalScroll(id="chat")
        yield Container(
            Input(placeholder="Message JARVIK…  (try /help)", id="input"),
            id="input-bar",
        )
        yield Footer()

    def _topbar_text(self) -> str:
        model = self.config.get("model", "?")
        key_state = "key set" if self.config.get("api_key") else "no key -- /apikey"
        return f"JARVIK  |  v{APP_VERSION}  |  model: {model}  |  {key_state}"

    def on_mount(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        intro = f"```\n{BANNER.strip(chr(10))}\n```\n\n" \
                "Welcome to **JARVIK** - your blue-glowing terminal AI.\n\n" \
                "Type a message to chat, or `/help` to see everything I can do."
        if not self.config.get("api_key"):
            intro += "\n\n**No OpenRouter API key set.** Run `/apikey sk-or-...` to get started."
        chat.mount(ChatBubble("system", intro, "banner"))
        self.query_one(Input).focus()

    # -------------------------------------------------------- utilities ----

    def refresh_topbar(self) -> None:
        self.query_one("#topbar", Static).update(self._topbar_text())

    async def add_bubble(self, role: str, text: str, css_class: str | None = None) -> ChatBubble:
        chat = self.query_one("#chat", VerticalScroll)
        bubble = ChatBubble(role, text, css_class)
        await chat.mount(bubble)
        chat.scroll_end(animate=False)
        return bubble

    # ------------------------------------------------------------ input ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.startswith("/"):
            await self.handle_command(text)
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
        self.run_generation()

    # ------------------------------------------------------- generation ----

    @work(exclusive=True, group="stream")
    async def run_generation(self) -> None:
        self.generating = True
        bubble = await self.add_bubble("assistant", "▌", "assistant")
        acc = ""
        last_update = 0.0
        try:
            async for chunk in api.stream_chat(
                api_key=self.config["api_key"],
                model=self.config["model"],
                messages=self.messages,
                temperature=float(self.config.get("temperature", 0.7)),
                max_tokens=int(self.config.get("max_tokens", 4096)),
            ):
                acc += chunk
                now = time.monotonic()
                if now - last_update > 0.05:  # throttle re-render for smoothness
                    await bubble.update_text(acc + " ▌")
                    last_update = now
            await bubble.update_text(acc if acc else "*(empty response)*")
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
            self.generating = False
            self.query_one("#chat", VerticalScroll).scroll_end(animate=False)

    def action_stop_generation(self) -> None:
        if self.generating:
            for w in self.workers:
                if w.group == "stream":
                    w.cancel()

    def action_clear_chat(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self.messages = [{"role": "system", "content": self.config["system_prompt"]}]

    # ------------------------------------------------------- commands ----

    async def handle_command(self, raw: str) -> None:
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": self.cmd_help,
            "/apikey": self.cmd_apikey,
            "/model": self.cmd_model,
            "/models": self.cmd_models,
            "/system": self.cmd_system,
            "/temp": self.cmd_temp,
            "/read": self.cmd_read,
            "/write": self.cmd_write,
            "/run": self.cmd_run,
            "/clear": self.cmd_clear,
            "/save": self.cmd_save,
            "/load": self.cmd_load,
            "/sessions": self.cmd_sessions,
            "/tokens": self.cmd_tokens,
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
        await self.add_bubble("system", f"Temperature set to `{t}`.", "system")

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
        idx = int(bits[1]) - 1 if len(bits) > 1 else -1
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
            result = subprocess.run(
                arg, shell=True, capture_output=True, text=True, timeout=60
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
        self.action_clear_chat()
        self.messages = messages or self.messages
        chat = self.query_one("#chat", VerticalScroll)
        for m in self.messages:
            if m["role"] == "system":
                continue
            css_class = "user" if m["role"] == "user" else "assistant"
            await chat.mount(ChatBubble(m["role"], m["content"], css_class))
        await self.add_bubble("system", f"Loaded session `{arg}`.", "system")

    async def cmd_sessions(self, arg: str) -> None:
        sessions = cfg.list_sessions()
        if not sessions:
            await self.add_bubble("system", "No saved sessions yet. Use `/save` to create one.", "system")
            return
        listing = "\n".join(f"- `{p.stem}`" for p in sessions[:30])
        await self.add_bubble("system", f"**Saved sessions:**\n\n{listing}", "system")

    async def cmd_tokens(self, arg: str) -> None:
        total = sum(estimate_tokens(m["content"]) for m in self.messages)
        await self.add_bubble(
            "system",
            f"Approx. **{total}** tokens in context across **{len(self.messages)}** messages "
            f"(rough estimate, not billing-accurate).",
            "system",
        )

    async def cmd_quit(self, arg: str) -> None:
        self.exit()


def main() -> None:
    JarvikApp().run()


if __name__ == "__main__":
    main()
