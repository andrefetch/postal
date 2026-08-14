from __future__ import annotations
from enum import Enum
import os
from pathlib import Path
from typing import Any, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from config.credentials import load_credentials

class ModelConfig(BaseModel):

    name: str = ''
    
    temperature: float = Field(
        default=1, 
        ge=0.0, 
        le=2.0
    ) # clarity of the model

    context_window: int = 256_000

class ReasoningConfig(BaseModel):
    """How much the model thinks, and whether that thinking is shown."""

    enabled: bool = True

    # OpenRouter takes either an effort level or a token budget, never both.
    effort: Literal["minimal", "low", "medium", "high"] | None = None
    max_tokens: int | None = Field(default=None, gt=0)

    # Off means the model still reasons, we just do not render it.
    visible: bool = True

    def to_request_payload(self) -> dict[str, Any] | None:
        """The `reasoning` body OpenRouter expects, or None to leave it alone."""

        if not self.enabled:
            return None
        if self.max_tokens is not None:
            return {"max_tokens": self.max_tokens}
        if self.effort is not None:
            return {"effort": self.effort}
        return {"enabled": True}


class SessionConfig(BaseModel):
    """Saving the conversation to disk so it can be resumed later."""

    enabled: bool = True

    # Checkpoints are full transcripts, so the cap is what keeps a long
    # session from growing without bound on disk.
    max_checkpoints: int = Field(default=20, ge=1)

    # Oldest sessions are dropped once there are more than this many.
    max_sessions: int = Field(default=50, ge=1)


class BashEnvironmentConfig(BaseModel):
    ignore_default_excludes: bool = False # for filtering keys, secrets
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)

class MCPServerConfig(BaseModel):

    enabled: bool = True
    startup_timeout: float = 10

    # standard input transport
    command: str | None = None

    args: list[str] = Field(
        default_factory=list
    )

    env: dict[str, str] = Field(
        default_factory=dict
    )

    cwd: Path | None = None

    # Http/ sse transports
    url: str | None = None

    @model_validator(
        mode='after'
    )
    def validate_transport(self) -> MCPServerConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(
                "MCP Servers must have either 'command' (stdio) or 'url' (http/sse)"
            )
        
        if has_command and has_url:
            raise ValueError(
                "MCP servers can't have both command and URL"
            )

        return self

class ApprovalPolicy(str, Enum):

    ON_REQUEST = "on_request"
    ON_FAIL = "on_fail"
    AUTO = "auto"
    AUTO_EDIT = "auto_edit"
    NEVER = "never"
    YOLO = "yolo" # You only live once!

    @property
    def label(self) -> str:
        return _APPROVAL_LABELS[self][0]

    @property
    def summary(self) -> str:
        return _APPROVAL_LABELS[self][1]

    @property
    def risk(self) -> str:
        """How loud the UI should be about this policy: normal, warn or danger."""
        if self is ApprovalPolicy.YOLO:
            return "danger"
        if self in {ApprovalPolicy.AUTO, ApprovalPolicy.ON_FAIL}:
            return "warn"
        return "normal"


_APPROVAL_LABELS: dict[ApprovalPolicy, tuple[str, str]] = {
    ApprovalPolicy.ON_REQUEST: ("ask", "confirm every mutating tool"),
    ApprovalPolicy.ON_FAIL: ("on fail", "run freely, ask only after a failure"),
    ApprovalPolicy.AUTO: ("auto", "run everything except dangerous commands"),
    ApprovalPolicy.AUTO_EDIT: ("auto-edit", "edit freely, confirm bash commands"),
    ApprovalPolicy.NEVER: ("read-only", "reject anything that is not known safe"),
    ApprovalPolicy.YOLO: ("yolo", "approve everything, including dangerous commands"),
}

class HookTrigger(str, Enum):

    BEFORE_AGENT = 'before_agent'
    AFTER_AGENT = 'after_agent'
    BEFORE_TOOL = 'before_tool'
    AFTER_TOOL = 'after_tool'
    ON_ERROR = 'on_error'

class HookConfig(BaseModel):

    name: str
    trigger: HookTrigger
    command: str | None = None
    script: str | None = None
    timeout_sec: float = 30
    enabled: bool = True

    @model_validator(mode='after')
    def validate_hook(self) -> HookConfig:

        if not self.command and not self.script:
            raise ValueError("Hook must either have a command or a script.")
        return self

class Config(BaseModel):

    # `shell_environment` is the pre-rename spelling; configs on disk still
    # carry it, so it stays accepted as an alias for `bash_environment`.
    model_config = ConfigDict(populate_by_name=True)

    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)
    bash_environment: BashEnvironmentConfig = Field(
        default_factory=BashEnvironmentConfig,
        validation_alias=AliasChoices("bash_environment", "shell_environment"),
    )

    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)

    session: SessionConfig = Field(default_factory=SessionConfig)

    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST

    allowed_tools: list[str] | None = Field(
        None,
        description='If set, only these tools will be available to the agent or subagents.'
    )

    hooks_enabled: bool = True
    hooks: list[HookConfig] = Field(default_factory=list)

    max_turns: int = 100
    mcp_servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict
    )
    max_tool_output_tokens: int = 50_000

    developer_instructions: str | None = None
    user_instructions: str | None = None
    debug: bool = False

    @property
    def api_key(self) -> str | None:
        # Env var wins (handy for CI / one-off overrides); otherwise fall
        # back to whatever `postal login` saved.
        return os.environ.get("API_KEY") or load_credentials().get("api_key")

    @property
    def base_url(self) -> str | None:
        return os.environ.get("BASE_URL") or load_credentials().get("base_url")
    
    @property
    def model_name(self) -> str:
        return self.model.name
    
    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        self.model.temperature = value
    
    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.api_key:
            errors.append("No API key was found. Solution: run `postal login` (or set the API_KEY environment variable)")
        
        if not self.cwd.exists():
            errors.append(f"Working directory does not exist: {self.cwd}")
        
        return errors
    
    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(
            mode='json'
        )