NEUTRALS = {
    "bright": "rgb(226,228,234)",
    "silver": "rgb(176,180,188)",
    "graphite": "rgb(120,124,132)",
    "slate": "rgb(88,94,104)",
    "accent": "rgb(130,150,180)",
}

HUES = {
    "blue": "rgb(116,160,216)",
    "green": "rgb(122,190,140)",
    "amber": "rgb(214,170,102)",
    "teal": "rgb(96,188,180)",
    "violet": "rgb(160,144,220)",
    "lilac": "rgb(198,148,214)",
    "orange": "rgb(218,140,98)",
    "magenta": "rgb(206,128,172)",
    "red": "rgb(216,96,96)",
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
