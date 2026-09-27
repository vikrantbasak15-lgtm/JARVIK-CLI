"""Small stateless helpers shared across the app."""

import re

CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+\-]*)\n(.*?)```", re.DOTALL)


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Return list of (language, code) tuples found in a markdown string."""
    return [(lang or "text", code) for lang, code in CODE_BLOCK_RE.findall(text)]


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) used only for the /tokens display."""
    return max(1, len(text) // 4)


def truncate(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def format_cost(cost: float | int | None) -> str:
    """Format a USD cost for display: $0 free, sub-cent amounts in micro-dollars."""
    if cost is None:
        return "—"
    if cost == 0:
        return "$0"
    if cost < 0.01:
        return f"${cost * 1_000_000:,.0f}µ"
    return f"${cost:,.4f}"


def format_elapsed(seconds: float) -> str:
    """Human-friendly elapsed time: 12.3s / 1m04s."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"
