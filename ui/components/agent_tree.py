from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from agent.events import AgentEvent, AgentEventType
from agent.runtime import TERMINAL_STATES

STATUS_MARKS = {
    "queued": ("○", "muted"), "running": ("◌", "info"),
    "waiting": ("◷", "warning"), "waiting_for_approval": ("?", "warning"),
    "waiting_for_writer": ("◷", "muted"), "completed": ("✓", "success"),
    "failed": ("✗", "error"), "timed_out": ("!", "error"),
    "cancelled": ("−", "muted"),
}


@dataclass
class AgentView:
    data: dict[str, Any]
    current_tool: str = ""
    progress: str = ""
    history: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    output: str = ""


class AgentTree:
    """A bounded view of structured agent events; never parses progress strings."""

    def __init__(self):
        self.nodes: dict[str, AgentView] = {}
        self.selected: str | None = None
        self.expanded: set[str] = set()

    @property
    def visible(self) -> bool:
        return len(self.nodes) > 1

    def update(self, event: AgentEvent) -> None:
        agent_id = event.agent_id
        if agent_id is None:
            return
        if event.type == AgentEventType.AGENT_STATUS:
            if agent_id not in self.nodes:
                self.nodes[agent_id] = AgentView(dict(event.data))
                if event.parent_agent_id is not None and self.selected is None:
                    self.selected = agent_id
            else:
                self.nodes[agent_id].data.update(event.data)
            return
        node = self.nodes.get(agent_id)
        if node is None:
            return
        if event.type == AgentEventType.TOOL_CALL_START:
            node.current_tool = event.data.get("name", "tool")
            node.progress = ""
            node.history.append(f"Running {node.current_tool}")
        elif event.type == AgentEventType.TOOL_PROGRESS:
            lines = event.data.get("content", "").strip().splitlines()
            if lines:
                node.progress = lines[-1][:160]
        elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
            name = event.data.get("name", "tool")
            status = "Completed" if event.data.get("success") else "Failed"
            node.history.append(f"{status} {name}")
            node.current_tool = ""
            node.progress = ""
            node.output = (event.data.get("output") or event.data.get("error") or "")[-2000:]
        elif event.type == AgentEventType.USAGE:
            node.data["usage"] = event.data.get("usage") or {}
        elif event.type == AgentEventType.TEXT_COMPLETE:
            node.data["result"] = event.data.get("content")

    def order(self) -> list[str]:
        ordered = []

        def visit(parent_id):
            for agent_id, node in self.nodes.items():
                if node.data.get("parent_agent_id") == parent_id:
                    ordered.append(agent_id)
                    visit(agent_id)

        visit(None)
        return ordered

    def move(self, amount: int) -> None:
        ids = [i for i in self.order() if self.nodes[i].data.get("parent_agent_id") is not None]
        if ids:
            current = ids.index(self.selected) if self.selected in ids else 0
            self.selected = ids[(current + amount) % len(ids)]

    def toggle_selected(self) -> None:
        if self.selected in self.expanded:
            self.expanded.remove(self.selected)
        elif self.selected is not None:
            self.expanded.add(self.selected)

    def render(self, *, interactive: bool = True, max_rows: int = 12) -> Panel:
        ids = self.order()
        children: dict[str | None, list[str]] = {}
        for agent_id in ids:
            children.setdefault(self.nodes[agent_id].data.get("parent_agent_id"), []).append(agent_id)

        def prefix_for(agent_id):
            ancestors = []
            parent_id = self.nodes[agent_id].data.get("parent_agent_id")
            current = parent_id
            while current is not None and self.nodes[current].data.get("parent_agent_id") is not None:
                grandparent = self.nodes[current].data.get("parent_agent_id")
                ancestors.append("│  " if children[grandparent][-1] != current else "   ")
                current = grandparent
            return "".join(reversed(ancestors)) + (
                ("└─ " if children[parent_id][-1] == agent_id else "├─ ") if parent_id is not None else ""
            )

        selected_index = ids.index(self.selected) if self.selected in ids else 0
        start = max(0, selected_index - max_rows + 1)
        shown = ids[start:start + max_rows]
        lines = []
        for agent_id in shown:
            node = self.nodes[agent_id]
            data = node.data
            status = data.get("status", "queued")
            mark, style = STATUS_MARKS.get(status, ("○", "muted"))
            depth = data.get("depth", 0)
            prefix = prefix_for(agent_id)
            selected = interactive and agent_id == self.selected
            line = Text(("> " if selected else "  ") + prefix)
            line.append(f"{mark} ", style=style)
            line.append(data.get("name", agent_id), style="bold" if selected else "subtitle")
            if depth:
                line.append(f" [{agent_id}]", style="dim")
            elapsed = int((data.get("finished_at") or time.monotonic()) - data.get("started_at", time.monotonic()))
            detail = status.replace("_", " ")
            if node.current_tool and status not in TERMINAL_STATES:
                detail += f" · {node.current_tool}"
                if node.progress:
                    detail += f" · {node.progress}"
            tokens = (data.get("usage") or {}).get("total_tokens", 0)
            line.append(f"  {detail} · {max(0, elapsed)}s", style=style)
            if tokens:
                line.append(f" · {tokens:,} tokens", style="dim")
            line.truncate(120, overflow="ellipsis")
            lines.append(line)
            if interactive and selected and agent_id in self.expanded:
                detail_lines = [f"Task: {data.get('goal', '')}", *list(node.history)[-4:]]
                output = data.get("error") or data.get("result") or node.output
                if output:
                    detail_lines.extend(str(output).splitlines()[-6:])
                for detail_line in detail_lines:
                    text = Text("    " + detail_line, style="muted")
                    text.truncate(110, overflow="ellipsis")
                    lines.append(text)
        if len(shown) < len(ids):
            lines.append(Text(f"  Showing {len(shown)} of {len(ids)} agents", style="dim"))
        running = sum(n.data.get("status") == "running" for n in self.nodes.values())
        waiting = sum(str(n.data.get("status", "")).startswith("waiting") for n in self.nodes.values())
        tokens = sum((n.data.get("usage") or {}).get("total_tokens", 0) for n in self.nodes.values())
        title = f"Agents · {running} running · {waiting} waiting · {tokens:,} tokens"
        subtitle = "↑↓ select · Enter details · c cancel subtree" if interactive else None
        return Panel(Group(*lines), title=title, subtitle=subtitle, border_style="muted", padding=(0, 1))
