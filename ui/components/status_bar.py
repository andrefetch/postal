from __future__ import annotations

from pathlib import Path


STATUS_MIN_WIDTH = 64


def status_bar(
    model_name: str,
    approval_label: str,
    context_ratio: float | None,
    cwd: Path | str | None,
    width: int,
) -> tuple[str, str] | None:
    """Build the compact status bar shown in the prompt footer."""

    if width < STATUS_MIN_WIDTH:
        return None

    directory = Path(cwd).name if cwd else ""
    parts = [
        part
        for part in (directory, model_name.rsplit("/", 1)[-1], approval_label)
        if part
    ]
    style = "status"
    if context_ratio is not None:
        if context_ratio >= 0.9:
            style = "status.danger"
        elif context_ratio >= 0.7:
            style = "status.warn"
        parts.append(f"{context_ratio * 100:.0f}% ctx")

    return (style, f" {' · '.join(parts)} ") if parts else None
