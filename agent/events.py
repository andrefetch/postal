from __future__ import annotations
from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from client.response import TokenUsage
from tools.base import ToolResult

class AgentEventType(str, Enum):

    # Agentic loops, and err
    AGENT_START="agent_start"
    AGENT_END="agent_end"
    AGENT_ERROR="agent_error"
    AGENT_STATUS = "agent_status"

    # Token accounting, emitted once per completion
    USAGE = "usage"

    # Text streaming
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"

    # Reasoning ("thinking") streaming, only for models that expose it
    REASONING_DELTA = "reasoning_delta"
    REASONING_COMPLETE = "reasoning_complete"

    # Tool Calls
    TOOL_CALL_START = 'tool_call_start'
    TOOL_CALL_COMPLETE = 'tool_call_complete'
    TOOL_PROGRESS = 'tool_progress'

@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    parent_agent_id: str | None = None

    @classmethod
    def agent_start(
        cls, 
        message: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_START,
            data={
                "message": message
            }
        )

    @classmethod
    def agent_end(
        cls, 
        response: str | None = None, 
        usage: TokenUsage | None = None
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_END,
            data={
                "response": response,
                'usage': usage.__dict__ if usage else None
            },
        )
    
    @classmethod
    def usage(
        cls,
        turn_usage: TokenUsage
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.USAGE,
            data={
                'usage': turn_usage.__dict__,
            }
        )

    @classmethod
    def agent_error(
        cls, 
        error: str, 
        details: dict[str, Any] | None = None
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={
                "error": error,
                'details': details or {} 
            }
        )

    @classmethod
    def text_delta(
        cls, 
        content: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={
                "content": content
            }
        )

    @classmethod
    def text_complete(
        cls, 
        content: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={
                "content": content
            }
        )
    
    @classmethod
    def reasoning_delta(
        cls,
        content: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.REASONING_DELTA,
            data={
                "content": content
            }
        )

    @classmethod
    def reasoning_complete(
        cls,
        content: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.REASONING_COMPLETE,
            data={
                "content": content
            }
        )

    @classmethod
    def tool_call_start(cls, call_id: str, name: str, arguments: dict[str, Any]):
        return cls(
            type=AgentEventType.TOOL_CALL_START,
            data={
                'call_id': call_id,
                'name': name,
                'arguments': arguments
            }
        )
    
    @classmethod
    def tool_call_complete(cls, call_id: str, name: str, result: ToolResult):
        return cls(
            type=AgentEventType.TOOL_CALL_COMPLETE,
            data={
                'call_id': call_id,
                'name': name,
                'success': result.success,
                'output': result.output,
                'error': result.error,
                'metadata': result.metadata,
                'diff': result.diff.create_diff() if result.diff else None,
                'truncated': result.truncated,
                'exit_code': result.exit_code,
            }
        )
