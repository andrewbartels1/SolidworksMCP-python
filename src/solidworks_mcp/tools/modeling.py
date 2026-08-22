"""Modeling tools for SolidWorks MCP Server.

Provides tools for creating and manipulating SolidWorks models, including parts,
assemblies, drawings, and features like extrusions, revolves, etc.
"""

from typing import Any, TypeVar

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from ..adapters.base import (
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SolidWorksAdapter,
    SweepParameters,
)
from .input_compat import CompatInput

TInput = TypeVar("TInput", bound=BaseModel)


# Input schemas using Python 3.14 built-in types


def _result_value(data: Any, *keys: str, default: Any = None) -> Any:
    """Build internal result value.

    Args:
        data (Any): The data value.
        *keys (str): Additional positional arguments forwarded to the call.
        default (Any): Fallback value returned when the operation fails. Defaults to None.

    Returns:
        Any: The result produced by the operation.
    """
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    for key in keys:
        if hasattr(data, key):
            value = getattr(data, key)
            if value is not None:
                return value
    return default


def _normalize_input(input_data: Any, model_type: type[TInput]) -> TInput:
    """Build internal normalize input.

    Args:
        input_data (Any): The input data value.
        model_type (type[TInput]): The model type value.

    Returns:
        TInput: The result produced by the operation.
    """
    if isinstance(input_data, model_type):
        return input_data
    return model_type.model_validate(input_data)


class OpenModelInput(BaseModel):
    """Input schema for opening a SolidWorks model.

    Attributes:
        file_path (str): The file path value.
    """

    file_path: str = Field(
        description="Full path to the SolidWorks file (.sldprt, .sldasm, .slddrw)"
    )


class CreatePartInput(CompatInput):
    """Input schema for creating a new SolidWorks part.

    Attributes:
        material (str | None): The material value.
        name (str): The name value.
        template (str | None): The template value.
        units (str | None): The units value.
    """

    name: str = Field(description="Name for the new part")
    template: str | None = Field(
        default=None, description="Template file path for the new part"
    )
    units: str | None = Field(default=None, description="Document units")
    material: str | None = Field(default=None, description="Material name")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create part input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if not self.name.strip():
            raise ValueError("name is required")


class CreateExtrusionInput(CompatInput):
    """Input schema for creating an extrusion feature.

    Attributes:
        both_directions (bool): The both directions value.
        depth (float): The depth value.
        direction (str): The direction value.
        draft_angle (float): The draft angle value.
        end_condition (str): The end condition value.
        merge_result (bool): The merge result value.
        reverse (bool | None): The reverse value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str): The sketch name value.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
    """

    sketch_name: str = Field(description="Sketch name to extrude")
    depth: float = Field(description="Extrusion depth in millimeters")
    direction: str = Field(default="blind", description="Extrusion direction")
    reverse: bool | None = Field(default=None, description="Reverse direction alias")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(
        default=False, description="Reverse extrusion direction"
    )
    both_directions: bool = Field(
        default=False, description="Extrude in both directions"
    )
    thin_feature: bool = Field(default=False, description="Create as thin wall feature")
    thin_thickness: float | None = Field(
        default=None, description="Thickness for thin wall feature in mm"
    )
    end_condition: str = Field(default="Blind", description="End condition type")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create extrusion input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Sketch_name is required.
        """
        if self.depth <= 0:
            raise ValueError("depth must be positive")
        if not self.sketch_name.strip():
            raise ValueError("sketch_name is required")
        if self.reverse is not None:
            self.reverse_direction = self.reverse


class CreateRevolveInput(CompatInput):
    """Input schema for creating a revolve feature.

    Attributes:
        angle (float): The angle value.
        axis_entity (str): The axis entity value.
        both_directions (bool): The both directions value.
        direction (str): The direction value.
        merge_result (bool): The merge result value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str): The sketch name value.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
    """

    sketch_name: str = Field(description="Sketch name to revolve")
    axis_entity: str = Field(description="Axis entity for the revolve")
    angle: float = Field(description="Revolve angle in degrees")
    direction: str = Field(default="one_direction", description="Revolve direction")
    reverse_direction: bool = Field(
        default=False, description="Reverse revolve direction"
    )
    both_directions: bool = Field(
        default=False, description="Revolve in both directions"
    )
    thin_feature: bool = Field(default=False, description="Create as thin wall feature")
    thin_thickness: float | None = Field(
        default=None, description="Thickness for thin wall feature in mm"
    )
    merge_result: bool = Field(default=True, description="Merge with existing geometry")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create revolve input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Angle must be positive.
        """
        if self.angle <= 0:
            raise ValueError("angle must be positive")


