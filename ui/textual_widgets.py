from __future__ import annotations

import json
import time

from rich.markdown import Markdown
from rich.markup import escape
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Static, TextArea, Tree

from tools.base import ToolConfirmation
from ui.format import headline
from ui.theme.syntax import POSTAL_SYNTAX


class Composer(TextArea):
    """Enter sends; explicit modified Enter preserves multiline prompts."""

    BINDINGS = [
        Binding("shift+enter,ctrl+j", "newline", show=False),
        Binding("alt+up", "history(-1)", show=False),
        Binding("alt+down", "history(1)", show=False),
    ]

    class Submitted(Message):
        def __init__(self, text: str):
            self.text = text
            super().__init__()

    def resize_to_content(self) -> None:
        # Use visual lines so pasted text and terminal resizes also fit.
        sources_height = int(self.app.query_one("#prompt-sources").display)
        limit = min(6, max(3, self.app.size.height - 17 - sources_height))
        self.styles.height = min(limit, max(3, self.wrapped_document.height + self.gutter.height))

    def on_resize(self) -> None:
        self.call_after_refresh(self.resize_to_content)

    @on(TextArea.Changed)
    def resize_after_edit(self) -> None:
        self.resize_to_content()

    async def _on_key(self, event: events.Key) -> None:
        menu = self.app.query_one("#commands")
        if menu.display and event.key in {"up", "down", "tab"}:
            event.prevent_default()
            event.stop()
            if event.key == "tab":
                self.app.complete_command()
            elif event.key == "up":
                menu.action_cursor_up()
            else:
                menu.action_cursor_down()
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            name = self.text.strip().removeprefix("/")
            if menu.display and name not in self.app.commands.command_names():
                self.app.complete_command()
            else:
                self.post_message(self.Submitted(self.text))
            return
        await super()._on_key(event)

    def action_newline(self) -> None:
        self.insert("\n")

    def action_history(self, direction: int) -> None:
        self.app.recall_prompt(direction)


class MessageBlock(Vertical):
    def __init__(self, role: str, text: str = ""):
        super().__init__(classes=f"message {role}")
        self.role = role
        self.text = text
        self.body = Static(markup=False, classes="message-body")

    def compose(self) -> ComposeResult:
        yield Static("You" if self.role == "user" else "Postal", classes="message-label")
        yield self.body

    def on_mount(self) -> None:
        self.refresh_text()

    def refresh_text(self) -> None:
        if self.role == "user":
            self.body.update(Text(self.text))
        else:
            self.body.update(Markdown(self.text, code_theme=POSTAL_SYNTAX, inline_code_theme=POSTAL_SYNTAX))


class ToolBlock(Collapsible):
    def __init__(self, name: str, arguments: dict):
        self.tool_name = name
        self.arguments = arguments
        self.started_at = time.monotonic()
        self.output = ""
        self.state = "running"
        self.details = Static(markup=False, classes="tool-details")
        super().__init__(
            self.details, title=self._tool_title(), collapsed=True,
            collapsed_symbol="›", expanded_symbol="⌄", classes="tool-block",
        )

    def _tool_title(self) -> str:
        head = headline(self.arguments)
        detail = str(head[1]) if head else str(self.arguments.get("role", ""))
        detail = " ".join(detail.split())[:70]
        icon = {"running": "◌", "completed": "✓", "failed": "×", "cancelled": "−"}[self.state]
        return escape(f"{icon} {self.tool_name}" + (f"  {detail}" if detail else ""))

    def progress(self, text: str) -> None:
        self.output = (self.output + text)[-12000:]

    def refresh_details(self) -> None:
        arguments = json.dumps(self.arguments, indent=2, ensure_ascii=False)
        self.details.update(Text(arguments + ("\n\n" + self.output if self.output else "")))

    @on(Collapsible.Expanded)
    def show_output(self) -> None:
        self.refresh_details()

    def complete(self, data: dict) -> None:
        self.state = "completed" if data.get("success") else "failed"
        self.output = "\n\n".join(str(part) for part in (
            data.get("error"), data.get("diff"), data.get("output"),
        ) if part)[-48000:]
        self.title = f"{self._tool_title()}  {time.monotonic() - self.started_at:.1f}s"
        self.refresh_details()
        if self.state == "failed":
            self.collapsed = False

    def cancel(self) -> None:
        self.state = "cancelled"
        self.title = self._tool_title()


class ApprovalScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "approve", "Approve", priority=True),
        Binding("n,escape,ctrl+c", "reject", "Reject", priority=True),
        Binding("pageup", "scroll_preview(-1)", show=False, priority=True),
        Binding("pagedown", "scroll_preview(1)", show=False, priority=True),
    ]

    def __init__(self, confirmation: ToolConfirmation):
        super().__init__()
        self.confirmation = confirmation

    def compose(self) -> ComposeResult:
        confirmation = self.confirmation
        with Vertical(id="approval-dialog", classes="dialog"):
            yield Static("Permission required", classes="dialog-title")
            yield Static(Text(confirmation.description), id="approval-description")
            with VerticalScroll(id="approval-content"):
                if confirmation.is_dangerous:
                    yield Static("! This operation is marked dangerous.", classes="notice")
                if confirmation.affected_paths:
                    yield Static(Text("Affects: " + ", ".join(map(str, confirmation.affected_paths))))
                body = confirmation.command or ""
                if confirmation.diff:
                    body = "\n\n".join(part for part in (body, confirmation.diff.create_diff()) if part)
                elif not body:
                    body = json.dumps(confirmation.params, indent=2, ensure_ascii=False)
                yield Static(Text(body), id="approval-body")
            with Horizontal(classes="dialog-actions"):
                yield Button(Text("Reject  [n]"), id="reject")
                yield Button(Text("Approve  [y]"), id="approve")
            yield Static("Esc rejects · PgUp/PgDn scroll the preview", classes="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#reject", Button).focus()

    def action_scroll_preview(self, direction: int) -> None:
        preview = self.query_one("#approval-content", VerticalScroll)
        if direction < 0:
            preview.scroll_page_up(animate=False)
        else:
            preview.scroll_page_down(animate=False)

    @on(Button.Pressed, "#approve")
    def action_approve(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#reject")
    def action_reject(self) -> None:
        self.dismiss(False)


class AgentsScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,ctrl+g", "close", "Close", priority=True),
        Binding("c", "cancel_agent", "Cancel selected agent", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.agent_tree = Tree("Main agent", data="main", id="agents-tree")
        self.tree_nodes = {"main": self.agent_tree.root}
        self.details = Static(markup=False, id="agent-details")

    def compose(self) -> ComposeResult:
        with Vertical(id="agents-dialog", classes="dialog"):
            yield Static("Agent activity", classes="dialog-title")
            yield self.agent_tree
            with VerticalScroll(id="agent-detail-scroll"):
                yield self.details
            yield Static("↑↓ select · Enter expand · c cancel subtree · Esc close", classes="dialog-hint")

    def on_mount(self) -> None:
        self.agent_tree.root.expand()
        self.refresh_agents()
        self.agent_tree.focus()
        self.set_interval(0.2, self.refresh_agents)

    def refresh_agents(self) -> None:
        views = self.app.agent_views
        if not views.nodes:
            self.details.update(Text("No delegated agents yet. Activity appears here when a task starts."))
            return
        for agent_id in views.order():
            view = views.nodes[agent_id]
            data = view.data
            parent_id = data.get("parent_agent_id")
            if agent_id not in self.tree_nodes:
                parent = self.tree_nodes.get(parent_id, self.agent_tree.root)
                self.tree_nodes[agent_id] = parent.add("", data=agent_id, expand=True)
            status = data.get("status", "queued").replace("_", " ")
            label = f"{data.get('name', agent_id)} · {status}"
            if view.current_tool and data.get("status") == "running":
                label += f" · {view.current_tool}"
            self.tree_nodes[agent_id].set_label(Text(label))
        self.show_details()

    @on(Tree.NodeHighlighted)
    def show_details(self) -> None:
        node = self.agent_tree.cursor_node or self.agent_tree.root
        view = self.app.agent_views.nodes.get(node.data)
        if view is None:
            return
        data = view.data
        parts = [f"{data.get('name', node.data)} [{node.data}]", data.get("goal", "")]
        if view.history:
            parts.extend(["", *view.history])
        if view.progress:
            parts.extend(["", view.progress])
        result = data.get("error") or data.get("result") or view.output
        if result:
            parts.extend(["", str(result)])
        self.details.update(Text("\n".join(parts)))

    def action_cancel_agent(self) -> None:
        node = self.agent_tree.cursor_node
        if node is not None and node.data != "main":
            self.app.cancel_agent(node.data)

    def action_close(self) -> None:
        self.dismiss(None)
