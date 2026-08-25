from pydantic import BaseModel, Field
from tools.base import FileDiff, Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
from utils.paths import ensure_parent_dir, resolve_path

class WriteFileParams(BaseModel):
    path: str = Field(
        ...,
        description='Path to the file to write, relative to the working or absolute path.'
    )
    content: str = Field(
        ...,
        description="Content to write to a file."
    )
    create_directories: bool = Field(
        True,
        description='Create parent directories if they are yet to exist.'
    )

class WriteFileTool(Tool):
    name = 'write'
    description = (
        "Write contents to a file, creates a file if it doesn't exist, "
        "or overwrites the file if it does. Parent directories are created automatically."
        "Use this tool for creating new files or replacing file contents."
        "For partial or smaller modifications, use the edit tool instead."
    )
    kind = ToolKind.WRITE
    schema = WriteFileParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()

        old_content = ""

        if not is_new_file:
            try:
                old_content = path.read_text(
                    encoding='utf-8'
                )
            except OSError:
                pass

        diff = FileDiff(
            path=path,
            old_content=old_content,
            new_content=params.content,
            is_new_file=is_new_file
        )

        action = "Create" if is_new_file else 'Overwrite'

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"{action} file: {path}",
            diff=diff,
            affected_paths=[path],
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()
        old_content = ""

        if not is_new_file:
            try:
                old_content = path.read_text(
                    encoding='utf-8'
                )
            except:
                pass
        
        try:
            if params.create_directories:
                ensure_parent_dir(path)
            elif not path.parent.exists():
                return ToolResult.error_result(f'Parent directory does not exist: {path.parent}')
            path.write_text(params.content, encoding='utf-8')

            action = "Created" if is_new_file else 'Updated'
            line_count = len(params.content.splitlines())

            return ToolResult.success_result(
                f"{action} {path} {line_count} lines",
                diff=FileDiff(
                    path=path,
                    old_content=old_content,
                    new_content=params.content,
                    is_new_file=is_new_file
                ),
                metadata = {
                    'path': str(path),
                    'is_new_file': is_new_file,
                    'lines': line_count,
                    'bytes': len(params.content.encode(
                        'utf-8'
                    ))
                }
            )
        
        except OSError as e:
            return ToolResult.error_result(f"Failed to write file: {e}")
        
