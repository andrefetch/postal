<h1 align='center'>
  Postal
</h1>

<p align="center">
  <b>An open-source AI coding agent that lives in your terminal.</b><br />
  Plans, edits, runs, and reviews code with any model on OpenRouter.
</p>

<p align="center">
  <a href="https://github.com/andrefetch/postal/stargazers"><img src="https://img.shields.io/github/stars/andrefetch/postal?style=for-the-badge&logo=github&logoColor=white&color=181717" alt="GitHub stars" /></a>
  <a href="https://github.com/andrefetch/postal/network/members"><img src="https://img.shields.io/github/forks/andrefetch/postal?style=for-the-badge&logo=github&logoColor=white&color=181717" alt="GitHub forks" /></a>
  <a href="https://github.com/andrefetch/postal/issues"><img src="https://img.shields.io/github/issues/andrefetch/postal?style=for-the-badge&logo=github&logoColor=white&color=181717" alt="GitHub issues" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/PYTHON-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/OPENROUTER-1a1a1a?style=for-the-badge&logoColor=white" alt="OpenRouter" />
  <img src="https://img.shields.io/badge/OPENAI%20SDK-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI SDK" />
  <img src="https://img.shields.io/badge/MCP-000000?style=for-the-badge&logo=modelcontextprotocol&logoColor=white" alt="Model Context Protocol" />
  <img src="https://img.shields.io/badge/PYDANTIC-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic" />
  <br />
  <img src="https://img.shields.io/badge/RICH-2b2b2b?style=for-the-badge&logoColor=white" alt="Rich" />
  <img src="https://img.shields.io/badge/CLICK-d1d1d1?style=for-the-badge&logoColor=black" alt="Click" />
  <img src="https://img.shields.io/badge/DOCKER-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

<p align="center">
  <img src="assets/postalnewdemo.gif" alt="Postal planning and executing a multi-step task in the terminal" width="100%" />
</p>

Postal connects to LLMs through OpenRouter, reads and edits your code with a built-in tool set, runs shell commands, delegates to specialized sub-agents, and streams everything through a full-screen TUI. Every mutating action goes through an approval policy you control, so it is as autonomous or as careful as you want it to be.

## Quickstart ↴

Two commands and you are talking to an agent in your own repo:

```bash
pip install postalcli
postal login    # opens your browser to authorize with OpenRouter
postal          # start the interactive TUI
```

More ways to run it:

```bash
postal "your prompt"     # single-shot mode, great for scripting
postal --cwd /path       # run against a different working directory
postal --continue        # pick up the last session in this directory
postal --resume 3f2a1c   # resume a specific session by id
postal sessions          # list saved sessions
```

Configuration lives in `~/.config/postal/config.toml`, with per-project overrides in `.postal/config.toml`, and `AGENTS.md` is picked up automatically.

Full [CLI reference](docs/cli.md) | [configuration reference](docs/configuration.md)

## Documentation

| Page | What it covers |
| --- | --- |
| [CLI reference](docs/cli.md) | Installing, logging in, every command and flag |
| [Configuration](docs/configuration.md) | `config.toml`, per-project overrides, `AGENTS.md`, every option |
| [Tools](docs/tools.md) | The built-in tool set, sub-agents, MCP servers |
| [Approvals](docs/approvals.md) | The six approval policies and the rules that override them |
| [Sessions](docs/sessions.md) | Saving, resuming, checkpointing and rewinding conversations |
| [Slash commands](docs/slash-commands.md) | Everything you can type after a `/` inside the TUI |
| [Architecture](docs/architecture.md) | How the codebase is put together, class by class |
| [Technologies](docs/technologies.md) | The libraries Postal is built on and what each one does |

## Why Postal?

- **Bring any model.** OpenRouter as the backend means versatility. One login gives you large models Claude, OpenAI, Deepseek, Kimi, and even access to smaller free models.
- **Safety is a first-class feature.** Six approval policies, dangerous-command rejection, and confirmation for anything outside the working directory. You choose the risk level, not the agent. See [Approvals](docs/approvals.md).
- **It survives long sessions.** Context pruning reclaims tokens from stale tool output, and when the window fills up, Postal compacts history into a continuation brief and keeps going instead of erroring out.
- **Nothing is lost when you close the terminal.** Sessions are checkpointed after every turn, so `postal --continue` puts you back exactly where you were, and `/rewind` walks the conversation back to any earlier checkpoint. See [Sessions](docs/sessions.md).
- **Configurable by design.** A readable, object-oriented Python codebase built on Rich, Click, and Pydantic. Every tool is one class behind a shared abstract base, so adding a tool or a sub-agent is a small, well-marked change. See [Architecture](docs/architecture.md).
- **Component-based UI design.** Postal uses a modular, component-based UI system with separate components for every visual element (spinners, gutters, markdown rendering, tool displays, confirmations, etc.), making it easy to maintain, customize, and extend the interface.

## What it can do

| | |
| --- | --- |
| **Files** | `read`, `write`, `edit`, `apply_patch`, `grep`, `glob`, and `list_directories` for working with a codebase. `apply_patch` batches creates, updates, deletes and renames across several files into one all-or-nothing call. |
| **Bash** | The `bash` tool executes commands in the working directory. Automatically detects your OS to know what shell commands to execute. |
| **Planning** | A `plan` tool tracks steps (a to do list) across the agent loop. |
| **Network and memory** | Web search via DuckDuckGo, URL fetching, and key-value storage that survives across sessions. |
| **Sub-agents** | Specialized agents the main agent can delegate to: `codebase_investigator`, `code_reviewer`, `software_architect`, `test_writer`, `debugger`. |
| **MCP** | Connects to external MCP servers for additional tools and data sources. |
| **Interactive TUI** | Full-screen terminal interface built on Rich, with streaming responses, live tool call output, visible model reasoning, and token usage tracking. |
| **Single-shot mode** | Pass a prompt as an argument for non-interactive runs, suitable for scripting. |

