"""CORS (Cross-Origin Resource Sharing) configuration for remote deployments.
"""

from typing import Any

from ..config import SolidWorksMCPConfig


def setup_cors(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Configure CORS middleware for remote deployments.
    
    Args:
        mcp (Any): The mcp value.
        config (SolidWorksMCPConfig): Configuration values for the operation.
    
    Returns:
        None: None.
    """
    cors_origins = getattr(config, "cors_origins", [])
    allowed_origins = getattr(config, "allowed_origins", [])
    enable_cors = bool(getattr(config, "enable_cors", False))
    origins = cors_origins or allowed_origins
    try:
        mcp._security_cors_enabled = enable_cors
        mcp._security_cors_origins = list(origins)
    except (AttributeError, TypeError):  # pragma: no cover
        # Some tests intentionally pass plain object() instances without __dict__.
        return
