import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.history import InMemoryHistory
from textual.widgets import Button, Collapsible, Input, OptionList, Static

from client.llm_client import LLMClient
from client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall
from config.config import Config
from ui.components.logo import logo
from ui.prompt_bar import PromptPicker
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
            self.assertEqual(app.theme, "postal-dark")
            self.assertIs(app.focused, composer)
            self.assertFalse(app.query_one("#commands").display)
            self.assertGreater(composer.region.y, conversation.region.y)
            self.assertLessEqual(composer.region.bottom, app.size.height)
            self.assertTrue(app.query("#welcome"))
            await asyncio.wait_for(pilot.press("ctrl+q"), 3)
            self.assertTrue(app._exit)

    async def test_home_centers_cloud_and_composer_at_different_sizes(self):
        for size in ((140, 40), (100, 30), (80, 24), (50, 18), (40, 12)):
            with self.subTest(size=size):
                async with self.running_app(size=size) as (app, pilot):
                    box = app.query_one("#composer-box").region
                    cloud = app.query_one("#cloud-logo", Static)
                    self.assertEqual(cloud.content.plain, logo().plain)
                    self.assertLessEqual(abs(box.center[0] - size[0] / 2), 1)
                    self.assertLessEqual(abs(box.center[1] - size[1] / 2), 2)
                    self.assertLessEqual(abs(cloud.region.center[0] - box.center[0]), 1)
                    self.assertLessEqual(cloud.region.bottom, box.y)
                    for selector in ("#prompt-add", "#prompt-model", "#prompt-effort", "#prompt-send"):
                        self.assertTrue(box.contains_region(app.query_one(selector).region), selector)
                    self.assertFalse(app.query_one("#conversation").display)
                    self.assertLessEqual(app.query_one("#statusbar").region.bottom, size[1])

    async def test_wrapped_input_grows_and_refits_after_resize(self):
        async with self.running_app(size=(100, 40)) as (app, pilot):
            composer = app.query_one("#composer", Composer)
            initial_height = composer.size.height
            text = "A prompt that wraps across several visual lines. " * 6
            composer.load_text(text)
            await pilot.pause()
            self.assertGreater(composer.size.height, initial_height)
            self.assertGreaterEqual(composer.content_size.height, composer.wrapped_document.height)
            self.assertFalse(composer.show_vertical_scrollbar)

            await pilot.resize_terminal(50, 18)
            await pilot.pause()
            self.assertEqual(composer.text, text)
            self.assertTrue(composer.show_vertical_scrollbar)
            self.assertLessEqual(app.query_one("#statusbar").region.bottom, app.size.height)

            composer.load_text("\n".join(f"line {i}" for i in range(20)))
            composer.move_cursor(composer.document.end)
            await pilot.pause()
            self.assertGreater(composer.scroll_y, 0)
            self.assertLessEqual(composer.region.bottom, app.query_one("#prompt-toolbar").region.y)

            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            self.assertLessEqual(composer.content_size.height, 5)
            composer.clear()
            await pilot.pause()
            self.assertEqual(composer.size.height, initial_height)
            self.assertFalse(composer.show_vertical_scrollbar)

    async def test_home_command_menu_fits_small_terminals(self):
        for size in ((80, 24), (50, 18), (40, 12)):
            with self.subTest(size=size):
                async with self.running_app(size=size) as (app, pilot):
                    await pilot.press("/")
                    menu = app.query_one("#commands", OptionList)
                    self.assertTrue(menu.display)
                    self.assertGreater(menu.region.height, 0)
                    self.assertLessEqual(menu.region.bottom, app.query_one("#composer-box").region.y)
                    self.assertLessEqual(app.query_one("#statusbar").region.bottom, size[1])
                    await pilot.press("escape")
                    self.assertFalse(menu.display)
                    self.assertTrue(app.query_one("#cloud-logo").visible)
                    self.assertIs(app.focused, app.query_one("#composer"))

    async def test_long_home_prompt_keeps_controls_inside_viewport(self):
        for size in ((80, 24), (80, 23), (50, 18), (50, 16), (40, 12)):
            with self.subTest(size=size):
                async with self.running_app(size=size) as (app, pilot):
                    composer = app.query_one("#composer", Composer)
                    composer.load_text("\n".join(f"line {i}" for i in range(20)))
                    composer.move_cursor(composer.document.end)
                    await pilot.pause()
                    viewport = app.query_one("#main").content_region
                    for selector in ("#composer-box", "#prompt-toolbar", "#statusbar"):
                        self.assertTrue(viewport.contains_region(app.query_one(selector).region))
                    self.assertTrue(composer.show_vertical_scrollbar)

    async def test_prompt_settings_preserve_draft_and_home(self):
        with patch("ui.repl.commands.settings.save_model_name") as save:
            async with self.running_app() as (app, pilot):
                composer = app.query_one(Composer)
                composer.load_text("Keep my draft")
                await pilot.pause()
                await pilot.click("#prompt-model")
                self.assertIsInstance(app.screen, PromptPicker)
                app.screen.query_one(Input).value = "provider/another-model"
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.config.model_name, "provider/another-model")
                save.assert_called_once_with("provider/another-model", cwd=self.cwd)
                await pilot.click("#prompt-effort")
                await pilot.press("down", "down", "down", "down", "enter")
                await pilot.pause()
                self.assertEqual(app.config.reasoning.to_request_payload(), {"effort": "high"})
                self.assertEqual(composer.text, "Keep my draft")
                self.assertTrue(app.query_one("#main").has_class("home"))
                self.assertIs(app.focused, composer)
                await pilot.click("#prompt-effort")
                await pilot.press("escape")
                self.assertNotIsInstance(app.screen, PromptPicker)

    async def test_send_button_stops_active_response_and_keeps_next_draft(self):
        cleaned = asyncio.Event()

        async def stalled(client, messages, tools=None, stream=True):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            yield

        async with self.running_app(stalled) as (app, pilot):
            send = app.query_one("#prompt-send", Button)
            composer = app.query_one(Composer)
            self.assertTrue(send.disabled)
            composer.load_text("Start working")
            await pilot.pause()
            self.assertFalse(send.disabled)
            await pilot.click("#prompt-send")
            await pilot.pause()
            self.assertTrue(app.busy)
            self.assertEqual(send.label.plain, "■")
            self.assertTrue(app.query_one("#prompt-model").disabled)
            composer.load_text("My next prompt")
            await pilot.pause()
            await pilot.click("#prompt-send")
            await self.finish_turn(app, pilot)
            self.assertTrue(cleaned.is_set())
            self.assertEqual(composer.text, "My next prompt")
            self.assertEqual(send.label.plain, "↑")
            self.assertFalse(send.disabled)

    async def test_file_and_web_sources_reach_next_prompt(self):
        (self.cwd / "example.py").write_text("print('hello')\n")
        received = []

        async def completion(client, messages, tools=None, stream=True):
            received.extend(message["content"] for message in messages if message["role"] == "user")
            async for event in answer(client, messages):
                yield event

        async with self.running_app(completion) as (app, pilot):
            composer = app.query_one(Composer)
            composer.load_text("Review this")
            await pilot.pause()
            await pilot.click("#prompt-add")
            await pilot.press("enter")
            app.screen.query_one(Input).value = "missing.py"
            await pilot.press("enter")
            self.assertTrue(app.screen.query_one("#picker-error").display)
            app.screen.query_one(Input).value = "example.py"
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(app.query_one("#file-chip").display)
            await pilot.click("#prompt-add")
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertTrue(app.query_one("#web-chip").display)
            self.assertEqual(composer.text, "Review this")
            await pilot.click("#prompt-send")
            await self.finish_turn(app, pilot)
            self.assertIn(str(self.cwd / "example.py"), received[0])
            self.assertIn("Use web search", received[0])
            self.assertFalse(app.query_one("#prompt-sources").display)

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
            self.assertFalse(app.query_one("#main").has_class("home"))
            self.assertTrue(app.query_one("#conversation").display)
            self.assertGreater(app.query_one("#composer").region.y, app.size.height / 2)

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
