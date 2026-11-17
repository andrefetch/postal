import asyncio
import json
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.history import InMemoryHistory

from client.llm_client import LLMClient
from client.response import StreamEvent, StreamEventType, TextDelta, ToolCall
from config.config import ApprovalPolicy, Config
from ui.bridge import BridgeSession


async def answer(client, messages, tools=None, stream=True):
    yield StreamEvent(StreamEventType.TEXT_DELTA, text_delta=TextDelta("Python response"))
    yield StreamEvent(StreamEventType.MESSAGE_COMPLETE)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cwd = Path(directory.name)
        self.config = Config(cwd=self.cwd, model={"name": "test/model"}, hooks_enabled=False, session={"enabled": False})

    @asynccontextmanager
    async def session(self, completion=answer):
        messages = []
        with patch("agent.session.Session._load_memory", return_value=None), patch.object(LLMClient, "chat_completion", completion):
            session = BridgeSession(self.config, messages.append, history=InMemoryHistory())
            lifecycle = asyncio.create_task(session.run())
            await asyncio.wait_for(session.ready.wait(), 3)
            self.assertIsNotNone(session.agent)
            try:
                yield session, messages
            finally:
                await session.close()
                await asyncio.wait_for(lifecycle, 3)

    async def wait_for(self, predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(0.01)

    async def test_streaming_settings_and_clear_stay_in_python(self):
        async with self.session() as (session, messages):
            ready = messages[0]
            self.assertEqual(ready["type"], "ready")
            self.assertNotIn("api_key", ready["settings"])
            self.assertEqual(len(ready["logo"]), 4)
            with patch("ui.repl.commands.settings.save_model_name") as save:
                await session.dispatch("model", {"model": "provider/new-model"})
                save.assert_called_once_with("provider/new-model", cwd=self.cwd)
            await session.dispatch("effort", {"effort": "high"})
            self.assertEqual(session.config.reasoning.to_request_payload(), {"effort": "high"})
            result = await session.dispatch("submit", {"text": "hello"})
            self.assertTrue(result["accepted"])
            await asyncio.wait_for(session.turn, 3)
            events = [message["event"] for message in messages if message["type"] == "agent_event"]
            self.assertTrue(any(event["type"] == "text_delta" and event["data"]["content"] == "Python response" for event in events))
            self.assertEqual(messages[-1], {"type": "turn_end", "status": "Ready"})
            self.assertEqual(session.agent.session.turns, 1)
            await session.dispatch("submit", {"text": "/clear"})
            self.assertEqual(session.agent.session.turns, 0)
            self.assertIn({"type": "transcript", "messages": []}, messages)

    async def test_approval_mode_changes_the_live_policy(self):
        async with self.session() as (session, messages):
            with self.assertRaises(ValueError):
                await session.dispatch("approval", {"mode": "sideways"})
            self.assertEqual(session.config.approval, ApprovalPolicy.ON_REQUEST)
            await session.dispatch("approval", {"mode": "yolo"})
            self.assertEqual(session.config.approval, ApprovalPolicy.YOLO)
            self.assertEqual(session.agent.session.approval_manager.approval_policy, ApprovalPolicy.YOLO)
            self.assertEqual(session.settings()["approval"], "yolo")

    async def test_approval_is_explicit_and_correlated(self):
        for approve in (True, False):
            with self.subTest(approve=approve):
                calls = 0
                target = self.cwd / f"result-{approve}.txt"

                async def completion(client, messages, tools=None, stream=True):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[ToolCall("write-1", "write", {"path": target.name, "content": "approved"})])
                    else:
                        async for event in answer(client, messages):
                            yield event

                async with self.session(completion) as (session, messages):
                    await session.dispatch("submit", {"text": "write the file"})
                    await self.wait_for(lambda: bool(session.pending))
                    approval = next(message["approval"] for message in messages if message["type"] == "approval")
                    self.assertFalse(target.exists())
                    with self.assertRaises(ValueError):
                        await session.dispatch("approve", {"approvalId": "wrong", "approved": True})
                    with self.assertRaises(ValueError):
                        await session.dispatch("approve", {"approvalId": approval["id"], "approved": "true"})
                    self.assertFalse(target.exists())
                    await session.dispatch("approve", {"approvalId": approval["id"], "approved": approve})
                    await asyncio.wait_for(session.turn, 3)
                    self.assertEqual(target.exists(), approve)
                    self.assertFalse(session.pending)

    async def test_disconnect_rejects_pending_write(self):
        async def completion(client, messages, tools=None, stream=True):
            yield StreamEvent(StreamEventType.MESSAGE_COMPLETE, tool_calls=[ToolCall("write-1", "write", {"path": "never.txt", "content": "no"})])

        async with self.session(completion) as (session, messages):
            await session.dispatch("submit", {"text": "write a file"})
            await self.wait_for(lambda: bool(session.pending))
            await session.close()
            self.assertFalse((self.cwd / "never.txt").exists())
            self.assertFalse(session.pending)
            self.assertFalse(session.busy)

    async def test_busy_guard_and_cancellation_cleanup(self):
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def stalled(client, messages, tools=None, stream=True):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            yield

        async with self.session(stalled) as (session, messages):
            await session.dispatch("submit", {"text": "keep working"})
            await asyncio.wait_for(entered.wait(), 3)
            with self.assertRaises(ValueError):
                await session.dispatch("model", {"model": "other/model"})
            with self.assertRaises(ValueError):
                await session.dispatch("submit", {"text": "duplicate"})
            await session.dispatch("cancel", {})
            self.assertTrue(cleaned.is_set())
            self.assertIn({"type": "turn_end", "status": "Interrupted"}, messages)

    async def test_context_validation_and_request(self):
        path = self.cwd / "example.py"
        path.write_text("print('hello')\n")
        received = []

        async def completion(client, messages, tools=None, stream=True):
            received.extend(message["content"] for message in messages if message["role"] == "user")
            async for event in answer(client, messages):
                yield event

        async with self.session(completion) as (session, messages):
            self.assertEqual(await session.dispatch("file", {"path": "example.py"}), {"path": str(path.resolve())})
            with self.assertRaises(ValueError):
                await session.dispatch("file", {"path": "../outside.txt"})
            with self.assertRaises(ValueError):
                await session.dispatch("submit", {"text": "read", "files": ["missing.py"]})
            self.assertFalse(session.busy)
            await session.dispatch("submit", {"text": "Review this", "files": [str(path)], "web": True})
            await asyncio.wait_for(session.turn, 3)
            self.assertIn(str(path.resolve()), received[0])
            self.assertIn("Use web search", received[0])

    async def test_worker_protocol_survives_invalid_json_and_quits(self):
        process = await asyncio.create_subprocess_exec(sys.executable, "-u", "-m", "ui.bridge",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            process.stdin.write(b"not-json\n")
            await process.stdin.drain()
            message = json.loads(await asyncio.wait_for(process.stdout.readline(), 3))
            self.assertEqual(message["type"], "error")
            process.stdin.write((json.dumps({"id": 1, "method": "init", "params": {"config": self.config.model_dump(mode="json")}}) + "\n").encode())
            await process.stdin.drain()
            while (message := json.loads(await asyncio.wait_for(process.stdout.readline(), 3)))["type"] != "ready":
                self.assertEqual(message["type"], "result")
            process.stdin.write(b'{"id":2,"method":"quit"}\n')
            await process.stdin.drain()
            await asyncio.wait_for(process.wait(), 3)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
