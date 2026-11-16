from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from config.config import Config


class Repl:
    """Launch the TypeScript terminal with the current Python interpreter."""

    def __init__(
        self,
        config: Config,
        resume: str | None = None,
        upgrade_notice: str | None = None,
    ) -> None:
        self.config = config
        self.resume = resume
        self.upgrade_notice = upgrade_notice

    async def run(self) -> None:
        if os.environ.get("POSTAL_UI") == "textual":
            from ui.textual_app import PostalApp
            await PostalApp(self.config, resume=self.resume, upgrade_notice=self.upgrade_notice).run_async()
            return
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("The TypeScript TUI requires Node.js 22+. Install Node, or set POSTAL_UI=textual to use the legacy interface.")
        version = await asyncio.create_subprocess_exec(node, "--version", stdout=asyncio.subprocess.PIPE)
        output, _ = await version.communicate()
        try:
            supported = int(output.decode().strip().lstrip("v").split(".")[0]) >= 22
        except ValueError:
            supported = False
        if not supported:
            raise RuntimeError("The TypeScript TUI requires Node.js 22 or later.")
        ui_dir = Path(__file__).resolve().parents[1]
        bundle = ui_dir / "terminal_bundle" / "postal.mjs"
        if not bundle.is_file():
            raise RuntimeError("Build the TypeScript TUI first: npm ci --prefix ui/terminal && npm run build --prefix ui/terminal")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ui_dir.parent), env.get("PYTHONPATH")]))
        with tempfile.TemporaryDirectory(prefix="postal-tui-") as directory:
            bootstrap = Path(directory) / "session.json"
            bootstrap.write_text(json.dumps({
                "config": self.config.model_dump(mode="json"),
                "resume": self.resume, "upgrade_notice": self.upgrade_notice,
            }), encoding="utf-8")
            bootstrap.chmod(0o600)
            process = await asyncio.create_subprocess_exec(
                node, str(bundle), "--python", sys.executable, "--bootstrap", str(bootstrap), env=env,
            )
            try:
                code = await process.wait()
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 8)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
            if code:
                raise RuntimeError(f"The terminal frontend exited with status {code}.")
