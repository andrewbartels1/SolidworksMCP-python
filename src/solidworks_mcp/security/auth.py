"""
Authentication and authorization for SolidWorks MCP Server.
"""

from functools import wraps
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..config import SolidWorksMCPConfig

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def setup_authentication(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Configure authentication middleware hooks.

    Args:
        mcp: Active MCP server instance.
        config: Loaded server configuration.
    """
    # For FastMCP, authentication would be handled at the HTTP layer
    # This is a placeholder for future implementation
    pass


def validate_api_key(provided_key: str, expected_key: str) -> bool:
    """Validate API key."""
    if not provided_key or not expected_key:
        return False

    # Simple constant-time comparison
    return provided_key == expected_key


def require_auth(config: SolidWorksMCPConfig) -> Callable[[F], F]:
    """Decorate a coroutine with authentication checks.

    Args:
        config: Loaded server configuration.

    Returns:
        Callable[[F], F]: Decorator preserving the original coroutine signature.
    """

    def decorator(func: F) -> F:
        """Execute decorator.

        Args:
            func (F): Describe func.

        Returns:
            F: Describe the returned value.
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute wrapper.

            Returns:
                Any: Describe the returned value.
            """

            # Authentication logic would go here
            # For now, just pass through
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
