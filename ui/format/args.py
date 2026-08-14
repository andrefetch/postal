from typing import Any, Tuple

HEADLINE_KEYS = ("path", "command", "pattern", "url", "query", "action")

BULKY_KEYS = frozenset({"content", "old_string", "new_string", "patch"})

ARG_ORDER = {
    "read": ["path", "offset", "limit"],
    "write": ["path", "create_directories", "content"],
    "edit": ["path", "replace_all", "old_string", "new_string"],
    "apply_patch": ["dry_run", "patch"],
    "bash": ['command', 'timeout', 'cwd'],
    "list_dir": ['path', 'include_hidden'],
    "grep": ['path', 'case_insensitive', 'pattern'],
    "glob": ['path', 'pattern'],
    "plan": ['action', 'id', 'content'],
    "memory": ['action', 'key', 'value'],
}

HEADLINE_MAX_WIDTH = 64

SUBAGENT_PREFIX = "subagent_"


def split_tool_name(name: str) -> tuple[str, str | None]:
    if not name.startswith(SUBAGENT_PREFIX):
        return name, None
    return "subagent", name[len(SUBAGENT_PREFIX):].replace("_", " ")


def ordered_args(tool_name: str, args: dict[str, Any]) -> list[Tuple[str, Any]]:
    preferred = ARG_ORDER.get(tool_name, [])
    ordered: list[Tuple[str, Any]] = []
    seen: set[str] = set()

    for key in preferred:
        if key in args:
            ordered.append((key, args[key]))
            seen.add(key)

    ordered.extend((key, args[key]) for key in sorted(args.keys() - seen))
    return ordered


def summarise_value(key: str, value: Any) -> str:
    if isinstance(value, str) and key in BULKY_KEYS:
        line_count = len(value.splitlines())
        byte_count = len(value.encode("utf-8", errors="replace"))
        return f"{line_count} lines ┈ {byte_count} bytes"

    if isinstance(value, bool):
        value = str(value)

    return str(value)


def headline(args: dict[str, Any]) -> tuple[str, str] | None:
    for key in HEADLINE_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            first_line = value.strip().splitlines()[0]
            if len(first_line) > HEADLINE_MAX_WIDTH:
                first_line = f"{first_line[:HEADLINE_MAX_WIDTH - 1]}…"
            return key, first_line
    return None


def secondary_args(args: dict[str, Any], headline_key: str | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in args.items()
        if key != headline_key and not (key == "cwd" and value == ".")
    }
