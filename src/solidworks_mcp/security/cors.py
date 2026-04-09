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
    cors_origins = getattr(config, "cors_origins", [])
    allowed_origins = getattr(config, "allowed_origins", [])
    enable_cors = bool(getattr(config, "enable_cors", False))
    origins = cors_origins or allowed_origins
    try:
        setattr(mcp, "_security_cors_enabled", enable_cors)
        setattr(mcp, "_security_cors_origins", list(origins))
    except (AttributeError, TypeError):
        # Some tests intentionally pass plain object() instances without __dict__.
        return
