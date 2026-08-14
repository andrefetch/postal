import random

REASONING_LABEL = "Thinking"

THINKING_WORDS = [
    "Thinking…",
    "Working…",
    "Fluctuating…",
    "Writing…",
    "Typing…",
    "Helping…",
]

TOOL_THINKING_WORDS = {
    "read": "Reading…",
    "write": "Writing…",
    "edit": "Editing…",
    "apply_patch": "Patching…",
    "bash": "Running…",
    "list_dir": "Looking around…",
    "grep": "Searching…",
    "glob": "Searching…",
    "search": "Searching…",
    "fetch": "Fetching…",
    "plan": "Planning…",
    "memory": "Remembering…",
}

KIND_THINKING_WORDS = {
    "read": "Reading…",
    "write": "Editing…",
    "bash": "Running…",
    "network": "Fetching…",
    "memory": "Remembering…",
    "mcp": "Working…",
    "git": "Checking git…",
    "subagent": "Delegating…",
}


def random_thinking_text() -> str:
    return random.choice(THINKING_WORDS)


def thinking_text_for(tool_name: str, tool_kind: str | None = None) -> str:
    if tool_name in TOOL_THINKING_WORDS:
        return TOOL_THINKING_WORDS[tool_name]
    return KIND_THINKING_WORDS.get(tool_kind or "", random_thinking_text())
