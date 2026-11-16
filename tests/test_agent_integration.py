import asyncio
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from agent.agent import Agent
from agent.events import AgentEventType
from client.llm_client import LLMClient
from client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall
from config.config import Config
from hooks.hook_system import HookSystem
from tools.base import Tool, ToolKind, ToolResult
from tools.registry import ToolRegistry
from ui.stream import stream_turn
from ui.theme import AGENT_THEME
from ui.tui import TUI


class AgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cwd = Path(directory.name)
        (self.cwd / "example.txt").write_text("fixture-value\n")
        self.config = Config(
            cwd=self.cwd, model={"name": "test-model"},
            session={"enabled": False}, hooks_enabled=False,
            agents={"max_concurrent": 2},
        )
        self.memory_patch = patch("agent.session.Session._load_memory", return_value=None)
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)

    @staticmethod
    def scripted_completion():
        rounds = {}

        async def completion(client, messages, tools=None, stream=True):
            index = rounds.get(client, 0)
            rounds[client] = index + 1
            prompt = next(m["content"] for m in messages if m["role"] == "user")
            root = prompt == "coordinate"
            branch = "Your task: branch" in prompt
            delegated = root or branch
            calls = []
            if index == 0:
                if root:
                    calls = [
                        ToolCall("spawn-1", "spawn_agent", {"goal": "branch"}),
                        ToolCall("spawn-2", "spawn_agent", {"role": "codebase_investigator", "goal": "reader"}),
                    ]
                elif branch:
                    calls = [ToolCall("spawn-leaf", "spawn_agent", {"goal": "leaf"})]
                else:
                    calls = [ToolCall("read-1", "read", {"path": "example.txt"})]
            elif index == 1 and delegated:
                agent_ids = [
                    json.loads(m["content"])["agent_id"] for m in messages
                    if m["role"] == "tool" and m.get("tool_call_id", "").startswith("spawn")
                ]
                calls = [ToolCall("wait-1", "wait_agents", {"agent_ids": agent_ids})]
            else:
                result = "combined summary" if root else "branch summary" if branch else "private child summary"
                yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta(result))
            yield StreamEvent(
                StreamEventType.MESSAGE_COMPLETE, tool_calls=calls,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        return completion

    async def test_real_agent_loops_spawn_nested_children_and_use_tools(self):
        with patch.object(LLMClient, "chat_completion", self.scripted_completion()):
            async with Agent(self.config) as agent:
                events = [e async for e in agent.run("coordinate")]
                records = list(agent.runtime.records.values())
                self.assertEqual(len(records), 4)
                self.assertTrue(all(r.status == "completed" for r in records))
                self.assertTrue(all(r.task.done() for r in records))
                self.assertEqual(agent.runtime.records["main"].result, "combined summary")
                self.assertEqual(agent.runtime.total_usage()["total_tokens"], 150)
                reads = [e for e in events if e.type == AgentEventType.TOOL_CALL_COMPLETE and e.data["name"] == "read"]
                self.assertEqual(len(reads), 2)
                self.assertTrue(all(e.data["success"] and "fixture-value" in e.data["output"] for e in reads))
                grandchild = next(r for r in records if r.depth == 2)
                self.assertNotEqual(grandchild.parent_agent_id, "main")
                self.assertEqual(events[-1].agent_id, "main")
                self.assertEqual(events[-1].type, AgentEventType.AGENT_END)

    async def test_tui_keeps_child_text_out_of_main_transcript(self):
        output = StringIO()
        tui = TUI(self.config, Console(file=output, width=110, theme=AGENT_THEME))
        with patch.object(LLMClient, "chat_completion", self.scripted_completion()):
            async with Agent(self.config) as agent:
                result = await stream_turn(tui, agent, "coordinate")
        self.assertEqual(result, "combined summary")
        rendered = output.getvalue()
        self.assertIn("combined summary", rendered)
        self.assertIn("Agents", rendered)
        self.assertIn("codebase_investigator", rendered)
        self.assertNotIn("private child summary", rendered)
        self.assertEqual(len(tui._recent_tools), 3)
        self.assertFalse(tui._spinner.running)

    async def test_parent_collects_results_even_if_model_forgets_to_wait(self):
        rounds = {}

        async def completion(client, messages, tools=None, stream=True):
            index = rounds.get(client, 0)
            rounds[client] = index + 1
            root = messages[1]["content"] == "coordinate"
            if root and index == 0:
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                    ToolCall("spawn", "spawn_agent", {"goal": "child"})
                ])
            else:
                answer = "child evidence" if not root else "early answer" if index == 1 else "incorporated child evidence"
                if root and index == 2:
                    self.assertIn("child evidence", messages[-1]["content"])
                yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta(answer))
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE)

        with patch.object(LLMClient, "chat_completion", completion):
            async with Agent(self.config) as agent:
                events = [e async for e in agent.run("coordinate")]
                self.assertEqual(events[-1].data["response"], "incorporated child evidence")

    async def test_closing_root_event_stream_cancels_background_children(self):
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        async def completion(client, messages, tools=None, stream=True):
            root = messages[1]["content"] == "coordinate"
            if root and not any(m["role"] == "tool" for m in messages):
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                    ToolCall("spawn", "spawn_agent", {"goal": "stalled"})
                ])
            elif root:
                ids = [json.loads(m["content"])["agent_id"] for m in messages if m["role"] == "tool"]
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[ToolCall("wait", "wait_agents", {"agent_ids": ids})])
            else:
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

        with patch.object(LLMClient, "chat_completion", completion):
            async with Agent(self.config) as agent:
                events = agent.run("coordinate")
                async for event in events:
                    if entered.is_set():
                        break
                await asyncio.wait_for(events.aclose(), 1)
                self.assertTrue(cleaned.is_set())
                self.assertTrue(all(r.task.done() for r in agent.runtime.records.values()))
                self.assertTrue(all(r.status == "cancelled" for r in agent.runtime.records.values()))
                messages = agent.session.context_manager.get_messages()
                requested = {t["id"] for m in messages for t in m.get("tool_calls", [])}
                answered = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
                self.assertEqual(requested, answered)


class RegistryAllowlistTests(unittest.IsolatedAsyncioTestCase):
    async def test_disallowed_registered_tool_cannot_execute(self):
        class HiddenTool(Tool):
            name = "hidden"
            kind = ToolKind.READ
            schema = {"type": "object", "properties": {}}

            async def execute(self, invocation):
                raise AssertionError("Disallowed tool ran")

        for allowed in ([], ["read"]):
            config = Config(allowed_tools=allowed, hooks_enabled=False)
            registry = ToolRegistry(config)
            registry.register(HiddenTool(config))
            self.assertEqual(registry.get_tools(), [])
            result = await registry.invoke("hidden", {}, config.cwd, HookSystem(config))
            self.assertFalse(result.success)
            self.assertIn("not allowed", result.error)
