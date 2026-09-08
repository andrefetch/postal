from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from ui.components.shimmer import shimmer_tool_label, shimmers


def tool_progress_panel(
    name: str,
    elapsed: int,
    progress: str = "",
    *,
    tool_kind: str | None = None,
    headline: str | None = None,
    spinner: str = "⠋",
    frame: int = 0,
) -> Panel:
    """Render the compact live panel shown while a tool is running."""

    line = Text.assemble((f"{spinner} ", "tool"))
    if shimmers(tool_kind):
        line.append_text(shimmer_tool_label(name, frame))
    else:
        line.append(name, style="highlight")
    if headline:
        line.append("  ")
        line.append(headline, style="subtitle")
    line.append(f" {elapsed}s", style="muted")
    if progress:
        line.append(" › ", style="dim")
        line.append(progress, style="muted")

    border = f"tool.{tool_kind}" if tool_kind else "tool"
    return Panel(line, border_style=border, padding=(0, 1))