class CreateSweepInput(BaseModel):
    """Input schema for creating a sweep feature.

    Attributes:
        merge_result (bool): The merge result value.
        path (str): The path value.
        twist_along_path (bool): The twist along path value.
        twist_angle (float): The twist angle value.
    """

    path: str = Field(description="Name or ID of the sweep path")
    twist_along_path: bool = Field(default=False, description="Twist along path")
    twist_angle: float = Field(default=0.0, description="Twist angle in degrees")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")


class CreateLoftInput(BaseModel):
    """Input schema for creating a loft feature.

    Attributes:
        end_tangent (str | None): The end tangent value.
        guide_curves (list[str] | None): The guide curves value.
        merge_result (bool): The merge result value.
        profiles (list[str]): The profiles value.
        start_tangent (str | None): The start tangent value.
    """

    profiles: list[str] = Field(description="List of profile names or IDs")
    guide_curves: list[str] | None = Field(
        default=None, description="List of guide curve names or IDs"
    )
    start_tangent: str | None = Field(
        default=None, description="Start tangent condition"
    )
    end_tangent: str | None = Field(default=None, description="End tangent condition")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")


class GetDimensionInput(CompatInput):
    """Input schema for getting a dimension value.

    Attributes:
        dimension_name (str | None): The dimension name value.
        name (str | None): The name value.
    """

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the get dimension input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class SetDimensionInput(CompatInput):
    """Input schema for setting a dimension value.

    Attributes:
        dimension_name (str | None): The dimension name value.
        name (str | None): The name value.
        units (str | None): The units value.
        value (float): The value value.
    """

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")
    value: float = Field(description="New dimension value in millimeters")
    units: str | None = Field(default=None, description="Units alias")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the set dimension input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class CloseModelInput(BaseModel):
    """Input schema for closing a model.

    Attributes:
        save (bool): The save value.
    """

    save: bool = Field(default=False, description="Save the model before closing")


class CreateCutExtrudeInput(CompatInput):
    """Input schema for creating a cut-extrude feature.

    Attributes:
        depth (float): Cut depth in millimeters.
        draft_angle (float): Draft angle in degrees.
        end_condition (str): End condition type.
        reverse_direction (bool): Reverse cut direction.
    """

    depth: float = Field(description="Cut depth in millimeters")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(default=False, description="Reverse cut direction")
    end_condition: str = Field(default="Blind", description="End condition type")

    def model_post_init(self, __context: Any) -> None:
        if self.depth <= 0:
            raise ValueError("depth must be positive")


class AddFilletInput(CompatInput):
    """Input schema for adding a fillet feature.

    Attributes:
        edge_names (list[str]): Edge names to fillet.
        radius (float): Fillet radius in millimeters.
    """

    radius: float = Field(description="Fillet radius in millimeters")
    edge_names: list[str] = Field(
        default_factory=list,
        description="Named edges to fillet (e.g. 'Edge<1>'). Leave empty to fillet all edges.",
    )

    def model_post_init(self, __context: Any) -> None:
        if self.radius <= 0:
            raise ValueError("radius must be positive")


class CreateAssemblyInput(CompatInput):
    """Input schema for creating a new assembly.

    Attributes:
        components (list[str]): The components value.
        name (str): The name value.
        template (str | None): The template value.
    """

    name: str = Field(description="Name for the new assembly")
    template: str | None = Field(
        default=None, description="Assembly template file path"
    )
    components: list[str] = Field(default_factory=list, description="Component list")


class InsertComponentInput(CompatInput):
    """Input schema for inserting a component into an assembly.

    Attributes:
        file_path (str): Path to the part or sub-assembly.
        x (float): X position in millimetres.
        y (float): Y position in millimetres.
        z (float): Z position in millimetres.
    """

    file_path: str = Field(
        description="Absolute path to the .sldprt or .sldasm to insert"
    )
    x: float = Field(default=0.0, description="X position in millimetres")
    y: float = Field(default=0.0, description="Y position in millimetres")
    z: float = Field(default=0.0, description="Z position in millimetres")

    def model_post_init(self, __context: Any) -> None:
        if not self.file_path.strip():
            raise ValueError("file_path is required")


class DeleteFeatureInput(CompatInput):
    """Input schema for deleting a feature.

    Attributes:
        name (str): Feature or sketch name to delete.
    """

    name: str = Field(
        description="Feature or sketch name, e.g. 'Boss-Extrude1' or 'Sketch1'"
    )


class SuppressFeatureInput(CompatInput):
    """Input schema for suppressing or unsuppressing a feature.

    Attributes:
        name (str): Feature name to toggle.
        suppress (bool): True to suppress, False to unsuppress.
    """

    name: str = Field(description="Feature name, e.g. 'Fillet1'")
    suppress: bool = Field(
        default=True, description="True to suppress, False to unsuppress"
    )


class UndoInput(CompatInput):
    """Input schema for undoing model operations.

    Attributes:
        count (int): Number of operations to undo.
    """

    count: int = Field(default=1, ge=1, description="Number of operations to undo")


