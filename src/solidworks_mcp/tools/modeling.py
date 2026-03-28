"""
Modeling tools for SolidWorks MCP Server.

Provides tools for creating and manipulating SolidWorks models, including
parts, assemblies, drawings, and features like extrusions, revolves, etc.
"""

from typing import Any, TypeVar
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from loguru import logger

from ..adapters.base import (
    SolidWorksAdapter,
    ExtrusionParameters,
    RevolveParameters,
    SweepParameters,
    LoftParameters,
)
from .input_compat import CompatInput


TInput = TypeVar("TInput", bound=BaseModel)


# Input schemas using Python 3.14 built-in types


def _result_value(data: Any, *keys: str, default: Any = None) -> Any:
    """Execute result value.
    
    Args:
        data (Any): Describe data.
        default (Any): Describe default.
    
    Returns:
        Any: Describe the returned value.
    
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
    """Execute normalize input.
    
    Args:
        input_data (Any): Describe input data.
        model_type (type[TInput]): Describe model type.
    
    Returns:
        TInput: Describe the returned value.
    
    """
    if isinstance(input_data, model_type):
        return input_data
    return model_type.model_validate(input_data)


class OpenModelInput(BaseModel):
    """Input schema for opening a SolidWorks model."""

    file_path: str = Field(
        description="Full path to the SolidWorks file (.sldprt, .sldasm, .slddrw)"
    )


class CreatePartInput(CompatInput):
    """Input schema for creating a new SolidWorks part."""

    name: str = Field(description="Name for the new part")
    template: str | None = Field(
        default=None, description="Template file path for the new part"
    )
    units: str | None = Field(default=None, description="Document units")
    material: str | None = Field(default=None, description="Material name")

    def model_post_init(self, __context: Any) -> None:
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if not self.name.strip():
            raise ValueError("name is required")


class CreateExtrusionInput(CompatInput):
    """Input schema for creating an extrusion feature."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.depth <= 0:
            raise ValueError("depth must be positive")
        if not self.sketch_name.strip():
            raise ValueError("sketch_name is required")
        if self.reverse is not None:
            self.reverse_direction = self.reverse


class CreateRevolveInput(CompatInput):
    """Input schema for creating a revolve feature."""

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
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.angle <= 0:
            raise ValueError("angle must be positive")


class CreateSweepInput(BaseModel):
    """Input schema for creating a sweep feature."""

    path: str = Field(description="Name or ID of the sweep path")
    twist_along_path: bool = Field(default=False, description="Twist along path")
    twist_angle: float = Field(default=0.0, description="Twist angle in degrees")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")


class CreateLoftInput(BaseModel):
    """Input schema for creating a loft feature."""

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
    """Input schema for getting a dimension value."""

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")

    def model_post_init(self, __context: Any) -> None:
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class SetDimensionInput(CompatInput):
    """Input schema for setting a dimension value."""

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")
    value: float = Field(description="New dimension value in millimeters")
    units: str | None = Field(default=None, description="Units alias")

    def model_post_init(self, __context: Any) -> None:
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class CloseModelInput(BaseModel):
    """Input schema for closing a model."""

    save: bool = Field(default=False, description="Save the model before closing")


class CreateAssemblyInput(CompatInput):
    """Input schema for creating a new assembly."""

    name: str = Field(description="Name for the new assembly")
    template: str | None = Field(
        default=None, description="Assembly template file path"
    )
    components: list[str] = Field(default_factory=list, description="Component list")


class CreateDrawingInput(CompatInput):
    """Input schema for creating a new drawing."""

    name: str = Field(description="Name for the new drawing")
    template: str | None = Field(default=None, description="Drawing template file path")
    model_path: str | None = Field(default=None, description="Source model path")
    sheet_format: str | None = Field(default=None, description="Sheet format template")


