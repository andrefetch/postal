import asyncio
import unittest

from agent.events import AgentEvent, AgentEventType
from agent.runtime import AgentRuntime
from client.response import TokenUsage
from config.config import Config
from tools.base import ToolConfirmation
from tools.subagents.subagents import GENERAL, CODEBASE_INVESTIGATOR, SubAgentTool


def fake_agent_factory(action):
    class FakeAgent:
        def __init__(self, config, runtime, agent_id, confirmation_callback=None):
            self.config = config
            self.runtime = runtime
            self.agent_id = agent_id
            self.confirm = confirmation_callback

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def run(self, prompt):
            yield AgentEvent.agent_start(prompt)
            result = await action(self)
            yield AgentEvent.text_complete(result)
            yield AgentEvent.agent_end(result)

    return FakeAgent


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self, action, callback=None, **limits):
        config = Config(agents=limits, session={"enabled": False})
        runtime = AgentRuntime(config, callback, fake_agent_factory(action))
        runtime.begin_turn("root task")
        self.addAsyncCleanup(runtime.cancel_descendants, runtime.root_id)
        return runtime

    async def test_siblings_overlap_without_exceeding_global_limit(self):
        active = peak = 0
        both_running = asyncio.Event()

        async def action(agent):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_running.set()
            await asyncio.wait_for(both_running.wait(), 1)
            await asyncio.sleep(0)
            active -= 1
            return "done"

        runtime = self.make_runtime(action, max_concurrent=2)
        async with runtime.execution_slot("main"):
            records = [runtime.spawn("main", runtime.config, GENERAL, str(i)) for i in range(5)]
            await asyncio.wait_for(runtime.wait("main", [r.agent_id for r in records]), 2)
        self.assertEqual(peak, 2)
        self.assertTrue(all(r.status == "completed" for r in records))

    async def test_nested_wait_releases_the_only_execution_slot(self):
        async def action(agent):
            if agent.runtime.records[agent.agent_id].depth == 1:
                children = [agent.runtime.spawn(agent.agent_id, agent.config, GENERAL, str(i)) for i in range(2)]
                results = await agent.runtime.wait(agent.agent_id, [r.agent_id for r in children])
                self.assertTrue(all(r.status == "completed" for r in results))
            return "done"

        runtime = self.make_runtime(action, max_concurrent=1)
        async with runtime.execution_slot("main"):
            record = runtime.spawn("main", runtime.config, GENERAL, "parent")
            await asyncio.wait_for(runtime.wait("main", [record.agent_id]), 2)
        self.assertEqual(record.status, "completed")
        self.assertEqual(len(runtime.records), 4)

    async def test_cancel_parent_awaits_all_descendant_cleanup(self):
        started = asyncio.Event()
        cleaned = set()

        async def action(agent):
            try:
                if agent.runtime.records[agent.agent_id].depth == 1:
                    child = agent.runtime.spawn(agent.agent_id, agent.config, GENERAL, "grandchild")
                    await agent.runtime.wait(agent.agent_id, [child.agent_id])
                else:
                    started.set()
                    await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.add(agent.agent_id)

        runtime = self.make_runtime(action)
        record = runtime.spawn("main", runtime.config, GENERAL, "parent")
        await asyncio.wait_for(started.wait(), 1)
        await asyncio.wait_for(runtime.cancel("main", record.agent_id), 1)
        descendants = runtime.descendants("main")
        self.assertEqual(cleaned, {r.agent_id for r in descendants})
        self.assertTrue(all(r.status == "cancelled" and r.task.done() for r in descendants))

    async def test_cancel_before_task_starts_marks_it_cancelled(self):
        async def action(agent):
            self.fail("A queued cancelled agent must not run")

        runtime = self.make_runtime(action, max_concurrent=1)
        async with runtime.execution_slot("main"):
            record = runtime.spawn("main", runtime.config, GENERAL, "queued")
            await runtime.cancel("main", record.agent_id)
        self.assertEqual(record.status, "cancelled")
        self.assertTrue(record.task.done())

    async def test_deadline_interrupts_agent_without_new_events(self):
        cleaned = asyncio.Event()

        async def action(agent):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        runtime = self.make_runtime(action, timeout_seconds=0.02)
        record = runtime.spawn("main", runtime.config, GENERAL, "stalled")
        await asyncio.wait_for(runtime.wait("main", [record.agent_id]), 1)
        self.assertEqual(record.status, "timed_out")
        self.assertTrue(cleaned.is_set())

    async def test_one_failure_does_not_cancel_siblings(self):
        async def action(agent):
            if agent.runtime.records[agent.agent_id].goal == "fail":
                raise RuntimeError("broken child")
            await asyncio.sleep(0)
            return "good result"

        runtime = self.make_runtime(action)
        bad = runtime.spawn("main", runtime.config, GENERAL, "fail")
        good = runtime.spawn("main", runtime.config, GENERAL, "succeed")
        await runtime.wait("main", [bad.agent_id, good.agent_id])
        self.assertEqual(bad.status, "failed")
        self.assertEqual(bad.error, "broken child")
        self.assertEqual(good.result, "good result")

    async def test_approvals_are_serialized_and_identify_the_agent(self):
        active = peak = 0
        descriptions = []

        async def approve(confirmation):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            descriptions.append(confirmation.description)
            await asyncio.sleep(0)
            active -= 1
            return len(descriptions) == 1

        async def action(agent):
            approved = await agent.confirm(ToolConfirmation("write", {}, "Write example"))
            return str(approved)

        runtime = self.make_runtime(action, callback=approve, max_concurrent=1)
        first = runtime.spawn("main", runtime.config, GENERAL, "first")
        second = runtime.spawn("main", runtime.config, GENERAL, "second")
        await asyncio.wait_for(runtime.wait("main", [first.agent_id, second.agent_id]), 1)
        self.assertEqual(peak, 1)
        self.assertEqual([first.result, second.result], ["True", "False"])
        self.assertIn(first.agent_id, descriptions[0])
        self.assertIn(second.agent_id, descriptions[1])

    async def test_mutation_lock_does_not_leak_on_cancellation(self):
        locked = asyncio.Event()

        async def action(agent):
            async with agent.runtime.mutation(agent.agent_id):
                locked.set()
                await asyncio.Event().wait()

        runtime = self.make_runtime(action)
        record = runtime.spawn("main", runtime.config, GENERAL, "writer")
        await asyncio.wait_for(locked.wait(), 1)
        await runtime.cancel("main", record.agent_id)
        async with asyncio.timeout(1):
            async with runtime.mutation("main"):
                pass

    async def test_limits_and_descendant_ownership_are_enforced(self):
        async def action(agent):
            await asyncio.Event().wait()

        runtime = self.make_runtime(action, max_agents=3, max_depth=1)
        first = runtime.spawn("main", runtime.config, GENERAL, "first")
        second = runtime.spawn("main", runtime.config, GENERAL, "second")
        with self.assertRaisesRegex(ValueError, "Maximum agents"):
            runtime.spawn("main", runtime.config, GENERAL, "third")
        with self.assertRaisesRegex(ValueError, "Maximum delegation depth"):
            runtime.spawn(first.agent_id, runtime.config, GENERAL, "grandchild")
        with self.assertRaisesRegex(ValueError, "own descendants"):
            await runtime.wait(first.agent_id, [second.agent_id])
        with self.assertRaisesRegex(ValueError, "own descendants"):
            await runtime.cancel(first.agent_id, "main")

    async def test_usage_updates_replace_cumulative_totals(self):
        async def action(agent):
            agent.runtime.publish(AgentEvent.usage(TokenUsage(total_tokens=10)), agent.agent_id)
            agent.runtime.publish(AgentEvent.usage(TokenUsage(total_tokens=25)), agent.agent_id)
            return "done"

        runtime = self.make_runtime(action)
        record = runtime.spawn("main", runtime.config, GENERAL, "count")
        await runtime.wait("main", [record.agent_id])
        runtime.publish(AgentEvent.usage(TokenUsage(total_tokens=30)), "main")
        self.assertEqual(runtime.total_usage()["total_tokens"], 55)
        events = []
        while not runtime.events.empty():
            events.append(runtime.events.get_nowait())
        child_events = [e for e in events if e.agent_id == record.agent_id]
        self.assertTrue(child_events)
        self.assertTrue(all(e.parent_agent_id == "main" for e in child_events))


class InheritedCapabilitiesTests(unittest.TestCase):
    def test_role_never_broadens_parent_permissions(self):
        config = Config(allowed_tools=["read", "spawn_agent", "wait_agents"])
        child = SubAgentTool(config, CODEBASE_INVESTIGATOR).subagent_config()
        self.assertEqual(set(child.allowed_tools), set(config.allowed_tools))
        grandchild = SubAgentTool(child, GENERAL).subagent_config()
        self.assertEqual(set(grandchild.allowed_tools), set(child.allowed_tools))
        self.assertFalse(grandchild.session.enabled)

    def test_empty_allowlist_remains_empty(self):
        child = SubAgentTool(Config(allowed_tools=[]), CODEBASE_INVESTIGATOR).subagent_config()
        self.assertEqual(child.allowed_tools, [])

    def test_general_role_preserves_permitted_external_tools(self):
        allowed = ["server__search", "custom_tool", "spawn_agent"]
        child = SubAgentTool(Config(allowed_tools=allowed), GENERAL).subagent_config()
        self.assertEqual(set(child.allowed_tools), set(allowed))
