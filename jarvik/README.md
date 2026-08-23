# JARVIK

A blue-themed terminal TUI chat client for [OpenRouter](https://openrouter.ai) models,
built with [Textual](https://textual.textualize.io/). Inspired by Claude Code's
workflow: slash commands, file-context injection, shell execution, code-block
extraction, and session save/load — all from a single terminal window.

## Install

```bash
cd jarvik
pip install -r requirements.txt
# or, to get a `jarvik` command on your PATH:
pip install -e .
```

## Run

```bash
python -m jarvik
# or, if installed with `pip install -e .`:
jarvik
```

On first launch, set your OpenRouter API key (get one at https://openrouter.ai/keys):

```
/apikey sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The key is stored locally at `~/.jarvik/config.json` (file permissions restricted
to your user).

## Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/apikey <key>` | Set / update your OpenRouter API key |
| `/model [name]` | Show current model or switch (e.g. `/model anthropic/claude-sonnet-4.5`) |
| `/models [filter]` | Fetch the live model list from OpenRouter, optionally filtered |
| `/system <prompt>` | Set the system prompt |
| `/temp <0.0-2.0>` | Set sampling temperature |
| `/read <path>` | Attach a local file's contents to your next message |
| `/write <path> [n]` | Save the n-th (default last) code block from the last reply to a file |
| `/run <cmd>` | Run a local shell command and show its output in the chat |
| `/clear` | Clear the conversation |
| `/save [name]` | Save the current conversation |
| `/load <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/tokens` | Show an approximate token count for the current context |
| `/quit`, `/exit` | Exit JARVIK |

**Escape** stops a response mid-stream. **Ctrl+L** clears the chat. **Ctrl+C** quits.

## Notes

- Any model listed on [openrouter.ai/models](https://openrouter.ai/models) works —
  just pass its id to `/model`, e.g. `openai/gpt-4o`, `anthropic/claude-sonnet-4.5`,
  `google/gemini-2.5-pro`, `deepseek/deepseek-chat`, etc.
- `/run` executes shell commands directly on your machine using your local
  environment/permissions — use it the same way you'd use a terminal.
- Sessions are stored as JSON under `~/.jarvik/sessions/`.
