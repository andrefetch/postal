from __future__ import annotations

import asyncio
import time
from io import StringIO
from pathlib import Path

from platformdirs import user_config_dir
from prompt_toolkit.history import FileHistory, History
from rich.console import Console
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.filter import Monochrome
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Collapsible, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from agent.agent import Agent
from agent.events import AgentEvent, AgentEventType
from config.config import Config
from tools.base import ToolConfirmation
from ui.components.agent_tree import AgentTree
from ui.components.logo import logo, small_wordmark
from ui.repl.commands import SlashCommands
from ui.textual_widgets import AgentsScreen, ApprovalScreen, Composer, MessageBlock, ToolBlock
from ui.theme import AGENT_THEME


class CommandConsole(Console):
    """Capture existing slash commands without writing outside Textual."""

    def __init__(self):
        super().__init__(file=StringIO(), theme=AGENT_THEME, color_system=None, highlight=False)
        self.cleared = False

    def clear(self, home: bool = True) -> None:
        self.cleared = True


class PostalApp(App[str | None]):
    TITLE = "Postal"
    CSS_PATH = "postal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
        Binding("escape", "escape", "Stop / close", priority=True),
        Binding("ctrl+p", "commands", "Commands", priority=True),
        Binding("ctrl+g", "agents", "Agents", priority=True),
        Binding("ctrl+o", "tool_details", "Tool details", priority=True),
        Binding("ctrl+end", "latest", "Latest message", priority=True),
    ]

    def __init__(
        self, config: Config, resume: str | None = None, upgrade_notice: str | None = None,
        *, agent_factory=Agent, history: History | None = None,
    ):
        self._monochrome = Monochrome()
        super().__init__()
        self.config = config
        self.resume_id = resume
        self.upgrade_notice = upgrade_notice
        self.agent_factory = agent_factory
        self.agent: Agent | None = None
        self.agent_views = AgentTree()
        self.last_response: str | None = None
        self.ready = asyncio.Event()
        self._stop_session = asyncio.Event()
        self._session_task: asyncio.Task | None = None
        self._turn_task: asyncio.Task | None = None
        self._control_tasks: set[asyncio.Task] = set()
        self._shutting_down = False
        self._pending_confirmation: tuple[ApprovalScreen, asyncio.Future] | None = None
        self._history = history
        self._prompts: list[str] = []
        self._history_index = 0
        self._draft = ""
        self._assistant: MessageBlock | None = None
        self._reasoning: Collapsible | None = None
        self._reasoning_body: Static | None = None
        self._reasoning_text = ""
        self._tools: dict[str, ToolBlock] = {}
        self._last_tool: ToolBlock | None = None
        self._dirty = False
        self._status = "Connecting"
        self._turn_started = 0.0
        self._context_tokens = 0
        self.command_console = CommandConsole()
        self.commands = SlashCommands(config, self.command_console)
        self.console.push_theme(AGENT_THEME)
        self.register_theme(Theme(
            name="postal-mono", primary="#d4d4d4", secondary="#a0a0a0", accent="#eeeeee",
            foreground="#dedede", background="#101010", surface="#181818", panel="#202020",
            warning="#d4d4d4", error="#eeeeee", success="#bcbcbc", boost="#ffffff",
            dark=True, variables={
                "footer-background": "#101010", "block-cursor-background": "#dedede",
                "block-cursor-foreground": "#101010", "border": "#3a3a3a",
                "scrollbar": "#454545", "scrollbar-hover": "#666666",
                "scrollbar-active": "#888888", "scrollbar-background": "#101010",
            },
        ))
        self.theme = "postal-mono"

    def get_line_filters(self):
        return [*super().get_line_filters(), self._monochrome]

    @property
    def busy(self) -> bool:
        return self._turn_task is not None and not self._turn_task.done()

    def compose(self) -> ComposeResult:
        with Vertical(id="shell"):
            with Horizontal(id="topbar"):
                yield Static("postal", id="brand")
                yield Static(Text(str(self.config.cwd)), id="workspace")
            with Vertical(id="main", classes="home"):
                with Vertical(id="welcome"):
                    with Center(id="cloud-row"):
                        yield Static(logo(), id="cloud-logo")
                    yield Static(small_wordmark(), id="wordmark")
                    yield Static("What would you like to work on?", id="welcome-hint")
                yield VerticalScroll(id="conversation")
                with Vertical(id="prompt-area"):
                    yield OptionList(id="commands", markup=False)
                    with Vertical(id="composer-box"):
                        yield Composer(
                            id="composer", placeholder="Ask anything…", disabled=True,
                            show_line_numbers=False, highlight_cursor_line=False,
                        )
                        yield Static(id="model-line", markup=False)
                    with Horizontal(id="statusbar"):
                        yield Static("Connecting", id="run-status", markup=False)
                        yield Static("Enter send · Ctrl+J newline · Ctrl+P commands", id="key-hints")
                yield Static(id="home-spacer")

    def on_resize(self, event: events.Resize) -> None:
        shell = self.query_one("#shell")
        shell.set_class(event.size.width < 80, "narrow")
        shell.set_class(event.size.height < 24, "short")
        shell.set_class(event.size.height < 18, "compact")

    def on_mount(self) -> None:
        self.show_commands(False)
        if self._history is None:
            path = Path(user_config_dir("postal")) / "history"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                self._history = FileHistory(str(path))
            except OSError:
                self._history = None
        if self._history is not None:
            try:
                self._prompts = list(reversed(list(self._history.load_history_strings())))
            except OSError:
                pass
        self._history_index = len(self._prompts)
        self.set_interval(0.08, self.refresh_live)
        self._session_task = asyncio.create_task(self._session_lifecycle(), name="postal-session")

    async def _session_lifecycle(self) -> None:
        try:
            async with self.agent_factory(
                self.config, confirmation_callback=self.confirm_tool, resume=self.resume_id,
            ) as agent:
                self.agent = agent
                try:
                    if self.resume_id:
                        await self.execute_command(f"/resume {self.resume_id}", announce=True)
                    if self.upgrade_notice:
                        await self.append_notice(self.upgrade_notice)
                    self._status = "Ready"
                    self.query_one("#composer", Composer).disabled = False
                    self.query_one("#composer", Composer).focus()
                    self.refresh_live()
                    self.ready.set()
                    await self._stop_session.wait()
                finally:
                    await self._cancel_turn()
                    if agent.session.turns:
                        agent.session.save_checkpoint()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._status = "Connection failed"
            if not self._shutting_down:
                await self.append_notice(f"Could not start the session: {exc}")
        finally:
            self.ready.set()

    async def on_unmount(self) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        self._shutting_down = True
        await self._cancel_turn()
        if self._control_tasks:
            await asyncio.gather(*self._control_tasks, return_exceptions=True)
        self._stop_session.set()
        if self._session_task is not None:
            if not self.ready.is_set():
                self._session_task.cancel()
            await asyncio.gather(self._session_task, return_exceptions=True)

    async def _cancel_turn(self) -> None:
        if self.busy:
            self._turn_task.cancel()
            await asyncio.gather(self._turn_task, return_exceptions=True)

    async def action_quit(self) -> None:
        await self.shutdown()
        self.exit(self.last_response)

    def action_interrupt(self) -> None:
        if self._pending_confirmation is not None:
            screen, future = self._pending_confirmation
            if not future.done():
                screen.dismiss(False)
        elif self.busy:
            self._turn_task.cancel()
        else:
            self.query_one("#composer", Composer).clear()

    def action_escape(self) -> None:
        if self._pending_confirmation is not None:
            self.action_interrupt()
        elif isinstance(self.screen, AgentsScreen):
            self.screen.dismiss(None)
        elif self.query_one("#commands").display:
            self.show_commands(False)
            self.query_one("#composer", Composer).focus()
        elif self.busy:
            self.action_interrupt()

    def action_agents(self) -> None:
        if self._pending_confirmation is not None:
            return
        if isinstance(self.screen, AgentsScreen):
            self.screen.dismiss(None)
        else:
            self.push_screen(AgentsScreen())

    def action_tool_details(self) -> None:
        if not isinstance(self.screen, ModalScreen) and self._last_tool is not None:
            self._last_tool.collapsed = not self._last_tool.collapsed
            self._last_tool.scroll_visible(animate=False)

    def action_latest(self) -> None:
        self.query_one("#conversation", VerticalScroll).scroll_end(animate=False)

    def action_commands(self) -> None:
        if isinstance(self.screen, ModalScreen):
            return
        menu = self.query_one("#commands", OptionList)
        self.show_commands(not menu.display)
        if menu.display:
            self.populate_commands("")
            menu.focus()
        else:
            self.query_one("#composer", Composer).focus()

    def show_commands(self, visible: bool) -> None:
        self.query_one("#commands").display = visible
        self.query_one("#main").set_class(visible, "commands-open")

    def populate_commands(self, prefix: str) -> None:
        menu = self.query_one("#commands", OptionList)
        matches = [name for name in self.commands.command_names() if name.startswith(prefix)]
        menu.clear_options()
        menu.add_options(Option(Text(f"/{name:<14} {self.commands.describe(name)}"), id=name) for name in matches)
        menu.highlighted = 0 if matches else None
        self.show_commands(bool(matches))

    @on(TextArea.Changed, "#composer")
    def composer_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        if text.startswith("/") and not any(char.isspace() for char in text):
            self.populate_commands(text[1:])
        else:
            self.show_commands(False)

    @on(OptionList.OptionSelected, "#commands")
    def complete_command(self) -> None:
        menu = self.query_one("#commands", OptionList)
        if menu.highlighted is None:
            return
        name = menu.get_option_at_index(menu.highlighted).id
        composer = self.query_one("#composer", Composer)
        composer.load_text(f"/{name} ")
        composer.move_cursor(composer.document.end)
        self.show_commands(False)
        composer.focus()

    def recall_prompt(self, direction: int) -> None:
        composer = self.query_one("#composer", Composer)
        if not self._prompts:
            return
        if self._history_index == len(self._prompts):
            self._draft = composer.text
        self._history_index = min(len(self._prompts), max(0, self._history_index + direction))
        composer.load_text(self._draft if self._history_index == len(self._prompts) else self._prompts[self._history_index])
        composer.move_cursor(composer.document.end)

    @on(Composer.Submitted)
    async def submit_prompt(self, event: Composer.Submitted) -> None:
        message = event.text.strip()
        if not message or self.agent is None or self._shutting_down:
            return
        if self.busy:
            self._status = "Working · Esc to interrupt"
            return
        self.query_one("#composer", Composer).clear()
        self._prompts.append(message)
        self._history_index = len(self._prompts)
        self._draft = ""
        if self._history is not None:
            try:
                self._history.append_string(message)
            except OSError:
                pass
        if message.startswith("/"):
            await self.execute_command(message)
            return
        await self.append_block(MessageBlock("user", message), force_scroll=True)
        self.agent_views = AgentTree()
        self._tools = {}
        self._assistant = None
        self._reasoning = None
        self.last_response = None
        self._turn_started = time.monotonic()
        self._status = "Thinking"
        plan = self.agent.session.tool_registry.get("plan")
        if plan is not None and hasattr(plan, "reset"):
            plan.reset()
        self._turn_task = asyncio.create_task(self._run_turn(message), name="postal-turn")

    async def execute_command(self, message: str, *, announce: bool = False) -> None:
        if message.strip() in {"/exit", "/quit"}:
            await self.action_quit()
            return
        if message.strip() == "/agents":
            self.action_agents()
            return
        self.command_console.width = max(20, self.size.width - 8)
        with self.command_console.capture() as capture:
            if announce and self.agent.resumed is not None:
                self.commands.announce_resume(self.agent)
            else:
                await self.commands.execute(self.agent, message)
        if self.command_console.cleared:
            await self.query_one("#conversation", VerticalScroll).remove_children()
            self.command_console.cleared = False
            self.agent_views = AgentTree()
            self._last_tool = None
            self._context_tokens = 0
        output = capture.get().strip()
        if output:
            await self.append_notice(output)
        self.refresh_live()

    async def append_block(self, block, *, force_scroll: bool = False) -> None:
        if self._shutting_down or not self.is_running:
            return
        conversation = self.query_one("#conversation", VerticalScroll)
        follow = force_scroll or conversation.is_vertical_scroll_end
        self.query_one("#main").remove_class("home")
        welcome = self.query("#welcome")
        if welcome:
            await welcome.remove()
        await conversation.mount(block)
        if follow:
            conversation.scroll_end(animate=False, immediate=False)

    async def append_notice(self, text: str) -> None:
        await self.append_block(Static(Text(text), classes="notice"))

    async def _run_turn(self, message: str) -> None:
        events = self.agent.run(message)
        try:
            async for event in events:
                await self.handle_agent_event(event)
            if self._status != "Failed":
                self._status = "Ready"
        except asyncio.CancelledError:
            self._status = "Interrupted"
            for tool in self._tools.values():
                if tool.state == "running":
                    tool.cancel()
        except Exception as exc:
            self._status = "Failed"
            if not self._shutting_down:
                await self.append_notice(f"Error: {exc}")
        finally:
            await events.aclose()
            for record in self.agent.runtime.records.values():
                self.agent_views.update(AgentEvent(
                    AgentEventType.AGENT_STATUS, record.snapshot(), record.agent_id, record.parent_agent_id,
                ))
            self.flush_streams()
            self._assistant = None
            self._reasoning = None
            if not self._shutting_down and self.is_running and not isinstance(self.screen, ModalScreen):
                self.query_one("#composer", Composer).focus()

    async def handle_agent_event(self, event: AgentEvent) -> None:
        self.agent_views.update(event)
        if self._shutting_down or not self.is_running:
            return
        if event.agent_id not in {None, self.agent.agent_id}:
            return
        data = event.data
        if event.type == AgentEventType.TEXT_DELTA:
            if self._assistant is None:
                self._assistant = MessageBlock("assistant")
                await self.append_block(self._assistant)
            self._assistant.text += data.get("content", "")
            self._dirty = True
            self._status = "Responding"
        elif event.type == AgentEventType.TEXT_COMPLETE:
            self.last_response = data.get("content")
            self.flush_streams()
            self._assistant = None
        elif event.type == AgentEventType.REASONING_DELTA and self.config.reasoning.visible:
            if self._reasoning is None:
                self._reasoning_text = ""
                self._reasoning_body = Static(markup=False)
                self._reasoning = Collapsible(
                    self._reasoning_body, title="Thinking", collapsed=True,
                    collapsed_symbol="›", expanded_symbol="⌄", classes="reasoning-block",
                )
                await self.append_block(self._reasoning)
            self._reasoning_text += data.get("content", "")
            self._dirty = True
        elif event.type == AgentEventType.REASONING_COMPLETE:
            self.flush_streams()
            self._reasoning = None
        elif event.type == AgentEventType.TOOL_CALL_START:
            tool = ToolBlock(data.get("name", "tool"), data.get("arguments", {}))
            self._tools[data.get("call_id", "")] = tool
            self._last_tool = tool
            await self.append_block(tool)
            tool.refresh_details()
            self._status = f"Running {tool.tool_name}"
        elif event.type == AgentEventType.TOOL_PROGRESS:
            tool = self._tools.get(data.get("call_id", ""))
            if tool:
                tool.progress(data.get("content", ""))
                self._dirty = True
        elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
            tool = self._tools.get(data.get("call_id", ""))
            if tool:
                tool.complete(data)
            self._status = "Thinking"
        elif event.type == AgentEventType.AGENT_END:
            self._context_tokens = (data.get("usage") or {}).get("prompt_tokens", 0)
        elif event.type == AgentEventType.AGENT_ERROR:
            self._status = "Failed"
            await self.append_notice(f"Error: {data.get('error', 'Agent failed')}")

    def flush_streams(self) -> None:
        if not self._dirty or self._shutting_down or not self.is_running:
            return
        conversation = self.query_one("#conversation", VerticalScroll)
        follow = conversation.is_vertical_scroll_end
        if self._assistant is not None:
            self._assistant.refresh_text()
        if self._reasoning is not None:
            self._reasoning_body.update(Text(self._reasoning_text, style="dim"))
        for tool in self._tools.values():
            if tool.state == "running" and not tool.collapsed:
                tool.refresh_details()
        self._dirty = False
        if follow:
            conversation.scroll_end(animate=False, immediate=False)

    def refresh_live(self) -> None:
        if self._shutting_down or not self.is_running:
            return
        self.flush_streams()
        total = sum((node.data.get("usage") or {}).get("total_tokens", 0) for node in self.agent_views.nodes.values())
        children = [node for node in self.agent_views.nodes.values() if node.data.get("parent_agent_id")]
        active = sum(node.data.get("status") not in {"completed", "failed", "timed_out", "cancelled"} for node in children)
        parts = [self._status]
        if self.busy:
            parts.append(f"{int(time.monotonic() - self._turn_started)}s")
        if children:
            parts.append(f"{active}/{len(children)} agents · Ctrl+G")
        if total:
            parts.append(f"{total:,} tokens")
        self.query_one("#run-status", Static).update(" · ".join(parts))
        model = self.config.model_name or "No model selected"
        info = f"{model}  ·  {self.config.approval.label}"
        if self._context_tokens:
            info += f"  ·  {self._context_tokens:,} context"
        self.query_one("#model-line", Static).update(info)
        hints = self.query_one("#key-hints", Static)
        hints.display = self.size.width >= 80
        hints.update(
            "Esc stop · Ctrl+O details" if self.busy else "Enter send · Ctrl+J newline · Ctrl+P commands"
        )

    async def confirm_tool(self, confirmation: ToolConfirmation) -> bool:
        if self._shutting_down or not self.is_running:
            return False
        screen = ApprovalScreen(confirmation)
        future = asyncio.get_running_loop().create_future()
        self._pending_confirmation = (screen, future)

        def answered(approved):
            if not future.done():
                future.set_result(bool(approved))

        self.push_screen(screen, answered)
        try:
            return await future
        finally:
            self._pending_confirmation = None
            if screen.is_mounted and self.screen is screen:
                screen.dismiss(False)

    def cancel_agent(self, agent_id: str) -> None:
        if self.agent is None or not self.busy:
            return
        task = asyncio.create_task(self.agent.runtime.cancel(self.agent.agent_id, agent_id))
        self._control_tasks.add(task)
        task.add_done_callback(self._control_tasks.discard)
