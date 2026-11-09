"""The single error boundary every MCP tool runs inside (spec: tools/error-boundary).

Tools contain business logic only. They:

* parse input with :func:`normalize_input` (raises :class:`InvalidInputError`),
* check adapter results with :func:`require_success` (raises
  :class:`ToolOperationError`), and
* return their success payload.

:func:`tool_boundary` turns anything raised into the uniform error payload -
``status``, ``message``, ``error_type``, ``hint`` and ``execution_time`` (the
adapter's timing, else the tool's own wall time) - using :class:`ErrorClassifier` to name the failure.
:class:`ToolRegistrar` applies the boundary to every tool at registration, so no
tool can forget it. It also adds each tool's support level (from
``support_levels.py``) to its tags and, for a beta or experimental tool, a
``warning`` to its successful results.
"""

from __future__ import annotations

import functools
import inspect
import time
import types
import typing
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from fastmcp.utilities.docstring_parsing import parse_docstring
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
from .input_compat import removed_inputs
from .support_levels import SUPPORT_LEVELS, Support
from .tool_hints import TOOL_HINTS, ToolHints

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


def model_parameters(fn: Callable[..., Any]) -> dict[str, type[BaseModel]]:
    """The parameters of ``fn`` annotated with a pydantic model.

    A parameter counts when its annotation is a model, or a model ``| None``.

    Args:
        fn: The tool function.

    Returns:
        dict[str, type[BaseModel]]: Parameter name to its model; empty when
        the annotations can't be resolved (a model defined inside a function).
    """
    try:
        hints = typing.get_type_hints(fn)
    except NameError:
        return {}
    models: dict[str, type[BaseModel]] = {}
    for name, hint in hints.items():
        options = (
            typing.get_args(hint)
            if isinstance(hint, types.UnionType)
            or typing.get_origin(hint) is typing.Union
            else (hint,)
        )
        found = [o for o in options if isinstance(o, type) and issubclass(o, BaseModel)]
        if name != "return" and len(found) == 1:
            models[name] = found[0]
    return models


