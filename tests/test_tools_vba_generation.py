"""
Tests for SolidWorks VBA generation tools.

Comprehensive test suite covering VBA code generation for complex
operations that exceed COM parameter limits (13+ parameters).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.vba_generation import (
    VBAAssemblyInput,
    VBABatchInput,
    VBADrawingInput,
    VBAExtrusionInput,
    VBARevolveInput,
    register_vba_generation_tools,
)


class TestVBAGenerationTools:
    """Test suite for VBA generation tools."""

    @pytest.mark.asyncio
    async def test_register_vba_generation_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that VBA generation tools register correctly."""
        tool_count = await register_vba_generation_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 10

    @pytest.mark.asyncio
    async def test_generate_vba_extrusion_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA extrusion code generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_extrusion = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": """Sub CreateAdvancedExtrusion()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swFeature As SldWorks.Feature

    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc

    swModel.FeatureManager.FeatureExtrusion2 True, False, False, 0, 0, 25.0, 0.0, False, False, False, False, 0.0, 0.0, False, False, False, False, True, True, True
End Sub""",
                    "operation": "Advanced Extrusion",
                    "parameter_count": 19,
                    "complexity_reason": "Exceeds COM parameter limit",
                    "execution_method": "VBA Macro",
                },
                execution_time=0.5,
            )
        )

        input_data = VBAExtrusionInput(
            sketch_name="Sketch1",
            depth=25.0,
            direction="Blind",
            reverse_direction=False,
            draft_angle=5.0,
            draft_outward=True,
            thin_feature=False,
            thin_thickness1=2.0,
            thin_thickness2=2.0,
            merge_result=True,
            start_condition="SketchPlane",
            end_condition="Blind",
            end_condition_reference="",
            offset_parameters={},
            feature_scope="All bodies",
            auto_select=True,
            assembly_feature_scope="All components",
            custom_properties={"Generated": "VBA Tool"},
            advanced_options={"optimize_geometry": True},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_extrusion":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "CreateAdvancedExtrusion" in result["data"]["vba_code"]
        assert result["data"]["parameter_count"] == 19
        assert result["data"]["complexity_reason"] == "Exceeds COM parameter limit"
        mock_adapter.generate_vba_extrusion.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_vba_revolve_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA revolve code generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_revolve = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": """Sub CreateAdvancedRevolve()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2

    Set swApp = Application.SldWorks
    Set swModel = swApp.ActiveDoc

    swModel.FeatureManager.FeatureRevolve2 True, True, False, False, False, False, 6.28318530717959, 0, False, False, 2.0, 2.0, False, False, False, False, True
End Sub""",
                    "operation": "Advanced Revolve",
                    "parameter_count": 17,
                    "axis_reference": "Line1",
                    "angle_degrees": 360.0,
                },
                execution_time=0.4,
            )
        )

        input_data = VBARevolveInput(
            sketch_name="Sketch2",
            axis_reference="Line1",
            angle_degrees=360.0,
            direction="One Direction",
            reverse_direction=False,
            thin_feature=True,
            thin_thickness1=2.0,
            thin_thickness2=2.0,
            merge_result=True,
            start_angle=0.0,
            end_condition="Blind",
            draft_angle=0.0,
            draft_outward=False,
            feature_scope="Selected bodies",
            auto_select=True,
            assembly_feature_scope="Selected components",
            custom_properties={},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_revolve":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "CreateAdvancedRevolve" in result["data"]["vba_code"]
        assert result["data"]["parameter_count"] == 17
        assert result["data"]["angle_degrees"] == 360.0
        mock_adapter.generate_vba_revolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_vba_assembly_insert_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA assembly component insertion."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_assembly_insert = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": """Sub InsertAssemblyComponent()
    Dim swApp As SldWorks.SldWorks
    Dim swAssembly As SldWorks.AssemblyDoc
    Dim swComponent As SldWorks.Component2

    Set swApp = Application.SldWorks
    Set swAssembly = swApp.ActiveDoc

    Set swComponent = swAssembly.AddComponent5("C:\\Parts\\bracket.sldprt", "", True, "", 0, 0, 0)
