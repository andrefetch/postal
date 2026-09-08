import unittest
from pathlib import Path

from rich.console import Console
from tools.base import FileDiff, ToolConfirmation
from ui.components.permission_prompt import permission_prompt
from ui.components.tool_progress import tool_progress_panel
from ui.theme import AGENT_THEME


class UIComponentTests(unittest.TestCase):
    def test_tool_progress_panel_includes_tool_and_progress(self) -> None:
        panel = tool_progress_panel(
            "bash", 4, "Running tests", headline="pytest", spinner="*"
        )
        self.assertIn("*", panel.renderable.plain)
        self.assertIn("bash", panel.renderable.plain)
        self.assertIn("pytest", panel.renderable.plain)
        self.assertIn("Running tests", panel.renderable.plain)
        self.assertIn("4s", panel.renderable.plain)

    def test_permission_prompt_uses_relative_diff_path(self) -> None:
        cwd = Path("/workspace/project")
        rendered = permission_prompt(
            ToolConfirmation(
                tool_name="write",
                params={},
                description="Write file",
                diff=FileDiff(cwd / "src/main.py", "old\n", "new\n"),
            ),
            cwd,
        )
        console = Console(record=True, width=100, theme=AGENT_THEME)
        for block in rendered:
            console.print(block)
        output = console.export_text()
        self.assertIn("src/main.py", output)
        self.assertNotIn("/workspace/project/src/main.py", output)

    def test_permission_prompt_marks_dangerous_operation_and_paths(self) -> None:
        rendered = permission_prompt(
            ToolConfirmation(
                tool_name="bash",
                params={"command": "rm -rf build"},
                description="Run command",
                affected_paths=[Path("build")],
                is_dangerous=True,
            )
        )
        console = Console(record=True, width=100, theme=AGENT_THEME)
        for block in rendered:
            console.print(block)
        output = console.export_text()
        self.assertIn("permission required", output)
        self.assertIn("dangerous", output)
        self.assertIn("Affects:", output)
        self.assertIn("build", output)


if __name__ == "__main__":
    unittest.main()
