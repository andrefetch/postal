import asyncio
import unittest
from unittest.mock import patch

from config.config import Config
from ui.repl.app import Repl


class ReplTerminalTests(unittest.TestCase):
    def run_repl(self, isatty: bool):
        with patch("ui.repl.app.sys.stdin") as stdin, patch("ui.repl.app.shutil.which") as which:
            stdin.isatty.return_value = isatty
            which.return_value = "/usr/bin/node"
            with patch("ui.repl.app.asyncio.create_subprocess_exec") as spawn:
                with self.assertRaises(RuntimeError) as raised:
                    asyncio.run(Repl(Config()).run())
        return raised.exception, which, spawn

    def test_missing_tty_explains_how_to_run_in_docker(self):
        error, which, spawn = self.run_repl(isatty=False)

        message = str(error)
        self.assertIn("needs a terminal", message)
        self.assertIn("docker run -it", message)
        self.assertIn("docker exec -it", message)
        self.assertIn("postal \"your prompt\"", message)
        which.assert_not_called()
        spawn.assert_not_called()

    def test_missing_tty_does_not_require_node(self):
        error, which, _ = self.run_repl(isatty=False)

        self.assertNotIn("Node.js", str(error))
        which.assert_not_called()


if __name__ == "__main__":
    unittest.main()
