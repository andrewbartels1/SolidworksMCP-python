"""
Authentication and authorization for SolidWorks MCP Server.
"""

import secrets
from functools import wraps
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from ..config import SolidWorksMCPConfig

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def setup_authentication(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Configure authentication middleware hooks.

    Args:
        mcp: Active MCP server instance.
        config: Loaded server configuration.
    """
    api_key = getattr(config, "api_key", None)
    api_keys = getattr(config, "api_keys", [])
    api_key_required = bool(getattr(config, "api_key_required", False))
    auth_mode = "api_key" if (api_key or api_keys or api_key_required) else "none"
    try:
        setattr(mcp, "_security_auth_enabled", True)
        setattr(mcp, "_security_auth_mode", auth_mode)
    except (AttributeError, TypeError):
        # Some tests intentionally pass plain object() instances without __dict__.
        return


def validate_api_key(provided_key: str, expected_key: str) -> bool:
    """Validate API key using constant-time comparison.

    Args:
        provided_key: API key received from the caller.
        expected_key: API key configured by the server.

    Returns:
        ``True`` when keys match.
    """
    if not provided_key or not expected_key:
        return False

    return secrets.compare_digest(provided_key, expected_key)


def require_auth(config: SolidWorksMCPConfig) -> Callable[[F], F]:
    """Decorate a coroutine with authentication checks.

    Args:
        config: Loaded server configuration.

    Returns:
        Callable[[F], F]: Decorator preserving the original coroutine signature.
    """

    def decorator(func: F) -> F:
        """Wrap a coroutine with request-level authentication checks.

        Args:
            func: Coroutine function.

        Returns:
            Wrapped coroutine.
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Run the wrapped coroutine after API key validation.

            Raises:
                RuntimeError: If authentication is required and key validation fails.
            """
            security_level = str(getattr(config, "security_level", "minimal"))
            if security_level == "minimal":
                return await func(*args, **kwargs)

            api_key_required = bool(getattr(config, "api_key_required", False))
            api_key = getattr(config, "api_key", None)
            api_keys = getattr(config, "api_keys", [])
            if not (api_key_required or api_key or api_keys):
                return await func(*args, **kwargs)

            payload = kwargs.get("input_data")
            if payload is None and args:
                payload = args[0]

            payload_dict: dict[str, Any] = {}
            if hasattr(payload, "model_dump"):
                payload_dict = cast(dict[str, Any], payload.model_dump())
            elif isinstance(payload, dict):
                payload_dict = payload

            provided_key_value = payload_dict.get("api_key")
            provided_key = str(provided_key_value) if provided_key_value else ""

            expected_key = ""
            if api_key is not None and hasattr(api_key, "get_secret_value"):
                expected_key = api_key.get_secret_value()
            elif isinstance(api_key, str):
                expected_key = api_key
            elif api_keys:
                expected_key = api_keys[0]

            if not validate_api_key(
                provided_key=provided_key, expected_key=expected_key
            ):
                raise RuntimeError("authentication failed: invalid api_key")

            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
