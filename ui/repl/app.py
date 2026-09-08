from __future__ import annotations

import asyncio

from pathlib import Path

from platformdirs import user_config_dir
from prompt_toolkit import PromptSession
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import to_filter
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from rich.text import Text

from agent.agent import Agent
from config.config import Config
from ui.components import echo_user_message
from ui.console import get_console
from ui.repl.banner import render_banner
from ui.repl.commands import SlashCommands
from ui.repl.keys import build_key_bindings, turn_keys
from ui.repl.prompt import (
    PROMPT_STYLE,
    PROMPT_WIDTH,
    bottom_fragments,
    continuation_fragments,
    prompt_fragments,
    soft_wrap,
    status_readout,
)
from ui.stream import stream_turn
from ui.tui import TUI

HISTORY_FILE = "history"


def _history_path() -> Path:
    path = Path(user_config_dir("postal")) / HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class Repl:

    def __init__(self, config: Config, resume: str | None = None) -> None:
        self.config = config
        self.resume = resume
        self.console = get_console()
        self.tui = TUI(config, self.console)
        self.commands = SlashCommands(config, self.console)
        self._completion_index = 0
        self.session: PromptSession[str] = PromptSession(
            history=FileHistory(str(_history_path())),
            style=PROMPT_STYLE,
            key_bindings=build_key_bindings(self.tui, self),
            erase_when_done=True,
        )
        self._reflowing = False
        self.session.default_buffer.on_text_changed += self._reflow

        window = self.session.app.layout.current_window
        window.dont_extend_height = to_filter(True)

    def _reflow(self, buffer: Buffer) -> None:
        if self._reflowing:
            return
        width = self.console.width - PROMPT_WIDTH
        if width < 16:
            return

        wrapped = soft_wrap(buffer.text.replace("\n", " "), width)
        if wrapped == buffer.text:
            return

        self._reflowing = True
        try:
            buffer.document = Document(wrapped, buffer.cursor_position)
        finally:
            self._reflowing = False

    def _banner(self) -> None:
        render_banner(self.console, self.config)
        self.tui.mark_dirty()

    def _farewell(self, agent: Agent) -> None:
        session = agent.session

        # A turn cut short by ctrl+c never reached its autosave.
        if session.turns:
            session.save_checkpoint()

        line = Text.assemble(("Session ", "muted"), (session.session_id, "subtitle"))

        self.tui.gap()
        self.tui.print_block(line)

        if self.config.session.enabled and session.store.exists(session.session_id):
            self.tui.print_block(
                Text(f"Resume it with postal --resume {session.short_id}", style="border")
            )
        else:
            self.tui.print_block(Text("Keep this id to resume the session.", style="border"))

    def _reset_plan(self, agent: Agent) -> None:
        tool = agent.session.tool_registry.get("plan")
        if tool is not None and hasattr(tool, "reset"):
            tool.reset()

    async def _run_turn(self, agent: Agent, message: str) -> None:
        task = asyncio.create_task(stream_turn(self.tui, agent, message))

        try:
            with turn_keys(self.tui, task):
                await task
        except asyncio.CancelledError:
            self.tui.stop_thinking()
            self.tui.gap()
            self.tui.print_block(Text("Interrupted, what should postal do instead?", style="warning"))
        except Exception as exc:
            self.tui.stop_thinking()
            self.tui.gap()
            self.tui.print_block(Text(f"{type(exc).__name__}: {exc}", style="error"))

    def _prompt_fragments(self) -> StyleAndTextTuples:
        text = self.session.default_buffer.text
        expansion = self.tui.expansion_fragments()

        if text.startswith("/") and " " not in text:
            prefix = text[1:]
            matches = [
                (name, self.commands.describe(name))
                for name in self.commands.command_names()
                if name.startswith(prefix)
            ]
            if matches:
                cmd_fragments: StyleAndTextTuples = []
                max_show = 8
                if getattr(self, "_completion_index", 0) >= len(matches):
                    self._completion_index = 0

                for idx, (name, desc) in enumerate(matches[:max_show]):
                    is_selected = (idx == self._completion_index)
                    mark = "  > " if is_selected else "    "
                    cmd_str = f"/{name}".ljust(18)

                    cmd_style = "class:prompt bold" if is_selected else "class:frame"
                    meta_style = "class:prompt" if is_selected else "class:status"

                    cmd_fragments.append(("", mark))
                    cmd_fragments.append((cmd_style, cmd_str))
                    cmd_fragments.append((meta_style, f"  {desc}\n"))

                if len(matches) > max_show:
                    hidden = len(matches) - max_show
                    cmd_fragments.append(("class:status", f"    … {hidden} more commands\n"))

                expansion = (expansion or []) + cmd_fragments

        return prompt_fragments(self.console.width, expansion)

    def _continuation_fragments(
        self, width: int, _line_number: int, _wrap_count: int
    ) -> StyleAndTextTuples:
        return continuation_fragments(width)

    def _bottom_fragments(self) -> StyleAndTextTuples:
        return bottom_fragments(
            self.console.width,
            self.tui.approval_badge(),
            self.config.approval.risk,
            status_readout(
                self.config.model_name,
                self.tui.context_ratio,
                self.console.width,
                self.config.approval.label,
                str(self.config.cwd),
            ),
        )

    async def _read_input(self) -> str:
        self.tui.gap()
        try:
            message = await self.session.prompt_async(
                self._prompt_fragments,
                bottom_toolbar=self._bottom_fragments,
                prompt_continuation=self._continuation_fragments,
            )
            return message.replace("\n", " ")
        finally:
            self.tui.expanded = False

    def _echo(self, message: str) -> None:
        self.tui.gap()
        self.tui.print_block(echo_user_message(message))

    def _resume_notice(self, agent: Agent) -> None:
        if agent.resumed is not None:
            self.commands.announce_resume(agent)
            self.tui.mark_dirty()
            return

        self.tui.gap()
        self.tui.print_block(
            Text(f"No saved session matched '{self.resume}', starting a new one.", style="warning")
        )

    async def run(self) -> None:
        async with Agent(
            self.config,
            confirmation_callback=self.tui.confirm_tool,
            resume=self.resume,
        ) as agent:
            self._banner()
            if self.resume:
                self._resume_notice(agent)
            try:
                while True:
                    try:
                        message = await self._read_input()
                    except KeyboardInterrupt:
                        continue
                    except EOFError:
                        break

                    message = message.strip()
                    if not message:
                        continue

                    self._echo(message)

                    if self.commands.is_command(message):
                        self.tui.gap()
                        keep_going = await self.commands.execute(agent, message)
                        self.tui.mark_dirty()
                        if not keep_going:
                            break
                        continue

                    self._reset_plan(agent)
                    await self._run_turn(agent, message)
            finally:
                self._farewell(agent)
