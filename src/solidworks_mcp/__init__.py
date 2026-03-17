"""
SolidWorks MCP Server - Python Implementation with FastMCP and PydanticAI

This is a comprehensive Python implementation of the SolidWorks MCP server,
providing 88+ tools for SolidWorks automation with enhanced security,
configurability, and modern Python architectures.

Original TypeScript implementation rights and IP remain with the original author.
This Python implementation adds FastMCP integration, PydanticAI capabilities,
and comprehensive testing for local and remote deployment scenarios.

Author: Andrew Bartels (hobby mechanical engineer learning LLMs and MCP)
License: MIT
"""

from typing import Any

from .config import SolidWorksMCPConfig
from .version import __version__

__all__ = [
    "create_server",
    "main",
    "SolidWorksMCPConfig",
    "__version__",
]


def __getattr__(name: str) -> Any:
    if name in {"create_server", "main"}:
        from .server import create_server, main

        exports = {
            "create_server": create_server,
            "main": main,
        }
        return exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
