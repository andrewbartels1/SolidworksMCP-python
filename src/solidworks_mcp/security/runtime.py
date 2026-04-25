"""Runtime security enforcement helpers for tool invocations."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from ..config import SecurityLevel, SolidWorksMCPConfig
from .auth import validate_api_key
from .rate_limiting import check_rate_limit


class SecurityError(RuntimeError):
    """Raised when a request violates configured security policies."""


@dataclass(frozen=True)
class SecurityContext:
    """Extracted invocation security context.

    Attributes:
        api_key (str | None): The api key value.
        client_id (str): The client id value.
    """

    client_id: str
    api_key: str | None


class SecurityEnforcer:
    """Enforce authentication and rate-limit policies at runtime.

    Args:
        config (SolidWorksMCPConfig): Configuration values for the operation.

    Attributes:
        _config (Any): The config value.
    """

    def __init__(self, config: SolidWorksMCPConfig) -> None:
        """Initialize the security enforcer.

        Args:
            config (SolidWorksMCPConfig): Configuration values for the operation.

        Returns:
            None: None.
        """
        self._config = config

    def enforce(self, tool_name: str, payload: object) -> None:
        """Validate invocation against runtime security policy.

        Args:
            tool_name (str): The tool name value.
            payload (object): The payload value.

        Returns:
            None: None.

        Raises:
            SecurityError: Authentication failed: invalid api_key.
        """
        context = self._extract_context(payload)

        if self._config.enable_rate_limiting and not check_rate_limit(
            context.client_id
        ):
            raise SecurityError(
                f"rate limit exceeded for client '{context.client_id}' while calling '{tool_name}'"
            )

        if not self._is_auth_required():
            return

        expected_key = self._expected_api_key()
        if not expected_key:
            raise SecurityError("authentication required but no API key configured")

        provided_key = context.api_key
        if provided_key is None:
            raise SecurityError("authentication required but api_key was not provided")

        if not validate_api_key(provided_key=provided_key, expected_key=expected_key):
            raise SecurityError("authentication failed: invalid api_key")

    def _extract_context(self, payload: object) -> SecurityContext:
        """Extract client and auth information from payload object.

        Args:
            payload (object): The payload value.

        Returns:
            SecurityContext: The result produced by the operation.
        """
        if hasattr(payload, "model_dump"):
            payload_dict = payload.model_dump()
        elif isinstance(payload, dict):
            payload_dict = payload
        else:
            payload_dict = {}

        client_id_raw = payload_dict.get("client_id", "anonymous")
        client_id = str(client_id_raw).strip() if client_id_raw else "anonymous"

        api_key_raw = payload_dict.get("api_key")
        api_key = str(api_key_raw) if api_key_raw is not None else None

        return SecurityContext(client_id=client_id, api_key=api_key)

    def _is_auth_required(self) -> bool:
        """Return whether API key validation should be enforced.

        Returns:
            bool: True if auth required, otherwise False.
        """
        if bool(getattr(self._config, "api_key_required", False)):
            return True
        if getattr(self._config, "security_level", None) == SecurityLevel.STRICT:
            return True
        return getattr(self._config, "api_key", None) is not None or bool(
            getattr(self._config, "api_keys", [])
        )

    def _expected_api_key(self) -> str | None:
        """Return configured expected API key for validation.

        Returns:
            str | None: The result produced by the operation.
        """
        api_key = getattr(self._config, "api_key", None)
        if api_key is not None:
            get_secret_value = getattr(api_key, "get_secret_value", None)
            if callable(get_secret_value):
                return get_secret_value()
            return str(api_key)

        api_keys = getattr(self._config, "api_keys", [])
        if api_keys:
            return api_keys[0]
        return None


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two strings in constant time.

    Args:
        left (str): The left value.
        right (str): The right value.

    Returns:
        bool: True if constant time equals, otherwise False.
    """
    return secrets.compare_digest(left, right)
