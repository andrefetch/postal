import unittest
from pathlib import Path

from config.config import ApprovalPolicy
from safety.approval import (
    ApprovalDecision,
    ApprovalManager,
    is_safe_command,
    split_command_segments,
)


class SplitCommandSegmentsTests(unittest.TestCase):
    def test_splits_on_every_operator(self):
        self.assertEqual(split_command_segments("ls && rm -rf ./src"), ["ls", "rm -rf ./src"])
        self.assertEqual(split_command_segments("ps aux; git push --force"), ["ps aux", "git push --force"])
        self.assertEqual(split_command_segments("cat a || rm b"), ["cat a", "rm b"])
        self.assertEqual(split_command_segments("cat a | tee b"), ["cat a", "tee b"])

    def test_keeps_a_plain_command_whole(self):
        self.assertEqual(split_command_segments("git status"), ["git status"])

    def test_does_not_split_inside_quotes(self):
        self.assertEqual(split_command_segments("echo 'a && b'"), ["echo 'a && b'"])
        self.assertEqual(split_command_segments('echo "a; b"'), ['echo "a; b"'])


class IsSafeCommandTests(unittest.TestCase):
    def test_plain_read_only_commands_stay_safe(self):
        for command in ("ls", "ls -la", "pwd", "git status", "git log --oneline", "ps aux"):
            with self.subTest(command=command):
                self.assertTrue(is_safe_command(command))

    def test_compound_command_is_only_safe_when_every_segment_is(self):
        self.assertFalse(is_safe_command("ls && rm -rf ./src"))
        self.assertFalse(is_safe_command("ps aux; git push --force"))
        self.assertFalse(is_safe_command("cat notes.txt | tee /etc/passwd"))
        self.assertTrue(is_safe_command("ls && pwd"))
        self.assertTrue(is_safe_command("git status | head -5"))

    def test_writing_text_tools_are_not_safe(self):
        for command in ("sed -i s/a/b/ config.py", "awk '{print}' f", "find . -name x -exec rm {} +"):
            with self.subTest(command=command):
                self.assertFalse(is_safe_command(command))

    def test_redirection_is_not_safe(self):
        self.assertFalse(is_safe_command("ls > /etc/passwd"))
        self.assertFalse(is_safe_command("echo x >> ~/.bashrc"))

    def test_command_substitution_is_not_safe(self):
        self.assertFalse(is_safe_command("echo $(rm -rf /)"))
        self.assertFalse(is_safe_command("echo `rm -rf /`"))

    def test_unparsable_command_is_not_safe(self):
        self.assertFalse(is_safe_command("echo 'unbalanced"))

    def test_empty_command_is_not_safe(self):
        self.assertFalse(is_safe_command(""))
        self.assertFalse(is_safe_command("   "))


class ApprovalDecisionForCompoundCommandTests(unittest.TestCase):
    def test_on_request_asks_instead_of_auto_approving(self):
        manager = ApprovalManager(ApprovalPolicy.ON_REQUEST, Path.cwd())

        decision = manager._assess_command_safety("ls && rm -rf ./src")

        self.assertEqual(decision, ApprovalDecision.NEEDS_CONFIRMATION)

    def test_on_request_still_auto_approves_a_read_only_command(self):
        manager = ApprovalManager(ApprovalPolicy.ON_REQUEST, Path.cwd())

        decision = manager._assess_command_safety("git status")

        self.assertEqual(decision, ApprovalDecision.APPROVED)


if __name__ == "__main__":
    unittest.main()
