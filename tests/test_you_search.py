"""Tests for the optional You.com search tool."""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from config.config import Config
from tools.base import ToolInvocation
from tools.network.you_search import (
    YouSearchParams,
    YouSearchTool,
    format_youcom_results,
)


@contextmanager
def mock_httpx(body: str, status_code: int = 200):
    """Patch the httpx AsyncClient POST used by YouSearchTool."""

    response = mock.Mock()
    response.status_code = status_code
    response.text = body
    response.raise_for_status = mock.Mock()

    client = mock.AsyncMock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=False)
    client.post = mock.AsyncMock(return_value=response)

    with mock.patch('tools.network.you_search.httpx.AsyncClient', return_value=client):
        yield client


def invocation(params: dict) -> ToolInvocation:
    return ToolInvocation(params=params, cwd=Path('.'))


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

    def test_formats_mcp_list_shape(self) -> None:
        # The hosted `you-search` MCP tool returns content[0].text as a
        # JSON-encoded list of {title, url, snippets} hits.
        payload = [
            {
                'title': 'Postal',
                'url': 'https://github.com/andrefetch/postal',
                'snippets': ['A terminal AI coding agent.'],
            },
            {
                'title': 'Postal docs',
                'url': 'https://example.com/postal-docs',
            },
        ]

        output = format_youcom_results('postal', payload)

        self.assertIn('Search results for: postal', output)
        self.assertIn('1. Title: Postal', output)
        self.assertIn('URL: https://github.com/andrefetch/postal', output)
        self.assertIn('Snippet: A terminal AI coding agent.', output)
        self.assertIn('2. Title: Postal docs', output)

    def test_empty_results(self) -> None:
        output = format_youcom_results('postal', {'results': {}})

        self.assertIn('Search results for: postal', output)

    def test_empty_mcp_list_shape(self) -> None:
        output = format_youcom_results('postal', [])

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

    def test_execute_reports_jsonrpc_error_message(self) -> None:
        body = '{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"rate limited"}}'

        with mock_httpx(body):
            result = asyncio.run(
                YouSearchTool(Config()).execute(
                    invocation({'query': 'postal'})
                )
            )

        self.assertFalse(result.success)
        self.assertIn('rate limited', result.error)

    def test_execute_reports_iserror_content(self) -> None:
        body = (
            '{"jsonrpc":"2.0","id":1,"result":{"isError":true,'
            '"content":[{"type":"text","text":"invalid api key"}]}}'
        )

        with mock_httpx(body):
            result = asyncio.run(
                YouSearchTool(Config()).execute(
                    invocation({'query': 'postal'})
                )
            )

        self.assertFalse(result.success)
        self.assertIn('invalid api key', result.error)

    def test_execute_formats_mcp_list_shape(self) -> None:
        hits = [
            {
                'title': 'Postal',
                'url': 'https://github.com/andrefetch/postal',
                'snippets': ['A terminal AI coding agent.'],
            }
        ]
        body = json.dumps({
            'jsonrpc': '2.0',
            'id': 1,
            'result': {
                'content': [
                    {'type': 'text', 'text': json.dumps(hits)}
                ]
            },
        })

        with mock_httpx(body):
            result = asyncio.run(
                YouSearchTool(Config()).execute(
                    invocation({'query': 'postal'})
                )
            )

        self.assertTrue(result.success)
        self.assertIn('1. Title: Postal', result.output)
        self.assertIn('Snippet: A terminal AI coding agent.', result.output)
        self.assertEqual(result.metadata['results'], 1)


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
