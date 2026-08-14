import unittest

from tools.core.bash import (
    DANGEROUS_COMMANDS,
    DANGEROUS_FRAGMENTS,
    DANGEROUS_PROGRAMS,
    find_blocked_entry,
)


class HarmlessCommandsTests(unittest.TestCase):
    def test_a_program_name_inside_ordinary_text_does_not_block(self):
        for command in (
            'python -c "time.sleep(1)"',
            "pytest tests/test_sleep.py",
            'git commit -m "fix reboot"',
            'echo "halt the rollout"',
            "grep -r poweroff docs/",
        ):
            with self.subTest(command=command):
                self.assertIsNone(find_blocked_entry(command))

    def test_sleep_is_no_longer_a_dangerous_command(self):
        self.assertNotIn("sleep", DANGEROUS_COMMANDS)


class DangerousCommandsStillBlockedTests(unittest.TestCase):
    def test_a_dangerous_program_at_a_command_position_blocks(self):
        for command, entry in (
            ("reboot", "reboot"),
            ("sudo reboot", "reboot"),
            ("shutdown -h now", "shutdown"),
            ("sudo mkfs.ext4 /dev/sda1", "mkfs"),
            ("ls && halt", "halt"),
            ("ls; poweroff", "poweroff"),
        ):
            with self.subTest(command=command):
                self.assertEqual(find_blocked_entry(command), entry)

    def test_specific_fragments_block_wherever_they_appear(self):
        for command in (
            "rm -rf /",
            'bash -c "rm -rf /"',
            "cd /tmp && rm -rf ~",
            "dd if=/dev/zero of=/dev/sda",
            "chmod -R 777 /etc",
            "init 0",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(find_blocked_entry(command))

    def test_matching_is_case_insensitive(self):
        self.assertIsNotNone(find_blocked_entry("REBOOT"))
        self.assertIsNotNone(find_blocked_entry("RM -RF /"))


class EntrySetsTests(unittest.TestCase):
    def test_dangerous_commands_is_the_union(self):
        self.assertEqual(DANGEROUS_COMMANDS, DANGEROUS_PROGRAMS | DANGEROUS_FRAGMENTS)

    def test_the_two_sets_do_not_overlap(self):
        self.assertEqual(DANGEROUS_PROGRAMS & DANGEROUS_FRAGMENTS, set())


if __name__ == "__main__":
    unittest.main()
