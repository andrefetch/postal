# Tools

Everything the model can call. Which of these are available in a given run depends on `allowed_tools` (see [Configuration](configuration.md)); whether a call goes through without asking depends on the approval policy (see [Approvals](approvals.md)).

`/tools` lists what is active in the running session.

## Files

| Tool | What it does |
| --- | --- |
| `read` | Read a file, with long files truncated rather than blowing the context window. |
| `write` | Create a file or replace its contents outright. |
| `edit` | Replace an exact string in a file. The match must be unique unless `replace_all` is set, which is what makes edits surgical instead of approximate. |
| `apply_patch` | Batch creates, updates, deletes and renames across several files into one all-or-nothing call — if any operation fails, none are committed. |
| `grep` | Search file contents by pattern. |
| `glob` | Find files by glob pattern, `**` included. |
| `list_directories` | List what is in a directory. |

Every write shows a diff in the confirmation prompt before it happens.

## Bash

The `bash` tool runs commands in the working directory. The environment it runs in is filtered first: variables matching `exclude_patterns` (by default anything that looks like a key, token or secret) are stripped, and `set_vars` are injected. Dangerous commands are refused outright by the safety layer, whatever the approval policy says.

## Planning

The `plan` tool keeps a todo list across the agent loop, so a multi-step task has a visible spine — steps get marked off in the transcript as they complete.

## Network

| Tool | What it does |
| --- | --- |
| `search` | Web search, backed by DuckDuckGo. |
| `fetch` | Fetch a URL and hand its contents to the model. |

## Memory

The `memory` tool is key-value storage that survives across sessions, for things worth remembering beyond one conversation.

## Sub-agents

The main agent can delegate to a specialized sub-agent, each of which runs its own full agent loop with a narrowed tool set and its own turn cap. Sub-agent runs are never checkpointed — they belong to the turn that spawned them.

| Sub-agent | What it is for |
| --- | --- |
| `codebase_investigator` | Answers questions about code structure; usually the first step before a review. |
| `code_reviewer` | Reviews changes for quality, bugs and improvements. |
| `software_architect` | Writes code to a prompt while staying inside the project's existing style. |
| `test_writer` | Writes tests, edge cases included. |
| `debugger` | Tracks down errors and inconsistencies, then fixes them with `read`, `write` and `edit`. |

Approvals still route through you: a sub-agent's tool calls surface as confirmations in the parent session, so delegation never becomes a way around the policy.

## MCP

Postal connects to external [Model Context Protocol](https://modelcontextprotocol.io/) servers over stdio or HTTP/SSE and registers their tools alongside the built-in ones. Configure servers under `[mcp_servers.<name>]` and check them with `/mcp`.

MCP tools are always treated as mutating, because a third-party server's side effects cannot be inferred from its schema.

## Context handling

Two mechanisms keep long sessions alive, and neither is a tool the model calls — they run around the loop:

- **Pruning.** Old tool outputs are cleared once they pile up past the recent working set, reclaiming tokens without touching the conversation itself.
- **Compaction.** When the context window fills up, history is summarized into a continuation brief and the session resumes from it instead of erroring out.
