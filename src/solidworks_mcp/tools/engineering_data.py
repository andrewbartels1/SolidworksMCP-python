"""Engineering-data tools: model dimensions, measurement, material, custom properties.

These read and edit the data a drawing, BOM or analysis is built from. Every tool
calls a real adapter method (``adapters/solidworks/documentation.py``) and returns
the adapter's own result - nothing here is simulated.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import AdapterResult, SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


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


def _success(result: AdapterResult[Any], message: str) -> dict[str, Any]:
    """Shape a successful adapter result as the standard tool response.

    Args:
        result: The adapter's successful result.
        message: What was done, for the ``message`` field.

    Returns:
        dict[str, Any]: ``status``, ``message``, ``data`` and ``execution_time``.
    """
    return {
        "status": "success",
        "message": message,
        "data": result.data,
        "execution_time": result.execution_time,
    }


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

    mcp = with_tool_boundary(mcp)

    def _supports(method: str) -> None:
        require_capability(
            adapter,
            method,
            f"The active adapter does not support {method}; nothing was done.",
        )

    @mcp.tool()
    async def list_model_dimensions(
        input_data: ListModelDimensionsInput | None = None,
    ) -> dict[str, Any]:
        """List every dimension in the active part or assembly with its full name.

        Read-only. Each entry's ``full_name`` (e.g. ``"D1@Sketch1"``) is the
        name ``set_dimension`` / ``get_dimension`` accept, so this is how to
        find and edit any driving dimension in an existing model. Pass
        ``feature_name`` to list one feature's dimensions only.

        Returns:
            dict[str, Any]: ``data`` is a list of ``{full_name, feature, value
            (document units), system_value (metres or radians), read_only}``.
            ``not_found`` when ``feature_name`` has no dimensions;
            ``wrong_document_type`` on a drawing.
        """
        input_data = normalize_input(input_data, ListModelDimensionsInput)
        _supports("list_model_dimensions")
        result = await adapter.list_model_dimensions(input_data.feature_name)
        require_success(result, context="Failed to list model dimensions")
        return _success(result, f"Listed {len(result.data or [])} dimension(s)")

    @mcp.tool()
    async def measure_entities(input_data: MeasureEntitiesInput) -> dict[str, Any]:
        """Measure faces, edges or vertices with SolidWorks' Measure tool.

        One face gives its area and perimeter; one edge its length (and radius
        and diameter for an arc); two entities give the distance and angle
        between them. Entity coordinates are in metres. Clears the selection
        afterwards.

        Returns:
            dict[str, Any]: ``data`` holds ``selected`` plus whichever of
            ``distance_m``, ``center_distance_m``, ``angle_rad``, ``radius_m``,
            ``diameter_m``, ``length_m``, ``arc_length_m``, ``area_m2``,
            ``perimeter_m``, ``delta_x_m``/``_y_m``/``_z_m`` and
            ``is_parallel`` apply to the selection.
        """
        input_data = normalize_input(input_data, MeasureEntitiesInput)
        _supports("measure_entities")
        result = await adapter.measure_entities(input_data.entities)
        require_success(result, context="Failed to measure")
        return _success(result, f"Measured {', '.join(input_data.entities)}")

    @mcp.tool()
    async def get_material(
        input_data: GetMaterialInput | None = None,
    ) -> dict[str, Any]:
        """Read the material assigned to the active part.

        Read-only. Parts only (``wrong_document_type`` otherwise).

        Returns:
            dict[str, Any]: ``data`` is ``{material, database, configuration}``;
            ``material`` is ``None`` when none is assigned.
        """
        input_data = normalize_input(input_data, GetMaterialInput)
        _supports("get_material")
        result = await adapter.get_material(input_data.configuration)
        require_success(result, context="Failed to read the material")
        material = (result.data or {}).get("material")
        return _success(
            result, f"Material: {material}" if material else "No material assigned"
        )

    @mcp.tool()
    async def set_material(input_data: SetMaterialInput) -> dict[str, Any]:
        """Assign a library material to the active part.

        The material drives mass properties (``get_mass_properties``) and what
        a title block's Material field shows. The name must match the library
        exactly; find it with ``list_available_materials``. The material is
        read back after assignment, so success means it really applied.

        Returns:
            dict[str, Any]: ``data`` is ``{material, database, configuration}``
            as read back from the part.
        """
        input_data = normalize_input(input_data, SetMaterialInput)
        _supports("set_material")
        result = await adapter.set_material(
            input_data.material_name, input_data.database, input_data.configuration
        )
        require_success(result, context="Failed to assign the material")
        return _success(result, f"Assigned {input_data.material_name}")

    @mcp.tool()
    async def list_available_materials(
        input_data: ListMaterialsInput | None = None,
    ) -> dict[str, Any]:
        """List materials in the installed SolidWorks material libraries.

        Read-only; parses every ``.sldmat`` library SolidWorks is configured
        to use. Filter with ``search`` (name or classification substring, e.g.
        ``"steel"`` or ``"6061"``) and pass the exact ``name`` to
        ``set_material``.

        Returns:
            dict[str, Any]: ``data`` is a list of ``{name, classification,
            database}``; ``message`` says how many of the libraries' materials
            matched and which folders were read.
        """
        input_data = normalize_input(input_data, ListMaterialsInput)
        _supports("list_available_materials")
        result = await adapter.list_available_materials(input_data.search)
        require_success(result, context="Failed to list materials")
        searched = result.metadata or {}
        found = len(result.data or [])
        message = f"Found {found} material(s)"
        if "total" in searched:
            message += (
                f" of {searched['total']} in {'; '.join(searched.get('folders', []))}"
            )
        return _success(result, message)

    @mcp.tool()
    async def get_custom_properties(
        input_data: CustomPropertiesInput | None = None,
    ) -> dict[str, Any]:
        """Read the active document's custom properties.

        Read-only. File-level properties (the default) are what drawing title
        blocks and BOMs usually link to; pass ``configuration`` for
        configuration-specific ones.

        Returns:
            dict[str, Any]: ``data`` is ``{configuration, properties}``, where
            ``properties`` maps each name to ``{value, resolved}`` (``value``
            may be a ``$PRP:`` link; ``resolved`` is what it evaluates to).
        """
        input_data = normalize_input(input_data, CustomPropertiesInput)
        _supports("get_custom_properties")
        result = await adapter.get_custom_properties(input_data.configuration)
        require_success(result, context="Failed to read custom properties")
        count = len((result.data or {}).get("properties", {}))
        return _success(result, f"Read {count} custom propert(ies)")

    @mcp.tool()
    async def set_custom_property(input_data: SetCustomPropertyInput) -> dict[str, Any]:
        """Create or overwrite one text custom property on the active document.

        Typical names: ``PartNo``, ``Description``, ``DrawnBy``, ``Revision``.
        The value is read back after writing, so success means it was stored.

        Returns:
            dict[str, Any]: ``data`` is ``{name, value, resolved,
            configuration}`` as read back.
        """
        input_data = normalize_input(input_data, SetCustomPropertyInput)
        _supports("set_custom_property")
        result = await adapter.set_custom_property(
            input_data.name, input_data.value, input_data.configuration
        )
        require_success(result, context="Failed to set the custom property")
        return _success(result, f"Set custom property {input_data.name}")

    @mcp.tool()
    async def export_flat_pattern(input_data: ExportFlatPatternInput) -> dict[str, Any]:
        """Export the active sheet-metal part's flat pattern to DXF or DWG.

        Exports the flat-pattern geometry only (no bend lines or sketches),
        for laser or waterjet cutting. Fails with a clear message when the
        part has no sheet-metal body.

        Returns:
            dict[str, Any]: ``data`` is ``{file_path, size_bytes}`` of the
            written file.
        """
        input_data = normalize_input(input_data, ExportFlatPatternInput)
        _supports("export_flat_pattern")
        result = await adapter.export_flat_pattern(input_data.file_path)
        require_success(result, context="Failed to export the flat pattern")
        written = (result.data or {}).get("file_path")
        return _success(result, f"Exported the flat pattern to {written}")

    return 8