async def register_modeling_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register modeling tools with FastMCP.

    Registers comprehensive modeling tools for SolidWorks automation including
    model creation, feature creation, and model management operations.

    Args:
        mcp: FastMCP server instance for tool registration
        adapter: SolidWorks adapter for COM operations
        config: Configuration dictionary for tool settings

    Returns:
        int: Number of tools registered (9 modeling tools)

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
        """
        Open a SolidWorks model (part, assembly, or drawing).

        Opens an existing SolidWorks file and makes it the active document for
        further operations. Supports all standard SolidWorks file formats and
        provides detailed model information upon successful opening.

        Args:
            input_data (OpenModelInput): Contains:
                - file_path (str): Absolute path to SolidWorks file
                  Supported formats: .sldprt, .sldasm, .slddrw

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - model (dict): Model information including:
                  - name (str): Model display name
                  - type (str): "Part", "Assembly", or "Drawing"
                  - path (str): Full file path
                  - configuration (str): Active configuration name
                - execution_time (float): Operation time in seconds

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
        """
        Create a new SolidWorks part document.

        Creates a new SolidWorks part document using the default part template.
        The new part becomes the active document and is ready for modeling operations
        such as sketch creation and feature addition.

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - model (dict): New part information including:
                  - name (str): Part document name (auto-generated)
                  - type (str): "Part"
                  - path (str): Temporary file path
                - execution_time (float): Operation time in seconds

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
        """
        Create a new SolidWorks assembly document.

        Creates a new SolidWorks assembly document using the default assembly template.
        The new assembly becomes the active document and is ready for component
        insertion, mating, and assembly-level operations.

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - model (dict): New assembly information including:
                  - name (str): Assembly document name (auto-generated)
                  - type (str): "Assembly"
                  - path (str): Temporary file path
                - execution_time (float): Operation time in seconds

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
        """
        Create a new SolidWorks drawing document.

        This tool creates a new drawing document using the default drawing template.
        The new drawing will become the active document.
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
        """
        Close the current SolidWorks model.

        Closes the currently active SolidWorks document with an option to save
        changes before closing. This is essential for proper model lifecycle
        management and preventing data loss.

        Args:
            input_data (CloseModelInput): Contains:
                - save (bool): Whether to save before closing (default: False)
                  Set to True to preserve changes before closing

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - saved (bool): Whether model was saved before closing
                - execution_time (float): Operation time in seconds

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
        """
        Create an extrusion feature from the active sketch.

        Creates a 3D extrusion feature (boss or cut) from the currently active 2D sketch.
        Supports advanced options like draft angles, thin features, bidirectional
        extrusion, and various end conditions for professional modeling workflows.

        Args:
            input_data (CreateExtrusionInput): Contains:
                - depth (float): Extrusion depth in millimeters (positive values)
                - draft_angle (float, optional): Draft angle in degrees (default: 0.0)
                  Useful for manufacturing considerations
                - reverse_direction (bool, optional): Reverse extrusion direction (default: False)
                  Set to True for cutting operations
                - both_directions (bool, optional): Extrude in both directions (default: False)
                - thin_feature (bool, optional): Create thin wall feature (default: False)
                - thin_thickness (float | None, optional): Wall thickness for thin feature in mm
                - end_condition (str, optional): End condition type (default: "Blind")
                  Options: "Blind", "Through All", "Up To Surface", "Mid Plane"
                - merge_result (bool, optional): Merge with existing geometry (default: True)

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - feature (dict): Created feature information including:
                  - name (str): Feature name in FeatureManager
                  - type (str): "Boss-Extrude" or "Cut-Extrude"
                  - depth (float): Applied extrusion depth
                  - volume_added (float): Volume added/removed in cubic mm
                - execution_time (float): Operation time in seconds

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

        Raises:
            ValueError: If no active sketch is available
            OperationError: If extrusion parameters are invalid

        Note:
            - Requires an active sketch before calling
            - Sketch must be closed (no open endpoints)
            - Direction depends on sketch plane orientation
            - Use reverse_direction=True for cut operations
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
        """
        Create a revolve feature from the active sketch.

        Creates a 3D revolve feature by rotating the active 2D sketch profile around
        a specified axis of revolution. Supports full and partial revolves, thin
        features, and bidirectional revolution for comprehensive rotational modeling.

        Args:
            input_data (CreateRevolveInput): Contains:
                - angle (float): Revolution angle in degrees (0-360)
                  Use 360 for full revolution, less for partial
                - reverse_direction (bool, optional): Reverse revolution direction (default: False)
                  Changes rotation from counterclockwise to clockwise
                - both_directions (bool, optional): Revolve in both directions (default: False)
                  Creates symmetric revolution from sketch plane
                - thin_feature (bool, optional): Create thin wall feature (default: False)
                  Useful for hollow or shell-like parts
                - thin_thickness (float | None, optional): Wall thickness for thin feature in mm
                  Required when thin_feature=True
                - merge_result (bool, optional): Merge with existing geometry (default: True)

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - feature (dict): Created feature information including:
                  - name (str): Feature name in FeatureManager
                  - type (str): "Boss-Revolve" or "Cut-Revolve"
                  - angle (float): Applied revolution angle
                  - volume_added (float): Volume added/removed in cubic mm
                - execution_time (float): Operation time in seconds

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

        Raises:
            ValueError: If no active sketch or revolution axis available
            OperationError: If revolution parameters are invalid

        Note:
            - Requires active sketch with defined revolution axis
            - Sketch profile must not intersect the revolution axis
            - Use centerline or construction geometry for axis definition
            - Revolution direction follows right-hand rule
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
        """
        Get the value of a dimension from the current model.

        Retrieves the current value of a named dimension from the active SolidWorks
        model. Dimensions can be from sketches, features, or global dimensions.
        Useful for parametric modeling and design validation.

        Args:
            input_data (GetDimensionInput): Contains:
                - name (str): Dimension name in SolidWorks format
                  Examples: 'D1@Sketch1', 'D1@Boss-Extrude1', 'Length@GlobalVariable'
                  Use FeatureManager dimension names exactly as shown

        Returns:
            dict[str, Any]: Operation result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - dimension (dict): Dimension information including:
                  - name (str): Full dimension name
                  - value (float): Current dimension value in millimeters
                  - units (str): Dimension units ("mm", "in", etc.)
                  - type (str): Dimension type ("Linear", "Angular", "Radial")
                  - feature (str): Parent feature name
                  - locked (bool): Whether dimension is locked
                - execution_time (float): Operation time in seconds

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

        Raises:
            ValueError: If dimension name is not found
            OperationError: If model has no active document

        Note:
            - Dimension names are case-sensitive
            - Use exact names from FeatureManager
            - Global variables use @GlobalVariable suffix
            - Angular dimensions returned in degrees

        This tool retrieves the current value of a named dimension.
        Common dimension names include D1@Sketch1, D2@Sketch1, D1@Boss-Extrude1, etc.
        """
        try:
            input_data = _normalize_input(input_data, GetDimensionInput)
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
        """
        Set the value of a dimension in the current model.

        This tool modifies the value of a named dimension and rebuilds the model.
        Use this to parametrically modify your model dimensions.
        """
        try:
            input_data = _normalize_input(input_data, SetDimensionInput)
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

    tool_count = 8  # Number of tools registered
    return tool_count
