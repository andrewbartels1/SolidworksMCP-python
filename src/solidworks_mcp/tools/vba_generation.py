"""
VBA Code Generation tools for SolidWorks MCP Server.

Provides tools for generating VBA macros for complex SolidWorks operations,
especially useful for operations with 13+ parameters that exceed COM limits.
"""

from typing import Any
from fastmcp import FastMCP
from pydantic import Field
from loguru import logger

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput


# Input schemas for VBA generation


class VBAExtrusionInput(CompatInput):
    """Input schema for generating VBA extrusion code."""

    sketch_name: str | None = Field(default=None, description="Sketch name")
    depth: float = Field(description="Extrusion depth in mm")
    direction: str | None = Field(default=None, description="Direction")
    both_directions: bool = Field(
        default=False, description="Extrude in both directions"
    )
    depth2: float = Field(
        default=0.0, description="Second direction depth if both_directions=True"
    )
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    draft_outward: bool = Field(default=True, description="Draft direction")
    thin_feature: bool = Field(default=False, description="Create thin feature")
    thin_thickness: float = Field(
        default=1.0, description="Thin feature thickness in mm"
    )
    thin_thickness1: float | None = Field(default=None, description="Alias thickness 1")
    thin_thickness2: float | None = Field(default=None, description="Alias thickness 2")
    thin_type: str = Field(default="OneDirection", description="Thin feature type")
    cap_ends: bool = Field(default=False, description="Cap thin feature ends")
    cap_thickness: float = Field(default=1.0, description="Cap thickness in mm")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")
    feature_scope: str | bool = Field(default=False, description="Use feature scope")
    auto_select: bool = Field(default=True, description="Auto select components")
    assembly_feature_scope: str | None = Field(
        default=None, description="Assembly feature scope"
    )
    start_condition: str | None = Field(default=None, description="Start condition")
    end_condition: str | None = Field(default=None, description="End condition")
    end_condition_reference: str | None = Field(
        default=None, description="End condition reference"
    )
    offset_parameters: dict[str, Any] | None = Field(
        default=None, description="Offset parameters"
    )
    custom_properties: dict[str, Any] | None = Field(
        default=None, description="Custom properties"
    )
    advanced_options: dict[str, Any] | None = Field(
        default=None, description="Advanced options"
    )


class VBARevolveInput(CompatInput):
    """Input schema for generating VBA revolve code."""

    angle: float | None = Field(default=None, description="Revolve angle in degrees")
    angle_degrees: float | None = Field(default=None, description="Angle alias")
    sketch_name: str | None = Field(default=None, description="Sketch name")
    axis_reference: str | None = Field(default=None, description="Axis reference")
    both_directions: bool = Field(
        default=False, description="Revolve in both directions"
    )
    angle2: float = Field(default=0.0, description="Second direction angle")
    thin_feature: bool = Field(default=False, description="Create thin feature")
    thin_thickness: float = Field(
        default=1.0, description="Thin feature thickness in mm"
    )
    merge_result: bool = Field(default=True, description="Merge with existing geometry")

    def model_post_init(self, __context: Any) -> None:
        """Execute model post init.
        
        Args:
            __context (Any): Describe context.
        
        Returns:
            None: Describe the returned value.
        
        """
        if self.angle is None:
            self.angle = self.angle_degrees if self.angle_degrees is not None else 360.0


class VBAAssemblyInput(CompatInput):
    """Input schema for generating VBA assembly operations."""

    operation_type: str | None = Field(
        default=None, description="Assembly operation (insert, mate, pattern, etc.)"
    )
    component_path: str | None = Field(
        default=None, description="Path to component file"
    )
    assembly_file: str | None = Field(default=None, description="Assembly file")
    component_file: str | None = Field(default=None, description="Component file alias")
    insertion_point: list[float] = Field(
        default=[0, 0, 0], description="Insertion coordinates [x,y,z]"
    )
    rotation: list[float] = Field(
        default=[0, 0, 0], description="Rotation angles [rx,ry,rz]"
    )