class AddMateInput(CompatInput):
    """Input schema for mating two assembly components.

    Attributes:
        component_a (str): First component instance name.
        component_b (str): Second component instance name.
        entity_a (str): Named feature on the first component.
        entity_b (str): Named feature on the second component.
        mate_type (str): Mate type.
        alignment (str): Mate alignment.
        distance (float): Distance in millimetres for a distance mate.
        angle (float): Angle in degrees for an angle mate.
    """

    component_a: str = Field(
        description="First component instance name, as reported by list_components"
    )
    component_b: str = Field(description="Second component instance name")
    entity_a: str = Field(
        default="Front Plane",
        description=(
            "Named feature on the first component. Only tree features "
            "(reference planes and axes) can be selected"
        ),
    )
    entity_b: str = Field(
        default="Front Plane", description="Named feature on the second component"
    )
    mate_type: str = Field(
        default="coincident",
        description=(
            "coincident, concentric, perpendicular, parallel, tangent, "
            "distance or angle"
        ),
    )
    alignment: str = Field(
        default="aligned", description="aligned, anti_aligned or closest"
    )
    distance: float = Field(
        default=0.0, description="Distance in millimetres, for a distance mate"
    )
    angle: float = Field(default=0.0, description="Angle in degrees, for an angle mate")

    def model_post_init(self, __context: Any) -> None:
        if not self.component_a.strip() or not self.component_b.strip():
            raise ValueError("component_a and component_b are required")


class CreateReferencePlaneInput(CompatInput):
    """Input schema for creating a reference plane.

    Attributes:
        reference (str): Name of the reference plane or planar face.
        offset (float): Offset distance in millimetres.
        angle (float): Angle in degrees.
        flip (bool): Reverse the offset or angle direction.
    """

    reference: str = Field(
        description="Name of the reference plane or planar face to offset "
        "from, e.g. 'Front Plane'"
    )
    offset: float = Field(
        default=0.0,
        description="Offset distance in millimetres. Must be non-zero — a "
        "plane coincident with its reference is not useful",
    )
    angle: float = Field(
        default=0.0,
        description="Angle in degrees. Not yet supported: an angled plane "
        "needs a second reference this tool cannot take, so a non-zero "
        "value errors. Use offset for parallel planes",
    )
    flip: bool = Field(default=False, description="Reverse the offset direction")

    def model_post_init(self, __context: Any) -> None:
        if not self.reference.strip():
            raise ValueError("reference is required")


