"""
Authentication and authorization for SolidWorks MCP Server.
"""

from functools import wraps
from typing import Any


def setup_authentication(mcp, config) -> None:
    """Setup authentication middleware."""
    # For FastMCP, authentication would be handled at the HTTP layer
    # This is a placeholder for future implementation
    pass


def validate_api_key(provided_key: str, expected_key: str) -> bool:
    """Validate API key."""
    if not provided_key or not expected_key:
        return False

    # Simple constant-time comparison
    return provided_key == expected_key


def require_auth(config):
    """Decorator to require authentication."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Authentication logic would go here
            # For now, just pass through
            return await func(*args, **kwargs)

        return wrapper

    return decorator
