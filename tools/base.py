from __future__ import annotations
import abc
from pathlib import Path
from pydantic import BaseModel, ValidationError
from pydantic.json_schema import model_json_schema
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from config.config import Config

class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    BASH = "bash"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"
    GIT = "git"
    SUBAGENT = "subagent"

@dataclass
class FileDiff:
    path: Path
    old_content: str
    new_content: str

    is_new_file: bool = False
    is_deletion: bool = False

    def create_diff(self) -> str:

        import difflib

        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith('\n'):
            old_lines[-1] += '\n'
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        
        old_name = '/dev/null' if self.is_new_file else str(self.path)
        new_name = '/dev/null' if self.is_deletion else str(self.path)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name,
        )

        return "".join(diff)

@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # if files are long, we have to truncate.
    truncated: bool = False
    diff: FileDiff | None = None
    exit_code: int | None = None

    @classmethod
    def error_result(
        cls,
        error: str,
        output: str = "",
        **kwargs: Any
    ):
        return cls(
            success=False,
            output=output,
            error=error,
            **kwargs,
        )

    @classmethod
    def success_result(
        cls,
        output: str,
        **kwargs: Any
    ):
        return cls(
            success=True,
            output=output,
            error=None,
            **kwargs
        )
    
    def to_model_output(self) -> str:
        if self.success:
            return self.output

        return f"Error: {self.error}\n\nOutput:\n{self.output}"


@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str
    diff: FileDiff | None = None
    affected_paths: list[Path] = field(default_factory=list)
    command: str | None = None
    is_dangerous: bool = False

@dataclass
class ToolInvocation:
    params: dict[str, Any]
    cwd: Path
    # Parent session's confirmation callback, so tools that spawn nested
    # agents (subagents) keep routing approvals through the user.
    confirmation_callback: Callable[['ToolConfirmation'], Awaitable[bool]] | None = None
    progress_callback: Callable[[str], None] | None = None

    def report_progress(self, chunk: str) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(chunk)
        except Exception:
            pass

class Tool(abc.ABC):
    name: str = "base_tool"
    description: str = "Base tool"
    kind: ToolKind = ToolKind.READ

    def __init__(self, config: Config) -> None:
        self.config = config

    @property
    def schema(self) -> dict[str, Any] | type['BaseModel']:
        raise NotImplementedError("Error: Tool must defined a schema property or an attribute.")

    @abc.abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    loc = ".".join(str(x) for x in error.get("loc", []))
                    msg = error.get('msg', 'Validation Error')
                    errors.append(f"Parameter '{loc}': {msg}")

                return errors
            except Exception as e:
                return [str(e)]

        return []

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return self.kind in {ToolKind.WRITE, ToolKind.BASH, ToolKind.NETWORK, ToolKind.MEMORY}

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        if not self.is_mutating(invocation.params):
            return None

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Run {self.name}",
            affected_paths=self.affected_paths(invocation),
        )

    def affected_paths(self, invocation: ToolInvocation) -> list[Path]:
        path = invocation.params.get("path")
        if not isinstance(path, str) or not path:
            return []

        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = invocation.cwd / resolved

        return [resolved]

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            json_schema = model_json_schema(schema, mode='serialization')

            return {
                'name': self.name,
                'description': self.description,
                'parameters': {
                    'type': 'object',
                    'properties': json_schema.get('properties', {}),
                    'required': json_schema.get('required', [])
                }
            }
        if isinstance(schema, dict):
            result = {
                'name': self.name,
                'description': self.description,
            }

            if 'parameters' in schema:
                result['parameters'] = schema["parameters"]
            else:
                result["parameters"] = schema # type: ignore

            return result

        raise ValueError(f"Error: Invalid schema type for tool: {self.name}: {type(schema)}")