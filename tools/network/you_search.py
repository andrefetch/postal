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

def format_youcom_results(query: str, payload: dict) -> str:
    """Turn the `you-search` tool payload into the same text shape as `search`."""

    output_lines = [f'Search results for: {query}']

    results = payload.get('results', {})
    numbered = 0

    for section in ('web', 'news', 'knowledge'):
        for result in results.get(section, []):
            numbered += 1
            output_lines.append(f"{numbered}. Title: {result.get('title', '')}")
            output_lines.append(f"     URL: {result.get('url', '')}")

            snippet = result.get('description', '')
            if not snippet:
                highlights = result.get('contents', {}).get('highlights', [])
                snippet = highlights[0] if highlights else ''

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

        tool_result = payload.get('result', {})
        if 'error' in tool_result:
            return ToolResult.error_result(
                f"Search failed: {tool_result['error'].get('message', tool_result['error'])}"
            )

        try:
            text = tool_result['content'][0]['text']
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return ToolResult.error_result(
                'Search failed: unexpected You.com response format'
            )

        output = format_youcom_results(params.query, data)

        total = sum(
            len(data.get('results', {}).get(section, []))
            for section in ('web', 'news', 'knowledge')
        )

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
