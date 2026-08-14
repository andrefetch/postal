# Configuration

## Where config lives

| Layer | Path | Notes |
| --- | --- | --- |
| User | `~/.config/postal/config.toml` | Cross-platform, resolved with `platformdirs` |
| Project | `.postal/config.toml` | Only read when the directory exists in the working directory |

The project file is merged over the user file, table by table, so a project can override `[model]` without restating `[session]`. Anything neither file sets falls back to the defaults below.

Two things are filled in for you when the config does not set them: `cwd` becomes the working directory Postal was started in, and `developer_instructions` is loaded from `AGENTS.md`.

## `AGENTS.md`

Postal walks up from the working directory to the repository root, collecting every `AGENTS.md` it finds, and hands them to the model as developer instructions. Files closer to the root come first, so a directory-level file gets the last word.

Setting `developer_instructions` in the config replaces that discovery entirely.

## Full example

```toml
# Top-level settings
approval = "on_request"         # "on_request", "auto_edit", "auto", "on_fail", "never", "yolo"
allowed_tools = ["read", "write"] # Optional: restrict the agent to these tools
developer_instructions = ""     # General instructions for the agent (overrides AGENTS.md when set)
user_instructions = ""          # Instructions for the user's specific preferences
debug = false                   # Enable debug logging
hooks_enabled = true            # Enable or disable hooks globally

[model]
name = "anthropic/claude-sonnet-4.5"
temperature = 1.0
context_window = 256000

[reasoning]
enabled = true     # ask the model to think (ignored by models that cannot)
effort = "medium"  # "minimal", "low", "medium", "high", or omit for the provider default
# max_tokens = 4000  # a thinking budget instead of an effort level
visible = true     # stream the thinking into the transcript

[session]
enabled = true       # save the conversation so it can be resumed
max_checkpoints = 20 # snapshots kept per session
max_sessions = 50    # sessions kept before the oldest are dropped

[bash_environment]
ignore_default_excludes = false
exclude_patterns = ["*KEY*", "*TOKEN*", "*SECRET*"] # Filters environment variables
set_vars = { MY_VAR = "value" }                     # Injects environment variables

# Connect to external tools via MCP (Model Context Protocol)
[mcp_servers.my_server]
enabled = true
startup_timeout = 10.0
command = "npx"             # For stdio servers
args = ["-y", "my-server"]
env = { API_KEY = "123" }
# url = "http://..."        # Alternatively, use a URL for HTTP/SSE servers
cwd = "/path/to/dir"

# Run commands or scripts at specific points in the agent lifecycle
[[hooks]]
name = "lint_check"
trigger = "after_tool"      # "before_agent", "after_agent", "before_tool", "after_tool", "on_error"
command = "npm run lint"
# script = "..."            # Alternatively, specify a bash script directly
timeout_sec = 30.0
enabled = true
```

## Reference

### Top level

| Key | Default | What it does |
| --- | --- | --- |
| `approval` | `"on_request"` | The approval policy. See [Approvals](approvals.md). |
| `allowed_tools` | unset | If set, the agent and its sub-agents only see these tools. |
| `developer_instructions` | from `AGENTS.md` | Project instructions handed to the model. |
| `user_instructions` | unset | Your personal preferences, sent alongside the above. |
| `hooks_enabled` | `true` | Master switch for every hook. |
| `max_turns` | `100` | Tool-calling rounds before one run gives up. |
| `max_tool_output_tokens` | `50000` | Ceiling on how much of a tool's output reaches the model. |
| `debug` | `false` | Debug logging. |

### `[model]`

| Key | Default | What it does |
| --- | --- | --- |
| `name` | unset | Any OpenRouter model slug, e.g. `anthropic/claude-sonnet-4.5`. `/model` changes it mid-session and writes it back to the config. |
| `temperature` | `1.0` | Clamped to 0.0–2.0. |
| `context_window` | `256000` | What Postal assumes the window is, which is what pruning and compaction budget against. |

### `[reasoning]`

| Key | Default | What it does |
| --- | --- | --- |
| `enabled` | `true` | Ask the model to think. Models without reasoning ignore it. |
| `effort` | unset | `"minimal"`, `"low"`, `"medium"` or `"high"`. |
| `max_tokens` | unset | A thinking budget instead of an effort level. |
| `visible` | `true` | Stream the thinking into the transcript. |

`effort` and `max_tokens` are mutually exclusive — OpenRouter takes one or the other, and a budget wins if both are set. `/thinking` retunes all of this without leaving the session.

### `[session]`

| Key | Default | What it does |
| --- | --- | --- |
| `enabled` | `true` | Write conversations to disk. `false` keeps everything in memory. |
| `max_checkpoints` | `20` | Snapshots kept per session before the oldest autosaves are trimmed. |
| `max_sessions` | `50` | Sessions kept before the oldest are dropped. |

See [Sessions](sessions.md) for what a checkpoint actually holds.

### `[bash_environment]`

Controls the environment the `bash` tool runs commands in. The old table name
`[shell_environment]` is still accepted for existing config files.

| Key | Default | What it does |
| --- | --- | --- |
| `exclude_patterns` | `["*KEY*", "*TOKEN*", "*SECRET*"]` | Glob patterns for environment variables to strip before running a command. |
| `ignore_default_excludes` | `false` | Keep the default patterns out of the way and use only yours. |
| `set_vars` | `{}` | Extra variables injected into every command. |

### `[mcp_servers.<name>]`

One table per server. Each needs **either** `command` (stdio) **or** `url` (HTTP/SSE) — setting both, or neither, is a config error.

| Key | Default | What it does |
| --- | --- | --- |
| `enabled` | `true` | Whether to connect at startup. |
| `command` | unset | Executable for a stdio server. |
| `args` | `[]` | Arguments for that executable. |
| `env` | `{}` | Environment for the server process. |
| `cwd` | unset | Working directory for the server process. |
| `url` | unset | Endpoint for an HTTP or SSE server. |
| `startup_timeout` | `10.0` | Seconds to wait for the server to come up. |

Tools from every connected server are registered under the agent's tool set; `/mcp` shows their status.

### `[[hooks]]`

An array of tables, one per hook. Each needs either `command` or `script`.

| Key | Default | What it does |
| --- | --- | --- |
| `name` | required | How the hook shows up in output. |
| `trigger` | required | `before_agent`, `after_agent`, `before_tool`, `after_tool` or `on_error`. |
| `command` | unset | A command to run. |
| `script` | unset | A bash script to run instead. |
| `timeout_sec` | `30.0` | Seconds before the hook is killed. |
| `enabled` | `true` | Turn one hook off without deleting it. |

## Credentials and environment

| Variable | What it does |
| --- | --- |
| `API_KEY` | Overrides the key saved by `postal login`. |
| `BASE_URL` | Overrides the saved API base URL. |

Both take precedence over what is on disk, so nothing needs to be written to a file to run in CI.
