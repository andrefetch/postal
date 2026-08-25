"""Tests for slash-command autocompletion in the REPL."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText

from ui.repl.completer import SlashCompleter
from ui.repl.commands import SlashCommands
from ui.repl.keys import build_key_bindings
from ui.tui import TUI


def _commands() -> SlashCommands:
    return SlashCommands(Mock(), Mock())


def _complete(text: str) -> list[tuple[str, str]]:
    doc = Document(text, len(text))
    completer = SlashCompleter(_commands())
    return [
        (c.text, c.display_meta)
        for c in completer.get_completions(doc, Mock(completion_requested=True))
    ]


class SlashCompleterTests(unittest.TestCase):
    def test_slash_alone_lists_every_command(self) -> None:
        names = {name for name, _ in _complete("/")}
        self.assertTrue({"help", "clear", "model", "exit", "quit"}.issubset(names))
        self.assertEqual(len(names), 18)

    def test_prefix_filters_commands(self) -> None:
        self.assertEqual({name for name, _ in _complete("/th")}, {"thinking"})
        self.assertEqual(
            {name for name, _ in _complete("/s")},
            {"save", "sessions", "stats"},
        )

    def test_completion_keeps_the_slash(self) -> None:
        doc = Document("/m", 2)
        completer = SlashCompleter(_commands())
        result = [c for c in completer.get_completions(doc, Mock())]
        self.assertTrue(result)
        for c in result:
            self.assertEqual(c.start_position, -1)

    def test_plain_text_gets_no_completions(self) -> None:
        self.assertEqual(_complete("hello"), [])
        self.assertEqual(_complete("what is /model?"), [])

    def test_arguments_get_no_completions(self) -> None:
        self.assertEqual(_complete("/model "), [])
        self.assertEqual(_complete("/thinking on"), [])

    def test_aliases_are_documented(self) -> None:
        by_name = dict(_complete("/save"))
        self.assertEqual(by_name["save"], FormattedText([("", "Alias for /checkpoint")]))


class KeyBindingTests(unittest.TestCase):
    def test_completion_navigation_is_bound_while_menu_is_open(self) -> None:
        bindings = build_key_bindings(TUI(Mock(), Mock()))

        for key in ("c-i", "down", "up", "c-m", "c-j"):
            matches = [b for b in bindings.bindings if b.keys[0].value == key]
            self.assertTrue(matches, f"no binding for {key}")
            for binding in matches:
                self.assertIsNotNone(binding.filter)

    def test_expand_binding_is_always_bound(self) -> None:
        bindings = build_key_bindings(TUI(Mock(), Mock()))
        expand = [b for b in bindings.bindings if b.keys[0].value == "c-o"]
        self.assertTrue(expand)


if __name__ == "__main__":
    unittest.main()
