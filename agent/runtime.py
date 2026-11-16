from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable

from agent.events import AgentEvent, AgentEventType
from config.config import Config
from tools.base import ToolConfirmation

TERMINAL_STATES = {"completed", "failed", "cancelled", "timed_out"}


@dataclass
class AgentRecord:
    agent_id: str
    parent_agent_id: str | None
    name: str
    goal: str
    depth: int
    status: str = "queued"
    result: str | None = None
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    task: asyncio.Task | None = field(default=None, repr=False)
    collected: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "name": self.name,
            "goal": self.goal,
            "depth": self.depth,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "usage": dict(self.usage),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class AgentRuntime:
    """Own all tasks in one turn. Only the root consumes the event stream."""

    def __init__(self, config: Config, confirmation_callback=None, agent_factory=None):
        self.config = config
        self.confirmation_callback = confirmation_callback
        self.agent_factory = agent_factory
        self.root_id = "main"
        self.records: dict[str, AgentRecord] = {}
        self.events: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._slots = asyncio.Semaphore(config.agents.max_concurrent)
        self._holding_slot: set[str] = set()
        self._approval_lock = asyncio.Lock()
        self._mutation_lock = asyncio.Lock()

    def begin_turn(self, goal: str) -> None:
        if any(r.task and not r.task.done() for r in self.records.values()):
            raise RuntimeError("The previous agent turn is still running")
        self.records = {
            self.root_id: AgentRecord(self.root_id, None, "Main agent", goal, 0)
        }
        self.events = asyncio.Queue()
        self._slots = asyncio.Semaphore(self.config.agents.max_concurrent)
        self._holding_slot.clear()
        self.set_status(self.root_id, "queued")

    def set_status(self, agent_id: str, status: str) -> None:
        record = self.records[agent_id]
        record.status = status
        if status in TERMINAL_STATES and record.finished_at is None:
            record.finished_at = time.monotonic()
        self.events.put_nowait(AgentEvent(
            AgentEventType.AGENT_STATUS, record.snapshot(), agent_id, record.parent_agent_id
        ))

    def publish(self, event: AgentEvent, agent_id: str) -> None:
        record = self.records[agent_id]
        event = replace(event, agent_id=agent_id, parent_agent_id=record.parent_agent_id)
        if event.type == AgentEventType.USAGE:
            record.usage = dict(event.data.get("usage") or {})
        elif event.type == AgentEventType.TEXT_COMPLETE:
            record.result = event.data.get("content")
        elif event.type == AgentEventType.AGENT_ERROR:
            record.error = event.data.get("error", "Agent failed")
            self.set_status(agent_id, "failed")
        elif event.type == AgentEventType.AGENT_END:
            record.result = event.data.get("response") or record.result
            if record.status not in TERMINAL_STATES:
                self.set_status(agent_id, "completed")
        self.events.put_nowait(event)

    @asynccontextmanager
    async def execution_slot(self, agent_id: str):
        await self._slots.acquire()
        self._holding_slot.add(agent_id)
        self.set_status(agent_id, "running")
        try:
            yield
        finally:
            if agent_id in self._holding_slot:
                self._holding_slot.remove(agent_id)
                self._slots.release()

    @asynccontextmanager
    async def suspended(self, agent_id: str, status: str = "waiting"):
        """Waiting for children, locks or approval must not consume a slot."""
        held = agent_id in self._holding_slot
        if held:
            self._holding_slot.remove(agent_id)
            self._slots.release()
        previous = self.records[agent_id].status
        if previous not in TERMINAL_STATES:
            self.set_status(agent_id, status)
        try:
            yield
        except BaseException:
            # Cancellation must never block trying to reacquire a slot.
            raise
        else:
            if held:
                await self._slots.acquire()
                self._holding_slot.add(agent_id)
            if self.records[agent_id].status not in TERMINAL_STATES:
                self.set_status(agent_id, previous)

    @asynccontextmanager
    async def mutation(self, agent_id: str):
        acquired = False
        try:
            async with self.suspended(agent_id, "waiting_for_writer"):
                await self._mutation_lock.acquire()
                acquired = True
            yield
        finally:
            if acquired:
                self._mutation_lock.release()

    def confirmation_for(self, agent_id: str) -> Callable[[ToolConfirmation], Awaitable[bool]] | None:
        if self.confirmation_callback is None:
            return None

        async def confirm(confirmation: ToolConfirmation) -> bool:
            record = self.records[agent_id]
            description = confirmation.description
            if record.parent_agent_id is not None:
                description = f"[{record.name} · {agent_id}] {description}"
            async with self.suspended(agent_id, "waiting_for_approval"):
                async with self._approval_lock:
                    return await self.confirmation_callback(
                        replace(confirmation, description=description)
                    )

        return confirm

    def descendants(self, agent_id: str) -> list[AgentRecord]:
        found = []
        for record in self.records.values():
            parent = record.parent_agent_id
            while parent is not None:
                if parent == agent_id:
                    found.append(record)
                    break
                parent = self.records[parent].parent_agent_id
        return found

    def _owned(self, parent_id: str, agent_ids: list[str]) -> list[AgentRecord]:
        allowed = {r.agent_id for r in self.descendants(parent_id)}
        if any(agent_id not in allowed for agent_id in agent_ids):
            raise ValueError("You can only wait for or cancel your own descendants")
        return [self.records[agent_id] for agent_id in dict.fromkeys(agent_ids)]

    def spawn(self, parent_id: str, config: Config, definition, goal: str) -> AgentRecord:
        from tools.subagents.subagents import SubAgentTool

        if not goal.strip():
            raise ValueError("An agent needs a non-empty goal")
        parent = self.records[parent_id]
        if parent.status in TERMINAL_STATES:
            raise ValueError("A finished agent cannot spawn children")
        if parent.depth >= self.config.agents.max_depth:
            raise ValueError(f"Maximum delegation depth ({self.config.agents.max_depth}) reached")
        if len(self.records) >= self.config.agents.max_agents:
            raise ValueError(f"Maximum agents per turn ({self.config.agents.max_agents}) reached")
        agent_id = uuid.uuid4().hex[:8]
        record = AgentRecord(agent_id, parent_id, definition.name, goal, parent.depth + 1)
        child_config = SubAgentTool(config, definition).subagent_config()
        self.records[agent_id] = record
        self.set_status(agent_id, "queued")
        record.task = asyncio.create_task(
            self._run_child(record, child_config, definition), name=f"agent:{agent_id}"
        )
        return record

    async def _run_child(self, record: AgentRecord, config: Config, definition) -> None:
        from agent.agent import Agent

        factory = self.agent_factory or Agent
        prompt = (
            f"You are a specialized sub-agent. {definition.goal_prompt}\n\n"
            f"Your task: {record.goal}\n\n"
            "Complete only this task. Your final response goes to your parent agent. "
            "Delegate independent subtasks when useful, then wait for their results. "
            "Descendants inherit your tool restrictions. Keep your final response concise."
        )
        prompt += f"\nYou are at delegation depth {record.depth} of {self.config.agents.max_depth}. "
        if record.depth >= self.config.agents.max_depth:
            prompt += "Do not spawn further agents; complete this task with your own tools."
        try:
            # Includes time queued and initialization, not just time between events.
            async with asyncio.timeout(min(definition.timeout_seconds, self.config.agents.timeout_seconds)):
                async with self.execution_slot(record.agent_id):
                    async with factory(
                        config, runtime=self, agent_id=record.agent_id,
                        confirmation_callback=self.confirmation_for(record.agent_id),
                    ) as agent:
                        async for event in agent.run(prompt):
                            self.publish(event, record.agent_id)
                        await self.join_children(record.agent_id)
            if record.status not in TERMINAL_STATES:
                self.set_status(record.agent_id, "completed")
        except TimeoutError:
            record.error = "Agent timed out"
            self.set_status(record.agent_id, "timed_out")
        except asyncio.CancelledError:
            if record.status not in TERMINAL_STATES:
                self.set_status(record.agent_id, "cancelled")
            raise
        except Exception as exc:
            record.error = str(exc)
            self.set_status(record.agent_id, "failed")
        finally:
            await self.cancel_descendants(record.agent_id)

    async def wait(self, parent_id: str, agent_ids: list[str]) -> list[AgentRecord]:
        records = self._owned(parent_id, agent_ids)
        tasks = [r.task for r in records if r.task is not None]
        if tasks:
            async with self.suspended(parent_id):
                # Cancelling the waiter is handled by subtree cleanup, not gather.
                await asyncio.gather(*(asyncio.shield(t) for t in tasks), return_exceptions=True)
        for record in records:
            if record.parent_agent_id == parent_id:
                record.collected = True
        return records

    async def join_children(self, parent_id: str) -> None:
        children = [r.agent_id for r in self.records.values() if r.parent_agent_id == parent_id]
        if children:
            await self.wait(parent_id, children)

    async def cancel(self, parent_id: str, agent_id: str) -> None:
        record = self._owned(parent_id, [agent_id])[0]
        targets = [record, *self.descendants(agent_id)]
        tasks = []
        for target in targets:
            if target.task is not None and not target.task.done():
                if not target.task.cancelling():
                    target.task.cancel()
                tasks.append(target.task)
        if tasks:
            # Another cancel request must not interrupt a task's cleanup.
            await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)
        # A task cancelled before its first instruction never enters its finally.
        for target in targets:
            if target.status not in TERMINAL_STATES:
                self.set_status(target.agent_id, "cancelled")

    async def cancel_descendants(self, parent_id: str) -> None:
        for record in list(self.records.values()):
            if record.parent_agent_id == parent_id:
                await self.cancel(parent_id, record.agent_id)

    def total_usage(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for record in self.records.values():
            for key, value in record.usage.items():
                totals[key] = totals.get(key, 0) + (value or 0)
        return totals
