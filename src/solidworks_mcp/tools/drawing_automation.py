"""Drawing-automation tools: model dimensions, layout, BOM, sheet scale, full drawings.

``generate_drawing_package`` produces a complete A3 drawing that follows the
A3 drafting standard in ``adapters/solidworks/drawing_standard.py``.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, get_type_hints

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput


class InsertModelDimensionsInput(CompatInput):
    """Input schema for importing model dimensions into drawing views.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
        include_hole_wizard (bool): Also import Hole Wizard location dims.
    """

    view_name: str | None = Field(
        default=None,
        description="One view, e.g. 'Drawing View1'; every view when omitted",
    )
    include_hole_wizard: bool = Field(
        default=True, description="Also import Hole Wizard location dimensions"
    )


class ArrangeDimensionsInput(CompatInput):
    """Input schema for arranging drawing dimensions.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
    """

    view_name: str | None = Field(
        default=None,
        description="One view, e.g. 'Drawing View1'; every view when omitted",
    )


def _guard(
    fn: Callable[..., Awaitable[dict[str, Any]]],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Make a tool accept a plain dict and never raise.

    MCP clients send validated models, but direct callers (and the all-tools
    smoke harness) pass raw dicts. The dict is validated into the annotated
    input model; any failure, validation included, becomes an error response.

    Args:
        fn: A tool coroutine taking one ``input_data`` model.

    Returns:
        Callable[..., Awaitable[dict[str, Any]]]: The guarded tool.
    """

    @functools.wraps(fn)
    async def wrapper(input_data: Any = None) -> dict[str, Any]:
        try:
            model = get_type_hints(fn).get("input_data")
            if not isinstance(input_data, BaseModel) and model is not None:
                input_data = model.model_validate(input_data or {})
            return await fn(input_data)
        except AttributeError as e:
            if "has no attribute" not in str(e):
                raise
            return {
                "status": "error",
                "message": f"Active adapter does not support {fn.__name__}; nothing was done.",
            }
        except Exception as e:
            logger.error(f"Error in {fn.__name__} tool: {e}")
            return {
                "status": "error",
                "message": f"Invalid input or unexpected error: {e}",
            }

    return wrapper


async def _run(
    call: Callable[..., Awaitable[Any]], describe: str, *args: Any
) -> dict[str, Any]:
    """Call one adapter method and shape the standard tool response.

    Args:
        call: The bound adapter method, e.g. ``adapter.get_material``.
        describe: Short description used in success / error messages.
        *args: Positional arguments for the adapter method.

    Returns:
        dict[str, Any]: ``status``, ``message`` and, on success, ``data``.
    """
    method = getattr(call, "__name__", "operation")
    try:
        result = await call(*args)
    except Exception as e:
        logger.error(f"Error in {method} tool: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}
    if result.is_success:
        return {
            "status": "success",
            "message": f"Successfully {describe}",
            "data": result.data,
            "execution_time": result.execution_time,
        }
    return {"status": "error", "message": result.error or f"{method} failed"}


async def register_drawing_automation_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register drawing-automation tools with FastMCP.

    Args:
        mcp (FastMCP): The MCP server.
        adapter (SolidWorksAdapter): Adapter used by every tool.
        config (dict[str, Any]): Server configuration (unused).

    Returns:
        int: Number of tools registered.
    """

    @mcp.tool()
    @_guard
    async def insert_model_dimensions(
        input_data: InsertModelDimensionsInput,
    ) -> dict[str, Any]:
        """Bring the model's dimensions into drawing views (auto-dimension).

        Imports the model's "marked for drawing" dimensions and falls back to
        SolidWorks AutoDimension for any view that stays empty. The response
        gives before/after dimension counts and the method used per view.
        """
        return await _run(
            adapter.insert_model_dimensions,
            "inserted model dimensions",
            input_data.view_name,
            input_data.include_hole_wizard,
        )

    @mcp.tool()
    @_guard
    async def arrange_dimensions(input_data: ArrangeDimensionsInput) -> dict[str, Any]:
        """Move drawing dimensions so nothing overlaps, then verify on the real geometry.

        Dimensions go outside the views in rows (first 8 mm out, rows 7 mm,
        columns 9 mm). Returns an error listing every remaining overlap if the
        rule cannot be met.
        """
        return await _run(
            adapter.arrange_dimensions, "arranged dimensions", input_data.view_name
        )

    return 2
