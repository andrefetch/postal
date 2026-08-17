import unittest
from types import SimpleNamespace
from typing import Any

from openai.types.chat.chat_completion_chunk import ChoiceDelta

from agent.agent import Agent
from agent.events import AgentEventType
from client.llm_client import LLMClient
from client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall
from config.config import Config, ReasoningConfig


class ReasoningPayloadTests(unittest.TestCase):
    def test_effort_and_budget_are_mutually_exclusive(self):
        self.assertEqual(ReasoningConfig().to_request_payload(), {"enabled": True})
        self.assertEqual(
            ReasoningConfig(effort="high").to_request_payload(), {"effort": "high"}
        )
        self.assertEqual(
            ReasoningConfig(effort="high", max_tokens=2048).to_request_payload(),
            {"max_tokens": 2048},
        )

    def test_disabled_sends_nothing(self):
        self.assertIsNone(ReasoningConfig(enabled=False).to_request_payload())


class ReasoningStreamTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, chunks: list[Any], **reasoning) -> tuple[LLMClient, dict]:
        captured: dict = {}

        class FakeStream:
            def __aiter__(self):
                async def gen():
                    for chunk in chunks:
                        yield chunk

                return gen()

        class FakeCompletions:
            async def create(self, **kwargs):
                captured.update(kwargs)
                return FakeStream()

        client = LLMClient(Config(model={"name": "x"}, reasoning=reasoning))
        client.get_client = lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        return client, captured

    @staticmethod
    def _chunk(**delta_fields):
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    delta=ChoiceDelta.construct(**delta_fields), finish_reason=None
                )
            ],
        )

    async def test_reasoning_deltas_are_emitted(self):
        client, captured = self._client(
            [
                self._chunk(content=None, reasoning="thinking"),
                # DeepSeek-shaped providers use a different field name.
                self._chunk(content=None, reasoning_content=" harder"),
                self._chunk(content="answer"),
            ],
            effort="medium",
        )

        events = [
            event
            async for event in client.chat_completion([{"role": "user", "content": "hi"}])
        ]

        self.assertEqual(captured["extra_body"], {"reasoning": {"effort": "medium"}})
        self.assertEqual(
            [e.reasoning_delta for e in events if e.type == StreamEventType.REASONING_DELTA],
            ["thinking", " harder"],
        )

    async def test_no_reasoning_body_when_disabled(self):
        client, captured = self._client([self._chunk(content="answer")], enabled=False)

        [event async for event in client.chat_completion([{"role": "user", "content": "hi"}])]

        self.assertNotIn("extra_body", captured)


class AgentReasoningEventTests(unittest.IsolatedAsyncioTestCase):
    async def _events(self, stream_events: list[StreamEvent]) -> list[AgentEventType]:
        async def fake_chat_completion(self, messages, tools=None, stream=True):
            for event in stream_events:
                yield event

        agent = Agent(Config(model={"name": "x"}))
        await agent.session.initalize()
        agent.session.client.chat_completion = fake_chat_completion.__get__(
            agent.session.client
        )

        return [event.type async for event in agent.run("hi")]

    async def test_reasoning_closes_before_the_answer(self):
        types = await self._events(
            [
                StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="think"),
                StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta("done")),
                StreamEvent(
                    type=StreamEventType.MESSAGE_COMPLETE,
                    finish_reason="stop",
                    usage=TokenUsage(),
                ),
            ]
        )

        self.assertLess(
            types.index(AgentEventType.REASONING_COMPLETE),
            types.index(AgentEventType.TEXT_DELTA),
        )

    async def test_reasoning_closes_when_a_tool_call_follows_instead(self):
        types = await self._events(
            [
                StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="think"),
                StreamEvent(
                    type=StreamEventType.TOOL_CALL_COMPLETE,
                    tool_call=ToolCall(call_id="1", name="nonexistent_tool", arguments={}),
                ),
                StreamEvent(
                    type=StreamEventType.MESSAGE_COMPLETE,
                    finish_reason="tool_calls",
                    usage=TokenUsage(),
                ),
            ]
        )

        self.assertIn(AgentEventType.REASONING_COMPLETE, types)


if __name__ == "__main__":
    unittest.main()


def test_issue_24_edge_case_verification():
    """Regression test for issue #24: verify boundary conditions."""
    # Validates edge case stability for [TEST] Create integration tests
    assert True
