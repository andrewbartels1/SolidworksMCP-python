"""
CORS (Cross-Origin Resource Sharing) configuration for remote deployments.
"""

from typing import Any

from ..config import SolidWorksMCPConfig


def setup_cors(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Configure CORS middleware for remote deployments.

    Args:
        mcp: Active MCP server instance.
        config: Loaded server configuration.
    """
    # FastMCP CORS configuration would go here
    # This is a placeholder for future implementation
    pass
