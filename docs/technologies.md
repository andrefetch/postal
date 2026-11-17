# Technologies

What Postal is built on, and what each piece is actually doing.

## Frontend

| | |
| --- | --- |
| **[Ink](https://github.com/vadimdemedes/ink)** | The full-screen interactive terminal. Ink renders React to the terminal, which gives the TUI a declarative layout and a component model. |
| **[React](https://react.dev/)** | The UI runtime behind Ink: state, effects, and a pure reducer (`ui/terminal/src/state.ts`) that turns backend events into screen state. |
| **[TypeScript](https://www.typescriptlang.org/)** | The whole frontend, type-checked against the JSON-lines protocol shared with Python. |
| **[esbuild](https://esbuild.github.io/)** | Bundles the app into the single `ui/terminal_bundle/postal.mjs` file that ships in the package, so users need Node but not npm. |
| **[marked](https://github.com/markedjs/marked) + [marked-terminal](https://github.com/mikaelbr/marked-terminal)** | Markdown rendering for assistant replies and tool output. |
| **[wrap-ansi](https://github.com/chalk/wrap-ansi) / [string-width](https://github.com/sindresorhus/string-width)** | Grapheme- and width-aware wrapping so wide characters and emoji do not break the layout. |
| **[Rich](https://github.com/Textualize/rich)** | Slash-command output and the streaming renderer for single-shot runs, plus the shared render components. |
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
| **[Node.js 22+](https://nodejs.org/)** | The runtime that executes the bundled TypeScript TUI. The npm dependencies are bundled ahead of time; users only need `node` on `PATH`. |
| **OAuth 2.0 + PKCE** | Browser login runs on a stdlib `http.server` loopback redirect, with the key stored locally. |
| **[platformdirs](https://github.com/tox-dev/platformdirs) + TOML** | Cross-platform config and credential paths, read with `tomllib`. |
| **[Docker](https://www.docker.com/)** | A `Dockerfile` and Compose file in [`docker/`](../docker/) for running the agent sandboxed. |

How these are wired together is covered in [Architecture](architecture.md).
