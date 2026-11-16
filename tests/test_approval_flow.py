import unittest
from pathlib import Path
from typing import Any

from config.config import ApprovalPolicy, Config
from hooks.hook_system import HookSystem
from safety.approval import ApprovalManager
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
from tools.registry import ToolRegistry
from tools.subagents.subagents import CODEBASE_INVESTIGATOR, SubAgentTool


class RecordingTool(Tool):
    name = "recording_tool"
    description = "Records the invocation it receives"
    kind = ToolKind.READ
    schema = {"parameters": {"type": "object", "properties": {}}}

    def __init__(self, config: Config):
        super().__init__(config)
        self.invocation: ToolInvocation | None = None

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocation = invocation
        return ToolResult.success_result("ok")


class RequestConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_callback_fails_closed(self):
        manager = ApprovalManager(ApprovalPolicy.ON_REQUEST, Path.cwd())

        approved = await manager.request_confirmation(
            ToolConfirmation(tool_name="write", params={}, description="Run write")
        )

        self.assertFalse(approved)

    async def test_callback_decision_is_used(self):
        async def deny(confirmation: ToolConfirmation) -> bool:
            return False

        manager = ApprovalManager(
            ApprovalPolicy.ON_REQUEST, Path.cwd(), confimation_callback=deny
        )

        approved = await manager.request_confirmation(
            ToolConfirmation(tool_name="write", params={}, description="Run write")
        )

        self.assertFalse(approved)


class RegistryCallbackWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoke_passes_confirmation_callback_to_invocation(self):
        async def approve(confirmation: ToolConfirmation) -> bool:
            return True

        config = Config()
        registry = ToolRegistry(config)
        tool = RecordingTool(config)
        registry.register(tool)

        manager = ApprovalManager(
            ApprovalPolicy.ON_REQUEST, config.cwd, confimation_callback=approve
        )

        result = await registry.invoke(
            "recording_tool", {}, config.cwd, HookSystem(config), manager
        )

        self.assertTrue(result.success)
        self.assertIs(tool.invocation.confirmation_callback, approve)


class SubagentApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_subagent_inherits_parent_confirmation_callback(self):
        import agent.agent as agent_module

        captured: dict[str, Any] = {}
        seen_confirmations: list[ToolConfirmation] = []

        async def parent_callback(confirmation: ToolConfirmation) -> bool:
            seen_confirmations.append(confirmation)
            return True

        class FakeAgent:
            def __init__(self, config, confirmation_callback=None, **kwargs):
                captured["confirmation_callback"] = confirmation_callback

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def run(self, prompt):
                return
                yield

        original_agent = agent_module.Agent
        agent_module.Agent = FakeAgent
        try:
            tool = SubAgentTool(Config(), CODEBASE_INVESTIGATOR)
            invocation = ToolInvocation(
                params={"goal": "inspect the codebase"},
                cwd=Path.cwd(),
                confirmation_callback=parent_callback,
            )

            result = await tool.execute(invocation)
        finally:
            agent_module.Agent = original_agent

        self.assertTrue(result.success)

        subagent_callback = captured["confirmation_callback"]
        self.assertIsNotNone(subagent_callback)

        # The wrapper must delegate to the parent callback and label the
        # confirmation with the subagent's name.
        confirmation = ToolConfirmation(
            tool_name="write", params={}, description="Run write"
        )
        approved = await subagent_callback(confirmation)

        self.assertTrue(approved)
        self.assertEqual(len(seen_confirmations), 1)
        self.assertIn("codebase_investigator", seen_confirmations[0].description)

    async def test_subagent_without_parent_callback_gets_none(self):
        import agent.agent as agent_module

        captured: dict[str, Any] = {}

        class FakeAgent:
            def __init__(self, config, confirmation_callback=None, **kwargs):
                captured["confirmation_callback"] = confirmation_callback

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def run(self, prompt):
                return
                yield

        original_agent = agent_module.Agent
        agent_module.Agent = FakeAgent
        try:
            tool = SubAgentTool(Config(), CODEBASE_INVESTIGATOR)
            invocation = ToolInvocation(
                params={"goal": "inspect the codebase"},
                cwd=Path.cwd(),
            )

            await tool.execute(invocation)
        finally:
            agent_module.Agent = original_agent

        # With no parent callback the subagent's ApprovalManager has no
        # callback either, and request_confirmation now fails closed.
        self.assertIsNone(captured["confirmation_callback"])


if __name__ == "__main__":
    unittest.main()
