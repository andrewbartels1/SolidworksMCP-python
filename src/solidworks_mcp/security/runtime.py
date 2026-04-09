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
        client_id: Logical client identifier.
        api_key: Optional API key supplied in payload.
    """

    client_id: str
    api_key: str | None


class SecurityEnforcer:
    """Enforce authentication and rate-limit policies at runtime."""

    def __init__(self, config: SolidWorksMCPConfig) -> None:
        """Initialize this object.

        Args:
            config: Server configuration.
        """
        self._config = config

    def enforce(self, tool_name: str, payload: object) -> None:
        """Validate invocation against runtime security policy.

        Args:
            tool_name: Tool function name.
            payload: Input payload.

        Raises:
            SecurityError: When policy validation fails.
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
        """Extract client and auth information from payload object."""
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
        """Return whether API key validation should be enforced."""
        if self._config.api_key_required:
            return True
        if self._config.security_level == SecurityLevel.STRICT:
            return True
        return self._config.api_key is not None or bool(self._config.api_keys)

    def _expected_api_key(self) -> str | None:
        """Return configured expected API key for validation."""
        if self._config.api_key is not None:
            return self._config.api_key.get_secret_value()
        if self._config.api_keys:
            return self._config.api_keys[0]
        return None


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two strings in constant time."""
    return secrets.compare_digest(left, right)
