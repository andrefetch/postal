from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base import Tool


def get_tool_guidelines_section(tools: list["Tool"]) -> str:
    """Generate tool usage guidelines."""

    regular_tools = [t for t in tools if not t.name.startswith("subagent_")]
    subagent_tools = [t for t in tools if t.name.startswith("subagent_")]

    guidelines = """# Tool Usage Guidelines

You have access to the following tools to accomplish your tasks:

"""

    for tool in regular_tools:
        description = tool.description
        if len(description) > 100:
            description = description[:100] + "..."
        guidelines += f"- **{tool.name}**: {description}\n"

    if subagent_tools:
        guidelines += "\n## Sub-Agents\n\n"
        for tool in subagent_tools:
            description = tool.description
            if len(description) > 100:
                description = description[:100] + "..."
            guidelines += f"- **{tool.name}**: {description}\n"

    guidelines += """
## Best Practices

1. **File Operations**:
   - Use `read_file` before editing to understand current content
   - Use `edit` for surgical changes (search/replace)
   - Use `write_file` for creating new files or complete rewrites
   - Use `apply_patch` when a change spans 2 or more files, instead of several
     `edit` calls: it creates, updates, deletes and renames in one batch and
     writes nothing unless every operation applies cleanly

2. **Search and Discovery**:
   - Use `grep` to find code by content
   - Use `glob` to find files by name pattern
   - Use `list_dir` to explore directory structure

3. **Shell Commands**:
   - Use `bash` for running commands, tests, builds
   - Prefer read-only commands when just gathering information
   - Be cautious with commands that modify state

4. **Task Management**:
   - Use `plan` (the todo list) to track multi-step tasks
   - Mark tasks as completed as you finish them

5. **Memory**:
   - Use `memory` to store important user preferences
   - Retrieve stored preferences when relevant"""

    if subagent_tools:
        guidelines += """
6. **Sub-Agents**:
   - Use sub-agents for complex codebase exploration, code review, or specialized multi-step tasks
   - Sub-agents run with isolated context and have limited tool access
   - Provide clear, specific goals when invoking sub-agents
   - For simple queries (like finding a specific function), use direct tools (`grep`, `read_file`) instead
   - Use sub-agents when the task involves complex refactoring, codebase exploration, or system-wide analysis"""

    return guidelines
