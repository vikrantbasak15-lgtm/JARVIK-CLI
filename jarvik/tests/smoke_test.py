"""
Headless smoke test for JARVIK.

Runs the real Textual app with a fake OpenRouter API and exercises every
slash command. Run from the jarvik/ directory:

    python tests/smoke_test.py

Uses JARVIK_HOME so the user's real ~/.jarvik is never touched.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# isolated config home so we never touch the real ~/.jarvik
TEST_HOME = tempfile.mkdtemp(prefix="jarvik-test-")
os.environ["JARVIK_HOME"] = TEST_HOME

# make the `jarvik` package importable (repo/jarvik)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jarvik.api as real_api  # noqa: E402
from jarvik.app import JarvikApp  # noqa: E402
from jarvik import config as cfg  # noqa: E402


# ----------------------------------------------------------- fake API ----

async def fake_stream(*args, **kwargs):
    for chunk in ["Hello ", "world ", "!\n\n```python\nprint('hi')\n```"]:
        yield chunk
    usage = kwargs.get("usage")
    if usage is not None:
        usage.update({"prompt_tokens": 42, "completion_tokens": 13, "cost": 0.000321})


async def fake_chat_once(*args, **kwargs):
    return "Summary of the conversation so far.", {"prompt_tokens": 500, "completion_tokens": 40}


async def fake_fetch_models(api_key=""):
    return [{"id": "openai/gpt-4o-mini"}, {"id": "anthropic/claude-sonnet-4.5"}]


async def fake_fetch_credits(api_key):
    return {"label": "test-key", "usage": 1.25, "limit": 10.0, "is_free_tier": False}


real_api.stream_chat = fake_stream
real_api.chat_once = fake_chat_once
real_api.fetch_models = fake_fetch_models
real_api.fetch_credits = fake_fetch_credits


# ------------------------------------------------------------- tests ----

async def main() -> int:
    app = JarvikApp()
    failures: list[str] = []

    def check(cond, msg):
        if cond:
            print(f"  ok  - {msg}")
        else:
            failures.append(msg)
            print(f"  FAIL - {msg}")

    async with app.run_test(size=(110, 40)) as pilot:
        async def send(cmd: str) -> None:
            inp = app.query_one("#input")
            inp.value = cmd
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        print("== simple commands ==")
        for cmd in [
            "/help", "/model", "/model openai/gpt-4o",
            "/temp 0.5", "/temp 9", "/maxtok 2048", "/maxtok abc",
            "/theme", "/theme matrix", "/theme blue",
            "/keyinfo", "/models gpt", "/usage", "/tokens",
            "/read README.md", "/read missing-file.xyz",
            "/write", "/undo", "/retry", "/unknowncmd",
        ]:
            await send(cmd)
        await pilot.pause(0.2)

        check(app.config["model"] == "openai/gpt-4o", "/model switch applied")
        check(app.config["temperature"] == 0.5, "/temp applied")
        check(app.config["max_tokens"] == 2048, "/maxtok applied")
        check(app.config["theme"] == "blue", "/theme switch + back applied")
        vars_now = app.get_css_variables()
        check(vars_now.get("screen-bg") == cfg.THEMES["blue"]["screen_bg"],
              "theme CSS variables applied")

        print("== chat generation ==")
        await send("Hi there, how are you?")
        await pilot.pause(0.3)
        last = app.messages[-1]
        check(last["role"] == "assistant", "assistant reply appended")
        check("Hello world" in last["content"], "streamed content captured")
        check(app.totals["requests"] >= 1, "usage totals updated")
        check(app.totals["cost"] > 0, "cost tracked from usage chunk")
        check(len(app.history) > 0, "input history recorded")

        print("== /write extracts code block ==")
        await send("/write out.py")
        await pilot.pause(0.2)
        out = Path("out.py")
        check(out.exists() and "print('hi')" in out.read_text(encoding="utf-8"),
              "code block written to file")
        out.unlink(missing_ok=True)

        print("== /run shell ==")
        await send("/run echo jarvik-smoke")
        await pilot.pause(0.5)

        print("== sessions ==")
        await send("/save smoke-session")
        await pilot.pause(0.2)
        check((Path(TEST_HOME) / "sessions" / "smoke-session.json").exists(),
              "session saved to JARVIK_HOME")
        await send("/sessions")
        await send("/load smoke-session")
        await pilot.pause(0.3)
        check(len(app.messages) >= 3, "session loaded back into context")
        await send("/sessions rm smoke-session")
        await pilot.pause(0.2)
        check(not (Path(TEST_HOME) / "sessions" / "smoke-session.json").exists(),
              "session deleted via /sessions rm")

        print("== /export ==")
        export_path = Path(TEST_HOME) / "export-test.md"
        await send(f"/export {export_path}")
        await pilot.pause(0.2)
        check(export_path.exists() and "JARVIK chat export" in export_path.read_text(encoding="utf-8"),
              "conversation exported as markdown")

        print("== /compact ==")
        app.config["api_key"] = "test-key"  # fake API is patched; no real call
        n_before = len(app.messages)
        await send("/compact")
        await pilot.pause(0.3)
        check(len(app.messages) == 3, "compact collapses context to 3 messages")
        check("Context summary" in app.messages[1]["content"], "compact summary inserted")
        check(n_before >= 3, "compact saw prior messages")

        print("== /multi editor ==")
        await send("/multi")
        await pilot.pause(0.2)
        await pilot.press("h", "i", "ctrl+s")
        await pilot.pause(0.3)
        check(app.messages[-1]["role"] == "assistant", "multiline prompt sent and answered")

        print("== /undo ==")
        await send("/undo")
        await pilot.pause(0.2)
        check(app.messages[-1]["role"] != "user", "/undo removed last exchange")

        print("== history files ==")
        hist = Path(TEST_HOME) / "history.json"
        check(hist.exists(), "persistent history file created")
        check((Path(TEST_HOME) / "config.json").exists(), "config file created in JARVIK_HOME")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
