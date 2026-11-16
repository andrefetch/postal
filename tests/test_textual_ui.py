import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.history import InMemoryHistory
from textual.widgets import Collapsible, OptionList, Static

from client.llm_client import LLMClient
from client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall
from config.config import Config
from ui.textual_app import PostalApp
from ui.textual_widgets import AgentsScreen, ApprovalScreen, Composer, MessageBlock, ToolBlock


async def answer(client, messages, tools=None, stream=True):
    yield StreamEvent(StreamEventType.REASONING_DELTA, reasoning_delta="Inspecting the request.")
    yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta("A **streamed** response."))
    yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, usage=TokenUsage(prompt_tokens=20, completion_tokens=5, total_tokens=25))


class TextualUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cwd = Path(directory.name)
        self.config = Config(
            cwd=self.cwd, model={"name": "test/model"},
            hooks_enabled=False, session={"enabled": False},
        )

    @asynccontextmanager
    async def running_app(self, completion=answer, size=(100, 30)):
        with (
            patch("agent.session.Session._load_memory", return_value=None),
            patch.object(LLMClient, "chat_completion", completion),
        ):
            app = PostalApp(self.config, history=InMemoryHistory())
            async with app.run_test(size=size) as pilot:
                await asyncio.wait_for(app.ready.wait(), 3)
                await pilot.pause()
                yield app, pilot
            self.assertTrue(app._session_task.done())
            if app._turn_task is not None:
                self.assertTrue(app._turn_task.done())

    async def submit(self, app, pilot, text):
        app.query_one("#composer", Composer).load_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def finish_turn(self, app, pilot):
        self.assertIsNotNone(app._turn_task)
        await asyncio.wait_for(asyncio.shield(app._turn_task), 3)
        await pilot.pause()

    async def test_home_layout_and_quit(self):
        async with self.running_app() as (app, pilot):
            composer = app.query_one("#composer", Composer)
            conversation = app.query_one("#conversation")
            self.assertEqual(app.theme, "postal-mono")
            self.assertIs(app.focused, composer)
            self.assertFalse(app.query_one("#commands").display)
            self.assertGreater(composer.region.y, conversation.region.y)
            self.assertLessEqual(composer.region.bottom, app.size.height)
            self.assertTrue(app.query("#welcome"))
            await asyncio.wait_for(pilot.press("ctrl+q"), 3)
            self.assertTrue(app._exit)

    async def test_multiline_input_and_history_preserve_newlines(self):
        async with self.running_app() as (app, pilot):
            await pilot.press("a", "ctrl+j", "b")
            self.assertEqual(app.query_one("#composer", Composer).text, "a\nb")
            await pilot.press("enter")
            await self.finish_turn(app, pilot)
            self.assertEqual(app.query(MessageBlock).first().text, "a\nb")
            await pilot.press("alt+up")
            self.assertEqual(app.query_one("#composer", Composer).text, "a\nb")
            await pilot.press("alt+down")
            self.assertEqual(app.query_one("#composer", Composer).text, "")

    async def test_streaming_reasoning_and_response(self):
        async with self.running_app() as (app, pilot):
            await self.submit(app, pilot, "hello")
            await self.finish_turn(app, pilot)
            messages = list(app.query(MessageBlock))
            self.assertEqual([m.role for m in messages], ["user", "assistant"])
            self.assertEqual(messages[-1].text, "A **streamed** response.")
            self.assertEqual(app.last_response, messages[-1].text)
            self.assertTrue(app.query_one(".reasoning-block", Collapsible).collapsed)
            self.assertEqual(app._context_tokens, 20)
            self.assertFalse(app.query("#welcome"))

    async def test_command_completion_help_and_clear(self):
        async with self.running_app() as (app, pilot):
            app.query_one("#composer", Composer).load_text("/he")
            await pilot.pause()
            menu = app.query_one("#commands", OptionList)
            self.assertTrue(menu.display)
            self.assertEqual(menu.option_count, 1)
            await pilot.press("tab")
            self.assertEqual(app.query_one("#composer", Composer).text, "/help ")
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(app.query(".notice"))
            await self.submit(app, pilot, "hello")
            await self.finish_turn(app, pilot)
            await self.submit(app, pilot, "/clear")
            self.assertEqual(len(app.query(MessageBlock)), 0)
            self.assertEqual(app.agent.session.turns, 0)

    async def test_read_tool_output_is_collapsed_and_can_be_expanded(self):
        (self.cwd / "example.txt").write_text("read result\n")
        calls = 0

        async def completion(client, messages, tools=None, stream=True):
            nonlocal calls
            calls += 1
            if calls == 1:
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[ToolCall("read-1", "read", {"path": "example.txt"})])
            else:
                async for event in answer(client, messages):
                    yield event

        async with self.running_app(completion) as (app, pilot):
            await self.submit(app, pilot, "read the file")
            await self.finish_turn(app, pilot)
            tool = app.query_one(ToolBlock)
            self.assertEqual(tool.state, "completed")
            self.assertIn("read result", tool.output)
            self.assertTrue(tool.collapsed)
            await pilot.press("ctrl+o")
            self.assertFalse(tool.collapsed)

    async def test_approval_accept_and_reject(self):
        for approve in (True, False):
            with self.subTest(approve=approve):
                path = self.cwd / "result.txt"
                original = "original\n" * 60
                path.write_text(original)
                calls = 0

                async def completion(client, messages, tools=None, stream=True):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                            ToolCall("write-1", "write", {"path": "result.txt", "content": "updated"})
                        ])
                    else:
                        async for event in answer(client, messages):
                            yield event

                async with self.running_app(completion) as (app, pilot):
                    await self.submit(app, pilot, "write the file")
                    self.assertIsInstance(app.screen, ApprovalScreen)
                    self.assertEqual(path.read_text(), original)
                    await pilot.press("pagedown")
                    await pilot.pause()
                    self.assertGreater(app.screen.query_one("#approval-content").scroll_y, 0)
                    await pilot.press("y" if approve else "escape")
                    await self.finish_turn(app, pilot)
                    self.assertEqual(path.read_text(), "updated" if approve else original)
                    self.assertIsNone(app._pending_confirmation)
                    self.assertNotIsInstance(app.screen, ApprovalScreen)

    async def test_interrupt_and_quit_cancel_the_agent(self):
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        async def stalled(client, messages, tools=None, stream=True):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            yield

        async with self.running_app(stalled) as (app, pilot):
            await self.submit(app, pilot, "keep working")
            await asyncio.wait_for(entered.wait(), 1)
            await pilot.press("escape")
            await self.finish_turn(app, pilot)
            self.assertTrue(cleaned.is_set())
            self.assertEqual(app._status, "Interrupted")
            entered.clear()
            cleaned.clear()
            await self.submit(app, pilot, "keep working again")
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.wait_for(pilot.press("ctrl+q"), 3)
            self.assertTrue(cleaned.is_set())

    async def test_quit_while_approval_is_open(self):
        async def completion(client, messages, tools=None, stream=True):
            yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                ToolCall("write-1", "write", {"path": "unapproved.txt", "content": "do not write"})
            ])

        async with self.running_app(completion) as (app, pilot):
            await self.submit(app, pilot, "write a file")
            self.assertIsInstance(app.screen, ApprovalScreen)
            await asyncio.wait_for(pilot.press("ctrl+q"), 3)
            self.assertIsNone(app._pending_confirmation)
            self.assertFalse((self.cwd / "unapproved.txt").exists())

    async def test_active_child_can_be_cancelled_in_dialog(self):
        child_started = asyncio.Event()
        child_cleaned = asyncio.Event()

        async def completion(client, messages, tools=None, stream=True):
            if messages[1]["content"] == "delegate":
                if not any(m["role"] == "tool" for m in messages):
                    yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                        ToolCall("spawn", "spawn_agent", {"goal": "keep working"})
                    ])
                else:
                    yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta("Waiting for my child."))
                    yield StreamEvent(StreamEventType.MESSAGE_COMPLETE)
            else:
                try:
                    child_started.set()
                    await asyncio.Event().wait()
                finally:
                    child_cleaned.set()

        async with self.running_app(completion) as (app, pilot):
            await self.submit(app, pilot, "delegate")
            await asyncio.wait_for(child_started.wait(), 1)
            await pilot.press("ctrl+g")
            await pilot.pause()
            await pilot.press("down", "c")
            await self.finish_turn(app, pilot)
            self.assertTrue(child_cleaned.is_set())
            children = app.agent.runtime.descendants(app.agent.agent_id)
            self.assertEqual([child.status for child in children], ["cancelled"])
            self.assertIsInstance(app.screen, AgentsScreen)
            self.assertIs(app.focused, app.screen.agent_tree)
            await pilot.press("escape")

    async def test_startup_failure_can_still_quit(self):
        @asynccontextmanager
        async def unavailable(*args, **kwargs):
            raise RuntimeError("test connection failed")
            yield

        app = PostalApp(self.config, history=InMemoryHistory(), agent_factory=unavailable)
        async with app.run_test() as pilot:
            await asyncio.wait_for(app.ready.wait(), 3)
            await pilot.pause()
            self.assertTrue(app.query_one("#composer", Composer).disabled)
            self.assertIn("test connection failed", str(app.query_one(".notice", Static).content))
            await asyncio.wait_for(pilot.press("ctrl+q"), 3)
        self.assertTrue(app._session_task.done())

    async def test_nested_activity_is_separate_from_main_conversation(self):
        calls = {}

        async def completion(client, messages, tools=None, stream=True):
            index = calls.get(client, 0)
            calls[client] = index + 1
            root = messages[1]["content"] == "delegate"
            if root and index == 0:
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[
                    ToolCall("spawn-1", "spawn_agent", {"goal": "first child"}),
                    ToolCall("spawn-2", "spawn_agent", {"goal": "second child"}),
                ])
            elif root and index == 1:
                ids = [json.loads(m["content"])["agent_id"] for m in messages if m["role"] == "tool"]
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[ToolCall("wait", "wait_agents", {"agent_ids": ids})])
            else:
                text = "Parent summary" if root else "Private child result"
                yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta(text))
                yield StreamEvent(StreamEventType.MESSAGE_COMPLETE)

        async with self.running_app(completion) as (app, pilot):
            await self.submit(app, pilot, "delegate")
            await self.finish_turn(app, pilot)
            self.assertEqual(len(app.agent_views.nodes), 3)
            self.assertEqual(
                [m.text for m in app.query(MessageBlock)], ["delegate", "Parent summary"],
                [str(notice.content) for notice in app.query(".notice")],
            )
            await pilot.press("ctrl+g")
            await pilot.pause()
            self.assertIsInstance(app.screen, AgentsScreen)
            self.assertEqual(len(app.screen.tree_nodes), 3)
            await pilot.press("down")
            await pilot.pause()
            self.assertIn("Private child result", str(app.screen.details.content))
            await pilot.press("escape")

    async def test_narrow_layout_keeps_composer_visible(self):
        async with self.running_app(size=(50, 18)) as (app, pilot):
            await self.submit(app, pilot, "hello")
            await self.finish_turn(app, pilot)
            composer = app.query_one("#composer", Composer)
            self.assertLessEqual(composer.region.right, app.size.width)
            self.assertLessEqual(composer.region.bottom, app.size.height)
            self.assertGreater(composer.region.width, 20)
            self.assertGreater(app.query_one("#conversation").region.height, 0)
            self.assertFalse(app.query_one("#key-hints").display)
            self.assertGreater(app.query_one("#run-status").region.width, 20)
