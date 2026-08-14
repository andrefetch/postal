from ddgs import DDGS

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

class WebSearchParams(BaseModel):

    query: str = Field(
        ...,
        description='Search query'
    )

    max_results: int = Field(
        10,
        ge=1,
        le=50,
        description='Maximum results to return (default: 10)'
    )

class WebSearchTool(Tool):
    name = 'search'
    description = 'Search the web for information. Returns the search results that contains titles, URL(s) and snippets.'
    kind = ToolKind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        try:
            results = DDGS().text(
                params.query,
                region='us-en',
                safesearch='off',
                timelimit='y',
                page=1,
                backend='auto'
            )
        except Exception as e:
            return ToolResult.error_result(
                f'Search failed: {e}'
            )

        if not results:
            return ToolResult.success_result(
                f'No results found for: {params.query}',
                metadata = {
                    'results': 0,
                }
            )

        output_lines = [
            f'Search results for: {params.query}'
        ]

        for i, result in enumerate(results, start=1):
            output_lines.append(f"{i}. Title: {result['title']}")
            output_lines.append(f"     URL: {result['href']}")
            if result.get('body'):
                output_lines.append(f"  Snippet: {result['body']}")

            output_lines.append("")

        return ToolResult.success_result(
            '\n'.join(output_lines),
            metadata = {
                'results': len(results),
            }
        )
