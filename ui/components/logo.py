from rich.text import Text

from ui.theme.palette import PALETTE

POSTAL_VERSION = "0.0.32"

CLOUD_PIXELS = (
    "..###...",
    ".######.",
    "########",
)
_PIXEL = "██"

POSTAL_BLOB = tuple(
    "".join(_PIXEL if cell == "#" else "  " for cell in row) for row in CLOUD_PIXELS
)

LOGO_WIDTH = max(len(row) for row in POSTAL_BLOB)
LOGO_HEIGHT = len(POSTAL_BLOB)

_BODY = PALETTE["bright"]

_SILVER = (168, 174, 186)


def small_wordmark(justify: str = "center") -> Text:
    r, g, b = _SILVER
    return Text(" ".join("postal"), style=f"rgb({r},{g},{b})", justify=justify, no_wrap=True)


def logo() -> Text:
    text = Text(no_wrap=True)
    for i, row in enumerate(POSTAL_BLOB):
        for char in row:
            text.append(char, style=_BODY if char != " " else None)
        if i != LOGO_HEIGHT - 1:
            text.append("\n")
    return text
