"""Engineering-data tools: dimensions, measurement, material, properties, flat pattern.

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

# Formats ExportToDWG2 writes a flat pattern to.
_FLAT_PATTERN_SUFFIXES = (".dxf", ".dwg")


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
        "Use list_available_materials to find it.",
        min_length=1,
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
        description="Property name, e.g. 'PartNo', 'Description', 'DrawnBy'",
        min_length=1,
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

    def model_post_init(self, __context: Any) -> None:
        """Refuse an output path that is not a DXF or DWG file.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: When ``file_path`` does not end in ``.dxf`` or ``.dwg``.
        """
        if not self.file_path.lower().endswith(_FLAT_PATTERN_SUFFIXES):
            raise ValueError(
                f"file_path must end in .dxf or .dwg, got {self.file_path!r}"
            )


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
        """List every dimension in the active part or assembly with its full name and value.

        Use it to find a dimension in an existing model before changing it: each
        `full_name` (e.g. "D1@Sketch1") is the name `get_dimension` and `set_dimension`
        take. Needs: an open part or assembly. Read-only. Returns: `data`, one entry per
        dimension with `full_name`, `feature`, `value` (document units), `system_value`
        (metres or radians) and `read_only`.

        Args:
            input_data: Nothing is required: give `feature_name` to list one
                feature's dimensions, or omit it for every dimension.

        Returns:
            dict[str, Any]: The dimensions.
        """
        input_data = normalize_input(input_data, ListModelDimensionsInput)
        _supports("list_model_dimensions")
        result = await adapter.list_model_dimensions(input_data.feature_name)
        require_success(result, context="Failed to list model dimensions")
        return _success(result, f"Listed {len(result.data or [])} dimension(s)")

    @mcp.tool()
    async def measure_entities(input_data: MeasureEntitiesInput) -> dict[str, Any]:
        """Measure faces, edges or vertices of the active model with SolidWorks' Measure tool.

        One face gives area and perimeter; one edge its length, and radius and diameter
        for an arc; two entities give the distance and angle between them. Use it to
        check a feature's size or position; for the whole model, use `verify_model`.
        Needs: an open part or assembly. Read-only. It clears the selection afterwards.
        Returns: `data` with `selected` and the values in metres, square metres and
        radians (`distance_m`, `angle_rad`, `length_m`, `radius_m`, `diameter_m`,
        `area_m2`, `perimeter_m`; for two entities `is_parallel`).

        Args:
            input_data: What to measure. `entities` (one or two) is required, each
                "face:x,y,z", "edge:x,y,z", "vertex:x,y,z" (a point on it, in metres)
                or a name like "Edge<1>".

        Returns:
            dict[str, Any]: The measurements.
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
        """Report the material assigned to the active part.

        Use it before `calculate_mass_properties` or `verify_model` with a mass: without
        a material SolidWorks uses a default density. Needs: an open, active part (any
        other document is `wrong_document_type`). Read-only. Returns: `data` with
        `material` (null when none is assigned), `database` and `density_kg_m3` (from
        the material's library entry; null when unknown). For the other properties
        (modulus, strength), open the material in SolidWorks.

        Args:
            input_data: Nothing is required: `configuration` defaults to the active
                one.

        Returns:
            dict[str, Any]: The material.
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
        """Assign a library material to the active part, e.g. "AISI 1020" or "6061-T6 (SS)".

        The material sets the mass and what a title block's Material field shows. The
        name must match the library exactly; find it with `list_available_materials`.
        The material is read back, so success means it applied. Needs: an open, active
        part. Changes: the part's material. Returns: `data` with `material`, `database`
        and `configuration`.

        Args:
            input_data: The material. `material_name` is required; `database`
                ("SOLIDWORKS Materials") and `configuration` (all) have defaults.

        Returns:
            dict[str, Any]: The material assigned.
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
        """List the materials in the installed SolidWorks material libraries.

        Use it to find the exact name `set_material` needs; filter with `search` (e.g.
        "steel" or "6061"). It reads every .sldmat library SolidWorks is set to use.
        Needs: SolidWorks installed. Read-only. Returns: `data`, each material's `name`,
        `classification` and `database`; the message gives the total and the folders
        read, so an empty search can be told from a missing library.

        Args:
            input_data: Nothing is required: `search` filters by name or
                classification, not case-sensitive.

        Returns:
            dict[str, Any]: The materials.
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
        """Read the active document's custom properties, such as PartNo, Description or Revision.

        File-level properties (the default) are what drawing title blocks and BOMs
        usually read; give `configuration` for that configuration's own. Needs: an open,
        active document. Read-only. Returns: `data` with `properties`, each name mapped
        to its `value` and `resolved` value (a $PRP link evaluated).

        Args:
            input_data: Nothing is required: `configuration` reads that
                configuration's properties instead of the file's.

        Returns:
            dict[str, Any]: The properties.
        """
        input_data = normalize_input(input_data, CustomPropertiesInput)
        _supports("get_custom_properties")
        result = await adapter.get_custom_properties(input_data.configuration)
        require_success(result, context="Failed to read custom properties")
        count = len((result.data or {}).get("properties", {}))
        return _success(result, f"Read {count} custom propert(ies)")

    @mcp.tool()
    async def set_custom_property(input_data: SetCustomPropertyInput) -> dict[str, Any]:
        """Create or overwrite one text custom property on the active document, e.g. PartNo or DrawnBy.

        Use it to fill what a title block or BOM reads. The value is read back, so
        success means it was stored. Needs: an open, active document. Changes: writes
        the property, replacing one of the same name (save the file to keep it).
        Returns: `data` with `name`, `value`, `resolved` and `configuration`.

        Args:
            input_data: The property. `name` and `value` (text, or a link such as
                $PRP:"SW-Mass") are required; `configuration` defaults to file-level.

        Returns:
            dict[str, Any]: The property stored.
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
        """Export the active sheet-metal part's flat pattern to DXF or DWG, for laser or waterjet cutting.

        It writes the flat outline only, without bend lines or sketches. A part with no
        sheet-metal body is `not_found` and nothing is written. Needs: an open, active
        sheet-metal part. Changes: writes the file, replacing one already there.
        Returns: `data` with `file_path` and `size_bytes`.

        Args:
            input_data: The export. `file_path` (ending in .dxf or .dwg) is
                required.

        Returns:
            dict[str, Any]: The file written.
        """
        input_data = normalize_input(input_data, ExportFlatPatternInput)
        _supports("export_flat_pattern")
        result = await adapter.export_flat_pattern(input_data.file_path)
        require_success(result, context="Failed to export the flat pattern")
        written = (result.data or {}).get("file_path")
        return _success(result, f"Exported the flat pattern to {written}")

    return 8
