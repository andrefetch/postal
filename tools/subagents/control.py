from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.subagents.subagents import get_default_subagent_definitions


def agent_metadata(records):
    return {"agents": [
        {"agent_id": r.agent_id, "name": r.name, "status": r.status}
        for r in records
    ]}


class SpawnParams(BaseModel):
    role: Literal[
        "general", "codebase_investigator", "code_reviewer", "software_architect",
        "test_writer", "debugger",
    ] = Field(default="general", description="Role preset. General inherits all permitted tools.")
    goal: str = Field(min_length=1, description="Self-contained task, including relevant context and file ownership.")


class WaitParams(BaseModel):
    agent_ids: list[str] = Field(min_length=1, description="IDs returned by spawn_agent to collect results from.")


class CancelParams(BaseModel):
    agent_id: str = Field(description="ID of your descendant to cancel along with its children.")


class EmptyParams(BaseModel):
    pass


class AgentTool(Tool):
    kind = ToolKind.SUBAGENT

    def is_mutating(self, params) -> bool:
        return False

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        if invocation.runtime is None or invocation.agent_id is None:
            return ToolResult.error_result("Agent control tools require an active agent turn")
        try:
            return await self.control(invocation)
        except ValueError as exc:
            return ToolResult.error_result(str(exc))

    async def control(self, invocation: ToolInvocation) -> ToolResult:
        raise NotImplementedError


class SpawnAgentTool(AgentTool):
    name = "spawn_agent"
    description = (
        "Start a child agent in the background and immediately return its ID. "
        "Spawn independent tasks before waiting. Children may delegate within inherited limits."
    )
    schema = SpawnParams

    async def control(self, invocation: ToolInvocation) -> ToolResult:
        params = SpawnParams(**invocation.params)
        definition = next(d for d in get_default_subagent_definitions() if d.name == params.role)
        record = invocation.runtime.spawn(invocation.agent_id, self.config, definition, params.goal)
        return ToolResult.success_result(json.dumps({
            "agent_id": record.agent_id, "role": record.name, "status": record.status,
        }), metadata=agent_metadata([record]))


class WaitAgentsTool(AgentTool):
    name = "wait_agents"
    description = "Wait for your delegated agents and return each result and status, including failures."
    schema = WaitParams

    async def control(self, invocation: ToolInvocation) -> ToolResult:
        params = WaitParams(**invocation.params)
        records = await invocation.runtime.wait(invocation.agent_id, params.agent_ids)
        return ToolResult.success_result(json.dumps([
            {"agent_id": r.agent_id, "role": r.name, "status": r.status,
             "result": r.result, "error": r.error, "usage": r.usage}
            for r in records
        ]), metadata=agent_metadata(records))


class ListAgentsTool(AgentTool):
    name = "list_agents"
    description = "List your descendant agents and their current status. Use wait_agents to collect results."
    schema = EmptyParams

    async def control(self, invocation: ToolInvocation) -> ToolResult:
        records = invocation.runtime.descendants(invocation.agent_id)
        return ToolResult.success_result(json.dumps([
            {"agent_id": r.agent_id, "parent_agent_id": r.parent_agent_id,
             "role": r.name, "goal": r.goal, "status": r.status}
            for r in records
        ]), metadata=agent_metadata(records))


class CancelAgentTool(AgentTool):
    name = "cancel_agent"
    description = "Cancel one of your delegated agents and its entire subtree, waiting for cleanup."
    schema = CancelParams

    async def control(self, invocation: ToolInvocation) -> ToolResult:
        params = CancelParams(**invocation.params)
        await invocation.runtime.cancel(invocation.agent_id, params.agent_id)
        return ToolResult.success_result(json.dumps({
            "agent_id": params.agent_id,
            "status": invocation.runtime.records[params.agent_id].status,
        }), metadata=agent_metadata([invocation.runtime.records[params.agent_id]]))


def get_agent_tools() -> list[type[Tool]]:
    return [SpawnAgentTool, WaitAgentsTool, ListAgentsTool, CancelAgentTool]
