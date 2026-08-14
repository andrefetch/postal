from tools.core.directories import ListDirectoriesTool
from tools.core.read import ReadFileTool
from tools.core.write import WriteFileTool
from tools.core.edit import EditTool
from tools.core.apply_patch import ApplyPatchTool
from tools.core.bash import BashTool
from tools.core.grep import GrepTool
from tools.core.glob import GlobTool
from tools.core.plan import PlanTool

from tools.network.search import WebSearchTool
from tools.network.fetch import WebFetchTool

from tools.memory.memory import MemoryTool

from tools.base import Tool

__all__ = [
    'ReadFileTool',
    'WriteFileTool',
    'EditTool',
    'ApplyPatchTool',
    'BashTool',
    'ListDirectoriesTool',
    'GrepTool',
    'GlobTool',
    'WebSearchTool',
    'WebFetchTool',
    'PlanTool',
    'MemoryTool',
]

def get_all_core_tools() -> list[Tool]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ApplyPatchTool,
        BashTool,
        ListDirectoriesTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        PlanTool,
        MemoryTool,
    ]
