from __future__ import annotations
import json
from typing import AsyncGenerator, Awaitable, Callable
from agent.session import Session
from agent.store import SessionRecord
from config.config import Config
from agent.events import AgentEvent, AgentEventType
from client.response import StreamEventType, TokenUsage, ToolCall, ToolResultMessage
from prompts import create_loop_breaker_prompt
from tools.base import ToolConfirmation

class Agent:
    def __init__(
        self,
        config: Config,
        confirmation_callback: Callable[[ToolConfirmation], Awaitable[bool]] | None = None,
        resume: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.config = config
        self.session: Session | None = Session(self.config)
        self.session.approval_manager.confirmation_callback = confirmation_callback

        self.progress_callback = progress_callback

        # Resolved on entry, once the session has a context manager to fill.
        self._resume = resume
        self.resumed: SessionRecord | None = None

    async def run(self, message: str):
        await self.session.hook_system.trigger_before_agent(message)
        yield AgentEvent.agent_start(message)
        self.session.inc_turn()
        self.session.note_prompt(message)
        self.session.reset_turn_usage()
        self.session.context_manager.add_user_message(message)

        final_response: str | None = None

        async for event in self._agentic_loop():
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")

        await self.session.hook_system.trigger_after_agent(message, final_response)
        self.session.save_checkpoint()
        yield AgentEvent.agent_end(final_response, self.session.last_usage)
    
    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:

        max_turns = self.config.max_turns

        for i in range(max_turns):

            response_text = ""
            reasoning_text = ""
            reasoning_done = False

            # Prune before compacting: a tool-heavy turn can blow past the context
            # window without ever reaching the end of the loop.
            self.session.context_manager.prune_tool_outputs()

            if self.session.context_manager.needs_compression():
                summary, usage = await self.session.chat_compactor.compress(
                    self.session.context_manager
                )

                if summary:
                    self.session.context_manager.replace_with_summary(summary)
                    self.session.context_manager.set_latest_usage(usage)
                    self.session.context_manager.add_usage(usage)

            tool_schemas = self.session.tool_registry.get_schemas()

            tool_calls: list[ToolCall] = []
            usage: TokenUsage | None = None
            
            async for event in self.session.client.chat_completion(
                self.session.context_manager.get_messages(), 
                tools=tool_schemas if tool_schemas else None, 
                stream=True
            ):
                if event.type == StreamEventType.REASONING_DELTA:
                    if not event.reasoning_delta:
                        continue
                    reasoning_text += event.reasoning_delta
                    yield AgentEvent.reasoning_delta(event.reasoning_delta)
                elif event.type == StreamEventType.TEXT_DELTA:
                    if not event.text_delta:
                        continue
                    content = event.text_delta.content
                    # Thinking always ends where the answer begins.
                    if reasoning_text and not reasoning_done:
                        reasoning_done = True
                        yield AgentEvent.reasoning_complete(reasoning_text)
                    response_text += content
                    yield AgentEvent.text_delta(content)
                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call:
                        tool_calls.append(event.tool_call)
                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                    if event.reasoning_delta and not reasoning_text:
                        reasoning_text = event.reasoning_delta
                        yield AgentEvent.reasoning_delta(event.reasoning_delta)
                    if event.usage:
                        usage = event.usage
                        self.session.last_usage = event.usage
                        self.session.turn_usage += event.usage
                        yield AgentEvent.usage(self.session.turn_usage)
                    if event.text_delta:
                        if reasoning_text and not reasoning_done:
                            reasoning_done = True
                            yield AgentEvent.reasoning_complete(reasoning_text)
                        response_text += event.text_delta.content
                        yield AgentEvent.text_delta(event.text_delta.content)
                    if event.tool_calls:
                        tool_calls.extend(event.tool_calls)
                elif event.type == StreamEventType.ERROR:
                    if reasoning_text and not reasoning_done:
                        reasoning_done = True
                        yield AgentEvent.reasoning_complete(reasoning_text)
                    yield AgentEvent.agent_error(event.error or "Unknown error occurred.")
                    return

            # Reasoning with no answer after it: the model went straight to
            # tool calls, so nothing else will close the block.
            if reasoning_text and not reasoning_done:
                yield AgentEvent.reasoning_complete(reasoning_text)

            self.session.context_manager.add_assistant_message(
                response_text or None,
                [
                    {
                        'id': tc.call_id,
                        'type': 'function',
                        'function': {
                            'name': tc.name,
                            'arguments': json.dumps(tc.arguments),
                        },
                    }
                    for tc in tool_calls
                ]
                if tool_calls
                else None
            )
        
            if response_text:
                yield AgentEvent.text_complete(response_text)
                self.session.loop_detector.record_action(
                    'response',
                    text=response_text
                )
            
            if not tool_calls:
                if usage:
                    self.session.context_manager.set_latest_usage(usage)
                    self.session.context_manager.add_usage(usage)

                return
            
            tool_call_results: list[ToolResultMessage] = []

            for tool_call in tool_calls:

                yield AgentEvent.tool_call_start(
                    tool_call.call_id,
                    tool_call.name,
                    tool_call.arguments
                )

                self.session.loop_detector.record_action(
                    "tool_call",
                    tool_name=tool_call.name,
                    args=tool_call.arguments
                )

                result = await self.session.tool_registry.invoke(
                    tool_call.name,
                    tool_call.arguments,
                    self.config.cwd,
                    self.session.hook_system,
                    self.session.approval_manager,
                    progress_callback=self.progress_callback,
                )

                yield AgentEvent.tool_call_complete(
                    tool_call.call_id,
                    tool_call.name,
                    result,
                )

                tool_call_results.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.call_id,
                        content=result.to_model_output(),
                        is_error=not result.success
                    )
                )

            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_result(
                    tool_result.tool_call_id,
                    tool_result.content,
                )

            loop_detection_err = self.session.loop_detector.check_for_loop()
                            
            if loop_detection_err:
            
                loop_prompt = create_loop_breaker_prompt(loop_detection_err)
            
                self.session.context_manager.add_user_message(loop_prompt)
                continue
    
    async def __aenter__(self) -> Agent:
        await self.session.initalize()
        if self._resume:
            self.resumed = self.session.resume(self._resume)
        return self
    
    async def __aexit__(
            self, 
            exc_type, 
            exc_val, 
            exc_tb
        ) -> None:

        if self.session and self.session.client and self.session.mcp_manager:
            await self.session.client.close()
            await self.session.mcp_manager.shutdown()
            self.session = None # Close session, everything else will be garbage collected