class VBADrawingInput(CompatInput):
    """Input schema for generating VBA drawing operations."""

    operation_type: str | None = Field(
        default=None,
        description="Drawing operation (view, dimension, annotation, etc.)",
    )
    model_path: str | None = Field(default=None, description="Path to 3D model")
    drawing_file: str | None = Field(default=None, description="Drawing file path")
    view_layout: str | None = Field(default=None, description="View layout")
    view_scale: str | None = Field(default=None, description="View scale")
    advanced_options: dict[str, Any] | None = Field(
        default=None, description="Advanced options"
    )
    sheet_format: str = Field(
        default="A3", description="Sheet format (A4, A3, B, C, etc.)"
    )
    scale: float = Field(default=1.0, description="Drawing scale")


class VBABatchInput(CompatInput):
    """Input schema for generating VBA batch operations."""

    operation_type: str | None = Field(
        default=None, description="Batch operation type (export, properties, etc.)"
    )
    file_pattern: str | None = Field(
        default=None, description="File pattern to process (e.g., '*.sldprt')"
    )
    source_folder: str | None = Field(default=None, description="Source folder path")
    target_folder: str | None = Field(default=None, description="Target folder path")
    source_directory: str | None = Field(
        default=None, description="Source directory alias"
    )
    export_format: str | None = Field(default=None, description="Export format alias")
    exclude_list: list[str] | None = Field(default=None, description="Exclude list")
    recursive: bool = Field(default=True, description="Process subfolders")


