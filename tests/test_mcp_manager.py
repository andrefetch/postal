import asyncio
import os
import socket
import unittest
from unittest import mock
from pathlib import Path

import uvicorn
from fastmcp import FastMCP
from fastmcp.client.transports import SSETransport, StreamableHttpTransport

from config.config import Config, MCPServerConfig
from tools.base import ToolInvocation
from tools.mcp.client import MCPClient, MCPServerStatus
from tools.mcp.manager import MCPManager
from tools.registry import ToolRegistry


class MCPTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_url_transport_defaults_to_sse(self) -> None:
        client = MCPClient("legacy", MCPServerConfig(url="https://example.test/sse"), Path.cwd())
        self.assertIsInstance(client._create_transport(), SSETransport)

    def test_streamable_http_must_be_selected_explicitly(self) -> None:
        client = MCPClient(
            "modern",
            MCPServerConfig(url="https://example.test/mcp", transport="streamable_http"),
            Path.cwd(),
        )
        self.assertIsInstance(client._create_transport(), StreamableHttpTransport)

    async def test_manager_registers_and_executes_streamable_http_tools(self) -> None:
        calls: list[tuple[str, object]] = []
        server = FastMCP("search-test")

        @server.tool
        def web_search(objective: str, search_queries: list[str]) -> str:
            calls.append(("web_search", {"objective": objective, "search_queries": search_queries}))
            return "search result"

        @server.tool
        def web_fetch(urls: list[str]) -> str:
            calls.append(("web_fetch", {"urls": urls}))
            if urls == ["https://example.test/error"]:
                raise ValueError("fetch failed")
            return "page contents"

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        app = server.http_app(path="/mcp", transport="streamable-http")
        http_server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        server_task = asyncio.create_task(http_server.serve())
        while not http_server.started:
            await asyncio.sleep(0.01)

        config = Config(
            mcp_servers={
                "parallel": MCPServerConfig(
                    url=f"http://127.0.0.1:{port}/mcp",
                    transport="streamable_http",
                )
            }
        )
        manager = MCPManager(config)
        try:
            with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1"}):
                await manager.initialize()
            self.assertEqual(manager.clients[0].status, MCPServerStatus.CONNECTED)

            registry = ToolRegistry(config)
            self.assertEqual(manager.register_tools(registry), 2)
            search = registry.get("parallel__web_search")
            fetch = registry.get("parallel__web_fetch")
            self.assertIsNotNone(search)
            self.assertIsNotNone(fetch)
            self.assertEqual(set(search.schema["properties"]), {"objective", "search_queries"})
            self.assertEqual(search.schema["required"], ["objective", "search_queries"])
            self.assertEqual(set(fetch.schema["properties"]), {"urls"})
            self.assertEqual(fetch.schema["required"], ["urls"])

            search_result = await search.execute(
                ToolInvocation(
                    params={"objective": "Find sources", "search_queries": ["Postal MCP"]},
                    cwd=None,
                )
            )
            fetch_result = await fetch.execute(
                ToolInvocation(params={"urls": ["https://example.test/page"]}, cwd=None)
            )
            error_result = await fetch.execute(
                ToolInvocation(params={"urls": ["https://example.test/error"]}, cwd=None)
            )

            self.assertIn("search result", search_result.output)
            self.assertIn("page contents", fetch_result.output)
            self.assertFalse(error_result.success)
            self.assertIn("fetch failed", error_result.error)
            self.assertEqual(
                calls[:2],
                [
                    ("web_search", {"objective": "Find sources", "search_queries": ["Postal MCP"]}),
                    ("web_fetch", {"urls": ["https://example.test/page"]}),
                ],
            )
        finally:
            await manager.shutdown()
            self.assertEqual(manager.clients, [])
            http_server.should_exit = True
            await server_task


if __name__ == "__main__":
    unittest.main()
