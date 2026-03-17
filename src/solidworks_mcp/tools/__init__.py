"""
Tools for SolidWorks MCP Server.

This module provides all the MCP tools for SolidWorks automation, organized by category.
"""

from typing import Any
from fastmcp import FastMCP
from loguru import logger

from .modeling import register_modeling_tools
from .sketching import register_sketching_tools
from .drawing import register_drawing_tools
from .drawing_analysis import register_drawing_analysis_tools
from .analysis import register_analysis_tools
from .export import register_export_tools
from .automation import register_automation_tools
from .file_management import register_file_management_tools
from .vba_generation import register_vba_generation_tools
from .template_management import register_template_management_tools
from .macro_recording import register_macro_recording_tools


async def register_tools(mcp: FastMCP, adapter, config) -> int:
    """Register all SolidWorks MCP tools."""
    tool_count = 0

    logger.info("Registering SolidWorks MCP tools...")

    # Register tool categories
    tool_count += await register_modeling_tools(mcp, adapter, config)
    tool_count += await register_sketching_tools(mcp, adapter, config)
    tool_count += await register_drawing_tools(mcp, adapter, config)
    tool_count += await register_drawing_analysis_tools(mcp, adapter, config)
    tool_count += await register_analysis_tools(mcp, adapter, config)
    tool_count += await register_export_tools(mcp, adapter, config)
    tool_count += await register_automation_tools(mcp, adapter, config)
    tool_count += await register_file_management_tools(mcp, adapter, config)
    tool_count += await register_vba_generation_tools(mcp, adapter, config)
    tool_count += await register_template_management_tools(mcp, adapter, config)
    tool_count += await register_macro_recording_tools(mcp, adapter, config)

    logger.info(f"Registered {tool_count} SolidWorks tools")
    return tool_count


__all__ = [
    "register_tools",
]