async def register_vba_generation_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config
) -> int:
    """Register VBA generation tools with FastMCP.

    Args:
        mcp: FastMCP server instance
        adapter: SolidWorks adapter for COM operations
        config: Configuration settings

    Returns:
        Number of tools registered

    Example:
        >>> tool_count = await register_vba_generation_tools(mcp, adapter, config)
    """
    tool_count = 0

    @mcp.tool()
    async def generate_vba_extrusion(input_data: VBAExtrusionInput) -> dict[str, Any]:
        """Generate VBA code for complex extrusion operations.

        Args:
            input_data: Extrusion parameters with 13+ options

        Returns:
            Generated VBA code and execution status

        Example:
            >>> result = await generate_vba_extrusion(extrusion_input)
        """
        try:
            if hasattr(adapter, "generate_vba_extrusion"):
                result = await adapter.generate_vba_extrusion(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Generated VBA code for advanced extrusion",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate VBA code",
                }

            vba_code = f"""Sub CreateAdvancedExtrusion()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swFeatMgr As SldWorks.FeatureManager
    Dim swFeat As SldWorks.Feature
    Dim myFeature As Object
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    
    If swModel Is Nothing Then
        MsgBox "No active document"
        Exit Sub
    End If
    
    Set swFeatMgr = swModel.FeatureManager
    
    ' Advanced extrusion with full parameter control
    myFeature = swFeatMgr.FeatureExtruThin2( _
        {input_data.depth / 1000.0}, _  ' Depth (meters)
        {input_data.depth2 / 1000.0}, _ ' Depth2 (meters)  
        {str(input_data.both_directions).lower()}, _ ' BothDirections
        {input_data.draft_angle * 3.14159 / 180.0}, _ ' DraftAngle (radians)
        {0}, _ ' DraftAngle2
        {str(input_data.draft_outward).lower()}, _ ' DraftOutward
        {str(input_data.draft_outward).lower()}, _ ' DraftOutward2
        {str(input_data.merge_result).lower()}, _ ' MergeResult
        {str(input_data.feature_scope).lower()}, _ ' FeatureScope
        {str(input_data.auto_select).lower()}, _ ' AutoSelect
        {input_data.thin_thickness / 1000.0}, _ ' Thickness (meters)
        {input_data.thin_thickness / 1000.0}, _ ' Thickness2
        False, _ ' ReverseOffset
        {str(input_data.both_directions).lower()}, _ ' BothDirectionThin
        {str(input_data.cap_ends).lower()}, _ ' CapEnds
        0, _ ' EndCondition
        0 _ ' EndCondition2
    )
    
    If myFeature Is Nothing Then
        MsgBox "Failed to create extrusion"
    Else
        MsgBox "Advanced extrusion created successfully"
    End If
    
End Sub"""

            return {
                "status": "success",
                "message": "Generated VBA code for advanced extrusion",
                "vba_code": vba_code,
                "parameters": {
                    "depth": input_data.depth,
                    "both_directions": input_data.both_directions,
                    "thin_feature": input_data.thin_feature,
                    "parameter_count": 17,
                    "complexity": "complex",
                },
                "usage_instructions": [
                    "1. Open SolidWorks VBA editor (Tools > Macro > Edit)",
                    "2. Create new module and paste the generated code",
                    "3. Ensure you have an active sketch selected",
                    "4. Run the macro (F5)",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_extrusion tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_revolve(input_data: VBARevolveInput) -> dict[str, Any]:
        """Generate VBA code for complex revolve operations.

        Args:
            input_data: Revolve parameters with advanced options

        Returns:
            Generated VBA code and execution results

        Example:
            >>> result = await generate_vba_revolve(revolve_input)
        """
        """
        Generate VBA code for complex revolve operations.

        Creates VBA macro for revolve features with advanced thin-wall options.
        """
        try:
            if hasattr(adapter, "generate_vba_revolve"):
                result = await adapter.generate_vba_revolve(input_data.model_dump())
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Generated VBA code for advanced revolve",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate VBA code",
                }

            vba_code = f"""Sub CreateAdvancedRevolve()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2 
    Dim swFeatMgr As SldWorks.FeatureManager
    Dim myFeature As Object
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swFeatMgr = swModel.FeatureManager
    
    ' Advanced revolve with thin-wall options
    myFeature = swFeatMgr.FeatureRevolve2( _
        True, _ ' SingleDir
        {str(input_data.both_directions).lower()}, _ ' IsSolid
        False, _ ' IsThin
        False, _ ' ReverseDir
        3, _ ' Type (swEndCondBlind)
        3, _ ' Type2
        {input_data.angle * 3.14159 / 180.0}, _ ' Angle (radians)
        {input_data.angle2 * 3.14159 / 180.0}, _ ' Angle2  
        {str(input_data.merge_result).lower()}, _ ' MergeResult
        False, _ ' FeatureScope
        False, _ ' Auto
        True, _ ' AssemblyFeatureScope
        0, _ ' AutoSelectComponents
        False, _ ' PropagateFeatureToParts
        True, _ ' CreateSelectionSet
        False, _ ' CurveToOrderUse
        False _ ' UseMachinedSurface
    )
    
    If myFeature Is Nothing Then
        MsgBox "Failed to create revolve"
    Else
        MsgBox "Advanced revolve created successfully"
    End If
    
End Sub"""

            return {
                "status": "success",
                "message": "Generated VBA code for advanced revolve",
                "vba_code": vba_code,
                "parameters": {
                    "angle": input_data.angle,
                    "both_directions": input_data.both_directions,
                    "thin_feature": input_data.thin_feature,
                    "parameter_count": 16,
                    "complexity": "complex",
                },
                "usage_instructions": [
                    "1. Create a sketch profile and axis of revolution",
                    "2. Select the sketch and axis",
                    "3. Run the generated VBA macro",
                    "4. Check the revolve feature in the feature tree",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_revolve tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_assembly_insert(
        input_data: VBAAssemblyInput,
    ) -> dict[str, Any]:
        (
            """Generate VBA code for assembly component insertion.
        
        Args:
            input_data: Assembly insertion parameters
            
        Returns:
            Generated VBA code for component operations
            
        Example:
            >>> result = await generate_vba_assembly_insert(assembly_input)
        """
            """
        Generate VBA code for inserting components into assemblies.

        Creates macro for component insertion with precise positioning.
        """
        )
        try:
            if hasattr(adapter, "generate_vba_assembly_insert"):
                result = await adapter.generate_vba_assembly_insert(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Generated VBA code for component insertion",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate VBA code",
                }

            vba_code = f'''Sub InsertComponent()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swAssy As SldWorks.AssemblyDoc
    Dim swComp As SldWorks.Component2
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swAssy = swModel
    
    ' Insert component at specified location
    Set swComp = swAssy.AddComponent5( _
        "{input_data.component_path}", _
        0, _ ' Configuration
        "", _ ' Config name
        False, _ ' LoadModel
        "", _ ' ReferenceName
        {input_data.insertion_point[0] / 1000.0}, _ ' X position (meters)
        {input_data.insertion_point[1] / 1000.0}, _ ' Y position (meters)  
        {input_data.insertion_point[2] / 1000.0} _ ' Z position (meters)
    )
    
    If swComp Is Nothing Then
        MsgBox "Failed to insert component"
    Else
        MsgBox "Component inserted successfully: " & swComp.Name2
    End If
    
End Sub'''

            return {
                "status": "success",
                "message": "Generated VBA code for component insertion",
                "vba_code": vba_code,
                "parameters": {
                    "component_path": input_data.component_path,
                    "insertion_point": input_data.insertion_point,
                    "operation_type": input_data.operation_type,
                },
                "usage_instructions": [
                    "1. Open the target assembly document",
                    "2. Ensure the component file path exists",
                    "3. Run the macro to insert the component",
                    "4. Add mates as needed for positioning",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_assembly_insert tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_drawing_views(input_data: VBADrawingInput) -> dict[str, Any]:
        """Generate VBA code for drawing view creation.

        Args:
            input_data: Drawing view parameters and settings

        Returns:
            Generated VBA code for drawing operations

        Example:
            >>> result = await generate_vba_drawing_views(drawing_input)
        """
        """
        Generate VBA code for creating drawing views.

        Creates macro for standard drawing view setup.
        """
        try:
            if hasattr(adapter, "generate_vba_drawing_views"):
                result = await adapter.generate_vba_drawing_views(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": "Generated VBA code for drawing views",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate VBA code",
                }

            vba_code = f'''Sub CreateDrawingViews()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swDraw As SldWorks.DrawingDoc
    Dim swView As SldWorks.View
    Dim swSheet As SldWorks.Sheet
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swDraw = swModel
    
    If swDraw Is Nothing Then
        MsgBox "No active drawing document"
        Exit Sub
    End If
    
    Set swSheet = swDraw.GetCurrentSheet
    
    ' Create standard 3 view drawing
    ' Front view
    Set swView = swDraw.CreateDrawViewFromModelView3( _
        "{input_data.model_path}", _
        "*Front", _
        0.1, _ ' X position 
        0.15, _ ' Y position
        0 _ ' Z position
    )
    
    swView.ScaleRatio = Array({input_data.scale}, 1)
    
    ' Top view  
    Set swView = swDraw.CreateDrawViewFromModelView3( _
        "{input_data.model_path}", _
        "*Top", _
        0.1, _
        0.25, _ 
        0 _
    )
    
    swView.ScaleRatio = Array({input_data.scale}, 1)
    
    ' Right view
    Set swView = swDraw.CreateDrawViewFromModelView3( _
        "{input_data.model_path}", _
        "*Right", _
        0.25, _
        0.15, _
        0 _
    )
    
    swView.ScaleRatio = Array({input_data.scale}, 1)
    
    MsgBox "Drawing views created successfully"
    
End Sub'''

            return {
                "status": "success",
                "message": "Generated VBA code for drawing views",
                "vba_code": vba_code,
                "parameters": {
                    "model_path": input_data.model_path,
                    "scale": input_data.scale,
                    "sheet_format": input_data.sheet_format,
                },
                "usage_instructions": [
                    "1. Create a new drawing document",
                    "2. Verify the 3D model path is correct",
                    "3. Run the macro to create standard views",
                    "4. Adjust view positions as needed",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_drawing_views tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_batch_export(input_data: VBABatchInput) -> dict[str, Any]:
        """Generate VBA code for batch file export operations.

        Args:
            input_data: Batch export configuration parameters

        Returns:
            Generated VBA batch processing code

        Example:
            >>> result = await generate_vba_batch_export(batch_input)
        """
        """
        Generate VBA code for batch file operations.

        Creates macro for processing multiple files automatically.
        """
        try:
            if hasattr(adapter, "generate_vba_batch_export"):
                result = await adapter.generate_vba_batch_export(
                    input_data.model_dump()
                )
                if result.is_success:
                    return {
                        "status": "success",
                        "message": f"Generated VBA code for batch {input_data.operation_type}",
                        "data": result.data,
                        "execution_time": result.execution_time,
                    }
                return {
                    "status": "error",
                    "message": result.error or "Failed to generate VBA code",
                }

            vba_code = f'''Sub BatchExport()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim fso As FileSystemObject
    Dim folder As Folder
    Dim file As file
    Dim filePath As String
    Dim exportPath As String
    Dim processedCount As Integer
    
    Set swApp = Application.SldWorks
    Set fso = New FileSystemObject
    Set folder = fso.GetFolder("{input_data.source_folder}")
    
    processedCount = 0
    
    ' Process all files matching pattern
    For Each file In folder.Files
        If LCase(file.Name) Like LCase("{input_data.file_pattern}") Then 
            filePath = file.Path
            
            ' Open the file
            Set swModel = swApp.OpenDoc6(filePath, 1, 1, "", 0, 0)
            
            If Not swModel Is Nothing Then
                ' Generate export path
                exportPath = "{input_data.target_folder}" & "\\" & _
                    fso.GetBaseName(file.Name) & ".step"
                
                ' Export as STEP
                swModel.SaveAs2 exportPath, 0, True, False
                
                ' Close the model
                swApp.CloseDoc swModel.GetTitle
                
                processedCount = processedCount + 1
            End If
        End If
    Next file
    
    MsgBox "Batch export completed. Processed " & processedCount & " files."
    
End Sub'''

            return {
                "status": "success",
                "message": f"Generated VBA code for batch {input_data.operation_type}",
                "vba_code": vba_code,
                "parameters": {
                    "operation_type": input_data.operation_type,
                    "file_pattern": input_data.file_pattern,
                    "source_folder": input_data.source_folder,
                    "target_folder": input_data.target_folder,
                    "recursive": input_data.recursive,
                },
                "usage_instructions": [
                    "1. Verify source and target folder paths exist",
                    "2. Close any open documents to avoid conflicts",
                    "3. Run the macro - it will process all matching files",
                    "4. Check the target folder for exported files",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_batch_export tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_part_modeling(input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate VBA code for complex part modeling operations.

        Args:
            input_data: Part modeling parameters and features

        Returns:
            Generated VBA code for part operations

        Example:
            >>> result = await generate_vba_part_modeling(part_input)
        """
        """
        Generate VBA code for advanced part modeling operations.

        Creates macro for complex part features like sweeps, lofts, shells.
        """
        try:
            operation = input_data.get("operation", "shell")
            thickness = input_data.get("thickness", 2.0)

            if operation == "shell":
                vba_code = f"""Sub CreateShell()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swFeatMgr As SldWorks.FeatureManager
    Dim swFeat As SldWorks.Feature
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swFeatMgr = swModel.FeatureManager
    
    ' Create shell feature
    Set swFeat = swFeatMgr.FeatureShell2( _
        {thickness / 1000.0}, _ ' Thickness (meters)
        False, _ ' OutwardThickness
        False, _ ' MultiThickness  
        False, _ ' ShowPreview
        False, _ ' MultipleFaceDef
        False _ ' MultipleThicknessDef
    )
    
    If swFeat Is Nothing Then
        MsgBox "Failed to create shell"
    Else
        MsgBox "Shell created successfully with thickness: {thickness}mm"
    End If
    
End Sub"""
            elif operation == "fillet":
                radius = input_data.get("radius", 5.0)
                vba_code = f"""Sub CreateFillet()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swFeatMgr As SldWorks.FeatureManager
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swFeatMgr = swModel.FeatureManager
    
    ' Create fillet feature  
    swFeatMgr.FeatureFillet4( _
        {radius / 1000.0}, _ ' Radius (meters)
        0, _ ' SecondRadius
        0, _ ' RollOnOff
        0, _ ' RollFirstRadius  
        0, _ ' RollSecondRadius
        0, _ ' RollSmoothTransition
        0, _ ' ConicRho
        0, _ ' SetbackDistance
        False, _ ' AssemblyFeatureScope
        False, _ ' AutoSelectComponents
        False, _ ' PropagateFeatureToParts
        False, _ ' CreateSelectionSet
        False, _ ' EnableSolidPreview
        0 _ ' CornerType
    )
    
    swModel.ClearSelection2 True
    MsgBox "Fillet created with radius: {radius}mm"
    
End Sub"""
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported operation: {operation}",
                }

            return {
                "status": "success",
                "message": f"Generated VBA code for {operation} operation",
                "vba_code": vba_code,
                "parameters": input_data,
                "usage_instructions": [
                    "1. Select the appropriate faces/edges",
                    "2. Run the generated VBA macro",
                    "3. Verify the feature was created correctly",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_part_modeling tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_assembly_mates(input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate VBA code for assembly mate creation.

        Args:
            input_data: Assembly mate parameters and constraints

        Returns:
            Generated VBA code for mate operations

        Example:
            >>> result = await generate_vba_assembly_mates(mate_input)
        """
        """
        Generate VBA code for creating assembly mates.

        Creates macro for various mate types (concentric, distance, parallel, etc).
        """
        try:
            mate_type = input_data.get("mate_type", "concentric")
            component1 = input_data.get("component1", "Part1")
            component2 = input_data.get("component2", "Part2")
            distance = input_data.get("distance", 0.0)

            mate_type_map = {
                "concentric": "swMateType_CONCENTRIC",
                "distance": "swMateType_DISTANCE",
                "parallel": "swMateType_PARALLEL",
                "perpendicular": "swMateType_PERPENDICULAR",
                "coincident": "swMateType_COINCIDENT",
            }

            sw_mate_type = mate_type_map.get(mate_type, "swMateType_CONCENTRIC")

            vba_code = f"""Sub CreateAssemblyMate()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swAssy As SldWorks.AssemblyDoc
    Dim swMateFeats As Variant
    Dim swMate As SldWorks.Feature
    
    Set swApp = Application.SldWorks  
    Set swModel = swApp.ActiveDoc
    Set swAssy = swModel
    
    ' Clear existing selections
    swModel.ClearSelection2 True
    
    ' Note: Entity selection needs to be done before running this macro
    ' Select appropriate faces/edges on {component1} and {component2}
    
    ' Create {mate_type} mate
    swMateFeats = swAssy.AddMate5( _
        {sw_mate_type}, _ ' Mate type
        swMateAlign_ALIGNED, _ ' Alignment
        False, _ ' Flip
        {distance / 1000.0}, _ ' Distance (meters)
        0, _ ' Distance2
        0, _ ' Angle
        0, _ ' Angle2
        False, _ ' LockRotation
        0, _ ' WidthMateOption
        0, _ ' For Positioning Only
        0 _ ' LockToSketch
    )
    
    If IsEmpty(swMateFeats) Then
        MsgBox "Failed to create mate. Check entity selection."
    Else 
        Set swMate = swMateFeats(0)
        MsgBox "Mate created: " & swMate.Name
    End If
    
End Sub"""

            return {
                "status": "success",
                "message": f"Generated VBA code for {mate_type} mate",
                "vba_code": vba_code,
                "parameters": {
                    "mate_type": mate_type,
                    "component1": component1,
                    "component2": component2,
                    "distance": distance,
                },
                "usage_instructions": [
                    "1. Open the assembly document",
                    "2. Select the two faces/edges to mate",
                    "3. Run the generated macro",
                    "4. Verify the mate was created in the feature tree",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_assembly_mates tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_drawing_dimensions(
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate VBA code for creating drawing dimensions.

        Creates macro for various dimension types in drawings.
        """
        try:
            dimension_type = input_data.get("dimension_type", "linear")
            precision = input_data.get("precision", 2)

            vba_code = f'''Sub CreateDrawingDimensions()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2  
    Dim swDraw As SldWorks.DrawingDoc
    Dim swView As SldWorks.View
    Dim swDisp As SldWorks.DisplayDimension
    Dim swDim As SldWorks.Dimension
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    Set swDraw = swModel
    
    ' Get active drawing view
    Set swView = swDraw.GetFirstView ' Sheet
    Set swView = swView.GetNextView ' First drawing view
    
    If swView Is Nothing Then
        MsgBox "No drawing view found"
        Exit Sub
    End If
    
    swModel.ClearSelection2 True
    
    ' Note: Select appropriate entities before running
    ' For linear dimensions: select two edges or points
    ' For radial: select arc or circle
    ' For angular: select two lines
    
    Select Case "{dimension_type}"
        Case "linear"
            Set swDisp = swModel.AddDimension2(0.05, 0.05, 0)
        Case "radial"  
            Set swDisp = swModel.AddDimension2(0.05, 0.05, 0)
        Case "angular"
            Set swDisp = swModel.AddDimension2(0.05, 0.05, 0)
        Case "diameter"
            Set swDisp = swModel.AddDimension2(0.05, 0.05, 0)
    End Select
    
    If Not swDisp Is Nothing Then
        Set swDim = swDisp.GetDimension2(0)
        ' Set precision
        swDim.SetPrecision2 swLinear, {precision}
        MsgBox "Dimension created with {precision} decimal places"
    Else
        MsgBox "Failed to create dimension. Check entity selection."
    End If
    
End Sub'''

            return {
                "status": "success",
                "message": f"Generated VBA code for {dimension_type} dimension",
                "vba_code": vba_code,
                "parameters": {
                    "dimension_type": dimension_type,
                    "precision": precision,
                },
                "usage_instructions": [
                    "1. Open a drawing with views",
                    "2. Select two edges, points, or appropriate entities",
                    "3. Run the macro to create dimension",
                    "4. Adjust dimension position as needed",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_drawing_dimensions tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_file_operations(
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate VBA code for file management operations.

        Args:
            input_data: File operation parameters and paths

        Returns:
            Generated VBA code for file operations

        Example:
            >>> result = await generate_vba_file_operations(file_input)

        Creates macro for custom properties, PDM operations, etc.
        """
        try:
            operation = input_data.get("operation", "custom_properties")

            if operation == "custom_properties":
                property_name = input_data.get("property_name", "Material")
                property_value = input_data.get("property_value", "Steel")

                vba_code = f'''Sub SetCustomProperties()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swCustPropMgr As SldWorks.CustomPropertyManager
    Dim configNames As Variant
    Dim i As Integer
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    
    ' Get configuration names
    configNames = swModel.GetConfigurationNames
    
    ' Set property for all configurations
    For i = 0 To UBound(configNames)
        Set swCustPropMgr = swModel.Extension.CustomPropertyManager(configNames(i))
        
        swCustPropMgr.Add3 "{property_name}", swCustomInfoText, _
            "{property_value}", swCustomPropertyAddOption_ReplaceValue
    Next i
    
    ' Also set at file level
    Set swCustPropMgr = swModel.Extension.CustomPropertyManager("")
    swCustPropMgr.Add3 "{property_name}", swCustomInfoText, _
        "{property_value}", swCustomPropertyAddOption_ReplaceValue
    
    MsgBox "Custom property '{property_name}' set to '{property_value}'"
    
End Sub'''

            elif operation == "pack_and_go":
                target_folder = input_data.get("target_folder", "C:\\PackAndGo")

                vba_code = f'''Sub PackAndGo()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swPackAndGo As SldWorks.PackAndGo
    Dim pgStatus As Long
    Dim pgWarnings As Long
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    
    Set swPackAndGo = swApp.GetPackAndGo
    
    ' Set Pack and Go settings
    swPackAndGo.IncludeDrawings = True
    swPackAndGo.IncludeSimulationResults = False
    swPackAndGo.IncludeToolboxComponents = False
    swPackAndGo.FlattenToSingleFolder = True
    
    ' Set destination folder
    swPackAndGo.SetSaveToName swModel.GetTitle, "{target_folder}"
    
    ' Execute Pack and Go
    swPackAndGo.PackAndGo2 pgStatus, pgWarnings
    
    If pgStatus = 0 Then
        MsgBox "Pack and Go completed successfully"
    Else
        MsgBox "Pack and Go failed with status: " & pgStatus
    End If
    
End Sub'''
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported operation: {operation}",
                }

            return {
                "status": "success",
                "message": f"Generated VBA code for {operation}",
                "vba_code": vba_code,
                "parameters": input_data,
                "usage_instructions": [
                    "1. Open the target document",
                    "2. Run the generated macro",
                    "3. Check results in properties or file system",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_file_operations tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    @mcp.tool()
    async def generate_vba_macro_recorder(input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate VBA code using macro recording patterns.

        Args:
            input_data: Macro recording parameters and actions

        Returns:
            Generated VBA code from recorded operations

        Example:
            >>> result = await generate_vba_macro_recorder(recorder_input)


        Returns:
            Generated VBA code from recorded operations

        Example:
            >>> result = await generate_vba_macro_recorder(recorder_input)
        """
        try:
            operation = input_data.get("operation", "start_recording")

            if operation == "start_recording":
                vba_code = """Sub StartMacroRecording()
    Dim swApp As SldWorks.SldWorks
    Set swApp = Application.SldWorks
    
    ' Enable macro recording
    swApp.UnloadAddIn "SldWorks.Addin.Utilities.MacroRecorder"
    swApp.LoadAddIn "SldWorks.Addin.Utilities.MacroRecorder"
    
    ' Note: Use Tools > Macro > Record in SolidWorks interface
    ' This code prepares the environment for recording
    
    MsgBox "Macro recording environment prepared. Use Tools > Macro > Record to start."
    
End Sub"""

            elif operation == "stop_recording":
                vba_code = """Sub StopMacroRecording()
    Dim swApp As SldWorks.SldWorks
    Set swApp = Application.SldWorks
    
    ' Note: Use Tools > Macro > Stop Record in SolidWorks interface
    ' This code helps manage the recording session
    
    MsgBox "Stop recording using Tools > Macro > Stop Record"
    
End Sub"""

            elif operation == "create_template":
                macro_name = input_data.get("macro_name", "CustomMacro")
                vba_code = f"""Sub {macro_name}Template()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    ' Add more variables as needed
    
    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc
    
    ' TODO: Add your custom automation code here
    ' This template provides the basic SolidWorks API structure
    
    ' Error handling
    If swModel Is Nothing Then
        MsgBox "No active document"
        Exit Sub
    End If
    
    ' Your automation logic goes here...
    
    MsgBox "Custom macro template ready for customization"
    
End Sub"""
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported operation: {operation}",
                }

            return {
                "status": "success",
                "message": f"Generated VBA code for macro {operation}",
                "vba_code": vba_code,
                "parameters": input_data,
                "usage_instructions": [
                    "1. Open SolidWorks VBA editor (Alt+F11)",
                    "2. Create new module and paste code",
                    "3. Customize as needed for your workflow",
                ],
            }

        except Exception as e:
            logger.error(f"Error in generate_vba_macro_recorder tool: {e}")
            return {
                "status": "error",
                "message": f"Failed to generate VBA code: {str(e)}",
            }

    # Core VBA generation tools
    tool_count = 10
    return tool_count
