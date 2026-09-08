from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.box import ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from tools.base import ToolConfirmation
from utils.paths import display_path_relative_to_cwd


def permission_prompt(
    confirmation: ToolConfirmation, cwd: Path | str | None = None
) -> list[Any]:
    """Build the approval prompt for a tool requiring user permission."""

    from ui.components.confirmation import confirmation_body

    border = "error" if confirmation.is_dangerous else "warning"
    title = Text.assemble(
        ("⏵ ", border),
        (confirmation.tool_name, "highlight"),
        ("  permission required", "subtitle"),
    )
    if confirmation.is_dangerous:
        title.append("  (dangerous)", style="error")

    description = confirmation.description
    if cwd:
        description = description.replace(f"{cwd}/", "")

    body: Any = confirmation_body(confirmation, cwd)
    if confirmation.affected_paths:
        paths = Text("Affects: ", style="muted")
        paths.append(
            ", ".join(
                display_path_relative_to_cwd(str(path), Path(cwd) if cwd else None)
                for path in confirmation.affected_paths
            ),
            style="code",
        )
        body = Group(body, paths)

    return [
        title,
        Text(description, style="muted"),
        Panel(body, box=ROUNDED, border_style=border, padding=(0, 1)),
    ]


def permission_choices(badge: str) -> Text:
    """Render the keyboard hints below a permission prompt."""

    from ui.components.confirmation import confirmation_choices

    return confirmation_choices(badge)
