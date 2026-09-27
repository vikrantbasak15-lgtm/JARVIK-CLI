"""Minimal probe to find where the smoke test hangs."""

import faulthandler
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# if we hang anywhere, dump every thread's stack and hard-exit so the log survives
faulthandler.dump_traceback_later(25, exit=True)

os.environ["JARVIK_HOME"] = tempfile.mkdtemp(prefix="jarvik-probe-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jarvik.api as real_api  # noqa: E402
from jarvik.app import JarvikApp  # noqa: E402


async def fake_stream(*args, **kwargs):
    for chunk in ["Hello ", "world"]:
        yield chunk
    u = kwargs.get("usage")
    if u is not None:
        u.update({"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0001})


async def fake_chat_once(*args, **kwargs):
    return "Summary.", {"prompt_tokens": 100, "completion_tokens": 10}


real_api.stream_chat = fake_stream
real_api.chat_once = fake_chat_once
real_api.fetch_models = fake_chat_once  # unused here
real_api.fetch_credits = fake_chat_once  # unused here


async def run_case(step_name: str, coro_factory, timeout: float = 10.0) -> None:
    print(f"--- {step_name} ---", flush=True)
    app = JarvikApp()
    try:
        async with asyncio.timeout(timeout):
            async with app.run_test(size=(110, 40)) as pilot:
                await coro_factory(app, pilot)
        print(f"    {step_name}: OK", flush=True)
    except BaseException as e:  # noqa: BLE001
        print(f"    {step_name}: FAILED -> {type(e).__name__}: {e}", flush=True)


async def case_plain(app, pilot):
    await pilot.pause()


async def case_cmd(app, pilot):
    inp = app.query_one("#input")
    inp.value = "/help"
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause(0.2)


async def case_chat(app, pilot):
    inp = app.query_one("#input")
    inp.value = "hello"
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause(0.5)
    print(f"    last msg role={app.messages[-1]['role']} content={app.messages[-1]['content']!r}", flush=True)


async def case_multi(app, pilot):
    inp = app.query_one("#input")
    inp.value = "/multi"
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause(0.5)
    print(f"    screen_stack={[type(s).__name__ for s in app.screen_stack]}", flush=True)
    await pilot.press("h", "i")
    await pilot.pause(0.2)
    print(f"    pressing ctrl+s", flush=True)
    await pilot.press("ctrl+s")
    await pilot.pause(0.5)
    print(f"    after ctrl+s, last role={app.messages[-1]['role']}", flush=True)


async def case_multi_escape(app, pilot):
    inp = app.query_one("#input")
    inp.value = "/multi"
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause(0.5)
    print(f"    pressing escape", flush=True)
    await pilot.press("escape")
    await pilot.pause(0.5)
    print(f"    after escape, stack={[type(s).__name__ for s in app.screen_stack]}", flush=True)


async def main():
    for name, factory in [
        ("plain boot", case_plain),
        ("/help", case_cmd),
        ("chat", case_chat),
        ("multi+ctrl+s", case_multi),
        ("multi+escape", case_multi_escape),
    ]:
        await run_case(name, factory)
    print("PROBE DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