def tool_boundary(
    fn: Callable[..., Awaitable[dict[str, Any]]],
    classifier: ErrorClassifier = _CLASSIFIER,
    warning: str | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Wrap an async tool so every failure becomes an error payload.

    ``functools.wraps`` keeps the signature, so FastMCP builds the same input
    schema for the wrapped tool.

    Args:
        fn: The tool function.
        classifier: Names the failure in an error payload.
        warning: Added as ``warning`` to every successful result (a beta or
            experimental tool's level), after any warning of the tool's own;
            errors carry a ``hint`` instead.

    A dict passed where the tool expects its input model is validated as
    that model first, so a script can call any tool function with a dict, as
    an MCP client effectively does. An input the tool no longer takes
    (``input_compat.REMOVED_INPUTS``) is refused as invalid input before the
    tool runs.

    Returns:
        The wrapped tool.
    """
    tool_name = fn.__name__
    models = model_parameters(fn)
    signature = inspect.signature(fn)

    def with_models(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> inspect.BoundArguments:
        bound = signature.bind_partial(*args, **kwargs)
        for name, model in models.items():
            if isinstance(bound.arguments.get(name), dict):
                bound.arguments[name] = normalize_input(bound.arguments[name], model)
            value = bound.arguments.get(name)
            removed = removed_inputs(value) if isinstance(value, BaseModel) else []
            if removed:
                raise InvalidInputError("; ".join(removed))
        return bound

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        started = time.perf_counter()

        def elapsed() -> float:
            return time.perf_counter() - started

        try:
            bound = with_models(args, kwargs)
            result = await fn(*bound.args, **bound.kwargs)
        except InvalidInputError as exc:
            return error_payload(
                f"Invalid input: {exc}",
                Classification(INVALID_INPUT, _INVALID_INPUT_HINT),
                elapsed(),
            )
        except ValidationError as exc:
            return error_payload(
                f"Invalid input: {describe_validation_error(exc)}",
                Classification(INVALID_INPUT, _INVALID_INPUT_HINT),
                elapsed(),
            )
        except UnsupportedOperationError as exc:
            return error_payload(
                str(exc),
                Classification(NOT_SUPPORTED, NOT_SUPPORTED_HINT),
                elapsed(),
            )
        except ToolOperationError as exc:
            message = str(exc)
            # Adapter guards (wrong document type, no active model) reject a
            # call before timing it; fall back to the tool's own wall time.
            timing = exc.execution_time if exc.execution_time is not None else elapsed()
            return error_payload(
                message, classifier.classify(message), timing, exc.data
            )
        except Exception as exc:
            logger.exception("Tool {} raised", tool_name)
            message = f"{tool_name} failed: {type(exc).__name__}: {exc}"
            return error_payload(
                message,
                classifier.classify(str(exc), exc, fallback=INTERNAL),
                elapsed(),
            )
        if warning is not None and result.get("status") == "success":
            # A tool's own warning (e.g. a cut that removed nothing) comes first.
            own = result.get("warning")
            return {**result, "warning": f"{own} {warning}" if own else warning}
        return result

    wrapper.__tool_boundary__ = True  # type: ignore[attr-defined]
    return wrapper


def has_tool_boundary(fn: Any) -> bool:
    """True when ``fn`` was wrapped by :func:`tool_boundary`."""
    return bool(getattr(fn, "__tool_boundary__", False))


def tool_family(fn: Callable[..., Any]) -> str:
    """The family tag of a tool: the name of the module that defines it.

    Args:
        fn: The tool function.

    Returns:
        str: The module's last dotted part, e.g. ``"modeling"``.
    """
    return fn.__module__.rsplit(".", 1)[-1]


class ToolRegistrar:
    """A FastMCP stand-in whose ``tool()`` applies :func:`tool_boundary` first.

    It also gives each tool its title and behaviour hints from the hints
    table, its family tag (see :func:`tool_family`), and its support level
    from the levels table: a ``level:<level>`` tag and, below stable, a
    ``warning`` on success. Everything else is forwarded to the wrapped
    server unchanged.
    """

    def __init__(
        self,
        mcp: Any,
        classifier: ErrorClassifier = _CLASSIFIER,
        hints: Mapping[str, ToolHints] = TOOL_HINTS,
        levels: Mapping[str, Support] = SUPPORT_LEVELS,
    ) -> None:
        self._mcp = mcp
        self._classifier = classifier
        self._hints = hints
        self._levels = levels

    def _support(self, name: str) -> Support:
        """The support entry of a tool being registered.

        Raises:
            KeyError: If the tool has no entry in the levels table.
        """
        support = self._levels.get(name)
        if support is None:
            raise KeyError(
                f"Tool {name!r} has no entry in tools/support_levels.py; add its "
                "support level (stable, beta, experimental or planned) there."
            )
        return support

    def _metadata(
        self, fn: Callable[..., Any], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """The registration kwargs with the tool's title, hints and tag added.

        Explicit ``title``/``annotations``/``description`` kwargs win over
        the tables; tags are merged. A beta or experimental tool's
        description opens with its level sentence, the same as its
        ``warning``.

        Args:
            fn: The tool function being registered.
            kwargs: The keyword arguments given to ``tool()``.

        Returns:
            dict[str, Any]: The keyword arguments to pass on to FastMCP.

        Raises:
            KeyError: If the tool has no entry in the hints or levels table.
        """
        name = kwargs.get("name") or fn.__name__
        hints = self._hints.get(name)
        if hints is None:
            raise KeyError(
                f"Tool {name!r} has no entry in tools/tool_hints.py; add its "
                "title and read-only / destructive / idempotent hints there."
            )
        merged = dict(kwargs)
        merged.setdefault("title", hints.title)
        merged.setdefault("annotations", hints.annotations())
        support = self._support(name)
        merged["tags"] = {
            tool_family(fn),
            f"level:{support.level.value}",
            *(kwargs.get("tags") or ()),
        }
        warning = support.warning()
        if warning is not None and "description" not in kwargs:
            body = parse_docstring(fn).description
            merged["description"] = "\n\n".join(filter(None, (warning, body)))
        return merged

    def _wrap(self, fn: Callable[..., Awaitable[dict[str, Any]]], name: str) -> Any:
        """The tool inside the boundary, with its level's success warning."""
        return tool_boundary(fn, self._classifier, self._support(name).warning())

    @classmethod
    def of(cls, mcp: Any) -> ToolRegistrar:
        """Wrap ``mcp`` unless it already is a registrar (idempotent).

        Every ``register_<area>_tools`` starts with ``mcp = ToolRegistrar.of(mcp)``
        so its tools get the boundary however the module is registered.
        """
        return mcp if isinstance(mcp, cls) else cls(mcp)

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """Same contract as ``FastMCP.tool``, with the boundary and hints applied."""
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            fn = args[0]
            return self._mcp.tool(**self._metadata(fn, {}))(self._wrap(fn, fn.__name__))

        if args and isinstance(args[0], str):
            kwargs = {"name": args[0], **kwargs}
            args = args[1:]

        def decorator(fn: Callable[..., Awaitable[dict[str, Any]]]) -> Any:
            register = self._mcp.tool(*args, **self._metadata(fn, kwargs))
            return register(self._wrap(fn, kwargs.get("name") or fn.__name__))

        return decorator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mcp, name)


def with_tool_boundary[TServer](mcp: TServer) -> TServer:
    """Return ``mcp`` wrapped in a :class:`ToolRegistrar` (typed as ``mcp``).

    The registrar duck-types the FastMCP surface the tool modules use
    (``tool()`` plus attribute forwarding), so modules keep their annotations.
    """
    return cast(TServer, ToolRegistrar.of(mcp))
