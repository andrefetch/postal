NEUTRALS = {
    "bright": "rgb(226,226,226)",
    "silver": "rgb(176,176,176)",
    "black": "rgb(0,0,0)",
    "graphite": "rgb(124,124,124)",
    "slate": "rgb(94,94,94)",
    "accent": "rgb(184,184,184)",
}

HUES = {
    "blue": "rgb(180,180,180)",
    "green": "rgb(190,190,190)",
    "amber": "rgb(202,202,202)",
    "teal": "rgb(176,176,176)",
    "violet": "rgb(164,164,164)",
    "lilac": "rgb(178,178,178)",
    "orange": "rgb(194,194,194)",
    "magenta": "rgb(184,184,184)",
    "red": "rgb(220,220,220)",
}

PALETTE = {**NEUTRALS, **HUES}

TOOL_COLOURS = {
    "read": PALETTE["blue"],
    "write": PALETTE["green"],
    "bash": PALETTE["amber"],
    "network": PALETTE["teal"],
    "memory": PALETTE["violet"],
    "mcp": PALETTE["lilac"],
    "git": PALETTE["orange"],
    "subagent": PALETTE["magenta"],
}


def rgb_parts(name: str) -> tuple[int, int, int]:
    r, g, b = (int(part) for part in PALETTE[name][4:-1].split(","))
    return r, g, b


def hex_colour(name: str) -> str:

    r, g, b = rgb_parts(name)
    return f"#{r:02x}{g:02x}{b:02x}"


def tool_colour(tool_kind: str | None) -> str:
    return TOOL_COLOURS.get(tool_kind or "", PALETTE["accent"])
