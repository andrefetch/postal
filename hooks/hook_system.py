import asyncio
import json
import os
import signal
import sys
import tempfile
from typing import Any
from config.config import Config, HookConfig, HookTrigger
from tools.base import ToolResult

class HookSystem:
    def __init__(self, config: Config):
        self.config = config
        self.hooks: list[HookConfig] = []
        if self.config.hooks_enabled:
            self.hooks = [hook for hook in self.config.hooks if hook.enabled]

    async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
        try:
            if hook.command:
                await self._run_command(hook.command, hook.timeout_sec, env)
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False
                ) as f:
                    f.write("#!/bin/bash\n")
                    f.write(hook.script)
                    script_path = f.name
                try:
                    os.chmod(script_path, 0o700)
                    await self._run_command(script_path, hook.timeout_sec, env)
                finally:
                    os.unlink(script_path)
        except Exception as e:
            print(e)

    async def _run_command(
        self,
        command: str,
        timeout: float,
        env: dict[str, str],
    ) -> None:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.cwd,
            env=env,
            start_new_session=True,
        )

        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            try:
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise

    def _build_env(
        self,
        trigger: HookTrigger,
        tool_name: str | None = None,
        user_message: str | None = None,
        error: Exception | None = None,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["AI_AGENT_TRIGGER"] = trigger.value
        env["AI_AGENT_CWD"] = str(self.config.cwd)

        if tool_name:
            env["AI_AGENT_TOOL_NAME"] = tool_name

        if user_message:
            env["AI_AGENT_USER_MESSAGE"] = user_message

        if error:
            env["AI_AGENT_ERROR"] = str(error)

        return env

    async def trigger_before_agent(self, user_message: str) -> None:
        env = self._build_env(
            HookTrigger.BEFORE_AGENT,
            user_message=user_message,
        )

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook, env)

    async def trigger_after_agent(
        self,
        user_message: str,
        agent_response: str,
    ) -> None:
        env = self._build_env(
            HookTrigger.AFTER_AGENT,
            user_message=user_message,
        )
        env["AI_AGENT_RESPONSE"] = agent_response

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT:
                await self._run_hook(hook, env)

    async def trigger_before_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> None:
        env = self._build_env(HookTrigger.BEFORE_TOOL, tool_name=tool_name)
        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL:
                await self._run_hook(hook, env)

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: ToolResult,
    ) -> None:
        env = self._build_env(HookTrigger.AFTER_TOOL, tool_name=tool_name)
        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        env["AI_AGENT_TOOL_RESULT"] = tool_result.to_model_output()

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL:
                await self._run_hook(hook, env)

    async def trigger_on_error(self, error: Exception) -> None:
        env = self._build_env(HookTrigger.ON_ERROR, error=error)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._run_hook(hook, env)
