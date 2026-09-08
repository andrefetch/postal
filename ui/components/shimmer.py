from rich.text import Text

from ui.format import split_tool_name
from ui.theme import rgb_parts

SHIMMER_BASE = rgb_parts("silver")
SHIMMER_PEAK = (255, 255, 255)
SHIMMER_WIDTH = 3.0
SHIMMER_SPEED = 0.4
SHIMMER_GAP = 10

SHIMMERING_KINDS = frozenset({"subagent"})


def shimmers(tool_kind: str | None) -> bool:
    return (tool_kind or "") in SHIMMERING_KINDS


def shimmer(label: str, frame: int) -> Text:
    head = (frame * SHIMMER_SPEED) % (len(label) + SHIMMER_GAP)
    text = Text()
    for index, char in enumerate(label):
        weight = max(0.0, 1.0 - (abs(index - head) / SHIMMER_WIDTH) ** 2)
        r, g, b = (
            round(base + (peak - base) * weight)
            for base, peak in zip(SHIMMER_BASE, SHIMMER_PEAK)
        )
        text.append(char, style=f"bold rgb({r},{g},{b})")
    return text


def shimmer_tool_label(name: str, frame: int) -> Text:
    label, variant = split_tool_name(name)
    text = shimmer(label, frame)
    if variant:
        text.append(": ", style="muted")
        text.append(variant, style="muted")
    return text
