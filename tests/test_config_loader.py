import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import loader
from config.loader import _strip_frontmatter, load_config


YOU_MD = """---
schema_version: "1.1"
privacy_level: "private"
---

# Me

## How I Communicate

Verbosity: concise
Tone: direct

## How I Work

- Prefer TypeScript in strict mode
- Explain tradeoffs before introducing dependencies
"""


class StripFrontmatterTests(unittest.TestCase):

    def test_removes_a_leading_yaml_block(self):
        body = _strip_frontmatter(YOU_MD)
        self.assertNotIn("schema_version", body)
        self.assertNotIn("privacy_level", body)
        self.assertTrue(body.lstrip().startswith("# Me"))

    def test_leaves_content_without_frontmatter_alone(self):
        content = "# Me\n\nJust markdown.\n"
        self.assertEqual(_strip_frontmatter(content), content)

    def test_keeps_an_unclosed_fence_as_content(self):
        content = "---\nnot: closed\n\n# Me\n"
        self.assertEqual(_strip_frontmatter(content), content)

    def test_a_horizontal_rule_later_in_the_file_is_not_frontmatter(self):
        content = "# Me\n\n---\n\nMore.\n"
        self.assertEqual(_strip_frontmatter(content), content)


class UserInstructionsFileTests(unittest.TestCase):
    """`user_instructions_file` fills `user_instructions` only when that is empty."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

        # Keep the test away from the real ~/.config/postal/config.toml.
        self.system_config = self.root / "system" / "config.toml"
        self.system_config.parent.mkdir(parents=True)
        patcher = mock.patch.object(
            loader, "get_system_config_path", return_value=self.system_config
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.project = self.root / "project"
        (self.project / ".postal").mkdir(parents=True)
        self.project_config = self.project / ".postal" / "config.toml"

    def _write(self, path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_default_leaves_user_instructions_unset(self):
        config = load_config(self.project)
        self.assertIsNone(config.user_instructions)
        self.assertIsNone(config.user_instructions_file)

    def test_loads_the_file_body_with_frontmatter_stripped(self):
        profile = self._write(self.root / "profile.md", YOU_MD)
        self._write(self.project_config, f'user_instructions_file = "{profile}"\n')

        config = load_config(self.project)

        self.assertEqual(config.user_instructions_file, str(profile))
        self.assertIsNotNone(config.user_instructions)
        self.assertTrue(config.user_instructions.startswith("# Me"))
        self.assertIn("Verbosity: concise", config.user_instructions)
        self.assertNotIn("schema_version", config.user_instructions)

    def test_inline_user_instructions_win_over_the_file(self):
        profile = self._write(self.root / "profile.md", YOU_MD)
        self._write(
            self.project_config,
            f'user_instructions = "Always answer in haiku."\nuser_instructions_file = "{profile}"\n',
        )

        config = load_config(self.project)

        self.assertEqual(config.user_instructions, "Always answer in haiku.")

    def test_an_empty_inline_placeholder_does_not_block_the_file(self):
        profile = self._write(self.root / "profile.md", "Be brief.\n")
        self._write(
            self.project_config,
            f'user_instructions = ""\nuser_instructions_file = "{profile}"\n',
        )

        config = load_config(self.project)

        self.assertEqual(config.user_instructions, "Be brief.")

    def test_expands_a_home_relative_path(self):
        home = self.root / "home"
        self._write(home / ".you.md", "Prefer short answers.\n")
        self._write(self.project_config, 'user_instructions_file = "~/.you.md"\n')

        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            config = load_config(self.project)

        self.assertEqual(config.user_instructions, "Prefer short answers.")

    def test_resolves_a_relative_path_against_the_working_directory(self):
        self._write(self.project / ".you.md", "Project-level preferences.\n")
        self._write(self.project_config, 'user_instructions_file = ".you.md"\n')

        config = load_config(self.project)

        self.assertEqual(config.user_instructions, "Project-level preferences.")

    def test_a_missing_file_warns_and_leaves_user_instructions_unset(self):
        missing = self.root / "nope.md"
        self._write(self.project_config, f'user_instructions_file = "{missing}"\n')

        with self.assertLogs("config.loader", level="WARNING") as logs:
            config = load_config(self.project)

        self.assertIsNone(config.user_instructions)
        self.assertTrue(any("not found" in line for line in logs.output))

    def test_a_file_with_only_frontmatter_is_skipped(self):
        profile = self._write(self.root / "empty.md", "---\nschema_version: \"1.1\"\n---\n")
        self._write(self.project_config, f'user_instructions_file = "{profile}"\n')

        with self.assertLogs("config.loader", level="WARNING"):
            config = load_config(self.project)

        self.assertIsNone(config.user_instructions)

    def test_the_file_setting_also_comes_from_the_user_config(self):
        profile = self._write(self.root / "profile.md", "From the user layer.\n")
        self._write(self.system_config, f'user_instructions_file = "{profile}"\n')

        config = load_config(self.project)

        self.assertEqual(config.user_instructions, "From the user layer.")


if __name__ == "__main__":
    unittest.main()
