from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.text import Text

from tools.base import ToolConfirmation
from ui.components.args_table import render_args_table
from ui.components.diff_viewer import diff_viewer
from ui.components.permission_prompt import permission_prompt
from utils.paths import display_path_relative_to_cwd

MAX_CONFIRM_DIFF_LINES = 20

APPROVE_KEYS = {"y", "a"}
REJECT_KEYS = {"n", "d", "q"}


def confirmation_body(
    confirmation: ToolConfirmation, cwd: Path | str | None = None
) -> Group:
    blocks: list[Any] = []

    if confirmation.command:
        blocks.append(Text(f"$ {confirmation.command}", style="code"))

    if confirmation.diff is not None:
        # The file header is redundant here: the path is already in the title.
        lines = [
            line
            for line in confirmation.diff.create_diff().splitlines()
            if not line.startswith(("--- ", "+++ "))
        ]
        if len(lines) > MAX_CONFIRM_DIFF_LINES:
            hidden = len(lines) - MAX_CONFIRM_DIFF_LINES
            lines = lines[:MAX_CONFIRM_DIFF_LINES] + [f"… {hidden} more lines"]
        diff = "\n".join(lines).strip()
        if diff:
            blocks.append(
                diff_viewer(
                    diff,
                    display_path_relative_to_cwd(
                        str(confirmation.diff.path), Path(cwd) if cwd else None
                    ),
                )
            )

    if not blocks:
        blocks.append(render_args_table(confirmation.tool_name, confirmation.params))

    return Group(*blocks)


def confirmation_request(
    confirmation: ToolConfirmation, cwd: Path | str | None = None
) -> list[Any]:
    """Title, description and body, ready to print in order."""

    return permission_prompt(confirmation, cwd)


def confirmation_choices(badge: str) -> Text:
    choices = Text()
    choices.append("y", style="success")
    choices.append(" accept", style="muted")
    choices.append("  ·  ", style="dim")
    choices.append("n", style="error")
    choices.append(" reject", style="muted")
    choices.append("  ·  ", style="dim")
    choices.append("esc", style="subtitle")
    choices.append(" reject", style="muted")
    choices.append("   ", style="dim")
    choices.append(badge, style="muted")
    return choices
