"""JSON-lines transport for the TypeScript terminal; agent work stays in Python."""
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import uuid
from io import StringIO
from pathlib import Path
from typing import Callable

from platformdirs import user_config_dir
from prompt_toolkit.history import FileHistory, History
from rich.console import Console

from agent.agent import Agent
from config.config import ApprovalPolicy, Config
from tools.base import ToolConfirmation
from ui.components.logo import POSTAL_BLOB, POSTAL_VERSION
from ui.repl.commands import SlashCommands
from ui.theme import AGENT_THEME
from utils.paths import is_binary_file, resolve_path


class CommandConsole(Console):
    def __init__(self):
        super().__init__(file=StringIO(), theme=AGENT_THEME, color_system=None, highlight=False)
        self.cleared = False

    def clear(self, home: bool = True) -> None:
        self.cleared = True


class BridgeSession:
    def __init__(
        self, config: Config, emit: Callable[[dict], None], *,
        resume: str | None = None, upgrade_notice: str | None = None,
        agent_factory=Agent, history: History | None = None,
    ):
        self.config, self.emit = config, emit
        self.resume, self.upgrade_notice = resume, upgrade_notice
        self.agent_factory, self.history = agent_factory, history
        self.agent: Agent | None = None
        self.ready = asyncio.Event()
        self.stopped = asyncio.Event()
        self.turn: asyncio.Task | None = None
        self.pending: dict[str, asyncio.Future[bool]] = {}
        self.console = CommandConsole()
        self.commands = SlashCommands(config, self.console)
        self.prompts: list[str] = []

    @property
    def busy(self) -> bool:
        return self.turn is not None and not self.turn.done()

    def settings(self) -> dict:
        return {
            "model": self.config.model_name, "cwd": str(self.config.cwd),
            "approval": self.config.approval.label,
            "reasoning": self.config.reasoning.model_dump(),
        }

    def transcript(self) -> list[dict]:
        if self.agent is None:
            return []
        return [
            {"role": message["role"], "text": message["content"]}
            for message in self.agent.session.context_manager.get_messages()
            if message.get("role") in {"user", "assistant"} and isinstance(message.get("content"), str)
            and message["content"]
        ]

    async def run(self) -> None:
        try:
            if self.history is None:
                history_path = Path(user_config_dir("postal")) / "history"
                try:
                    history_path.parent.mkdir(parents=True, exist_ok=True)
                    self.history = FileHistory(str(history_path))
                except OSError:
                    pass
            if self.history is not None:
                try:
                    self.prompts = list(reversed(list(self.history.load_history_strings())))[-100:]
                except OSError:
                    pass
            async with self.agent_factory(
                self.config, confirmation_callback=self.confirm, resume=self.resume,
            ) as agent:
                self.agent = agent
                self.emit({
                    "type": "ready", "settings": self.settings(), "history": self.prompts,
                    "messages": self.transcript(), "logo": list(POSTAL_BLOB), "version": POSTAL_VERSION,
                    "commands": [{"name": name, "description": self.commands.describe(name)}
                                 for name in self.commands.command_names()],
                    "capabilities": {name: agent.session.tool_registry.get(name) is not None for name in ("read", "search")},
                })
                self.ready.set()
                if self.resume and agent.resumed is None:
                    self.emit({"type": "notice", "text": f"No saved session matched '{self.resume}'."})
                if self.upgrade_notice:
                    self.emit({"type": "toast", "text": self.upgrade_notice})
                try:
                    await self.stopped.wait()
                finally:
                    await self.cancel()
                    if agent.session.turns:
                        agent.session.save_checkpoint()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.emit({"type": "fatal", "message": f"Could not start the session: {exc}"})
        finally:
            self.ready.set()
            self.agent = None
            self.stopped.set()

    async def close(self) -> None:
        await self.cancel()
        self.stopped.set()

    async def cancel(self) -> None:
        for future in self.pending.values():
            if not future.done():
                future.set_result(False)
        if self.busy:
            self.turn.cancel()
            await asyncio.gather(self.turn, return_exceptions=True)

    def file_reference(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Enter a file path inside this workspace.")
        path = resolve_path(self.config.cwd, value)
        if not path.is_file():
            raise ValueError("Enter the path to an existing file.")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Choose a file smaller than 10 MB.")
        if is_binary_file(path):
            raise ValueError("Choose a text or code file; images aren't supported yet.")
        with path.open("rb") as file:
            file.read(1)
        return path

    async def dispatch(self, method: str, params: dict) -> dict:
        if method == "quit":
            await self.close()
            return {}
        if method == "resize":
            self.console.width = min(300, max(20, int(params.get("columns", 80)) - 8))
            return {}
        if method == "approve":
            future = self.pending.get(params.get("approvalId"))
            if future is None or future.done():
                raise ValueError("This approval is no longer pending.")
            approved = params.get("approved")
            if not isinstance(approved, bool):
                raise ValueError("Approval must be true or false.")
            future.set_result(approved)
            return {}
        if method == "cancel":
            await self.cancel()
            return {}
        if self.agent is None or not self.ready.is_set() or self.stopped.is_set():
            raise ValueError("The Python agent is not ready yet.")
        if method == "agents":
            return {"agents": [record.snapshot() for record in self.agent.runtime.records.values()]}
        if method == "cancel_agent":
            await self.agent.runtime.cancel(self.agent.agent_id, params["agentId"])
            return {}
        if method == "file":
            if self.agent.session.tool_registry.get("read") is None:
                raise ValueError("File reading is disabled in this workspace.")
            return {"path": str(self.file_reference(params.get("path", "")))}
        if self.busy:
            raise ValueError("A response is already running. Stop it before changing settings or sending another prompt.")
        if method == "model":
            model = params.get("model", "").strip()
            if not model or any(char.isspace() for char in model):
                raise ValueError("Enter a model ID without spaces.")
            await self.command(f"/model {model}", quiet=True)
            return self.settings()
        if method == "effort":
            effort = params.get("effort")
            if effort not in {"auto", "minimal", "low", "medium", "high", "none"}:
                raise ValueError("Unsupported reasoning effort.")
            if effort == "auto":
                self.config.reasoning.effort = None
                self.config.reasoning.max_tokens = None
                effort = "on"
            await self.command(f"/thinking {effort}", quiet=True)
            return self.settings()
        if method == "approval":
            mode = params.get("mode")
            if mode not in {policy.value for policy in ApprovalPolicy}:
                raise ValueError("Unsupported approval mode.")
            await self.command(f"/approval {mode}", quiet=True)
            return self.settings()
        if method == "submit":
            text = params.get("text", "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Enter a prompt first.")
            text = text.strip()
            files = params.get("files", [])
            if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
                raise ValueError("File references must be a list of paths.")
            paths = [str(self.file_reference(path)) for path in files]
            if paths and self.agent.session.tool_registry.get("read") is None:
                raise ValueError("File reading is disabled in this workspace.")
            if params.get("web") and self.agent.session.tool_registry.get("search") is None:
                raise ValueError("Web search is disabled in this workspace.")
            if self.history is not None:
                try:
                    self.history.append_string(text)
                except OSError:
                    pass
            if text.startswith("/"):
                await self.command(text)
                return {"accepted": True}
            request = text
            if paths:
                request += "\n\nRead these referenced files as context:\n" + "\n".join(f"- {path}" for path in paths)
            if params.get("web"):
                request += "\n\nUse web search for this request and cite the sources you use."
            plan = self.agent.session.tool_registry.get("plan")
            if plan is not None and hasattr(plan, "reset"):
                plan.reset()
            self.emit({"type": "turn_start", "text": text, "files": paths, "web": bool(params.get("web"))})
            self.turn = asyncio.create_task(self.run_turn(request), name="postal-bridge-turn")
            return {"accepted": True}
        raise ValueError(f"Unknown frontend request: {method}")

    async def command(self, text: str, *, quiet: bool = False) -> None:
        if text.strip() in {"/exit", "/quit"}:
            await self.close()
            self.emit({"type": "exit"})
            return
        if text.strip() == "/agents":
            self.emit({"type": "open_agents"})
            return
        with self.console.capture() as capture:
            await self.commands.execute(self.agent, text)
        cleared = self.console.cleared
        if cleared:
            self.console.cleared = False
            self.emit({"type": "transcript", "messages": self.transcript()})
        output = capture.get().strip()
        if output:
            self.emit({"type": "toast" if quiet or cleared else "notice", "text": output})
        self.emit({"type": "settings", "settings": self.settings()})

    async def run_turn(self, text: str) -> None:
        events = self.agent.run(text)
        status = "Ready"
        try:
            async for event in events:
                if event.type.value == "agent_error" and event.agent_id in {None, self.agent.agent_id}:
                    status = "Failed"
                self.emit({"type": "agent_event", "event": {
                    "type": event.type.value, "data": event.data,
                    "agent_id": event.agent_id, "parent_agent_id": event.parent_agent_id,
                }})
        except asyncio.CancelledError:
            status = "Interrupted"
        except Exception as exc:
            status = "Failed"
            self.emit({"type": "notice", "text": f"Error: {exc}"})
        finally:
            await events.aclose()
            for record in self.agent.runtime.records.values():
                self.emit({"type": "agent_event", "event": {
                    "type": "agent_status", "data": record.snapshot(),
                    "agent_id": record.agent_id, "parent_agent_id": record.parent_agent_id,
                }})
            self.emit({"type": "turn_end", "status": status})

    async def confirm(self, confirmation: ToolConfirmation) -> bool:
        if self.stopped.is_set():
            return False
        approval_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[approval_id] = future
        self.emit({"type": "approval", "approval": {
            "id": approval_id, "tool": confirmation.tool_name,
            "description": confirmation.description, "params": confirmation.params,
            "command": confirmation.command,
            "diff": confirmation.diff.create_diff() if confirmation.diff else None,
            "paths": list(map(str, confirmation.affected_paths)),
            "dangerous": confirmation.is_dangerous,
        }})
        try:
            return await future
        finally:
            self.pending.pop(approval_id, None)
            self.emit({"type": "approval_closed", "id": approval_id})


async def serve() -> None:
    output = sys.stdout

    def emit(message: dict) -> None:
        output.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
        output.flush()

    session = None
    lifecycle = None
    # Plugin/tool startup prints must never corrupt the transport stream.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            while line := await asyncio.to_thread(sys.stdin.readline):
                request_id = None
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ValueError("A request must be an object.")
                    request_id = request.get("id")
                    method = request.get("method")
                    params = request.get("params", {})
                    if not isinstance(params, dict):
                        raise ValueError("Request parameters must be an object.")
                    if method == "init":
                        if session is not None:
                            raise ValueError("The session is already initialized.")
                        session = BridgeSession(
                            Config.model_validate(params["config"]), emit,
                            resume=params.get("resume"), upgrade_notice=params.get("upgrade_notice"),
                        )
                        lifecycle = asyncio.create_task(session.run(), name="postal-bridge-session")
                        result = {}
                    elif session is None:
                        raise ValueError("Initialize the session first.")
                    else:
                        result = await session.dispatch(method, params)
                    emit({"type": "result", "id": request_id, "result": result})
                    if method == "quit" or (session and session.stopped.is_set()):
                        break
                except Exception as exc:
                    emit({"type": "error", "id": request_id, "message": str(exc)})
        finally:
            if session:
                await session.close()
            if lifecycle:
                if session and not session.ready.is_set():
                    lifecycle.cancel()
                await asyncio.gather(lifecycle, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(serve())
