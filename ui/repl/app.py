from __future__ import annotations

from config.config import Config
from ui.textual_app import PostalApp


class Repl:
    """Launch the full-screen Textual interface for an interactive session."""

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
        app = PostalApp(self.config, resume=self.resume, upgrade_notice=self.upgrade_notice)
        await app.run_async()
