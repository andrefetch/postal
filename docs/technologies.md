# Technologies

What Postal is built on, and what each piece is actually doing.

## Frontend

| | |
| --- | --- |
| **[Textual](https://github.com/Textualize/textual)** | The full-screen interactive terminal: multiline editing, command completion, streaming messages, collapsible tools, approvals, and the agent activity tree. |
| **[Rich](https://github.com/Textualize/rich)** | Markdown and command output inside Textual, plus the streaming renderer for single-shot runs. |
| **[prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit)** | Persistent prompt history shared with the previous interface, and legacy terminal input helpers. |
| **[Pygments](https://pygments.org/)** | Syntax highlighting for code blocks and file previews rendered through Rich. |

## Backend

| | |
| --- | --- |
| **[Python 3.11+](https://www.python.org/)** | The agent loop is `asyncio`-based, so streaming, tool calls, and MCP connections run concurrently. |
| **[OpenAI SDK](https://github.com/openai/openai-python)** | The API client, pointed at OpenRouter's OpenAI-compatible endpoint for streaming and tool calling. |
| **[OpenRouter](https://openrouter.ai/)** | The model gateway. One login, any model, no per-vendor SDKs. |
| **[Pydantic](https://docs.pydantic.dev/)** | Config schemas, tool argument validation, and the JSON Schema sent to the model for each tool definition. |
| **[FastMCP](https://github.com/jlowin/fastmcp) / [MCP](https://modelcontextprotocol.io/)** | Connecting to external MCP servers and exposing their tools to the agent. |
| **[tiktoken](https://github.com/openai/tiktoken)** | Token counting that drives context pruning and compaction. |
| **[httpx](https://www.python-httpx.org/)** | Async HTTP for URL fetching and the OAuth token exchange. |
| **[ddgs](https://github.com/deedy5/ddgs)** | DuckDuckGo-backed web search. |
| **[Click](https://click.palletsprojects.com/)** | The `postal` CLI: flags, single-shot mode, and the `login` / `logout` subcommands. |
| **OAuth 2.0 + PKCE** | Browser login runs on a stdlib `http.server` loopback redirect, with the key stored locally. |
| **[platformdirs](https://github.com/tox-dev/platformdirs) + TOML** | Cross-platform config and credential paths, read with `tomllib`. |
| **[Docker](https://www.docker.com/)** | A `Dockerfile` and Compose file in [`docker/`](../docker/) for running the agent sandboxed. |

How these are wired together is covered in [Architecture](architecture.md).