End Sub""",
                    "operation": "Assembly Component Insertion",
                    "component_file": "C:\\Parts\\bracket.sldprt",
                    "insertion_point": [0, 0, 0],
                    "suppress_on_insert": False,
                },
                execution_time=0.3,
            )
        )

        input_data = VBAAssemblyInput(
            assembly_file="main_assembly.sldasm",
            component_file="C:\\Parts\\bracket.sldprt",
            insertion_point=[0, 0, 0],
            configuration="Default",
            suppress_on_insert=False,
            reference_component="",
            mate_references=[],
            positioning_method="Origin",
            component_properties={},
            display_state="Default",
            lightweight=False,
            envelope=False,
            exclude_from_bom=False,
            fixed_component=False,
            smart_fasteners=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_assembly_insert":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "InsertAssemblyComponent" in result["data"]["vba_code"]
        assert result["data"]["component_file"] == "C:\\Parts\\bracket.sldprt"
        mock_adapter.generate_vba_assembly_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_vba_drawing_views_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA drawing views generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_drawing_views = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": """Sub CreateDrawingViews()
    Dim swApp As SldWorks.SldWorks
    Dim swDrawing As SldWorks.DrawingDoc
    Dim swView As SldWorks.View

    Set swApp = Application.SldWorks
    Set swDrawing = swApp.ActiveDoc

    Set swView = swDrawing.CreateDrawViewFromModelView3("C:\\Models\\part.sldprt", "*Front", 0.1, 0.1, 0)
End Sub""",
                    "operation": "Drawing Views Creation",
                    "model_file": "C:\\Models\\part.sldprt",
                    "views_to_create": ["Front", "Right", "Top", "Isometric"],
                    "total_views": 4,
                },
                execution_time=1.2,
            )
        )

        input_data = VBADrawingInput(
            drawing_file="part_drawing.slddrw",
            model_file="C:\\Models\\part.sldprt",
            sheet_name="Sheet1",
            views_to_create=["Front", "Right", "Top", "Isometric"],
            view_positions=[[0.1, 0.1], [0.3, 0.1], [0.1, 0.3], [0.3, 0.3]],
            view_scales=["1:1", "1:1", "1:1", "1:2"],
            view_orientations=["*Front", "*Right", "*Top", "*Isometric"],
            sheet_format="A (ANSI) Landscape",
            template_file="",
            auto_position_views=True,
            include_dimensions=True,
            include_annotations=True,
            display_hidden_edges=False,
            view_quality="High",
            custom_properties={},
            advanced_options={},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_drawing_views":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "CreateDrawingViews" in result["data"]["vba_code"]
        assert result["data"]["total_views"] == 4
        mock_adapter.generate_vba_drawing_views.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_vba_batch_export_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA batch export generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_batch_export = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": """Sub BatchExportFiles()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim errors As Long
    Dim warnings As Long

    Set swApp = Application.SldWorks
    ' Batch export logic here
