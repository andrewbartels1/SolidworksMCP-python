"""
Security module for SolidWorks MCP Server.

Provides authentication, authorization, and security features based on
the configured security level.
"""

from .auth import setup_authentication, validate_api_key
from .cors import setup_cors
from .rate_limiting import setup_rate_limiting


async def setup_security(mcp, config):
    """Setup security features based on configuration."""
    from ..config import SecurityLevel

    if config.security_level == SecurityLevel.MINIMAL:
        # Local only, minimal security
        return

    if config.security_level in [SecurityLevel.STANDARD, SecurityLevel.STRICT]:
        # Setup API key authentication
        if config.api_key:
            setup_authentication(mcp, config)

        # Setup CORS
        if config.enable_cors:
            setup_cors(mcp, config)

        # Setup rate limiting
        if config.enable_rate_limiting:
            setup_rate_limiting(mcp, config)


__all__ = [
    "setup_security",
    "setup_authentication",
    "validate_api_key",
    "setup_cors",
    "setup_rate_limiting",
]
