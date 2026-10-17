"""Engineering-data tools: model dimensions, measurement, material, custom properties.

These read and edit the data a drawing, BOM or analysis is built from. Every tool
calls a real adapter method (``adapters/solidworks/documentation.py``) and returns
the adapter's own result - nothing here is simulated.
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


class ListModelDimensionsInput(CompatInput):
    """Input schema for listing model dimensions.

    Attributes:
        feature_name (str | None): Only this feature's dimensions.
    """

    feature_name: str | None = Field(
        default=None,
        description="Only list this feature's dimensions, e.g. 'Boss-Extrude1'. "
        "Omit to list every dimension in the model.",
    )


class MeasureEntitiesInput(CompatInput):
    """Input schema for measuring entities.

    Attributes:
        entities (list[str]): One or two entity specs.
    """

    entities: list[str] = Field(
        description=(
            "One or two entities to measure. Each is 'face:x,y,z' (a point inside "
            "the face), 'edge:x,y,z', 'vertex:x,y,z', a bare 'x,y,z' (nearest "
            "edge) or a topology name like 'Edge<1>'. Coordinates are in metres. "
            "One face gives area/perimeter; one edge gives length/radius; two "
            "entities give distance and angle."
        ),
        min_length=1,
        max_length=2,
    )


class GetMaterialInput(CompatInput):
    """Input schema for reading a part's material.

    Attributes:
        configuration (str | None): Configuration name.
    """

    configuration: str | None = Field(
        default=None, description="Configuration; the active one when omitted"
    )


class SetMaterialInput(CompatInput):
    """Input schema for assigning a material.

    Attributes:
        material_name (str): Exact library material name.
        database (str | None): Material library name.
        configuration (str | None): Configuration name.
    """

    material_name: str = Field(
        description="Exact library name, e.g. 'AISI 1020', '6061-T6 (SS)', 'ABS'. "
        "Use list_available_materials to find it."
    )
    database: str | None = Field(
        default=None, description="Library; 'SOLIDWORKS Materials' when omitted"
    )
    configuration: str | None = Field(
        default=None, description="Configuration; all configurations when omitted"
    )


class ListMaterialsInput(CompatInput):
    """Input schema for listing materials.

    Attributes:
        search (str | None): Substring filter.
    """

    search: str | None = Field(
        default=None,
        description="Case-insensitive filter on material name or classification, "
        "e.g. 'steel' or '6061'",
    )


class CustomPropertiesInput(CompatInput):
    """Input schema for reading custom properties.

    Attributes:
        configuration (str | None): Configuration name.
    """

    configuration: str | None = Field(
        default=None,
        description="Configuration-specific properties; file-level (what title "
        "blocks usually read) when omitted",
    )


class SetCustomPropertyInput(CompatInput):
    """Input schema for writing one custom property.

    Attributes:
        name (str): Property name.
        value (str): Property value.
        configuration (str | None): Configuration name.
    """

    name: str = Field(
        description="Property name, e.g. 'PartNo', 'Description', 'DrawnBy'"
    )
    value: str = Field(description='Text value; may be a $PRP:"SW-Mass" style link')
    configuration: str | None = Field(
        default=None, description="Configuration; file-level when omitted"
    )


class ExportFlatPatternInput(CompatInput):
    """Input schema for sheet-metal flat-pattern export.

    Attributes:
        file_path (str): Output .dxf or .dwg path.
    """

    file_path: str = Field(description="Output path ending in .dxf or .dwg")


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


async def register_engineering_data_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register engineering-data tools with FastMCP.

    Args:
        mcp (FastMCP): The MCP server.
        adapter (SolidWorksAdapter): Adapter used by every tool.
        config (dict[str, Any]): Server configuration (unused).

    Returns:
        int: Number of tools registered.
    """

    @mcp.tool()
    @_guard
    async def list_model_dimensions(
        input_data: ListModelDimensionsInput,
    ) -> dict[str, Any]:
        """List every dimension in the active part or assembly with its full name.

        Each ``full_name`` (e.g. ``"D1@Sketch1"``) can be passed to
        ``set_dimension`` to change that parameter, so this is the way to find
        and edit any driving dimension in an existing model.
        """
        return await _run(
            adapter.list_model_dimensions,
            "listed model dimensions",
            input_data.feature_name,
        )

    @mcp.tool()
    @_guard
    async def measure_entities(input_data: MeasureEntitiesInput) -> dict[str, Any]:
        """Measure faces, edges or vertices with SolidWorks' Measure tool.

        Returns distance, angle, radius, diameter, length, area and perimeter as
        applicable (SI units: metres, square metres, radians).
        """
        return await _run(
            adapter.measure_entities, "measured entities", input_data.entities
        )

    @mcp.tool()
    @_guard
    async def get_material(input_data: GetMaterialInput) -> dict[str, Any]:
        """Read the material assigned to the active part."""
        return await _run(
            adapter.get_material, "read the material", input_data.configuration
        )

    @mcp.tool()
    @_guard
    async def set_material(input_data: SetMaterialInput) -> dict[str, Any]:
        """Assign a library material to the active part (drives mass properties)."""
        return await _run(
            adapter.set_material,
            f"assigned {input_data.material_name}",
            input_data.material_name,
            input_data.database,
            input_data.configuration,
        )

    @mcp.tool()
    @_guard
    async def list_available_materials(
        input_data: ListMaterialsInput,
    ) -> dict[str, Any]:
        """List materials in the SolidWorks material libraries, optionally filtered."""
        return await _run(
            adapter.list_available_materials, "listed materials", input_data.search
        )

    @mcp.tool()
    @_guard
    async def get_custom_properties(
        input_data: CustomPropertiesInput,
    ) -> dict[str, Any]:
        """Read the active document's custom properties (title block / BOM data)."""
        return await _run(
            adapter.get_custom_properties,
            "read custom properties",
            input_data.configuration,
        )

    @mcp.tool()
    @_guard
    async def set_custom_property(input_data: SetCustomPropertyInput) -> dict[str, Any]:
        """Create or overwrite one text custom property on the active document."""
        return await _run(
            adapter.set_custom_property,
            f"set custom property {input_data.name}",
            input_data.name,
            input_data.value,
            input_data.configuration,
        )

    @mcp.tool()
    @_guard
    async def export_flat_pattern(input_data: ExportFlatPatternInput) -> dict[str, Any]:
        """Export the active sheet-metal part's flat pattern to DXF or DWG."""
        return await _run(
            adapter.export_flat_pattern,
            f"exported the flat pattern to {input_data.file_path}",
            input_data.file_path,
        )

    return 8
