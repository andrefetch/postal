"""Tests for the optional You.com search tool."""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from config.config import Config
from tools.base import ToolInvocation
from tools.network.you_search import (
    YouSearchParams,
    YouSearchTool,
    format_youcom_results,
)


class YouSearchParamTests(unittest.TestCase):
    def test_defaults(self) -> None:
        params = YouSearchParams(query='postal coding agent')

        self.assertEqual(params.max_results, 10)

    def test_max_results_bounds(self) -> None:
        with self.assertRaises(Exception):
            YouSearchParams(query='q', max_results=0)

        with self.assertRaises(Exception):
            YouSearchParams(query='q', max_results=31)


class FormatYoucomResultsTests(unittest.TestCase):
    def test_formats_web_section(self) -> None:
        payload = {
            'results': {
                'web': [
                    {
                        'title': 'Postal',
                        'url': 'https://github.com/andrefetch/postal',
                        'description': 'A terminal AI coding agent.',
                    }
                ]
            }
        }

        output = format_youcom_results('postal', payload)

        self.assertIn('Search results for: postal', output)
        self.assertIn('1. Title: Postal', output)
        self.assertIn('URL: https://github.com/andrefetch/postal', output)
        self.assertIn('Snippet: A terminal AI coding agent.', output)

    def test_falls_back_to_highlights(self) -> None:
        payload = {
            'results': {
                'web': [
                    {
                        'title': 'Postal',
                        'url': 'https://github.com/andrefetch/postal',
                        'contents': {'highlights': ['First highlight.']},
                    }
                ]
            }
        }

        output = format_youcom_results('postal', payload)

        self.assertIn('Snippet: First highlight.', output)

    def test_empty_results(self) -> None:
        output = format_youcom_results('postal', {'results': {}})

        self.assertIn('Search results for: postal', output)


class YouSearchToolTests(unittest.TestCase):
    def test_extract_result_from_sse(self) -> None:
        body = '\n'.join(
            [
                'event: message',
                'data: {"jsonrpc":"2.0","method":"notifications/message","params":{"level":"info"}}',
                'data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\\"results\\":{}}"}]}}',
                '',
            ]
        )

        message = YouSearchTool._extract_result(body)

        self.assertIsNotNone(message)
        self.assertIn('result', message)

    def test_extract_result_ignores_other_ids(self) -> None:
        body = 'data: {"jsonrpc":"2.0","id":99,"result":{}}\n\n'

        self.assertIsNone(YouSearchTool._extract_result(body))

    def test_extract_result_plain_json(self) -> None:
        body = '{"jsonrpc":"2.0","id":1,"result":{"content":[]}}'

        message = YouSearchTool._extract_result(body)

        self.assertIsNotNone(message)

    def test_tool_metadata(self) -> None:
        tool = YouSearchTool(Config())

        self.assertEqual(tool.name, 'you_search')
        self.assertEqual(tool.schema, YouSearchParams)


class RegistrationTests(unittest.TestCase):
    def test_default_registry_omits_you_search(self) -> None:
        from tools import create_default_registry

        os.environ.pop('YOUCOM_SEARCH', None)

        registry = create_default_registry(Config())

        self.assertIsNone(registry.get('you_search'))

    def test_registry_includes_you_search_when_opted_in(self) -> None:
        from tools import create_default_registry

        os.environ['YOUCOM_SEARCH'] = '1'

        try:
            registry = create_default_registry(Config())

            tool = registry.get('you_search')

            self.assertIsNotNone(tool)
            self.assertEqual(tool.name, 'you_search')
        finally:
            os.environ.pop('YOUCOM_SEARCH', None)


if __name__ == '__main__':
    unittest.main()
