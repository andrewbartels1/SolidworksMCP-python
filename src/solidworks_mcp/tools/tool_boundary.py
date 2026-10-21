"""The single error boundary every MCP tool runs inside (spec: tools/error-boundary).

Tools contain business logic only. They:

* parse input with :func:`normalize_input` (raises :class:`InvalidInputError`),
* check adapter results with :func:`require_success` (raises
  :class:`ToolOperationError`), and
* return their success payload.

:func:`tool_boundary` turns anything raised into the uniform error payload -
``status``, ``message``, ``error_type``, ``hint`` and ``execution_time`` (null
when unknown) - using :class:`ErrorClassifier` to name the failure.
:class:`ToolRegistrar` applies the boundary to every tool at registration, so no
tool can forget it.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, cast

from loguru import logger
from pydantic import BaseModel, ValidationError

from ..adapters.base import AdapterResult
from .error_classifier import (
    INTERNAL,
    INVALID_INPUT,
    NOT_SUPPORTED,
    NOT_SUPPORTED_HINT,
    Classification,
    ErrorClassifier,
)

_INVALID_INPUT_HINT = (
    "Fix the named field(s) and call the tool again; see the tool's input "
    "schema for the expected types and units."
)
_CLASSIFIER = ErrorClassifier()


class InvalidInputError(ValueError):
    """The tool's input failed validation; the adapter was not called."""