## Slash commands

| Command | What it does |
| --- | --- |
| `/help` | Show all commands |
| `/model <name>` | Switch models mid-session |
| `/approval <mode>` | Switch the approval policy mid-session |
| `/thinking [on\|off\|low\|medium\|high]` | Show, hide, or retune the model's reasoning |
| `/clear` | Start a fresh conversation (the old one stays saved) |
| `/config` | Show the active configuration |
| `/stats` | Session statistics: tokens, elapsed time, tool calls |
| `/tools` | List available tools |
| `/mcp` | Show MCP server status |
| `/sessions [all]` | List saved sessions, newest first |
| `/sessions rm <n\|id>` | Delete a saved session |
| `/resume <n\|id>` | Load a saved session into the current one |
| `/checkpoint [label]` | Save a checkpoint now, with an optional name |
| `/checkpoints` | List the checkpoints in this session |
| `/rewind <n\|id>` | Roll the conversation back to a checkpoint |
| `/exit`, `/quit` | Leave the agent |

Commands autocomplete as you type: hitting `/` lists every command, the list narrows as you keep typing, and `↑`/`↓` select while `Enter` runs the highlighted one (`Tab` fills it in if you want to add arguments first).

## Sessions

Postal writes the conversation to disk after every turn, so closing the terminal does not kill your conversation. All conversations are resumable and can be accessed by running a command shown below.

```bash
postal --continue        # resume the most recent session in this directory
postal --resume 3f2a1c   # resume a specific session (a prefix of the id is enough)
postal sessions          # what is saved for this directory
postal sessions --all    # every directory
postal sessions rm 3f2a1c
```

Inside the TUI, `/sessions` lists what is saved and `/resume` loads one into the running agent, transcript and token totals included. The system prompt is not restored: it is rebuilt from the current config and tool set, so a resumed session picks up any model, approval, or `AGENTS.md` changes you have made since.

### Checkpoints

Each save is a checkpoint, a full snapshot of the conversation at that point. Turns are checkpointed automatically, and `/checkpoint <label>` marks one by hand before you try something risky:

```text
❯ /checkpoint before the refactor
Saved before the refactor · 24 messages · session 3f2a1c8b

❯ /checkpoints
1  a41f9c02  turn 3                 18 msgs  22m ago
2  7d2b1e55  turn 4                 24 msgs  4m ago
3  e0c34a91  before the refactor    24 msgs  just now

❯ /rewind 1
Rewound to turn 3 · 18 messages · turn 3
```

Rewinding replaces the conversation the model sees, which makes it the way out of a turn that went sideways: roll back to before the detour and take another run at it. **It only rewinds the conversation, not your files** — anything already written to disk stays written.

Sessions live in `~/.config/postal/sessions/<id>/`, one directory per session, with the transcripts in a JSONL file next to a small `meta.json`. Old checkpoints are trimmed once a session passes `max_checkpoints` (autosaves go first, named ones are kept), and the oldest sessions are dropped past `max_sessions`. Set `enabled = false` under `[session]` to keep conversations off disk entirely.

## Approvals

Before Postal runs anything that changes state, the approval policy decides whether it goes ahead, asks you, or is refused outright. Read-only tools (`read`, `grep`, `glob`, `list_directories`, `plan`) never prompt, so a policy only affects writes, bash commands, network calls, memory writes, MCP tools, and sub-agent runs.

| Value | Badge | Behaviour |
| --- | --- | --- |
| `on_request` *(default)* | `ask` | Confirm every mutating tool call. Commands matched as known-safe (`ls`, `git status`, `grep`, …) run without asking. |
| `auto_edit` | `auto-edit` | File edits and writes inside the working directory go through unprompted; bash commands still need confirmation unless known-safe. |
| `auto` | `auto` | Everything runs except dangerous commands, which are rejected. |
| `on_fail` | `on fail` | Currently identical to `auto`. Reserved for prompting after a failed tool call, which is not implemented yet. |
| `never` | `read-only` | Rejects anything that isn't a known-safe command. Nothing gets written, and you are never prompted. |
| `yolo` | `yolo` | Approves everything, including commands matched as dangerous. Only use this in a sandbox or container. |

Two rules apply on top of the policy, and no policy except `yolo` overrides them:

- **Dangerous commands are rejected.** `rm -rf /`, `dd if=`, `mkfs`, `shutdown`, `curl … | bash`, fork bombs, and similar patterns are refused before bash ever sees them (the full list is `DANGEROUS_PATTERNS` in `safety/approval.py`).
- **Anything touching a path outside the working directory is confirmed**, however permissive the policy is (`never` rejects it instead).

## Roadmap

Currently being worked on:

- **Skill Integration** - allows users to import skills and use with their favorite model.
- **Git Integration** - allows users to use git commands with postal.
- **More assets** - Logo, banner, etc

Have an idea? [Open an issue](https://github.com/andrefetch/postal/issues), feature discussions are very welcome.

## Contributing

Contributions of every size are appreciated, from typo fixes to new tools and sub-agents. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started, and check the [open issues](https://github.com/andrefetch/postal/issues) for something to pick up!

If Postal is useful to you, **a star on the repo genuinely helps** the project reach more developers. ⭐

## License

[GNU GENERAL PUBLIC LICENSE v3.0](LICENSE)
