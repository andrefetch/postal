from __future__ import annotations

from agent.agent import Agent
from agent.events import AgentEventType
from ui.components import random_thinking_text, thinking_text_for
from ui.tui import TUI


def _tool_kind(agent: Agent, tool_name: str) -> str | None:
    tool = agent.session.tool_registry.get(tool_name)
    return tool.kind.value if tool else None


async def stream_turn(tui: TUI, agent: Agent, message: str) -> str | None:

    final_response: str | None = None
    streaming = False
    failed = False
    label = random_thinking_text()

    tui.begin_agent_turn(agent.runtime)
    events = agent.run(message)

    try:
        async for event in events:
            tui.agent_event(event)
            if event.agent_id != agent.agent_id:
                continue
            if event.type == AgentEventType.AGENT_START:
                tui.start_thinking(label)

            elif event.type == AgentEventType.USAGE:
                tui.update_turn_usage(event.data.get("usage"))

            elif event.type == AgentEventType.REASONING_DELTA:
                tui.begin_reasoning()
                tui.stream_reasoning_delta(event.data.get("content", ""))

            elif event.type == AgentEventType.REASONING_COMPLETE:
                tui.end_reasoning()
                tui.start_thinking(label)

            elif event.type == AgentEventType.TEXT_DELTA:
                if not streaming:
                    tui.begin_assistant()
                    streaming = True
                tui.stream_assistant_delta(event.data.get("content", ""))

            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
                if streaming:
                    tui.end_assistant()
                    streaming = False

            elif event.type == AgentEventType.TOOL_CALL_START:
                name = event.data.get("name", "unknown")
                tui.tool_call_start(
                    event.data.get("call_id", ""),
                    name,
                    _tool_kind(agent, name),
                    event.data.get("arguments", {}),
                )

            elif event.type == AgentEventType.TOOL_PROGRESS:
                tui.tool_progress(event.data.get("content", ""))

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                name = event.data.get("name", "unknown")
                kind = _tool_kind(agent, name)
                tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    name,
                    kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("truncated", False),
                    event.data.get("diff"),
                    event.data.get("exit_code"),
                )
                label = thinking_text_for(name, kind)
                tui.start_thinking(label)

            elif event.type == AgentEventType.AGENT_END:
                tui.stop_thinking()
                tui.render_usage(event.data.get("usage"))

            elif event.type == AgentEventType.AGENT_ERROR:
                tui.stop_thinking()
                tui.gap()
                tui.print_block(f"[error]{event.data.get('error')}[/error]")
                failed = True
                break
    finally:
        await events.aclose()
        tui.stop_thinking()
        tui.end_reasoning()
        if streaming:
            tui.end_assistant()
        await tui.finish_agent_turn()

    return None if failed else final_response
