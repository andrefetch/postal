import asyncio
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.config import Config
from hooks.hook_system import HookSystem
from tools.base import ToolInvocation
from tools.core.bash import BashTool


@unittest.skipIf(sys.platform == "win32", "POSIX process-group cleanup")
class SubprocessCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bash_cancellation_kills_and_reaps_the_process_group(self):
        started = asyncio.Event()
        processes = []
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "orphan-ran"
            child_script = f"import time; from pathlib import Path; time.sleep(0.25); Path({str(marker)!r}).touch(); time.sleep(60)"
            script = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
                "print('ready', flush=True); time.sleep(60)"
            )
            command = f"{shlex.quote(sys.executable)} -u -c {shlex.quote(script)}"
            invocation = ToolInvocation(
                {"command": command}, Path(directory),
                progress_callback=lambda text: started.set() if "ready" in text else None,
            )
            with patch("asyncio.create_subprocess_exec", capture):
                task = asyncio.create_task(BashTool(Config()).execute(invocation))
                try:
                    await asyncio.wait_for(started.wait(), 2)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
            self.assertIsNotNone(processes[0].returncode)
            await asyncio.sleep(0.35)
            self.assertFalse(marker.exists(), "A descendant survived cancellation")

    async def test_hook_cancellation_reaps_its_process(self):
        started = asyncio.Event()
        processes = []
        original = asyncio.create_subprocess_shell

        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            started.set()
            return process

        command = f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(60)'"
        with patch("asyncio.create_subprocess_shell", capture):
            task = asyncio.create_task(HookSystem(Config())._run_command(command, 60, dict(os.environ)))
            try:
                await asyncio.wait_for(started.wait(), 2)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertIsNotNone(processes[0].returncode)
