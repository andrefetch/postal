from __future__ import annotations

import asyncio
import signal

from contextlib import contextmanager

from typing import Any

from prompt_toolkit.filters import Condition
from prompt_toolkit.input import create_input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from ui.tui import TUI

EXPAND_KEY = "c-o"


def build_key_bindings(tui: TUI, repl: Any = None) -> KeyBindings:

    bindings = KeyBindings()

    @bindings.add(EXPAND_KEY)
    def _(event) -> None:
        tui.toggle_expansion()

        app = event.app
        app.renderer.erase()
        app.renderer.reset()
        app._request_absolute_cursor_position()
        app._redraw()

    def is_slash_cmd() -> bool:
        if repl is None:
            return False
        text = repl.session.default_buffer.text
        return text.startswith("/") and " " not in text

    @Condition
    def slash_cmd_active() -> bool:
        return is_slash_cmd()

    def get_matches() -> list[tuple[str, str]]:
        if repl is None:
            return []
        text = repl.session.default_buffer.text
        if not text.startswith("/") or " " in text:
            return []
        prefix = text[1:]
        return [
            (name, repl.commands.describe(name))
            for name in repl.commands.command_names()
            if name.startswith(prefix)
        ]

    @bindings.add("down", filter=slash_cmd_active)
    @bindings.add("tab", filter=slash_cmd_active)
    def _(event) -> None:
        matches = get_matches()
        if matches and repl is not None:
            repl._completion_index = (repl._completion_index + 1) % len(matches)

    @bindings.add("up", filter=slash_cmd_active)
    def _(event) -> None:
        matches = get_matches()
        if matches and repl is not None:
            repl._completion_index = (repl._completion_index - 1) % len(matches)

    @bindings.add("enter", filter=slash_cmd_active)
    @bindings.add("c-j", filter=slash_cmd_active)
    def _(event) -> None:
        matches = get_matches()
        if matches and repl is not None:
            idx = getattr(repl, "_completion_index", 0)
            if 0 <= idx < len(matches):
                event.current_buffer.text = f"/{matches[idx][0]}"
                event.current_buffer.cursor_position = len(event.current_buffer.text)
            repl._completion_index = 0
        event.current_buffer.validate_and_handle()

    return bindings


@contextmanager
def turn_keys(tui: TUI, task: asyncio.Task):
    """Read keys for the length of a turn, falling back to SIGINT with no tty."""

    try:
        device = create_input()
    except Exception:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, task.cancel)
        except (NotImplementedError, RuntimeError):
            pass
        try:
            yield
        finally:
            try:
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, RuntimeError):
                pass
        return

    def on_keys() -> None:
        for key_press in device.read_keys():
            if tui.feed_confirmation_key(key_press):
                continue
            if key_press.key == Keys.ControlO:
                tui.toggle_expansion()
            elif key_press.key == Keys.ControlC:
                task.cancel()

    tui.external_keys = True
    try:
        with device.raw_mode(), device.attach(on_keys):
            yield
    finally:
        tui.external_keys = False
