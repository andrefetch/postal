from __future__ import annotations

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from ui.format import diff_stat_text
from ui.theme import POSTAL_SYNTAX


def diff_viewer(
    diff: str,
    path: str | None = None,
    *,
    max_lines: int | None = None,
) -> Panel:
    """Render a labeled, syntax-highlighted unified diff."""

    lines = diff.splitlines()
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… {len(lines) - max_lines} more lines"]

    title = Text(path or "diff", style="highlight")
    title.append("  ")
    title.append_text(diff_stat_text(diff))
    return Panel(
        Syntax(
            "\n".join(lines).strip(),
            "diff",
            theme=POSTAL_SYNTAX,
            word_wrap=True,
            background_color="default",
        ),
        title=title,
        border_style="border",
        padding=(0, 1),
    )
