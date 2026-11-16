from typing import Any

from pydantic import BaseModel, Field

from config import Config
from dataclasses import dataclass
from tools import Tool, ToolInvocation
from tools.base import ToolResult, ToolKind

class SubagentParams(BaseModel):
    goal: str = Field(
        ...,
        description='The specific task or goal for the subagent to accomplish or achieve.'
    )

@dataclass
class SubagentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600

class SubAgentTool(Tool):
    def __init__(self, config: Config, definition: SubagentDefinition):
        super().__init__(config)

        self.definition = definition
    
    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return self.definition.description

    schema = SubagentParams
    kind = ToolKind.SUBAGENT

    def is_mutating(self, params: dict[str, Any]) -> bool:
        # Delegation itself has no side effects. Every child tool is checked.
        return False

    def subagent_config(self) -> Config:
        config_dict = self.config.to_dict()
        config_dict['max_turns'] = self.definition.max_turns
        allowed = self.definition.allowed_tools
        if allowed is not None:
            controls = {'spawn_agent', 'wait_agents', 'list_agents', 'cancel_agent'}
            controls.update(f'subagent_{d.name}' for d in get_default_subagent_definitions())
            allowed = set(allowed) | controls
        if self.config.allowed_tools is not None:
            inherited = set(self.config.allowed_tools)
            allowed = inherited if allowed is None else allowed & inherited
        config_dict['allowed_tools'] = sorted(allowed) if allowed is not None else None
        config_dict['session'] = {'enabled': False}
        return Config(**config_dict)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        from agent.runtime import AgentRuntime

        params = SubagentParams(**invocation.params)
        runtime = invocation.runtime
        standalone = runtime is None
        if standalone:
            runtime = AgentRuntime(self.config, invocation.confirmation_callback)
            runtime.begin_turn(params.goal)
        parent_id = invocation.agent_id or runtime.root_id
        try:
            record = runtime.spawn(parent_id, self.config, self.definition, params.goal)
            await runtime.wait(parent_id, [record.agent_id])
            output = (
                f"Sub-agent '{record.name}' ({record.agent_id}): {record.status}\n\n"
                f"{record.result or record.error or 'No response'}"
            )
            if record.status != 'completed':
                return ToolResult.error_result(output)
            return ToolResult.success_result(output)
        except ValueError as exc:
            return ToolResult.error_result(str(exc))
        finally:
            if standalone:
                await runtime.cancel_descendants(parent_id)

CODEBASE_INVESTIGATOR = SubagentDefinition(

    name='codebase_investigator',
    description='Investigates the codebase to answer question about code structure, or is a pre-req for code review.',
    goal_prompt="""

    You are a codebase investigation specialist. Your job is soley to explore and understand code to answer questions.
    Use tools that can only read files, ex: read, grep, glob, and list_directories to investigation.
    I repeat, DO NOT modify any files.

    """,

    allowed_tools=[
        "read",
        "grep",
        "glob",
        "list_directories"
    ],

    max_turns=15
)

CODE_REVIEWER = SubagentDefinition(

    name = 'code_reviewer',
    description='Reviews code changes and provides feedback on quality, bugs and improvements upon the request of the user',
    goal_prompt="""

    You are a code review specialist. Your job is to review code and provide constructive feedback to the user. 
    Look for bugs, inconsistent or non-clean code, security vulnerabilities or issues, and improvement opportunities.
    Use read, list_directories and grep to examine the code.

    """,

    allowed_tools=[
        "read",
        "grep",
        "list_directories"
    ],

    max_turns=10,
    timeout_seconds=300

)

SOFTWARE_ARCHITECT = SubagentDefinition(

    name = 'software_architect',
    description="Changes code based on the user's prompt, provides clean and quality code and does not stray away from the codestyle written by the developer of the project.",

    goal_prompt="""

    You are a software architect. Your job is to maintain quality code in the codebase and write functional code. 
    Read before you write, implement code based on user's request.
    Especially, use the plan tool when tasks get complicated or long.
    You can give back feedback of code if necessary Tools that can be called and used are
    read, list_directories, grep, glob, write, edit, apply_patch, plan

    """,

    allowed_tools=[
        'read',
        'list_directories',
        'grep',
        'glob',
        'write',
        'edit',
        'apply_patch',
        'plan'
    ],

    max_turns=10
)

TEST_WRITER = SubagentDefinition(

    name = 'test_writer',
    description="Creates tests upon the user's request to make tests for their code. Make sure to test for edge cases and specific ways the code can error.",

    goal_prompt=""""

    You are a code test writer, your speciality is in writing tests for the user to put their code against edge cases, and special areas where their code
    can fail.

    Especially, use tools like plan to plan out multiple tests if neccessary, tools you can call are read, list_directories, grep, glob, write, edit, apply_patch, bash, and plan.

    """,

    allowed_tools=[
        'read',
        'list_directories',
        'grep',
        'glob',
        'write',
        'plan',
        'edit',
        'apply_patch',
        'bash'
    ],

    max_turns=10
)

DEBUGGER = SubagentDefinition(

    name = "debugger",
    description="You are a debugger, you help find errors or incosistencies in code then use tools like read, write, and edit to fix files.",
    goal_prompt="""

    You are a professional debugger. Your purpose in working with the user is to find bugs of any severity in the code.
    Use the plan tool when debugging gets complex or long.
    Use tools such as: grep, glob, write, edit, apply_patch, read, plan

    """,

    allowed_tools=[
        'grep',
        'glob',
        'write',
        'edit',
        'apply_patch',
        'read',
        'plan'
    ],

    max_turns=10

)

GENERAL = SubagentDefinition(
    name='general',
    description='Completes a delegated task using any tools permitted by its parent, including MCP and custom tools.',
    goal_prompt='Use the tools permitted by your parent to complete the task. Delegate independent subtasks when useful.',
)

# The general role inherits the parent tool set; specialized roles narrow it.

def get_default_subagent_definitions() -> list[SubagentDefinition]:
    return [
        GENERAL,
        CODEBASE_INVESTIGATOR,
        CODE_REVIEWER,
        SOFTWARE_ARCHITECT,
        TEST_WRITER,
        DEBUGGER,
    ]