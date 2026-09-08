from __future__ import annotations

from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.styles import Style

from ui.components import PROMPT_MARK, status_bar
from ui.theme import hex_colour

PROMPT_WIDTH = len("│ ") + len(PROMPT_MARK) + len(" ")

PROMPT_STYLE = Style.from_dict(
    {
        "prompt": f"{hex_colour('accent')} bold",
        "frame": hex_colour("slate"),
        "bottom-toolbar": f"noreverse {hex_colour('slate')}",
        "bottom-toolbar.text": f"noreverse {hex_colour('slate')}",
        "approval": f"noreverse {hex_colour('accent')}",
        "approval.warn": f"noreverse {hex_colour('amber')}",
        "approval.danger": f"noreverse bold {hex_colour('red')}",
        "status": f"noreverse {hex_colour('graphite')}",
        "status.warn": f"noreverse {hex_colour('amber')}",
        "status.danger": f"noreverse bold {hex_colour('red')}",
        "completion-menu": "",
        "completion-menu.completion": f"{hex_colour('bright')}",
        "completion-menu.completion.current": f"{hex_colour('accent')} bold",
        "completion-menu.meta.completion": f"{hex_colour('silver')}",
        "completion-menu.meta.completion.current": f"{hex_colour('silver')}",
    }
)

APPROVAL_RISK_CLASSES = {
    "normal": "class:approval",
    "warn": "class:approval.warn",
    "danger": "class:approval.danger",
}


def soft_wrap(text: str, width: int) -> str:
    """Break the buffer at spaces so the frame never has to scroll sideways."""

    if width < 1:
        return text

    chars = list(text)
    line_start = 0
    last_space = -1
    i = 0

    while i < len(chars):
        if chars[i] == " ":
            last_space = i
        if i - line_start + 1 > width and last_space > line_start:
            chars[last_space] = "\n"
            line_start = last_space + 1
            last_space = -1
            i = line_start
            continue
        i += 1

    return "".join(chars)


def status_readout(
    model_name: str,
    context_ratio: float | None,
    width: int,
    approval_label: str = "",
    cwd: str | None = None,
) -> tuple[str, str] | None:
    """The right-hand side of the frame's foot."""

    return status_bar(model_name, approval_label, context_ratio, cwd, width)


def prompt_fragments(
    width: int, expansion: StyleAndTextTuples | None = None
) -> StyleAndTextTuples:
    top = "╭" + "─" * (width - 2) + "╮\n"
    return [
        *(expansion or []),
        ("class:frame", top),
        ("class:frame", "│ "),
        ("class:prompt", f"{PROMPT_MARK} "),
    ]


def continuation_fragments(width: int) -> StyleAndTextTuples:
    return [("class:frame", "│"), ("", " " * (width - 1))]


def bottom_fragments(
    width: int,
    badge: str,
    risk: str,
    readout: tuple[str, str] | None = None,
) -> StyleAndTextTuples:
    badge = f" {badge} "

    trailing = width - 3 - len(badge)
    if trailing < 1:
        return [("class:frame", "╰" + "─" * (width - 2) + "╯")]

    fragments: StyleAndTextTuples = [
        ("class:frame", "╰─"),
        (APPROVAL_RISK_CLASSES.get(risk, "class:approval"), badge),
    ]

    if readout is not None and trailing - len(readout[1]) >= 2:
        style, text = readout
        fragments.append(("class:frame", "─" * (trailing - len(text))))
        fragments.append((f"class:{style}", text))
        fragments.append(("class:frame", "╯"))
        return fragments

    fragments.append(("class:frame", "─" * trailing + "╯"))
    return fragments
