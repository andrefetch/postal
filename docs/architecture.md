# Architecture

Postal is an object-oriented codebase. The agent loop, the tool layer, the safety layer and the terminal UI are separate classes with a single responsibility each, wired together at startup rather than resolved through module-level globals. This is what keeps the project extensible: adding a tool or a sub-agent requires implementing one class and registering it, not threading a new branch through the loop.

## Packages

| Package | What lives there |
| --- | --- |
| `agent/` | `Agent` (the loop), `Session` (all state owned by one conversation), `AgentEvent`, `SessionStore` |
| `tools/` | The `Tool` base class, `ToolRegistry`, and every concrete tool: core, network, memory, MCP, sub-agents |
| `client/` | `LLMClient` and the streaming response types |
| `context/` | `ContextManager`, `ChatCompactor`, `LoopDetector` |
| `safety/` | `ApprovalManager` and the approval policy types |
| `config/` | Pydantic config models and the TOML loader |
| `hooks/` | `HookSystem`, which executes lifecycle hooks |
| `ui/` | `TUI`, `Repl`, the slash command groups, and the render components |

## One abstract base class, every tool

Every model-callable operation is a subclass of `Tool` (`tools/base.py`), an `abc.ABC` that declares `execute` abstract and provides a concrete default for everything else. A tool is therefore a class attribute block plus one method:

```python
class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern"
    kind = ToolKind.READ
    schema = GlobParams          # a pydantic BaseModel

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        ...
```

The base class supplies the remaining behaviour to every subclass: `validate_params` runs the Pydantic model, `to_openai_schema` compiles the same model into the JSON Schema sent to the API, `is_mutating` derives from `kind` whether the approval layer is invoked, and `get_confirmation` constructs the prompt presented to the user.

Subclasses override only where their behaviour genuinely diverges, which is the reason the base is concrete rather than abstract throughout:

- `EditTool` and `WriteFileTool` override `get_confirmation` to attach a `FileDiff`, so the confirmation displays the exact patch rather than a generic "run edit".
- `MCPTool` overrides `is_mutating` to return `True` unconditionally, since the side effects of a third-party server cannot be determined statically.
- `SubAgentTool` promotes `name` and `description` to properties, because both are derived from the `SubagentDefinition` passed to `__init__`. A single class backs all five sub-agents.
- `ApplyPatchTool` confines its multi-file staging to a private `_WorkingTree` helper, giving all-or-nothing semantics: a patch either commits every operation or none.

Because the loop is typed against the base class only, it never branches on the concrete tool type. `ToolRegistry` stores tools behind private `_tools` and `_mcp_tools` dictionaries and returns `Tool` instances; the agent calls `execute` and relies on dynamic dispatch.

## Composition over deep hierarchies

Inheritance is one level deep almost everywhere. Structure is expressed through object ownership instead:

- **`Session` is the composition root.** It constructs and owns the `LLMClient`, `ToolRegistry`, `ContextManager`, `ApprovalManager`, `HookSystem`, `MCPManager`, `ChatCompactor`, `LoopDetector` and `SessionStore` for one conversation.
- **`Agent` holds a `Session`** and drives it. The loop body reads as orchestration (prune, compact, stream, dispatch, checkpoint) because each of those operations is delegated to a collaborator.
- **Sub-agents are a consequence of the same structure.** `SubAgentTool.execute` builds a narrowed `Config` (a reduced tool set, its own turn cap, checkpointing disabled) and constructs a full `Agent` from it. Nesting requires no additional machinery: it is the same class, composed again.

The slash commands are the single deliberate use of multiple inheritance. `HelpCommands`, `SettingsCommands`, `SessionCommands` and `InspectCommands` each extend a shared `CommandGroup`, and `SlashCommands` mixes all four so that every group observes the same console, config, and last-printed listings. That shared state is what allows `/rewind 1` to resolve against the index `/checkpoints` last printed.

## Value objects, named constructors, closed sets

Data crossing a layer boundary is a dataclass, not a dict:

| Type | Role |
| --- | --- |
| `ToolResult` | Returned by every tool. Constructed through the `success_result` / `error_result` classmethod factories, and serialized for the model via `to_model_output`. |
| `FileDiff` | Old and new content for one path, with `create_diff()` colocated with the data it formats. |
| `ToolConfirmation` | The input the approval layer requires to prompt the user, including the diff and affected paths. |
| `AgentEvent` | One classmethod per event type (`AgentEvent.agent_start`, `.reasoning_delta`, …), so the loop never assembles event payloads inline. |
| `Checkpoint`, `SessionMeta`, `SessionRecord` | The on-disk session format, serialized by `SessionStore`. |

Any type with a fixed value set is a `str`-backed `Enum` (`ToolKind`, `ApprovalDecision`, `AgentEventType`, `StreamEventType`, `PatchAction`, `MCPServerStatus`), which makes it exhaustive at the type level while remaining readable in serialized JSON.

Configuration is a tree of Pydantic models (`ModelConfig`, `ReasoningConfig`, `SessionConfig`, `BashEnvironmentConfig`, `MCPServerConfig`, `HookConfig`) that carry field-level validation and class-level behaviour: `ReasoningConfig.to_request_payload()` encapsulates the mutually exclusive effort-or-budget rule that OpenRouter enforces, so no caller has to reimplement it.

Errors form a single hierarchy rooted at `AgentError`, which carries a message, structured `details`, and the underlying `cause`, and serializes through `to_dict()`. `ConfigError` extends it with the offending key and file.

## The UI splits state from rendering

`ui/components/` contains one module per visual element (spinner, gutter, markdown, tool calls, confirmations, plans, thinking, usage, transcript), and the split within them is deliberate. Anything that carries state across frames is a class: `Spinner` owns its frame counter, `MarkdownStream` owns the partial-line buffer that permits markdown to render while it is still arriving, and `Gutter` wraps a renderable so it can be drawn indented beneath a bar. Everything else is a pure function from a value object to a Rich renderable. That is why `tool_call.py` can dispatch on tool kind (`_read`, `_bash`, `_patch`, …) over a single `ToolOutcome` dataclass rather than subclassing a renderer per tool.

`Gutter` implements Rich's rendering protocol directly: `__rich_console__` yields the bar and the indented body segment by segment, so it nests inside any other renderable exactly as a built-in Rich object does.

## Adding a tool

The structure of the codebase reduces this to a two-step change:

1. Write a `BaseModel` for the parameters and a `Tool` subclass declaring `name`, `description`, `kind`, `schema` and `execute`.
2. Register it in `tools/registry.py`.

The schema exposed to the model, the argument validation, and the approval behaviour all follow from those declarations. [CONTRIBUTING.md](../CONTRIBUTING.md) documents the remainder of the workflow.
