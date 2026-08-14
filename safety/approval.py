from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import shlex
from typing import Any, Awaitable, Callable

from config.config import ApprovalPolicy
from tools.base import ToolConfirmation

class ApprovalDecision(str, Enum):

    APPROVED = 'approved'
    REJECTED = 'rejected'
    NEEDS_CONFIRMATION = 'needs_confirmation'

@dataclass
class ApprovalContext:

    tool_name: str
    params: dict[str, Any]
    is_mutating: bool
    affected_paths: list[Path]
    command: str | None = None
    is_dangerous: bool = False

DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+(-rf?|--recursive)\s+[/~]",
    r"rm\s+-rf?\s+\*",
    r"rmdir\s+[/~]",
    # Disk operations
    r"dd\s+if=",
    r"mkfs",
    r"fdisk",
    r"parted",
    # System control
    r"shutdown",
    r"reboot",
    r"halt",
    r"poweroff",
    r"init\s+[06]",
    # Permission changes on root
    r"chmod\s+(-R\s+)?777\s+[/~]",
    r"chown\s+-R\s+.*\s+[/~]",
    # Network exposure
    r"nc\s+-l",
    r"netcat\s+-l",
    # Code execution from network
    r"curl\s+.*\|\s*(bash|sh)",
    r"wget\s+.*\|\s*(bash|sh)",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;",
]

# Patterns for safe commands (can be auto-approved)
SAFE_PATTERNS = [
    # Information commands
    r"^(ls|dir|pwd|cd|echo|cat|head|tail|less|more|wc)(\s|$)",
    r"^(locate|which|whereis|file|stat)(\s|$)",
    # Development tools (read-only)
    r"^git\s+(status|log|diff|show|branch|remote|tag)(\s|$)",
    r"^(npm|yarn|pnpm)\s+(list|ls|outdated)(\s|$)",
    r"^pip\s+(list|show|freeze)(\s|$)",
    r"^cargo\s+(tree|search)(\s|$)",
    # Text processing (read-only: sed, awk and find are left out because all three can write)
    r"^(grep|cut|sort|uniq|tr|diff|comm)(\s|$)",
    # System info
    r"^(date|cal|uptime|whoami|id|groups|hostname|uname)(\s|$)",
    r"^(env|printenv|set)$",
    # Process info
    r"^(ps|top|htop|pgrep)(\s|$)",
]

def is_dangerous_command(command: str) -> bool:

    for pattern in DANGEROUS_PATTERNS:
        if re.search(
            pattern,
            command,
            re.IGNORECASE
        ):
            return True
        
    return False

# Operators that chain one command into another. A compound command is only as
# safe as its least safe part, so each side is checked on its own.
COMMAND_SEPARATORS = {';', '&&', '||', '|'}

# Constructs that let a segment write, spawn or expand into something the safe
# pattern never saw: redirection, command substitution, subshells, background.
UNSAFE_CONSTRUCTS = ('>', '<', '$(', '`', '(', ')', '&', '{', '}')

def split_command_segments(command: str) -> list[str]:
    """Split a compound command on shell operators, leaving quoted text alone.

    Raises ValueError when the command cannot be tokenised, e.g. an unbalanced quote.
    """

    lexer = shlex.shlex(command, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True

    segments: list[str] = []
    current: list[str] = []

    for token in lexer:
        if token in COMMAND_SEPARATORS:
            segments.append(' '.join(current))
            current = []
            continue
        current.append(token)

    segments.append(' '.join(current))

    return [segment for segment in segments if segment]

def _is_safe_segment(segment: str) -> bool:

    if any(construct in segment for construct in UNSAFE_CONSTRUCTS):
        return False

    for pattern in SAFE_PATTERNS:
        if re.search(
            pattern,
            segment,
            re.IGNORECASE
        ):
            return True

    return False

def is_safe_command(command: str) -> bool:
    """A command is safe only when every segment of it is.

    Matching the whole string against the safe patterns anchored the check on the
    first word, so anything prefixed with a read-only command was auto-approved:
    `ls && rm -rf ./src` passed on the `ls`.
    """

    try:
        segments = split_command_segments(command)
    except ValueError:
        # Cannot be parsed, so it cannot be vouched for.
        return False

    if not segments:
        return False

    return all(_is_safe_segment(segment) for segment in segments)

class ApprovalManager:

    def __init__(
            self,
            approval_policy: ApprovalPolicy,
            cwd: Path,
            confimation_callback: Callable[[ToolConfirmation], Awaitable[bool]] | None = None
    ) -> None:

        self.approval_policy = approval_policy
        self.cwd = cwd
        self.confirmation_callback = confimation_callback

    def _assess_command_safety(self, command: str) -> ApprovalDecision:

        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalDecision.APPROVED
        
        if is_dangerous_command(command):
            return ApprovalDecision.REJECTED

        if self.approval_policy == ApprovalPolicy.NEVER:
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.REJECTED

        if self.approval_policy in {
            ApprovalPolicy.AUTO,
            ApprovalPolicy.ON_FAIL
        }:
            return ApprovalDecision.APPROVED

        if self.approval_policy == ApprovalPolicy.AUTO_EDIT:

            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.NEEDS_CONFIRMATION

        if is_safe_command(command):
            return ApprovalDecision.APPROVED

        return ApprovalDecision.NEEDS_CONFIRMATION

    async def check_approval(
            self,
            context: ApprovalContext
    ) -> ApprovalDecision:

        if not context.is_mutating:
            return ApprovalDecision.APPROVED

        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalDecision.APPROVED

        if context.command:
            return self._assess_command_safety(context.command)

        # Anything reaching outside the working directory is always confirmed,
        # no matter how permissive the policy is.
        outside_cwd = any(
            not path.is_relative_to(self.cwd) for path in context.affected_paths
        )
        if outside_cwd:
            if self.approval_policy == ApprovalPolicy.NEVER:
                return ApprovalDecision.REJECTED
            return ApprovalDecision.NEEDS_CONFIRMATION

        if self.approval_policy == ApprovalPolicy.NEVER:
            return ApprovalDecision.REJECTED

        if context.is_dangerous:
            return ApprovalDecision.NEEDS_CONFIRMATION

        if self.approval_policy in {
            ApprovalPolicy.AUTO,
            ApprovalPolicy.AUTO_EDIT,
            ApprovalPolicy.ON_FAIL,
        }:
            return ApprovalDecision.APPROVED

        return ApprovalDecision.NEEDS_CONFIRMATION

    async def request_confirmation(
            self,
            confirmation: ToolConfirmation,
    ) -> bool:

        if self.confirmation_callback:

            result = await self.confirmation_callback(confirmation)
            return result

        # No way to ask the user: fail closed instead of silently approving.
        return False