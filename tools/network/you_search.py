import json
import os

import httpx

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

# The keyless profile serves the same `you-search` tool without an API key;
# pointing at the authenticated endpoint with a key unlocks higher limits.
YOUCOM_FREE_URL = 'https://api.you.com/mcp?profile=free'
YOUCOM_AUTH_URL = 'https://api.you.com/mcp'

class YouSearchParams(BaseModel):

    query: str = Field(
        ...,
        description='Search query'
    )

    max_results: int = Field(
        10,
        ge=1,
        le=30,
        description='Maximum results to return (default: 10)'
    )

def _iter_youcom_results(data):
    """Yield result dicts from either MCP response shape.

    The hosted `you-search` tool returns `content[0].text` as a JSON-encoded
    list of {title, url, snippets} hits; the Search API returns a dict with
    `results.web` / `results.news` / `results.knowledge` sections. Both are
    accepted here.
    """

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
        return

    if not isinstance(data, dict):
        return

    results = data.get('results', {})
    if not isinstance(results, dict):
        return

    for section in ('web', 'news', 'knowledge'):
        section_items = results.get(section)
        if not isinstance(section_items, list):
            continue
        for item in section_items:
            if isinstance(item, dict):
                yield item

def _result_snippet(result: dict) -> str:
    snippet = result.get('description', '') or result.get('snippet', '')

    if not snippet:
        snippets = result.get('snippets')
        if isinstance(snippets, list) and snippets:
            snippet = snippets[0]

    if not snippet:
        contents = result.get('contents')
        if isinstance(contents, dict):
            highlights = contents.get('highlights')
            if isinstance(highlights, list) and highlights:
                snippet = highlights[0]

    return snippet or ''

def format_youcom_results(query: str, payload) -> str:
    """Turn the `you-search` tool payload into the same text shape as `search`."""

    output_lines = [f'Search results for: {query}']
    numbered = 0

    for result in _iter_youcom_results(payload):
        numbered += 1
        output_lines.append(f"{numbered}. Title: {result.get('title', '')}")
        output_lines.append(f"     URL: {result.get('url', '')}")

        snippet = _result_snippet(result)
        if snippet:
            output_lines.append(f'  Snippet: {snippet}')

        output_lines.append('')

    return '\n'.join(output_lines)

class YouSearchTool(Tool):
    name = 'you_search'
    description = 'Search the web for information with You.com. Returns the search results that contains titles, URL(s) and snippets.'
    kind = ToolKind.NETWORK
    schema = YouSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = YouSearchParams(**invocation.params)

        api_key = os.environ.get('YDC_API_KEY')
        url = YOUCOM_AUTH_URL if api_key else YOUCOM_FREE_URL

        headers = {'Accept': 'application/json, text/event-stream'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        request = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/call',
            'params': {
                'name': 'you-search',
                'arguments': {
                    'query': params.query,
                    'count': params.max_results,
                },
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60),
                headers=headers,
            ) as client:
                response = await client.post(url, json=request)
                response.raise_for_status()
                body = response.text
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                f'HTTP {e.response.status_code}: {e.response.reason_phrase}'
            )
        except httpx.TimeoutException:
            return ToolResult.error_result(
                'Request timed out after 60s'
            )
        except Exception as e:
            return ToolResult.error_result(
                f'Search failed: {e}'
            )

        payload = self._extract_result(body)
        if payload is None:
            return ToolResult.error_result(
                'Search failed: could not parse the You.com response'
            )

        if 'error' in payload:
            error = payload['error']
            message = error.get('message', error) if isinstance(error, dict) else error
            return ToolResult.error_result(
                f'Search failed: {message}'
            )

        tool_result = payload.get('result', {})

        if not isinstance(tool_result, dict):
            return ToolResult.error_result(
                'Search failed: unexpected You.com response format'
            )

        if tool_result.get('isError'):
            error_text = self._error_text(tool_result)
            return ToolResult.error_result(
                f'Search failed: {error_text}'
            )

        try:
            text = tool_result['content'][0]['text']
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return ToolResult.error_result(
                'Search failed: unexpected You.com response format'
            )

        output = format_youcom_results(params.query, data)
        total = sum(1 for _ in _iter_youcom_results(data))

        if total == 0:
            return ToolResult.success_result(
                f'No results found for: {params.query}',
                metadata = {
                    'results': 0,
                }
            )

        return ToolResult.success_result(
            output,
            metadata = {
                'results': total,
            }
        )

    @staticmethod
    def _error_text(tool_result: dict) -> str:
        """Pull the server's error message out of an isError MCP result."""

        content = tool_result.get('content')

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get('text')
                if isinstance(text, str) and text.strip():
                    return text.strip()

        return 'You.com tool call failed'

    @staticmethod
    def _extract_result(body: str) -> dict | None:
        """Pull the JSON-RPC reply out of an SSE stream (or plain JSON body)."""

        for line in body.splitlines():
            if not line.startswith('data:'):
                continue

            try:
                message = json.loads(line[len('data:'):])
            except json.JSONDecodeError:
                continue

            if message.get('id') == 1:
                return message

        try:
            message = json.loads(body)
        except json.JSONDecodeError:
            return None

        return message if message.get('id') == 1 else None
