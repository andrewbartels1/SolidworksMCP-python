"""Security module for SolidWorks MCP Server.

Provides authentication, authorization, and security features based on the configured
security level.
"""

from typing import Any

from ..config import SolidWorksMCPConfig
from .auth import setup_authentication, validate_api_key
from .cors import setup_cors
from .rate_limiting import setup_rate_limiting
from .runtime import SecurityEnforcer

_security_enforcer: SecurityEnforcer | None = None


def get_security_enforcer() -> SecurityEnforcer | None:
    """Return the active runtime security enforcer, if configured.
    
    Returns:
        SecurityEnforcer | None: The result produced by the operation.
    """
    return _security_enforcer


async def setup_security(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Configure security middleware based on selected security level.
    
    Args:
        mcp (Any): The mcp value.
        config (SolidWorksMCPConfig): Configuration values for the operation.
    
    Returns:
        None: None.
    """
    from ..config import SecurityLevel

    if config.security_level == SecurityLevel.MINIMAL:
        # Local only, minimal security
        global _security_enforcer
        _security_enforcer = SecurityEnforcer(config)
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

    _security_enforcer = SecurityEnforcer(config)


__all__ = [
    "setup_security",
    "setup_authentication",
    "validate_api_key",
    "setup_cors",
    "setup_rate_limiting",
    "get_security_enforcer",
]
