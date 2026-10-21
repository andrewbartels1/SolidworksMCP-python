"""Tests for the MCP tool error boundary (spec: tools/error-boundary)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from pydantic import BaseModel, ValidationError

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.tools.error_classifier import RPC_S_SERVER_UNAVAILABLE
from solidworks_mcp.tools.tool_boundary import (
    InvalidInputError,
    ToolOperationError,
    ToolRegistrar,
    describe_validation_error,
    normalize_input,
    require_success,
    tool_boundary,
)


class _Input(BaseModel):
    radius: float
    name: str = "x"


class _Defaults(BaseModel):
    name: str = "default"


class _PostInitInput(BaseModel):
    value: int

    def model_post_init(self, _context: Any) -> None:
        if self.value < 0:
            raise ValueError("value must be >= 0")


class _ComError(Exception):
    """Stand-in for ``pywintypes.com_error``."""


# ---- normalize_input -------------------------------------------------------


def test_normalize_input_passes_a_model_through() -> None:
    model = _Input(radius=1)

    assert normalize_input(model, _Input) is model


def test_normalize_input_validates_a_mapping() -> None:
    assert normalize_input({"radius": "2.5"}, _Input).radius == 2.5


def test_normalize_input_treats_none_as_all_defaults() -> None:
    assert normalize_input(None, _Defaults) == _Defaults()


def test_normalize_input_converts_model_dump_carriers() -> None:
    class _Carrier:
        def model_dump(self) -> dict[str, Any]:
            return {"radius": 4}

    assert normalize_input(_Carrier(), _Input).radius == 4


def test_normalize_input_rejects_plain_objects() -> None:
    class _Plain:
        radius = 1.0

    with pytest.raises(InvalidInputError):
        normalize_input(_Plain(), _Input)


def test_normalize_input_names_the_missing_field() -> None:
    with pytest.raises(InvalidInputError, match="radius: Field required"):
        normalize_input({}, _Input)


def test_normalize_input_wraps_post_init_value_errors() -> None:
    with pytest.raises(InvalidInputError, match="value must be >= 0"):
        normalize_input({"value": -1}, _PostInitInput)


def test_describe_validation_error_falls_back_to_input_for_empty_loc() -> None:
    try:
        _Input.model_validate("not a mapping")
    except ValidationError as exc:
        assert describe_validation_error(exc).startswith("input:")


# ---- require_success --------------------------------------------------------


def test_require_success_returns_a_successful_result() -> None:
    ok = AdapterResult(status=AdapterResultStatus.SUCCESS, data=1)

    assert require_success(ok) is ok


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        (AdapterResultStatus.ERROR, "No active model", "No active model"),
        (AdapterResultStatus.TIMEOUT, None, "Export failed"),
        (AdapterResultStatus.WARNING, "careful", "careful"),
    ],
)
def test_require_success_raises_for_errors_and_timeouts(
    status: AdapterResultStatus, error: str | None, expected: str
) -> None:
    result = AdapterResult(status=status, error=error, execution_time=0.5)

    with pytest.raises(ToolOperationError, match=expected) as info:
        require_success(result, "Export failed")

    assert info.value.execution_time == 0.5


# ---- tool_boundary ----------------------------------------------------------


@pytest.mark.asyncio
async def test_success_payload_is_returned_unchanged() -> None:
    payload = {"status": "success", "message": "done", "data": {"a": 1}}

    @tool_boundary
    async def tool() -> dict[str, Any]:
        return payload

    assert await tool() is payload


@pytest.mark.asyncio
async def test_invalid_input_never_reaches_the_adapter() -> None:
    adapter = AsyncMock()

    @tool_boundary
    async def tool(input_data: Any) -> dict[str, Any]:
        normalize_input(input_data, _Input)
        await adapter.do_work()
        return {"status": "success"}

    payload = await tool({})

    assert payload["status"] == "error"
    assert payload["error_type"] == "invalid_input"
    assert "radius" in payload["message"]
    assert payload["execution_time"] is None
    adapter.do_work.assert_not_called()


@pytest.mark.asyncio
async def test_raw_validation_error_is_invalid_input() -> None:
    @tool_boundary
    async def tool() -> dict[str, Any]:
        _Input.model_validate({})
        return {"status": "success"}

    payload = await tool()

    assert payload["error_type"] == "invalid_input"
    assert payload["message"] == "Invalid input: radius: Field required"


@pytest.mark.asyncio
async def test_adapter_failure_is_classified_with_timing() -> None:
    @tool_boundary
    async def tool() -> dict[str, Any]:
        require_success(
            AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active sketch",
                execution_time=0.25,
            )
        )
        return {"status": "success"}

    payload = await tool()

    assert payload == {
        "status": "error",
        "message": "No active sketch",
        "error_type": "no_active_sketch",
        "hint": payload["hint"],
        "execution_time": 0.25,
    }
    assert "sketch" in payload["hint"]


def test_require_success_prefixes_context() -> None:
    failed = AdapterResult(status=AdapterResultStatus.ERROR, error="boom")

    with pytest.raises(ToolOperationError, match="^Failed to create part: boom$"):
        require_success(failed, context="Failed to create part")


@pytest.mark.asyncio
async def test_unrecognised_adapter_failure_is_operation_failed() -> None:
    @tool_boundary
    async def tool() -> dict[str, Any]:
        raise ToolOperationError("Failed to create extrusion")

    payload = await tool()

    assert payload["error_type"] == "operation_failed"
    assert payload["message"] == "Failed to create extrusion"


@pytest.mark.asyncio
async def test_unexpected_exception_is_internal_and_names_the_tool() -> None:
    @tool_boundary
    async def explode() -> dict[str, Any]:
        raise ZeroDivisionError("division by zero")

    payload = await explode()

    assert payload["error_type"] == "internal"
    assert payload["message"] == "explode failed: ZeroDivisionError: division by zero"


@pytest.mark.asyncio
async def test_unexpected_com_error_is_classified_by_hresult() -> None:
    @tool_boundary
    async def tool() -> dict[str, Any]:
        raise _ComError(RPC_S_SERVER_UNAVAILABLE, "The RPC server is unavailable.")

    payload = await tool()

    assert payload["error_type"] == "solidworks_unavailable"


# ---- ToolRegistrar ----------------------------------------------------------


class _Args(BaseModel):
    name: str


@pytest.mark.asyncio
async def test_registrar_keeps_the_schema_and_applies_the_boundary() -> None:
    plain, wrapped = FastMCP("plain"), FastMCP("wrapped")
    registrar = ToolRegistrar(wrapped)

    async def body(input_data: _Args) -> dict[str, Any]:
        raise ToolOperationError("Feature not found: X")

    plain.tool()(body)
    registrar.tool()(body)

    (plain_tool,) = await plain.list_tools()
    (wrapped_tool,) = await wrapped.list_tools()
    assert wrapped_tool.parameters == plain_tool.parameters

    result = await wrapped.call_tool("body", {"input_data": {"name": "a"}})
    assert result.structured_content["error_type"] == "not_found"


@pytest.mark.asyncio
async def test_registrar_forwards_tool_kwargs_and_bare_decorator() -> None:
    mcp = FastMCP("t")
    registrar = ToolRegistrar(mcp)

    @registrar.tool(name="renamed")
    async def first() -> dict[str, Any]:
        return {"status": "success"}

    @registrar.tool
    async def second() -> dict[str, Any]:
        raise RuntimeError("x")

    names = {t.name for t in await mcp.list_tools()}
    assert names == {"renamed", "second"}
    result = await mcp.call_tool("second", {})
    assert result.structured_content["error_type"] == "internal"


def test_registrar_forwards_other_attributes() -> None:
    mcp = FastMCP("forward-me")

    assert ToolRegistrar(mcp).name == "forward-me"


@pytest.mark.asyncio
async def test_every_registered_tool_runs_inside_the_boundary(mock_adapter) -> None:
    """Guard: a tool module that skips ``with_tool_boundary`` fails here."""
    from solidworks_mcp.tools import register_tools
    from solidworks_mcp.tools.tool_boundary import has_tool_boundary

    mcp = FastMCP("all-tools")
    count = await register_tools(mcp, mock_adapter, {})
    tools = await mcp.list_tools()

    unwrapped = sorted(t.name for t in tools if not has_tool_boundary(t.fn))
    assert count == len(tools) > 100
    assert unwrapped == []


def test_registrar_of_is_idempotent() -> None:
    registrar = ToolRegistrar(FastMCP("x"))

    assert ToolRegistrar.of(registrar) is registrar


@pytest.mark.asyncio
async def test_failure_data_is_returned_when_requested() -> None:
    failed = AdapterResult(
        status=AdapterResultStatus.ERROR,
        error="Rebuild failed: Fillet1",
        data={"error_count": 1},
        execution_time=0.1,
    )

    @tool_boundary
    async def with_data() -> dict[str, Any]:
        require_success(failed, with_data=True)
        return {"status": "success"}

    @tool_boundary
    async def without_data() -> dict[str, Any]:
        require_success(failed)
        return {"status": "success"}

    assert (await with_data())["data"] == {"error_count": 1}
    assert "data" not in await without_data()
