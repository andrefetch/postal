from typing import TYPE_CHECKING

from prompts.agents_md import get_agents_md_section
from prompts.environment import get_environment_section
from prompts.identity import get_identity_section
from prompts.skills import get_skills_section
from prompts.instructions import (
    get_developer_instructions_section,
    get_memory_section,
    get_user_instructions_section,
)
from prompts.operational import get_operational_section
from prompts.security import get_security_section
from prompts.tool_guidelines import get_tool_guidelines_section

if TYPE_CHECKING:
    from config.config import Config
    from tools.base import Tool


def get_system_prompt(

        config: "Config",
        user_memory: str | None = None,
        tools: list["Tool"] | None = None

    ) -> str:

    parts = []

    # Identity and role
    parts.append(get_identity_section())
    # Environment

    # AGENTS.md spec
    parts.append(get_agents_md_section())

    # Security guidelines
    parts.append(get_security_section())

    # SKILLS.md spec
    parts.append(get_skills_section());

    # env section, for win data, mac and linux for shell command usage.
    parts.append(get_environment_section(config))

    if tools:
        parts.append(get_tool_guidelines_section(tools))

    if config.developer_instructions:
        parts.append(get_developer_instructions_section(config.developer_instructions))

    if config.user_instructions:
        parts.append(get_user_instructions_section(config.user_instructions))

    if user_memory:
        parts.append(get_memory_section(user_memory))


    # Operational guidelines
    parts.append(get_operational_section())

    return "\n\n".join(parts)