class CreateAxisInput(CompatInput):
    """Input schema for creating a reference axis.

    Attributes:
        reference (str): Principal axis direction.
    """

    reference: str = Field(
        description="Principal axis direction: 'x', 'y' or 'z' "
        "(case-insensitive; a leading +/- is stripped)"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.reference.strip():
            raise ValueError("reference is required")


class CreateDrawingInput(CompatInput):
    """Input schema for creating a new drawing.

    Attributes:
        model_path (str | None): The model path value.
        name (str): The name value.
        sheet_format (str | None): The sheet format value.
        template (str | None): The template value.
    """

    name: str = Field(description="Name for the new drawing")
    template: str | None = Field(default=None, description="Drawing template file path")
    model_path: str | None = Field(default=None, description="Source model path")
    sheet_format: str | None = Field(default=None, description="Sheet format template")


async def register_modeling_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register modeling tools with FastMCP.

    Registers comprehensive modeling tools for SolidWorks automation including model
    creation, feature creation, and model management operations.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.modeling import register_modeling_tools

                        tool_count = await register_modeling_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} modeling tools")
                        ```
    """
    tool_count = 0

    @mcp.tool()
    async def open_model(input_data: OpenModelInput) -> dict[str, Any]:
        """Open a SolidWorks model (part, assembly, or drawing).

        Opens an existing SolidWorks file and makes it the active document for further
        operations. Supports all standard SolidWorks file formats and provides detailed model
        information upon successful opening.

        Args:
            input_data (OpenModelInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await open_model({
                                "file_path": "C:/Models/bracket.sldprt"
                            })

                            if result["status"] == "success":
                                model = result["model"]
                                print(f"Opened {model['type']}: {model['name']}")
                                print(f"Configuration: {model['configuration']}")
                            ```

                        Note:
                            File path must be absolute and accessible to SolidWorks.
                            Model becomes the active document for subsequent operations.
        """
        try:
            input_data = _normalize_input(input_data, OpenModelInput)
            result = await adapter.open_model(input_data.file_path)

            if result.is_success:
                model = result.data
                title = _result_value(
                    model, "title", "name", default=input_data.file_path
                )
                model_type = _result_value(model, "type", default="Part")
                path = _result_value(
                    model, "path", "file_path", default=input_data.file_path
                )
                configuration = _result_value(model, "configuration", default="Default")
                return {
                    "status": "success",
                    "message": f"Opened {model_type}: {title}",
                    "model": {
                        "title": title,
                        "name": title,
                        "type": model_type,
                        "path": path,
                        "configuration": configuration,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to open model: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in open_model tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_part(input_data: CreatePartInput) -> dict[str, Any]:
        """Create a new SolidWorks part document.

        Creates a new SolidWorks part document using the default part template. The new part
        becomes the active document and is ready for modeling operations such as sketch creation
        and feature addition.

        Args:
            input_data (CreatePartInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await create_part()

                            if result["status"] == "success":
                                part = result["model"]
                                print(f"Created new part: {part['name']}")
                                # Ready for sketching and feature creation
                            ```

                        Note:
                            - Uses default SolidWorks part template
                            - Part document is created in memory (not saved)
                            - Use save operations to persist to disk
                            - Subsequent modeling operations will apply to this part
        """
        try:
            input_data = _normalize_input(input_data, CreatePartInput)
            result = await adapter.create_part(input_data.name, input_data.units)

            if result.is_success:
                model = result.data
                part_name = _result_value(model, "name", default=input_data.name)
                units = _result_value(model, "units", default=input_data.units or "mm")
                return {
                    "status": "success",
                    "message": f"Created new part: {part_name}",
                    "part": {
                        "name": part_name,
                        "units": units,
                        "material": input_data.material,
                        "template": input_data.template,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create part: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in create_part tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_assembly(input_data: CreateAssemblyInput) -> dict[str, Any]:
        """Create a new SolidWorks assembly document.

        Creates a new SolidWorks assembly document using the default assembly template. The new
        assembly becomes the active document and is ready for component insertion, mating, and
        assembly-level operations.

        Args:
            input_data (CreateAssemblyInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await create_assembly()

                            if result["status"] == "success":
                                assembly = result["model"]
                                print(f"Created new assembly: {assembly['name']}")
                                # Ready for component insertion and mating
                            ```

                        Note:
                            - Uses default SolidWorks assembly template
                            - Assembly document is created in memory (not saved)
                            - Use save operations to persist to disk
                            - Ready for component insertion and mate creation
                            - Assembly tree will initially be empty

                        This tool creates a new assembly document using the default assembly template.
                        The new assembly will become the active document.
        """
        try:
            input_data = _normalize_input(input_data, CreateAssemblyInput)
            result = await adapter.create_assembly(input_data.name)

            if result.is_success:
                model = result.data
                assembly_name = _result_value(model, "name", default=input_data.name)
                return {
                    "status": "success",
                    "message": f"Created new assembly: {assembly_name}",
                    "assembly": {
                        "name": assembly_name,
                        "components": input_data.components,
                        "template": input_data.template,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create assembly: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in create_assembly tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_drawing(input_data: CreateDrawingInput) -> dict[str, Any]:
        """Create a new SolidWorks drawing document.

        This tool creates a new drawing document using the default drawing template. The new
        drawing will become the active document.

        Args:
            input_data (CreateDrawingInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        try:
            input_data = _normalize_input(input_data, CreateDrawingInput)
            result = await adapter.create_drawing(input_data.name)

            if result.is_success:
                model = result.data
                drawing_name = _result_value(model, "name", default=input_data.name)
                sheet_format = _result_value(
                    model, "sheet_format", default=input_data.sheet_format
                )
                return {
                    "status": "success",
                    "message": f"Created new drawing: {drawing_name}",
                    "drawing": {
                        "name": drawing_name,
                        "model_path": input_data.model_path,
                        "sheet_format": sheet_format,
                        "template": input_data.template,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create drawing: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in create_drawing tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def close_model(input_data: CloseModelInput) -> dict[str, Any]:
        """Close the current SolidWorks model.

        Closes the currently active SolidWorks document with an option to save changes before
        closing. This is essential for proper model lifecycle management and preventing data
        loss.

        Args:
            input_data (CloseModelInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Close without saving
                            result = await close_model({"save": False})

                            # Save and close
                            result = await close_model({"save": True})

                            if result["status"] == "success":
                                print(f"Model closed, saved: {result['saved']}")
                            ```

                        Note:
                            - Unsaved changes will be lost if save=False
                            - Always save important work before closing
                            - Model must be open to close it
        """
        try:
            input_data = _normalize_input(input_data, CloseModelInput)
            result = await adapter.close_model(input_data.save)

            if result.is_success:
                return {
                    "status": "success",
                    "message": "Model closed successfully",
                    "saved": input_data.save,
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to close model: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in close_model tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_extrusion(input_data: CreateExtrusionInput) -> dict[str, Any]:
        """Create an extrusion feature from the active sketch.

        Creates a 3D extrusion feature (boss or cut) from the currently active 2D sketch.
        Supports advanced options like draft angles, thin features, bidirectional extrusion, and
        various end conditions for professional modeling workflows.

        Args:
            input_data (CreateExtrusionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Simple boss extrusion
                            result = await create_extrusion({
                                "depth": 25.0,
                                "merge_result": True
                            })

                            # Cut with draft angle
                            result = await create_extrusion({
                                "depth": 10.0,
                                "reverse_direction": True,
                                "draft_angle": 2.0
                            })

                            # Thin wall feature
                            result = await create_extrusion({
                                "depth": 50.0,
                                "thin_feature": True,
                                "thin_thickness": 2.0
                            })
                            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateExtrusionInput)
            # Convert input to ExtrusionParameters
            params = ExtrusionParameters(
                depth=input_data.depth,
                draft_angle=input_data.draft_angle,
                reverse_direction=input_data.reverse_direction,
                both_directions=input_data.both_directions,
                thin_feature=input_data.thin_feature,
                thin_thickness=input_data.thin_thickness,
                end_condition=input_data.end_condition,
                merge_result=input_data.merge_result,
                feature_scope=False,
                auto_select=True,
            )

            result = await adapter.create_extrusion(params)

            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created extrusion: {_result_value(feature, 'feature_name', 'name', default='Extrusion')}",
                    "extrusion": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Extrusion"
                        ),
                        "sketch": input_data.sketch_name,
                        "depth": input_data.depth,
                        "direction": input_data.direction,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create extrusion: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in create_extrusion tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_revolve(input_data: CreateRevolveInput) -> dict[str, Any]:
        """Create a revolve feature from the active sketch.

        Creates a 3D revolve feature by rotating the active 2D sketch profile around a specified
        axis of revolution. Supports full and partial revolves, thin features, and bidirectional
        revolution for comprehensive rotational modeling.

        Args:
            input_data (CreateRevolveInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Full revolution (cylinder)
                            result = await create_revolve({
                                "angle": 360.0,
                                "merge_result": True
                            })

                            # Partial revolution (arc section)
                            result = await create_revolve({
                                "angle": 120.0,
                                "both_directions": True
                            })

                            # Thin wall revolution (pipe)
                            result = await create_revolve({
                                "angle": 360.0,
                                "thin_feature": True,
                                "thin_thickness": 3.0
                            })
                            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateRevolveInput)
            # Convert input to RevolveParameters
            params = RevolveParameters(
                angle=input_data.angle,
                reverse_direction=input_data.reverse_direction,
                both_directions=input_data.both_directions,
                thin_feature=input_data.thin_feature,
                thin_thickness=input_data.thin_thickness,
                merge_result=input_data.merge_result,
            )

            result = await adapter.create_revolve(params)

            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created revolve: {_result_value(feature, 'feature_name', 'name', default='Revolve')}",
                    "revolve": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Revolve"
                        ),
                        "sketch": input_data.sketch_name,
                        "axis_entity": input_data.axis_entity,
                        "angle": input_data.angle,
                        "direction": input_data.direction,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create revolve: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in create_revolve tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def get_dimension(input_data: GetDimensionInput) -> dict[str, Any]:
        """Get the value of a dimension from the current model.

        Retrieves the current value of a named dimension from the active SolidWorks model.
        Dimensions can be from sketches, features, or global dimensions. Useful for parametric
        modeling and design validation.

        Args:
            input_data (GetDimensionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Get sketch dimension
                            result = await get_dimension({
                                "name": "D1@Sketch1"
                            })

                            if result["status"] == "success":
                                dim = result["dimension"]
                                print(f"Dimension {dim['name']}: {dim['value']} {dim['units']}")

                            # Get feature dimension
                            result = await get_dimension({
                                "name": "D1@Boss-Extrude1"
                            })
                            ```
        """
        try:
            input_data = _normalize_input(input_data, GetDimensionInput)
            if not input_data.name:
                return {"status": "error", "message": "Dimension name is required"}
            result = await adapter.get_dimension(input_data.name)

            if result.is_success:
                value = result.data
                dimension_value = _result_value(value, "value", default=value)
                dimension_units = _result_value(value, "units", default="mm")
                return {
                    "status": "success",
                    "message": f"Dimension {input_data.name} = {dimension_value} {dimension_units}",
                    "dimension": {
                        "name": input_data.name,
                        "value": dimension_value,
                        "units": dimension_units,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to get dimension: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in get_dimension tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def set_dimension(input_data: SetDimensionInput) -> dict[str, Any]:
        """Set the value of a dimension in the current model.

        This tool modifies the value of a named dimension and rebuilds the model. Use this to
        parametrically modify your model dimensions.

        Args:
            input_data (SetDimensionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        try:
            input_data = _normalize_input(input_data, SetDimensionInput)
            if not input_data.name:
                return {"status": "error", "message": "Dimension name is required"}
            result = await adapter.set_dimension(input_data.name, input_data.value)

            if result.is_success:
                payload = result.data
                return {
                    "status": "success",
                    "message": f"Set dimension {input_data.name} = {input_data.value} mm",
                    "dimension_update": {
                        "name": input_data.name,
                        "old_value": _result_value(payload, "old_value"),
                        "new_value": _result_value(
                            payload, "new_value", default=input_data.value
                        ),
                        "units": input_data.units or "mm",
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to set dimension: {result.error}",
                }

        except Exception as e:
            logger.error(f"Error in set_dimension tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_cut_extrude(input_data: CreateCutExtrudeInput) -> dict[str, Any]:
        """Cut material from the active model using the current sketch profile.

        Creates a Cut-Extrude feature (Insert > Cut > Extrude) from the active sketch.
        Use this after exit_sketch when you want to remove material — e.g. to create
        windows, holes, slots, or any through/blind cut in an existing solid body.

        Args:
            input_data (CreateCutExtrudeInput): Depth, direction and draft parameters.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Cut a blind pocket 10 mm deep
            result = await create_cut_extrude({"depth": 10.0})

            # Through-all cut (use a depth larger than the solid)
            result = await create_cut_extrude({"depth": 200.0})
            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateCutExtrudeInput)
            params = ExtrusionParameters(
                depth=input_data.depth,
                draft_angle=input_data.draft_angle,
                reverse_direction=input_data.reverse_direction,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
                end_condition=input_data.end_condition,
                merge_result=False,
                feature_scope=False,
                auto_select=True,
            )
            result = await adapter.create_cut_extrude(params)
            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created cut-extrude: {_result_value(feature, 'feature_name', 'name', default='Cut-Extrude')}",
                    "cut_extrude": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Cut-Extrude"
                        ),
                        "depth": input_data.depth,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create cut-extrude: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in create_cut_extrude tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def add_fillet(input_data: AddFilletInput) -> dict[str, Any]:
        """Add a fillet (rounded edge) to selected edges of the current model.

        Rounds the specified named edges with the given radius. Edge names use the
        SolidWorks convention, e.g. 'Edge<1>', or you can leave edge_names empty to
        fillet all edges if the adapter supports it.

        Args:
            input_data (AddFilletInput): Radius and edge names.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Fillet two specific edges with 2 mm radius
            result = await add_fillet({"radius": 2.0, "edge_names": ["Edge<1>", "Edge<2>"]})
            ```
        """
        try:
            input_data = _normalize_input(input_data, AddFilletInput)
            result = await adapter.add_fillet(input_data.radius, input_data.edge_names)
            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created fillet: {_result_value(feature, 'feature_name', 'name', default='Fillet')}",
                    "fillet": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Fillet"
                        ),
                        "radius": input_data.radius,
                        "edges": input_data.edge_names,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to add fillet: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in add_fillet tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def create_sweep(input_data: CreateSweepInput) -> dict[str, Any]:
        """Sweep the active profile sketch along a named path sketch.

        Creates a swept boss/protrusion (Insert > Boss/Base > Sweep). Requires
        two sketches in the active part: a closed profile sketch and an open
        path sketch named by ``path``. The profile is inferred as the sketch
        that is not the path (in the usual "draw profile, draw path, sweep"
        flow this is unambiguous). Optionally applies a constant twist along
        the path.

        Args:
            input_data (CreateSweepInput): Path name and twist/merge options.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Sweep a circular profile along "Sketch2"
            result = await create_sweep({"path": "Sketch2"})

            # Sweep with a 90-degree twist along the path
            result = await create_sweep({
                "path": "Sketch2",
                "twist_along_path": True,
                "twist_angle": 90.0,
            })
            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateSweepInput)
            params = SweepParameters(
                path=input_data.path,
                twist_along_path=input_data.twist_along_path,
                twist_angle=input_data.twist_angle,
                merge_result=input_data.merge_result,
            )
            result = await adapter.create_sweep(params)
            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created sweep: {_result_value(feature, 'feature_name', 'name', default='Sweep')}",
                    "sweep": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Sweep"
                        ),
                        "path": input_data.path,
                        "twist_along_path": input_data.twist_along_path,
                        "twist_angle": input_data.twist_angle,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create sweep: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in create_sweep tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def create_loft(input_data: CreateLoftInput) -> dict[str, Any]:
        """Loft a solid between two or more profile sketches.

        Creates a lofted boss/protrusion (Insert > Boss/Base > Loft) blending
        the listed profile sketches in order. Each profile must be a closed
        contour. Optional guide curves shape the transition between profiles.

        Args:
            input_data (CreateLoftInput): Profile names, optional guide curves,
                and tangency/merge options.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Loft between two profiles (e.g. a tapered bevel)
            result = await create_loft({"profiles": ["Sketch1", "Sketch2"]})

            # Loft with guide curves
            result = await create_loft({
                "profiles": ["Sketch1", "Sketch2"],
                "guide_curves": ["Sketch3"],
            })
            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateLoftInput)
            params = LoftParameters(
                profiles=input_data.profiles,
                guide_curves=input_data.guide_curves,
                start_tangent=input_data.start_tangent,
                end_tangent=input_data.end_tangent,
                merge_result=input_data.merge_result,
            )
            result = await adapter.create_loft(params)
            if result.is_success:
                feature = result.data
                return {
                    "status": "success",
                    "message": f"Created loft: {_result_value(feature, 'feature_name', 'name', default='Loft')}",
                    "loft": {
                        "name": _result_value(
                            feature, "feature_name", "name", default="Loft"
                        ),
                        "profiles": input_data.profiles,
                        "guide_curves": input_data.guide_curves,
                    },
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create loft: {result.error}",
                }
        except Exception as e:
            logger.error(f"Error in create_loft tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def insert_component(input_data: InsertComponentInput) -> dict[str, Any]:
        """Insert a part or sub-assembly into the active assembly.

        Call ``create_assembly`` first. Position is in millimetres from the
        assembly origin.

        **The component file must contain solid geometry** — SolidWorks
        silently refuses to insert an empty part, so a missing or empty
        component surfaces as an error rather than a fabricated success.

        Args:
            input_data (InsertComponentInput): File path and position.

        Returns:
            dict[str, Any]: Status, the component's instance name and counts.

        Example:
            ```python
            await create_assembly({"name": "bracket_asm"})
            await insert_component({"file_path": "C:/parts/plate.sldprt"})
            await insert_component({"file_path": "C:/parts/plate.sldprt", "x": 100.0})
            ```
        """
        try:
            input_data = _normalize_input(input_data, InsertComponentInput)
            result = await adapter.insert_component(
                input_data.file_path, input_data.x, input_data.y, input_data.z
            )
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                return {
                    "status": "success",
                    "message": f"Inserted {data.get('component', 'component')}",
                    "component": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to insert component: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in insert_component tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def add_mate(input_data: AddMateInput) -> dict[str, Any]:
        """Mate two components in the active assembly.

        Positions components relative to one another — coincident planes to
        stack or align them, concentric to line up axes, distance to hold a
        gap.

        Entities are selected by feature name, so only each component's
        reference planes and axes can be mated. Mating to a specific face or
        edge needs entity names this adapter cannot enumerate.

        Args:
            input_data (AddMateInput): Components, entities and mate type.

        Returns:
            dict[str, Any]: Status and mate details.

        Example:
            ```python
            components = await list_components()
            await add_mate({
                "component_a": components["components"][0],
                "component_b": components["components"][1],
                "mate_type": "coincident",
            })
            ```
        """
        try:
            input_data = _normalize_input(input_data, AddMateInput)
            result = await adapter.add_mate(
                input_data.component_a,
                input_data.component_b,
                input_data.entity_a,
                input_data.entity_b,
                input_data.mate_type,
                input_data.alignment,
                input_data.distance,
                input_data.angle,
            )
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                message = (
                    f"Added {input_data.mate_type} mate between "
                    f"{input_data.component_a} and {input_data.component_b}"
                )
                # SolidWorks accepts a mate whose constraint is already
                # satisfied and moves nothing. That is a real success, but
                # saying so plainly beats leaving the caller to infer it.
                if data.get("geometry_moved") is False:
                    message += (
                        " (no component moved - the constraint was already "
                        "satisfied)"
                    )
                return {
                    "status": "success",
                    "message": message,
                    "mate": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to add mate: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in add_mate tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def list_components() -> dict[str, Any]:
        """List the top-level components of the active assembly.

        Returns:
            dict[str, Any]: Status and the component instance names.
        """
        try:
            result = await adapter.list_components()
            if result.is_success:
                components = result.data if isinstance(result.data, list) else []
                return {
                    "status": "success",
                    "message": f"{len(components)} component(s) in the assembly",
                    "components": components,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to list components: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in list_components tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def delete_feature(input_data: DeleteFeatureInput) -> dict[str, Any]:
        """Delete a feature or sketch from the active model.

        Deleting a parent feature also removes everything that depends on it —
        SolidWorks' normal cascade — so the response lists every feature that
        went, not just the one named.

        Args:
            input_data (DeleteFeatureInput): The feature to delete.

        Returns:
            dict[str, Any]: Status and what was removed.

        Example:
            ```python
            await delete_feature({"name": "Boss-Extrude1"})
            ```
        """
        try:
            input_data = _normalize_input(input_data, DeleteFeatureInput)
            result = await adapter.delete_feature(input_data.name)
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                removed = data.get("removed_features") or [input_data.name]
                return {
                    "status": "success",
                    "message": (
                        f"Deleted {input_data.name}"
                        + (
                            f" and {len(removed) - 1} dependent feature(s)"
                            if len(removed) > 1
                            else ""
                        )
                    ),
                    "data": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to delete feature: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in delete_feature tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def suppress_feature(input_data: SuppressFeatureInput) -> dict[str, Any]:
        """Suppress or unsuppress a feature in the active model.

        Suppressing rolls a feature and its children out of the model without
        deleting it — the reversible way to turn off a feature that is causing
        trouble.

        Args:
            input_data (SuppressFeatureInput): The feature and desired state.

        Returns:
            dict[str, Any]: Status and the resulting suppression state.

        Example:
            ```python
            await suppress_feature({"name": "Fillet1"})
            await suppress_feature({"name": "Fillet1", "suppress": False})
            ```
        """
        try:
            input_data = _normalize_input(input_data, SuppressFeatureInput)
            result = await adapter.suppress_feature(
                input_data.name, input_data.suppress
            )
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                verb = "Suppressed" if input_data.suppress else "Unsuppressed"
                message = f"{verb} {input_data.name}"
                if data.get("suppressed") is None:
                    message += " (state could not be read back)"
                return {
                    "status": "success",
                    "message": message,
                    "data": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to suppress feature: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in suppress_feature tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def undo(input_data: UndoInput | None = None) -> dict[str, Any]:
        """Undo the last operations in the active model.

        SolidWorks accepts an undo with nothing left to undo without
        complaining, so the response reports whether the feature tree actually
        changed rather than assuming it did.

        Args:
            input_data (UndoInput | None): How many steps to undo.

        Returns:
            dict[str, Any]: Status and whether the tree changed.

        Example:
            ```python
            await undo({"count": 1})
            ```
        """
        try:
            input_data = _normalize_input(input_data or UndoInput(), UndoInput)
            result = await adapter.undo(input_data.count)
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                changed = data.get("tree_changed")
                if changed is False:
                    message = (
                        f"Undo of {input_data.count} step(s) left the feature "
                        "tree unchanged - there was nothing to undo"
                    )
                else:
                    message = f"Undid {input_data.count} step(s)"
                return {
                    "status": "success",
                    "message": message,
                    "data": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to undo: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in undo tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
    @mcp.tool()
    async def create_reference_plane(
        input_data: CreateReferencePlaneInput,
    ) -> dict[str, Any]:
        """Create a reference plane offset from an existing plane or planar face.

        Adds a new plane to the feature tree, parallel to and offset from the
        named reference. The returned plane name can be passed straight to
        ``create_sketch`` to sketch anywhere other than the six built-in
        planes.

        Angled planes are not supported by this tool: an angled plane needs a
        second reference (an axis or edge) to rotate about, which this
        signature cannot take. Use ``offset`` for parallel planes. An
        ``offset`` of zero is rejected — a plane coincident with its
        reference is not useful.

        Args:
            input_data (CreateReferencePlaneInput): Reference name, offset,
                angle and flip.

        Returns:
            dict[str, Any]: Status and the new plane's details.

        Example:
            ```python
            plane = await create_reference_plane(
                {"reference": "Front Plane", "offset": 76.2}
            )
            await create_sketch({"plane": plane["plane"]["name"]})
            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateReferencePlaneInput)
            result = await adapter.create_reference_plane(
                input_data.reference,
                input_data.offset,
                input_data.angle,
                input_data.flip,
            )
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                return {
                    "status": "success",
                    "message": f"Created reference plane: {data.get('name', 'Plane')}",
                    "plane": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to create reference plane: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in create_reference_plane tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    @mcp.tool()
    async def create_axis(input_data: CreateAxisInput) -> dict[str, Any]:
        """Create a reference axis along a principal direction.

        Builds an axis from the intersection of two built-in planes: x from
        Top + Front, y from Front + Right, z from Top + Right.

        Args:
            input_data (CreateAxisInput): The principal direction ('x', 'y'
                or 'z').

        Returns:
            dict[str, Any]: Status and the axis details (planes used).

        Example:
            ```python
            result = await create_axis({"reference": "z"})
            ```
        """
        try:
            input_data = _normalize_input(input_data, CreateAxisInput)
            result = await adapter.create_axis(input_data.reference)
            if result.is_success:
                data = result.data if isinstance(result.data, dict) else {}
                axis_name = data.get("reference", input_data.reference)
                return {
                    "status": "success",
                    "message": f"Created {axis_name} axis",
                    "axis": data,
                    "execution_time": result.execution_time,
                }
            return {
                "status": "error",
                "message": f"Failed to create axis: {result.error}",
            }
        except Exception as e:
            logger.error(f"Error in create_axis tool: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    # Counted from the registry rather than hand-maintained. The literal that
    # used to live here had drifted: it read 15 while 16 tools were actually
    # registered, so the function misreported its own work and the test
    # enshrined the wrong number.
    tool_count = len(await mcp.list_tools())
    return tool_count