class ToolOperationError(Exception):
    """An adapter operation reported failure.

    Attributes:
        execution_time: The adapter's timing for the failed call, if any.
        data: Diagnostic data that explains the failure (e.g. rebuild errors),
            returned to the caller under ``data``.
    """

    def __init__(
        self,
        message: str,
        execution_time: float | None = None,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.execution_time = execution_time
        self.data = data


class UnsupportedOperationError(Exception):
    """The active adapter has no capability for the requested operation."""


def require_capability(adapter: Any, method: str, message: str) -> None:
    """Raise :class:`UnsupportedOperationError` unless ``adapter`` has ``method``.

    Args:
        adapter: The active SolidWorks adapter.
        method: The adapter method the tool needs.
        message: What was not done, and what to do instead.
    """
    if not hasattr(adapter, method):
        raise UnsupportedOperationError(message)


def normalize_input[TModel: BaseModel](
    input_data: Any, model_type: type[TModel]
) -> TModel:
    """Validate ``input_data`` as ``model_type``.

    Args:
        input_data: A ``model_type`` instance, a mapping of its fields, another
            pydantic model (converted through ``model_dump``), or ``None`` for
            a tool whose fields all have defaults.
        model_type: The tool's pydantic input model.

    Returns:
        TModel: The validated model.

    Raises:
        InvalidInputError: Naming the offending field(s).
    """
    if isinstance(input_data, model_type):
        return input_data
    if input_data is None:
        input_data = {}
    elif not isinstance(input_data, dict) and hasattr(input_data, "model_dump"):
        input_data = input_data.model_dump()
    try:
        return model_type.model_validate(input_data)
    except ValidationError as exc:  # also wraps ValueErrors from validators
        raise InvalidInputError(describe_validation_error(exc)) from exc


def describe_validation_error(exc: ValidationError) -> str:
    """Render a pydantic error as ``field: problem; field: problem``."""
    parts = []
    for error in exc.errors():
        field = ".".join(str(p) for p in error.get("loc", ())) or "input"
        parts.append(f"{field}: {error.get('msg', 'invalid')}")
    return "; ".join(parts)


def require_success[TResult](
    result: AdapterResult[TResult],
    failure_message: str = "Operation failed",
    *,
    context: str | None = None,
    with_data: bool = False,
) -> AdapterResult[TResult]:
    """Return ``result`` when it succeeded; raise otherwise.

    Mirrors the ``if result.is_success: ... else: error`` the tools used before
    the boundary, so anything that is not a success - including a warning - is
    reported as a failure. Tools that treat a warning as success check
    ``result.status`` themselves before calling this.

    Args:
        result: The adapter result to check.
        failure_message: Message used when the adapter gave none.
        context: Prefix naming what failed, e.g. ``"Failed to create part"``,
            giving ``"<context>: <adapter error>"``.
        with_data: Return the adapter's ``data`` with the error, for tools whose
            failure data is the diagnosis (e.g. ``rebuild_model``).

    Raises:
        ToolOperationError: Carrying the adapter's message and timing.
    """
    if not result.is_success:
        message = str(result.error or failure_message)
        raise ToolOperationError(
            f"{context}: {message}" if context else message,
            result.execution_time,
            result.data if with_data else None,
        )
    return result


def error_payload(
    message: str,
    classification: Classification,
    execution_time: float | None = None,
    data: Any = None,
) -> dict[str, Any]:
    """Build the spec's error payload."""
    payload: dict[str, Any] = {
        "status": "error",
        "message": message,
        "error_type": classification.error_type,
        "hint": classification.hint,
    }
    payload["execution_time"] = execution_time
    if data is not None:
        payload["data"] = data
    return payload


def tool_boundary(
    fn: Callable[..., Awaitable[dict[str, Any]]],
    classifier: ErrorClassifier = _CLASSIFIER,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Wrap an async tool so every failure becomes an error payload.

    ``functools.wraps`` keeps the signature, so FastMCP builds the same input
    schema for the wrapped tool.
    """
    tool_name = fn.__name__

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await fn(*args, **kwargs)
        except InvalidInputError as exc:
            return error_payload(
                f"Invalid input: {exc}",
                Classification(INVALID_INPUT, _INVALID_INPUT_HINT),
            )
        except ValidationError as exc:
            return error_payload(
                f"Invalid input: {describe_validation_error(exc)}",
                Classification(INVALID_INPUT, _INVALID_INPUT_HINT),
            )
        except UnsupportedOperationError as exc:
            return error_payload(
                str(exc), Classification(NOT_SUPPORTED, NOT_SUPPORTED_HINT)
            )
        except ToolOperationError as exc:
            message = str(exc)
            return error_payload(
                message, classifier.classify(message), exc.execution_time, exc.data
            )
        except Exception as exc:
            logger.exception("Tool {} raised", tool_name)
            message = f"{tool_name} failed: {type(exc).__name__}: {exc}"
            return error_payload(
                message, classifier.classify(str(exc), exc, fallback=INTERNAL)
            )

    wrapper.__tool_boundary__ = True  # type: ignore[attr-defined]
    return wrapper


def has_tool_boundary(fn: Any) -> bool:
    """True when ``fn`` was wrapped by :func:`tool_boundary`."""
    return bool(getattr(fn, "__tool_boundary__", False))


class ToolRegistrar:
    """A FastMCP stand-in whose ``tool()`` applies :func:`tool_boundary` first.

    Everything else is forwarded to the wrapped server unchanged.
    """

    def __init__(self, mcp: Any, classifier: ErrorClassifier = _CLASSIFIER) -> None:
        self._mcp = mcp
        self._classifier = classifier

    @classmethod
    def of(cls, mcp: Any) -> ToolRegistrar:
        """Wrap ``mcp`` unless it already is a registrar (idempotent).

        Every ``register_<area>_tools`` starts with ``mcp = ToolRegistrar.of(mcp)``
        so its tools get the boundary however the module is registered.
        """
        return mcp if isinstance(mcp, cls) else cls(mcp)

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """Same contract as ``FastMCP.tool``, with the boundary applied."""
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return self._mcp.tool()(tool_boundary(args[0], self._classifier))
        register = self._mcp.tool(*args, **kwargs)

        def decorator(fn: Callable[..., Awaitable[dict[str, Any]]]) -> Any:
            return register(tool_boundary(fn, self._classifier))

        return decorator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mcp, name)


def with_tool_boundary[TServer](mcp: TServer) -> TServer:
    """Return ``mcp`` wrapped in a :class:`ToolRegistrar` (typed as ``mcp``).

    The registrar duck-types the FastMCP surface the tool modules use
    (``tool()`` plus attribute forwarding), so modules keep their annotations.
    """
    return cast(TServer, ToolRegistrar.of(mcp))