End Sub""",
                    "operation": "Batch Export",
                    "export_format": "STEP",
                    "file_count": 25,
                    "source_directory": "C:\\Models\\",
                    "export_directory": "C:\\Exports\\",
                },
                execution_time=0.8,
            )
        )

        input_data = VBABatchInput(
            source_directory="C:\\Models\\",
            export_directory="C:\\Exports\\",
            export_format="STEP",
            file_pattern="*.sldprt",
            include_subdirectories=True,
            export_options={
                "step_version": "AP214",
                "units": "mm",
                "precision": "high",
            },
            overwrite_existing=False,
            create_log=True,
            parallel_processing=False,
            error_handling="Continue",
            backup_originals=False,
            custom_naming_pattern="",
            pre_processing_steps=[],
            post_processing_steps=[],
            recursive=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_batch_export":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "BatchExportFiles" in result["data"]["vba_code"]
        assert result["data"]["export_format"] == "STEP"
        mock_adapter.generate_vba_batch_export.assert_called_once()

    @pytest.mark.asyncio
    async def test_vba_generation_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in VBA generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_extrusion = AsyncMock(
            return_value=Mock(
                is_success=False, error="Invalid sketch reference", execution_time=0.1
            )
        )

        input_data = VBAExtrusionInput(sketch_name="InvalidSketch", depth=25.0)

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_extrusion":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Invalid sketch reference" in result["message"]

    @pytest.mark.unit
    def test_vba_extrusion_input_validation(self):
        """Test input validation for VBA extrusion."""
        # Valid input
        valid_input = VBAExtrusionInput(sketch_name="Sketch1", depth=25.0)
        assert valid_input.sketch_name == "Sketch1"
        assert valid_input.depth == 25.0

        # Test with all optional parameters
        full_input = VBAExtrusionInput(
            sketch_name="Sketch1",
            depth=25.0,
            direction="Blind",
            reverse_direction=False,
            draft_angle=5.0,
            thin_feature=True,
            merge_result=True,
        )
        assert full_input.draft_angle == 5.0
        assert full_input.thin_feature is True

    @pytest.mark.unit
    def test_vba_batch_input_validation(self):
        """Test input validation for VBA batch operations."""
        # Valid input
        valid_input = VBABatchInput(
            source_directory="./models/",
            export_directory="./exports/",
            export_format="STEP",
        )
        assert valid_input.source_directory == "./models/"
        assert valid_input.export_format == "STEP"

        # Test with optional parameters
        full_input = VBABatchInput(
            source_directory="./models/",
            export_directory="./exports/",
            export_format="IGES",
            file_pattern="*.sldprt",
            include_subdirectories=True,
            parallel_processing=False,
        )
        assert full_input.file_pattern == "*.sldprt"
        assert full_input.parallel_processing is False

    @pytest.mark.performance
    async def test_vba_generation_performance(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test performance characteristics of VBA generation."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        # Mock a complex operation that should trigger VBA generation
        mock_adapter.generate_vba_extrusion = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": "Test VBA Code",
                    "parameter_count": 25,  # High complexity
                    "generation_time": 0.8,
                },
                execution_time=0.8,
            )
        )

        input_data = VBAExtrusionInput(sketch_name="ComplexSketch", depth=50.0)

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_extrusion":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)

        # Verify VBA generation is chosen for complex operations
        assert result["status"] == "success"
        assert result["data"]["parameter_count"] == 25
        assert result["data"]["generation_time"] < 1.0  # Should be fast


class TestVBAGenerationBranchCoverage:
    """Additional branch coverage for uncovered VBA generation tool lines."""

    @pytest.mark.asyncio
    async def test_vba_core_tool_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover exception blocks for typed VBA generator tools."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_revolve = AsyncMock(
            side_effect=RuntimeError("boom revolve")
        )
        mock_adapter.generate_vba_assembly_insert = AsyncMock(
            side_effect=RuntimeError("boom asm")
        )
        mock_adapter.generate_vba_drawing_views = AsyncMock(
            side_effect=RuntimeError("boom draw")
        )
        mock_adapter.generate_vba_batch_export = AsyncMock(
            side_effect=RuntimeError("boom batch")
        )

        by_name = {t.name: t.func for t in mcp_server._tools}

        r1 = await by_name["generate_vba_revolve"](
            VBARevolveInput(sketch_name="S1", axis_reference="A1", angle_degrees=90.0)
        )
        r2 = await by_name["generate_vba_assembly_insert"](
            VBAAssemblyInput(
                assembly_file="a.sldasm",
                component_file="c.sldprt",
                insertion_point=[0, 0, 0],
            )
        )
        r3 = await by_name["generate_vba_drawing_views"](
            VBADrawingInput(
                drawing_file="d.slddrw",
                model_file="m.sldprt",
                views_to_create=["Front"],
            )
        )
        r4 = await by_name["generate_vba_batch_export"](
            VBABatchInput(
                source_directory="./in", export_directory="./out", export_format="STEP"
            )
        )

        for result in (r1, r2, r3, r4):
            assert result["status"] == "error"
            assert "failed to generate vba code" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_vba_extrusion_exception_and_adapter_error_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover extrusion exception branch and non-success branches for typed VBA tools."""
        await register_vba_generation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_extrusion = AsyncMock(
            side_effect=RuntimeError("boom extrusion")
        )
        mock_adapter.generate_vba_revolve = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )
        mock_adapter.generate_vba_assembly_insert = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )
        mock_adapter.generate_vba_drawing_views = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )
        mock_adapter.generate_vba_batch_export = AsyncMock(
            return_value=Mock(is_success=False, error=None)
        )

        by_name = {t.name: t.func for t in mcp_server._tools}

        extrusion = await by_name["generate_vba_extrusion"](
            VBAExtrusionInput(sketch_name="Sketch1", depth=10.0)
        )
        revolve = await by_name["generate_vba_revolve"](
            VBARevolveInput(sketch_name="S1", axis_reference="A1", angle_degrees=90.0)
        )
        assembly = await by_name["generate_vba_assembly_insert"](
            VBAAssemblyInput(
                assembly_file="a.sldasm",
                component_file="c.sldprt",
                insertion_point=[0, 0, 0],
            )
        )
        drawing = await by_name["generate_vba_drawing_views"](
            VBADrawingInput(
                drawing_file="d.slddrw",
                model_file="m.sldprt",
                views_to_create=["Front"],
            )
        )
        batch = await by_name["generate_vba_batch_export"](
            VBABatchInput(
                source_directory="./in", export_directory="./out", export_format="STEP"
            )
        )

        for result in (extrusion, revolve, assembly, drawing, batch):
            assert result["status"] == "error"
            assert "failed to generate vba code" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_vba_dict_tools_supported_and_unsupported_paths(
        self, mcp_server, mock_config
    ):
        """Cover success, unsupported-operation, and exception branches for dict-input VBA tools."""
        await register_vba_generation_tools(mcp_server, object(), mock_config)
        by_name = {t.name: t.func for t in mcp_server._tools}

        part_ok = await by_name["generate_vba_part_modeling"](
            {"operation": "fillet", "radius": 2.5}
        )
        mate_ok = await by_name["generate_vba_assembly_mates"](
            {"mate_type": "distance", "distance": 10.0}
        )
        dim_ok = await by_name["generate_vba_drawing_dimensions"](
            {"dimension_type": "angular", "precision": 4}
        )
        file_custom_props = await by_name["generate_vba_file_operations"](
            {
                "operation": "custom_properties",
                "property_name": "Finish",
                "property_value": "Anodized",
            }
        )
        file_ok = await by_name["generate_vba_file_operations"](
            {"operation": "pack_and_go", "target_folder": "C:\\Out"}
        )
        rec_start = await by_name["generate_vba_macro_recorder"](
            {"operation": "start_recording"}
        )
        rec_stop = await by_name["generate_vba_macro_recorder"](
            {"operation": "stop_recording"}
        )
        rec_ok = await by_name["generate_vba_macro_recorder"](
            {"operation": "create_template", "macro_name": "MyMacro"}
        )

        file_unsupported = await by_name["generate_vba_file_operations"](
            {"operation": "unknown"}
        )
        rec_unsupported = await by_name["generate_vba_macro_recorder"](
            {"operation": "unknown"}
        )
        part_unsupported = await by_name["generate_vba_part_modeling"](
            {"operation": "unknown"}
        )

        # Trigger exception handlers with invalid non-dict payloads
        part_exc = await by_name["generate_vba_part_modeling"](None)
        mate_exc = await by_name["generate_vba_assembly_mates"](None)
        dim_exc = await by_name["generate_vba_drawing_dimensions"](None)
        file_exc = await by_name["generate_vba_file_operations"](None)
        rec_exc = await by_name["generate_vba_macro_recorder"](None)

        for result in (
            part_ok,
            mate_ok,
            dim_ok,
            file_custom_props,
            file_ok,
            rec_start,
            rec_stop,
            rec_ok,
        ):
            assert result["status"] == "success"

        assert "SetCustomProperties" in file_custom_props["vba_code"]
        assert "StartMacroRecording" in rec_start["vba_code"]
        assert "StopMacroRecording" in rec_stop["vba_code"]

        for result in (file_unsupported, rec_unsupported, part_unsupported):
            assert result["status"] == "error"
            assert "unsupported operation" in result["message"].lower()

        for result in (part_exc, mate_exc, dim_exc, file_exc, rec_exc):
            assert result["status"] == "error"
            assert "failed to generate vba code" in result["message"].lower()
