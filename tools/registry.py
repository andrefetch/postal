from config.config import Config
from hooks.hook_system import HookSystem
from safety.approval import ApprovalContext, ApprovalDecision, ApprovalManager
from tools.base import Tool
from typing import Any, Callable
from pathlib import Path
from tools.base import ToolResult, ToolInvocation
from tools.core import get_all_core_tools
import logging

from tools.subagents.subagents import SubAgentTool, get_default_subagent_definitions


logger = logging.getLogger(__name__)

class ToolRegistry:

    def __init__(self, config: Config):
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}
        self.config = config
    
    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool: {tool.name}")
        
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def register_mcp_tool(self, tool: Tool) -> None:

        self._mcp_tools[tool.name] = tool
        logger.debug(f"Registered MCP tool: {tool.name}")
   
    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        
        return False
    
    def get(self, name: str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        elif name in self._mcp_tools:
            return self._mcp_tools[name]
        
        return None
    
    def get_tools(self) -> list[Tool]:
        tools: list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)
        
        for mcp_tool in self._mcp_tools.values():
            tools.append(mcp_tool)

        if self.config.allowed_tools:
            allowed_set = set(self.config.allowed_tools)
            tools = [t for t in tools if t.name in allowed_set]

        return tools
    
    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]
    
    async def invoke(
            self,
            name: str,
            params: dict[str, Any],
            cwd: Path | None,
            hook_system: HookSystem,
            approval_manager: ApprovalManager | None = None,
            progress_callback: Callable[[str], None] | None = None,
        ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            result = ToolResult.error_result(
                f"Unknown Tool: {name}",
                metadata={
                    'tool_name': name
                },
            )

            await hook_system.trigger_after_tool(name, params, result)
            return result
        
        validation_errors = tool.validate_params(params)
        if validation_errors:
            result = ToolResult.error_result(
                f"Invalid parameters: {'; '.join(validation_errors)}",
                metadata={
                    'tool_name': name,
                    'validation_errors': validation_errors
                }
            )

            await hook_system.trigger_after_tool(name, params, result)
            return result

        await hook_system.trigger_before_tool(name, params)
        invocation = ToolInvocation(
            params=params,
            cwd=cwd,
            confirmation_callback=(
                approval_manager.confirmation_callback if approval_manager else None
            ),
            progress_callback=progress_callback,
        )
        if approval_manager:
            confirmation = await tool.get_confirmation(invocation)
            if confirmation:
                context = ApprovalContext(
                    tool_name=name,
                    params=params,
                    is_mutating=tool.is_mutating(params),
                    affected_paths=confirmation.affected_paths,
                    command=confirmation.command,
                    is_dangerous=confirmation.is_dangerous,
                )

                decision = await approval_manager.check_approval(context)
                if decision == ApprovalDecision.REJECTED:
                    result = ToolResult.error_result(
                        "Operation rejected"
                    )

                    await hook_system.trigger_after_tool(name, params, result)
                    return result

                elif decision == ApprovalDecision.NEEDS_CONFIRMATION:
                    approved = await approval_manager.request_confirmation(confirmation)

                    if not approved:
                        result = ToolResult.error_result(
                                "User rejected the operation"
                            )
                        await hook_system.trigger_after_tool(name, params, result)
                        return result
        try:
            result = await tool.execute(invocation)
        except Exception as e:
            logger.exception(f"Tool {name} raised unexpected error")
            result = ToolResult.error_result(
                f"Internal error: {(str(e))}",
                metadata = {
                    "tool_name": name
                }
            )
        await hook_system.trigger_after_tool(name, params, result)
        return result
        
def create_default_registry(config: Config) -> ToolRegistry:

    registry = ToolRegistry(config)
    
    for tool_class in get_all_core_tools():
        registry.register(tool_class(config))
    
    for subagent_def in get_default_subagent_definitions():
        registry.register(SubAgentTool(config, subagent_def))

    return registry