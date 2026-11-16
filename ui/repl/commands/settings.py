from __future__ import annotations

from rich.table import Table
from rich.text import Text

from agent.agent import Agent
from config.config import ApprovalPolicy
from config.loader import save_model_name
from ui.repl.commands.base import CommandGroup


class SettingsCommands(CommandGroup):

    def show_config(self, agent: Agent, args: list[str]) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="muted")
        table.add_column(style="subtitle")

        policy = self.config.approval
        rows = [
            ("Model", self.config.model_name),
            ("Temperature", str(self.config.temperature)),
            ("Context window", f"{self.config.model.context_window:,}"),
            ("Directory", str(self.config.cwd)),
            ("Approval", f"{policy.label} - {policy.summary}"),
            ("Thinking", self._thinking_summary()),
            ("Max turns", str(self.config.max_turns)),
            ("Concurrent agents", str(self.config.agents.max_concurrent)),
            ("Delegation depth", str(self.config.agents.max_depth)),
            ("Agents per turn", str(self.config.agents.max_agents)),
            ("Max tool output tokens", f"{self.config.max_tool_output_tokens:,}"),
            ("Hooks enabled", str(self.config.hooks_enabled)),
            ("MCP servers", str(len(self.config.mcp_servers))),
            ("Debug", str(self.config.debug)),
        ]
        for label, value in rows:
            table.add_row(f"{label}:", value)

        self.console.print(Text("Configuration", style="highlight"))
        self.console.print(table)

    def set_model(self, agent: Agent, args: list[str]) -> None:
        if not args:
            self.console.print(
                Text.assemble(("Current model: ", "muted"), (self.config.model_name, "subtitle"))
            )
            self.console.print(Text("Usage: /model <name>", style="muted"))
            return

        self.config.model_name = args[0]
        try:
            save_model_name(args[0], cwd=self.config.cwd)
        except Exception as exc:
            self.console.print(f"[warning]Model changed for this session, but could not be saved: {exc}[/warning]")
            return
        self.console.print(f"[success]Model set to {args[0]}[/success]")

    def set_approval(self, agent: Agent, args: list[str]) -> None:
        if not args:
            self._approval_modes()
            return

        try:
            policy = ApprovalPolicy(args[0].lower())
        except ValueError:
            self.console.print(f"[error]Unknown approval mode: {args[0]}[/error]")
            self._approval_modes()
            return

        self.config.approval = policy
        agent.session.approval_manager.approval_policy = policy
        self.console.print(f"[success]Approval mode set to {policy.label}[/success]")

    def _approval_modes(self) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="subtitle")
        table.add_column(style="muted")
        for policy in ApprovalPolicy:
            marker = " (current)" if policy is self.config.approval else ""
            table.add_row(policy.value, f"{policy.summary}{marker}")

        self.console.print(Text("Approval modes:", style="highlight"))
        self.console.print(table)
        self.console.print(Text("Usage: /approval <mode>", style="muted"))

    def _thinking_summary(self) -> str:
        reasoning = self.config.reasoning
        if not reasoning.enabled:
            return "off"

        detail = (
            f"{reasoning.max_tokens:,} tokens"
            if reasoning.max_tokens is not None
            else reasoning.effort or "default"
        )
        return f"{'shown' if reasoning.visible else 'hidden'} - {detail}"

    def set_thinking(self, agent: Agent, args: list[str]) -> None:
        reasoning = self.config.reasoning

        if not args:
            self._thinking_state()
            self.console.print(
                Text("Usage: /thinking <on|off|low|medium|high|minimal>", style="muted")
            )
            return

        choice = args[0].lower()

        if choice in {"on", "show"}:
            reasoning.enabled = True
            reasoning.visible = True
        elif choice in {"off", "hide"}:
            # The model keeps reasoning, we just stop printing it.
            reasoning.visible = False
        elif choice in {"minimal", "low", "medium", "high"}:
            reasoning.enabled = True
            reasoning.visible = True
            reasoning.effort = choice
            reasoning.max_tokens = None
        elif choice == "none":
            reasoning.enabled = False
            reasoning.visible = False
        else:
            self.console.print(f"[error]Unknown thinking option: {args[0]}[/error]")
            self.console.print(
                Text("Usage: /thinking <on|off|low|medium|high|minimal|none>", style="muted")
            )
            return

        self._thinking_state()

    def _thinking_state(self) -> None:
        reasoning = self.config.reasoning

        if not reasoning.enabled:
            self.console.print(Text("Thinking is off - no reasoning requested.", style="muted"))
            return

        if reasoning.max_tokens is not None:
            budget = f"{reasoning.max_tokens:,} token budget"
        elif reasoning.effort is not None:
            budget = f"{reasoning.effort} effort"
        else:
            budget = "provider default"

        line = Text.assemble(
            ("thinking ", "muted"),
            ("shown" if reasoning.visible else "hidden", "success" if reasoning.visible else "subtitle"),
            (f" — {budget}", "muted"),
        )
        self.console.print(line)
        self.console.print(
            Text("Models without reasoning support simply ignore this.", style="dim")
        )
