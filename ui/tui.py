from __future__ import annotations

import asyncio
import time

from collections import deque
from io import StringIO
from typing import Any, Callable

from prompt_toolkit.formatted_text import ANSI, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys
from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from config.config import ApprovalPolicy, Config
from tools.base import ToolConfirmation
from ui.components import (
    APPROVE_KEYS,
    REASONING_LABEL,
    REJECT_KEYS,
    TOOL_ICON,
    Gutter,
    MarkdownStream,
    Spinner,
    ToolOutcome,
    confirmation_choices,
    confirmation_request,
    random_thinking_text,
    shimmer,
    tool_blocks,
    tool_header,
    tool_progress_panel,
    tool_status,
    usage_line,
)
from ui.console import get_console
from ui.format import format_elapsed, headline as headline_of
from ui.theme import AGENT_THEME
from utils.paths import display_path_relative_to_cwd

MAX_REMEMBERED_TOOLS = 20
MAX_EXPANSION_LINES = 24

PROGRESS_MAX_WIDTH = 48

APPROVAL_RISK_STYLES = {
    "normal": "info",
    "warn": "warning",
    "danger": "error",
}


class TUI:
    def __init__(self, config: Config, console: Console | None = None) -> None:
        self.console = console or get_console()
        self.config = config
        self.cwd = config.cwd
        self._assistant_stream_open = False
        self._assistant_markdown: MarkdownStream | None = None
        self._reasoning_stream_open = False
        self._reasoning_line = ""
        self._reasoning_started_at = 0.0
        self.tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.tool_started_at: dict[str, float] = {}
        self._tool_progress = ""

        self._at_gap = True

        self.collapsed = True
        self.expanded = False
        self._recent_tools: deque[tuple[Table, list[Any], list[Any], str]] = deque(
            maxlen=MAX_REMEMBERED_TOOLS
        )

        self._spinner = Spinner(self.console)
        self._thinking_label = ""
        self._thinking_started_at = 0.0
        self._turn_tokens = 0
        self._context_tokens = 0

        # Set by the REPL while it owns the keyboard, so confirmations can be
        # answered through its key reader instead of opening a second one.
        self.external_keys = False
        self._pending_confirmation: asyncio.Future[bool] | None = None

    @property
    def approval_policy(self) -> ApprovalPolicy:
        return self.config.approval

    @property
    def awaiting_confirmation(self) -> bool:
        return self._pending_confirmation is not None

    @property
    def context_ratio(self) -> float | None:
        window = self.config.model.context_window
        if not window or not self._context_tokens:
            return None
        return min(self._context_tokens / window, 1.0)

    def gap(self) -> None:
        if not self._at_gap:
            self.console.print()
            self._at_gap = True

    def print_block(self, *renderables: Any) -> None:
        for renderable in renderables:
            self.console.print(renderable)
        self._at_gap = False

    def mark_dirty(self) -> None:
        self._at_gap = False

    def _live_group(self, line: Text) -> Any:

        expansion = self.expansion_renderable()
        if expansion is not None:
            return Group(Text(""), expansion, line)
        return Group(Text(""), line)

    def _thinking_renderable(self) -> Any:
        line = Text.assemble((f"{self._spinner.char()} ", "tool"))
        line.append_text(shimmer(self._thinking_label, self._spinner.frame))
        elapsed = int(time.monotonic() - self._thinking_started_at)
        line.append(f" ({elapsed}s", style="muted")
        line.append(" · ", style="dim")
        line.append(f"{self._turn_tokens:,} tokens)", style="muted")
        return self._live_group(line)

    def update_turn_usage(self, usage: dict[str, Any] | None) -> None:

        if not usage:
            return
        self._turn_tokens = usage.get("total_tokens", 0) or 0
        self._context_tokens = usage.get("prompt_tokens", 0) or self._context_tokens

    def start_thinking(self, label: str | None = None) -> None:
        self._thinking_label = label if label is not None else random_thinking_text()

        if self._thinking_started_at == 0.0:
            self._thinking_started_at = time.monotonic()
        self._spinner.start(self._thinking_renderable)

    def stop_thinking(self) -> None:
        self._spinner.stop()
        self._thinking_started_at = 0.0
        self._turn_tokens = 0

    @property
    def show_reasoning(self) -> bool:
        return self.config.reasoning.visible

    def _reasoning_renderable(self) -> Any:
        line = Text.assemble((f"{self._spinner.reasoning_char()} ", "reasoning.mark"))
        line.append_text(shimmer(REASONING_LABEL, self._spinner.frame))
        elapsed = int(time.monotonic() - self._reasoning_started_at)
        line.append(f" ({elapsed}s)", style="muted")
        return line

    def begin_reasoning(self) -> None:
        if not self.show_reasoning or self._reasoning_stream_open:
            return

        self._reasoning_stream_open = True
        self._reasoning_line = ""
        self._reasoning_started_at = time.monotonic()

        self.gap()
        self._spinner.start(self._reasoning_renderable)

    def stream_reasoning_delta(self, content: str) -> None:
        """Reasoning is printed a line at a time so the gutter can wrap with it."""

        if not self._reasoning_stream_open:
            return

        self._reasoning_line += content
        while "\n" in self._reasoning_line:
            line, self._reasoning_line = self._reasoning_line.split("\n", 1)
            self._print_reasoning_line(line)

    def end_reasoning(self) -> None:
        if not self._reasoning_stream_open:
            return

        self._spinner.stop()

        if self._reasoning_line.strip():
            self._print_reasoning_line(self._reasoning_line)
        self._reasoning_line = ""
        self._reasoning_stream_open = False

        elapsed = format_elapsed(time.monotonic() - self._reasoning_started_at)
        self.print_block(Text(f"  thought for {elapsed}", style="dim"))

    def _print_reasoning_line(self, line: str) -> None:
        self.print_block(
            Gutter(Text(line.rstrip(), style="reasoning"), style="reasoning.mark")
        )

    def begin_assistant(self) -> None:
        self._spinner.stop()
        self.gap()
        self._assistant_markdown = MarkdownStream(self._print_assistant_block)
        self._assistant_stream_open = True

    def end_assistant(self) -> None:
        if self._assistant_markdown is not None:
            self._assistant_markdown.close()
            self._assistant_markdown = None
        if self._assistant_stream_open:
            self.gap()
        self._assistant_stream_open = False

    def _print_assistant_block(self, renderable: Any) -> None:
        if isinstance(renderable, Text) and not renderable.plain:
            self.gap()
            return
        self.print_block(renderable)

    def stream_assistant_delta(self, content: str) -> None:
        if self._assistant_markdown is None:
            return
        self._assistant_markdown.feed(content)

    def _relativise(self, arguments: dict[str, Any]) -> dict[str, Any]:
        display_args = dict(arguments)
        for key in ("path", "cwd"):
            value = display_args.get(key)
            if isinstance(value, str) and self.cwd:
                display_args[key] = str(display_path_relative_to_cwd(value, self.cwd))
        return display_args

    def _print_tool(
        self, header: Table, blocks: list[Any], border_style: str, hint: bool = False
    ) -> None:
        self.gap()
        self.print_block(header)
        if blocks:
            self.print_block(Gutter(Group(*blocks), style=border_style))
        if hint:
            self.print_block(Text("ctrl+o expands output", style="dim"))

    def toggle_details(self) -> None:
        self.collapsed = not self.collapsed
        state = "collapsed" if self.collapsed else "expanded"
        self.print_block(Text(f"Tool output is now {state}.", style="muted"))

    def show_recent_tool(self, back: int = 1) -> None:

        if not self._recent_tools or back < 1 or back > len(self._recent_tools):
            self.print_block(Text("Nothing to expand.", style="muted"))
            return
        header, summary, details, border_style = self._recent_tools[-back]
        self._print_tool(header, summary + details, border_style)

    def toggle_expansion(self) -> None:
        self.expanded = not self.expanded

    def expansion_renderable(self, back: int = 1) -> Any | None:

        if not self.expanded or not self._recent_tools:
            return None
        if back < 1 or back > len(self._recent_tools):
            return None

        _header, _summary, details, border_style = self._recent_tools[-back]
        if not details:
            return None
        return Gutter(Group(*details), style=border_style)

    def expansion_fragments(self, back: int = 1) -> StyleAndTextTuples:

        renderable = self.expansion_renderable(back)
        if renderable is None:
            return []

        buffer = StringIO()
        console = Console(
            theme=AGENT_THEME,
            file=buffer,
            force_terminal=True,
            width=self.console.width,
            highlight=False,
        )
        console.print(renderable)

        lines = buffer.getvalue().rstrip("\n").split("\n")
        if len(lines) > MAX_EXPANSION_LINES:
            hidden = len(lines) - MAX_EXPANSION_LINES
            lines = lines[:MAX_EXPANSION_LINES] + [f"… {hidden} more lines"]
        return to_formatted_text(ANSI("\n".join(lines) + "\n"))

    def tool_call_start(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        arguments: dict[str, Any],
    ) -> None:
        display_args = self._relativise(arguments)
        self.tool_args_by_call_id[call_id] = display_args
        started_at = time.monotonic()
        self.tool_started_at[call_id] = started_at
        head = headline_of(display_args)
        self._tool_progress = ""

        def render() -> Any:
            elapsed = int(time.monotonic() - started_at)
            return self._live_group(
                tool_progress_panel(
                    name,
                    elapsed,
                    self._tool_progress,
                    tool_kind=tool_kind,
                    headline=head[1] if head else None,
                    spinner=self._spinner.char(),
                    frame=self._spinner.frame,
                )
            )

        self._spinner.start(render)

    def tool_progress(self, chunk: str) -> None:
        line = chunk.strip().splitlines()[-1] if chunk.strip() else ""
        if not line:
            return

        if len(line) > PROGRESS_MAX_WIDTH:
            line = f"{line[:PROGRESS_MAX_WIDTH - 1]}…"
        self._tool_progress = line

    def tool_call_complete(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None,
        metadata: dict[str, Any] | None,
        truncated: bool,
        diff: str | None,
        exit_code: int | None,
    ) -> None:
        self._spinner.stop()
        self._tool_progress = ""

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        started_at = self.tool_started_at.pop(call_id, None)
        elapsed = (
            format_elapsed(time.monotonic() - started_at) if started_at is not None else None
        )
        display_args = self.tool_args_by_call_id.pop(call_id, {})

        summary, details = tool_blocks(
            ToolOutcome(
                name=name,
                args=display_args,
                success=success,
                output=output,
                error=error,
                metadata=metadata or {},
                truncated=truncated,
                diff=diff,
                exit_code=exit_code,
                model_name=self.config.model_name,
            )
        )

        collapsed = self.collapsed and success
        hidden = collapsed and bool(details)

        head = headline_of(display_args)
        header = tool_header(
            TOOL_ICON,
            border_style,
            name,
            head[1] if head else None,
            tool_status(
                success,
                elapsed,
                len((diff or output).splitlines()) if hidden else None,
            ),
        )

        self._recent_tools.append((header, summary, details, border_style))
        self._print_tool(
            header,
            summary if collapsed else summary + details,
            border_style,
            hint=True,
        )

    def render_confirmation_request(self, confirmation: ToolConfirmation) -> None:
        self.gap()
        self.print_block(*confirmation_request(confirmation, self.cwd))
        self.print_block(confirmation_choices(self.approval_badge()))

    def approval_badge(self) -> str:
        policy = self.approval_policy
        return f"approval: {policy.label}"

    def render_approval_mode(self) -> None:
        policy = self.approval_policy
        style = APPROVAL_RISK_STYLES.get(policy.risk, "info")
        line = Text.assemble(
            ("approval ", "muted"),
            (policy.label, style),
        )
        self.print_block(line)

    def feed_confirmation_key(self, key_press: Any) -> bool:
        """Answer a pending confirmation. Returns True when the key was consumed."""

        pending = self._pending_confirmation
        if pending is None:
            return False
        if pending.done():
            return True

        key = key_press.key
        data = (key_press.data or "").lower()

        if key in (Keys.ControlC, Keys.Escape) or data in REJECT_KEYS:
            pending.set_result(False)
        elif key in (Keys.ControlM, Keys.ControlJ) or data in APPROVE_KEYS:
            pending.set_result(True)

        # Swallow everything while a confirmation is open; a stray ctrl+o
        # should not reflow the screen underneath the prompt.
        return True

    async def _read_confirmation_key(self, pending: asyncio.Future[bool]) -> bool:
        """Own the keyboard for the confirmation when the REPL is not doing it."""

        try:
            device = create_input()
        except Exception:
            self.console.print(
                Text("No terminal available to confirm on, rejecting.", style="warning")
            )
            return False

        def on_keys() -> None:
            for key_press in device.read_keys():
                self.feed_confirmation_key(key_press)

        with device.raw_mode(), device.attach(on_keys):
            return await pending

    async def confirm_tool(self, confirmation: ToolConfirmation) -> bool:

        previous_spinner: Callable[[], Any] | None = self._spinner.render
        self._spinner.stop()

        self.render_confirmation_request(confirmation)

        loop = asyncio.get_running_loop()
        pending: asyncio.Future[bool] = loop.create_future()
        self._pending_confirmation = pending

        try:
            if self.external_keys:
                approved = await pending
            else:
                approved = await self._read_confirmation_key(pending)
        except asyncio.CancelledError:
            self.print_block(Text("Rejected (interrupted)", style="warning"))
            raise
        finally:
            self._pending_confirmation = None

        self.print_block(
            Text("Approved", style="success") if approved else Text("Rejected", style="error")
        )

        if previous_spinner is not None:
            self._spinner.start(previous_spinner)

        return approved

    def render_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return

        self._context_tokens = (usage.get("prompt_tokens", 0) or 0) or self._context_tokens

        self.gap()
        self.print_block(usage_line(usage, self.config.model.context_window))
