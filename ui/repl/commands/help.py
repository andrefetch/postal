from __future__ import annotations

from rich.markdown import Markdown

from agent.agent import Agent
from ui.repl.commands.base import CommandGroup

HELP_TEXT = """\
## Commands

- `/help` - Show this help
- `/exit` or `/quit` - Exit the agent
- `/clear` - Clear conversation history for a fresh start (old session is still saved)
- `/config` - Show current configuration options and their values
- `/model <name>` - Change the model mid-session (e.g. `/model gpt-4o` or `/model anthropic/claude-sonnet-4.5`)
- `/approval <mode>` - Change approval mode (e.g. `/approval yolo` or `/approval auto_edit`)
- `/thinking [on|off|low|medium|high]` - Show or configure model reasoning (e.g. `/thinking high`)
- `/stats` - Show session statistics (token counts, time elapsed, tool calls)
- `/tools` - List available tools the agent can use
- `/agents [id]` - Show the last turn's agent tree or an agent's full result
- `/mcp` - Show connected MCP server status

## Sessions

- `/sessions [all]` - List saved sessions, newest first (e.g. `/sessions all` for every directory)
- `/sessions rm <n|id>` - Delete a saved session (e.g. `/sessions rm 1` or `/sessions rm 3f2a1c`)
- `/resume <n|id>` - Load a saved session into this one (e.g. `/resume 1` or `/resume 3f2a1c`)
- `/checkpoint [label]` - Save a checkpoint now, with an optional name (e.g. `/checkpoint before refactor`)
- `/checkpoints` - List checkpoints in this session
- `/rewind <n|id>` - Roll the conversation back to a previous checkpoint (e.g. `/rewind 2`)

## Tips

- Just type your message to chat with the agent
- Type `/` to see every command and keep typing to filter them; `↑`/`↓` to pick, `Enter` to run, `Tab` to fill in
- The agent can read, write, and execute code
- Some operations require approval (can be configured)
- In the live agent tree, `↑`/`↓` select, `Enter` expands details, and `c` cancels the selected subtree
- Sessions are saved after every turn; `postal --resume` picks the last one up
"""


class HelpCommands(CommandGroup):

    def show_help(self, agent: Agent, args: list[str]) -> None:
        self.console.print(Markdown(HELP_TEXT))
