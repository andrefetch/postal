import asyncio
import unittest
from io import StringIO
from types import SimpleNamespace

from prompt_toolkit.keys import Keys
from rich.console import Console

from agent.events import AgentEvent, AgentEventType
from agent.runtime import AgentRecord
from config.config import Config
from tools.base import ToolResult
from ui.components.agent_tree import AgentTree
from ui.theme import AGENT_THEME
from ui.tui import TUI


class AgentTreeTests(unittest.TestCase):
    def tree(self):
        tree = AgentTree()
        for agent_id, parent_id, name, depth in (
            ("main", None, "Main agent", 0),
            ("a", "main", "Investigator", 1),
            ("b", "main", "Reviewer", 1),
            ("c", "a", "Dependency explorer", 2),
        ):
            record = AgentRecord(agent_id, parent_id, name, "Inspect the relevant files", depth, "running")
            tree.update(AgentEvent(AgentEventType.AGENT_STATUS, record.snapshot(), agent_id, parent_id))
        return tree

    def render(self, tree, width=100):
        output = StringIO()
        Console(file=output, width=width, theme=AGENT_THEME).print(tree.render())
        return output.getvalue()

    def test_interleaved_progress_is_attributed_to_the_correct_agent(self):
        tree = self.tree()
        for agent_id, name, progress in (("a", "grep", "Searching auth"), ("b", "read", "Reading routes")):
            tree.update(AgentEvent(AgentEventType.TOOL_CALL_START, {"call_id": "same-id", "name": name}, agent_id))
            tree.update(AgentEvent(AgentEventType.TOOL_PROGRESS, {"call_id": "same-id", "content": progress}, agent_id))
        output = self.render(tree)
        self.assertIn("grep · Searching auth", output)
        self.assertIn("read · Reading routes", output)
        self.assertEqual(tree.order(), ["main", "a", "c", "b"])
        self.assertIn("├─", output)
        self.assertIn("│  └─", output)

    def test_selecting_and_expanding_reveals_only_selected_details(self):
        tree = self.tree()
        tree.update(AgentEvent(AgentEventType.TEXT_COMPLETE, {"content": "private review result"}, "b"))
        tree.move(2)
        self.assertEqual(tree.selected, "b")
        self.assertNotIn("private review result", self.render(tree))
        tree.toggle_selected()
        self.assertIn("private review result", self.render(tree))
        tree.toggle_selected()
        self.assertNotIn("private review result", self.render(tree))

    def test_large_output_is_bounded_and_narrow_terminals_render(self):
        tree = self.tree()
        event = AgentEvent.tool_call_complete("one", "read", ToolResult.success_result("x" * 10000))
        event.agent_id = "a"
        tree.update(event)
        self.assertEqual(len(tree.nodes["a"].output), 2000)
        tree.toggle_selected()
        output = self.render(tree, width=45)
        self.assertTrue(all(len(line) <= 45 for line in output.splitlines()))


class AgentTreeControlsTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_key_targets_selected_subtree(self):
        cancelled = []

        async def cancel(parent_id, agent_id):
            cancelled.append((parent_id, agent_id))

        runtime = SimpleNamespace(root_id="main", cancel=cancel, records={})
        tui = TUI(Config(), Console(file=StringIO(), theme=AGENT_THEME))
        tui.begin_agent_turn(runtime)
        tui.agent_tree = AgentTreeTests().tree()
        self.assertTrue(tui.feed_agent_key(SimpleNamespace(key=Keys.Down, data="")))
        self.assertEqual(tui.agent_tree.selected, "c")
        self.assertTrue(tui.feed_agent_key(SimpleNamespace(key="c", data="c")))
        await tui.finish_agent_turn()
        self.assertEqual(cancelled, [("main", "c")])

