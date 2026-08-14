import asyncio
import codecs
import os
import fnmatch
from pathlib import Path
import signal
import sys

from pydantic import BaseModel, Field

from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult

DANGEROUS_COMMANDS = {
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    "sleep",
}

class BashParams(BaseModel):

    command: str = Field(
        ...,
        description='The bash command used to execute system commands',
    )

    timeout: int = Field(
        120,
        ge=1,
        le=600,
        description='Timeout in seconds (defaulted: 120s)'
    )

    cwd: str | None = Field(
        None,
        description='The working directory for the command to be ran'
    )

class BashTool(Tool):

    name = 'bash'
    kind = ToolKind.BASH
    description = "Execute a bash command. Use this for running system wide commands, scripts and usage of CLI Tools."

    schema = BashParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation:
        params = BashParams(**invocation.params)

        command = params.command.lower().strip()
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in command:
                return ToolConfirmation(
                    tool_name=self.name,
                    params=invocation.params,
                    description=f"Execute (DANGEROUS): {params.command}",
                    command=params.command,
                    is_dangerous=True,
                )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute: {params.command}",
            command=params.command,
            is_dangerous=False,
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = BashParams(**invocation.params)

        command = params.command.lower().strip()
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in command:
                return ToolResult.error_result(
                    f'Command blocked: {params.command}',
                    metadata = {
                        'blocked': True
                    }
                )
        
        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd / cwd
        else:
            cwd = invocation.cwd
        
        if not cwd.exists():
            return ToolResult.error_result(
                f"Working directory doesn't exist: {cwd}"
            )
        
        env = self._build_environment()
        if sys.platform == 'win32':
            bash_cmd = ['cmd.exe', '/c', params.command]
        else:
            bash_cmd = ['/bin/bash', '-c', params.command]

        process = await asyncio.create_subprocess_exec(
            *bash_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        pumps = asyncio.gather(
            self._pump(process.stdout, stdout_chunks, invocation),
            self._pump(process.stderr, stderr_chunks, invocation),
        )

        try:
            await asyncio.wait_for(
                asyncio.gather(pumps, process.wait()),
                timeout = params.timeout
            )
        except asyncio.TimeoutError:
            pumps.cancel()
            if sys.platform != 'win32':
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
            return ToolResult.error_result(
                f'Command timed out after: {params.timeout}'
            )

        exit_code = process.returncode

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)

        output = ""
        if stdout.strip():
            output += stdout.rstrip()
        
        if stderr.strip():
            output += "\n--- stderr ---\n"
            output += stderr.rstrip()
        
        if exit_code != 0:
            output += f'\nExit code: {exit_code}'
        
        if len(output) > 100*1024:
            output = output[: 100 * 1024] + "\n.. [output truncated]"
        
        return ToolResult(
            success=exit_code==0,
            output=output,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code,
        )

    async def _pump(
        self,
        stream: asyncio.StreamReader | None,
        chunks: list[str],
        invocation: ToolInvocation,
    ) -> None:
        if stream is None:
            return

        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

        while True:
            data = await stream.read(8192)
            if not data:
                break

            text = decoder.decode(data)
            if not text:
                continue

            chunks.append(text)
            invocation.report_progress(text)

        tail = decoder.decode(b"", final=True)
        if tail:
            chunks.append(tail)

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()

        bash_environment = self.config.bash_environment

        if not bash_environment.ignore_default_excludes:
            for pattern in bash_environment.exclude_patterns:
                keys_to_remove = [k for k in env.keys() if fnmatch.fnmatch(k.upper(), pattern.upper())]

                for k in keys_to_remove:
                    del env[k]

        if bash_environment.set_vars:
            env.update(bash_environment.set_vars)

        return env
