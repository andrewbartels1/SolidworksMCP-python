from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
)
from src.solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
import src.solidworks_mcp.adapters.pywin32_adapter as pywin32_mod
from src.solidworks_mcp.exceptions import SolidWorksMCPError
from src.solidworks_mcp.tools.drawing import (
    AddDimensionInput as DrawingAddDimensionInput,
    AddNoteInput,
    AnnotationInput,
    CreateDetailViewInput,
    CreateDrawingViewInput,
    CreateSectionViewInput,
    DrawingCreationInput,
    DrawingViewInput,
    DimensionInput,
    UpdateSheetFormatInput,
    register_drawing_tools,
)
from src.solidworks_mcp.tools.drawing_analysis import (
    AnnotationAnalysisInput,
    ComplianceCheckInput,
    DimensionAnalysisInput,
    DrawingAnalysisInput,
    register_drawing_analysis_tools,
)
from src.solidworks_mcp.tools.export import (
    BatchExportInput,
    ExportFileInput,
    ExportImageInput,
    register_export_tools,
)
from src.solidworks_mcp.tools.sketching import (
    AddArcInput,
    AddCircleInput,
    AddDimensionInput as SketchAddDimensionInput,
    AddLineInput,
    AddRectangleInput,
    AddRelationInput,
    AddSplineInput,
    CreateSketchInput,
    TutorialSimpleHoleInput,
    register_sketching_tools,
)
from src.solidworks_mcp.tools.vba_generation import (
    VBAAssemblyInput,
    VBABatchInput,
    VBADrawingInput,
    VBAExtrusionInput,
    VBARevolveInput,
    register_vba_generation_tools,
)


def _ok(data):
    """Test helper for ok."""
    return SimpleNamespace(
        is_success=True,
        data=data,
        error=None,
        execution_time=0.01,
    )


def _tool(mcp_server, name: str):
    """Test helper for tool."""
    for registered in mcp_server._tools:
        if registered.name == name:
            return registered.handler
    raise AssertionError(f"Tool not found: {name}")


class _PoolAdapterStub:
    """Test suite for PoolAdapterStub."""
    def __init__(self, fail: bool = False):
        """Test helper for init."""
        self.fail = fail
        self.disconnected = False

    async def connect(self):
        """Test helper for connect."""
        return None

    async def disconnect(self):
        """Test helper for disconnect."""
        self.disconnected = True

    async def health_check(self):
        """Test helper for health check."""
        return AdapterHealth(
            healthy=not self.fail,
            last_check=datetime.now(),
            error_count=1 if self.fail else 0,
            success_count=0 if self.fail else 1,
            average_response_time=0.01,
            connection_status="connected",
            metrics={"id": id(self)},
        )


@pytest.mark.asyncio
async def test_connection_pool_adapter_retry_and_error_result():
    """Test connection pool adapter retry and error result."""
    created: list[_PoolAdapterStub] = []

    def factory():
        """Test helper for factory."""
        adapter = _PoolAdapterStub()
        created.append(adapter)
        return adapter

    pool = ConnectionPoolAdapter(adapter_factory=factory, pool_size=1, max_retries=1)

    async def always_fail(_adapter):
        """Test helper for always fail."""
        raise RuntimeError("boom")

    result = await pool._execute_with_pool("unit_test", always_fail)
    assert isinstance(result, AdapterResult)
    assert result.status == AdapterResultStatus.ERROR
    assert "failed after" in (result.error or "")
    assert len(created) >= 2


@pytest.mark.asyncio
async def test_connection_pool_adapter_health_and_timeout_paths():
    """Test connection pool adapter health and timeout paths."""
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: _PoolAdapterStub(), pool_size=1
    )

    not_ready = await pool.health_check()
    assert not_ready.connection_status == "pool_not_initialized"

    await pool.connect()
    healthy = await pool.health_check()
    assert healthy.connection_status == "pooled"
    assert healthy.metrics["pool_size"] == 1

    await pool.disconnect()
    pool.pool_initialized = True
    with pytest.raises(Exception, match="No adapter available"):
        await pool._get_adapter(timeout=0.001)


@pytest.mark.asyncio
async def test_mock_adapter_error_and_edge_paths(mock_config):
    """Test mock adapter error and edge paths."""
    adapter = MockSolidWorksAdapter(mock_config)

    unsupported = await adapter.open_model("not_supported.txt")
    assert unsupported.is_error

    closed = await adapter.close_model()
    assert closed.status == AdapterResultStatus.WARNING

    no_model_export = await adapter.export_file("out.step", "step")
    assert no_model_export.is_error

    await adapter.connect()
    await adapter.create_part("UnitPart")
    missing_dim = await adapter.get_dimension("D999@Sketch1")
    assert missing_dim.is_error

    bad_sketch_line = await adapter.add_line(0, 0, 1, 1)
    assert bad_sketch_line.is_error

    await adapter.create_sketch("Front Plane")
    assert (await adapter.add_line(0, 0, 10, 0)).is_success
    assert (await adapter.exit_sketch()).is_success


def test_pywin32_adapter_guard_and_helpers(monkeypatch):
    """Test pywin32 adapter guard and helpers."""
    class _ConcretePyWin32Adapter(PyWin32Adapter):
        """Test suite for ConcretePyWin32Adapter."""
        async def exit_sketch(self):
            """Test helper for exit sketch."""
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", False)
    with pytest.raises(SolidWorksMCPError):
        _ConcretePyWin32Adapter({})

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", True)
    monkeypatch.setattr(pywin32_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        pywin32_mod,
        "pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )

    adapter = _ConcretePyWin32Adapter({})
    adapter.currentModel = SimpleNamespace(GetType=lambda: 3)
    assert adapter._get_document_type() == "Drawing"

    ok = adapter._handle_com_operation("simple", lambda: "done")
    assert ok.is_success
    assert ok.data == "done"

    err = adapter._handle_com_operation(
        "simple", lambda: (_ for _ in ()).throw(ValueError("x"))
    )
    assert err.is_error
    assert "Error in simple" in (err.error or "")


@pytest.mark.asyncio
async def test_drawing_tools_simulation_branches(mcp_server, mock_config):
    """Test drawing tools simulation branches."""
    await register_drawing_tools(mcp_server, object(), mock_config)

    assert (
        await _tool(mcp_server, "create_drawing_view")(
            input_data=CreateDrawingViewInput(model_path="m.sldprt", view_type="front")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_dimension")(
            input_data=DrawingAddDimensionInput(
                dimension_type="linear", entity1="L1", position_x=1, position_y=2
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_note")(
            input_data=AddNoteInput(text="n", position_x=1, position_y=2)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "create_section_view")(
            input_data=CreateSectionViewInput(
                section_line_start=(0, 0),
                section_line_end=(1, 1),
                view_position_x=1,
                view_position_y=2,
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "create_detail_view")(
            input_data=CreateDetailViewInput(
                center_x=0, center_y=0, radius=2, view_position_x=3, view_position_y=4
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "update_sheet_format")(
            input_data=UpdateSheetFormatInput(format_file="f.slddrt")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "auto_dimension_view")(
            input_data={"view_name": "Front"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "check_drawing_standards")(
            input_data={"standard": "ANSI"}
        )
    )["status"] == "success"

    alias_result = await _tool(mcp_server, "add_dimension")(
        input_data=DimensionInput(
            entities=["E1", "E2"], position=[5, 6], dimension_type="linear"
        )
    )
    assert alias_result["status"] == "success"

    assert (
        await _tool(mcp_server, "create_technical_drawing")(
            input_data=DrawingCreationInput(
                output_path="o.slddrw", auto_populate_views=True
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_drawing_view")(
            input_data=DrawingViewInput(
                view_name="Front", view_type="front", position=[1, 1]
            )
        )
    )["status"] == "success"
    assert (await _tool(mcp_server, "update_title_block")(input_data={"title": "A"}))[
        "status"
    ] == "success"


class _ExportFallbackAdapter:
    """Test suite for ExportFallbackAdapter."""
    async def export_file(self, file_path: str, format_type: str):
        """Test helper for export file."""
        if not file_path:
            return SimpleNamespace(
                is_success=False, error="missing path", execution_time=0.01
            )
        return SimpleNamespace(
            is_success=True,
            error=None,
            data={"file": file_path, "fmt": format_type},
            execution_time=0.01,
        )


@pytest.mark.asyncio
async def test_export_tools_fallback_and_aliases(mcp_server, mock_config):
    """Test export tools fallback and aliases."""
    await register_export_tools(mcp_server, _ExportFallbackAdapter(), mock_config)

    assert (
        await _tool(mcp_server, "export_step")(
            input_data={"file_path": "a.step", "format_type": "step"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_iges")(
            input_data=ExportFileInput(file_path="a.igs", format_type="iges")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_stl")(
            input_data=ExportFileInput(file_path="a.stl", format_type="stl")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_pdf")(
            input_data=ExportFileInput(file_path="a.pdf", format_type="pdf")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_dwg")(
            input_data=ExportFileInput(file_path="a.dwg", format_type="dwg")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_image")(
            input_data=ExportImageInput(
                output_path="a.png", image_format="png", resolution="800x600"
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "batch_export")(
            input_data=BatchExportInput(
                source_directory="src",
                output_directory="out",
                export_format="step",
                file_pattern="*.sldprt",
            )
        )
    )["status"] == "success"

    error_result = await _tool(mcp_server, "export_step")(
        input_data={"file_path": None, "format_type": "step"}
    )
    assert error_result["status"] == "error"


@pytest.mark.asyncio
async def test_drawing_analysis_simulation_paths(mcp_server, mock_config):
    """Test drawing analysis simulation paths."""
    await register_drawing_analysis_tools(mcp_server, object(), mock_config)

    assert (
        await _tool(mcp_server, "analyze_drawing_comprehensive")(
            input_data=DrawingAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_dimensions")(
            input_data=DimensionAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_annotations")(
            input_data=AnnotationAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "check_drawing_compliance")(
            input_data=ComplianceCheckInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_views")(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_drawing_report")(
            input_data={"drawing_path": "a.slddrw", "report_type": "summary"}
        )
    )["status"] == "success"


@pytest.mark.asyncio
async def test_vba_generation_uncovered_branches(mcp_server, mock_config):
    """Test vba generation uncovered branches."""
    await register_vba_generation_tools(mcp_server, object(), mock_config)

    assert (
        await _tool(mcp_server, "generate_vba_extrusion")(
            input_data=VBAExtrusionInput(depth=5)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_revolve")(
            input_data=VBARevolveInput(angle_degrees=180)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_assembly_insert")(
            input_data=VBAAssemblyInput(component_path="c.sldprt")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_drawing_views")(
            input_data=VBADrawingInput(model_path="m.sldprt", scale=1.0)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_batch_export")(
            input_data=VBABatchInput(
                operation_type="export",
                file_pattern="*.sldprt",
                source_folder="src",
                target_folder="out",
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_part_modeling")(
            input_data={"operation": "shell", "thickness": 2.0}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_part_modeling")(
            input_data={"operation": "fillet", "radius": 3.0}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_assembly_mates")(
            input_data={"mate_type": "concentric"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_drawing_dimensions")(
            input_data={"dimension_type": "angular", "precision": 3}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_file_operations")(
            input_data={"operation": "pack_and_go", "target_folder": "C:/tmp"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_vba_macro_recorder")(
            input_data={"operation": "create_template", "macro_name": "MyMacro"}
        )
    )["status"] == "success"

    unsupported = await _tool(mcp_server, "generate_vba_file_operations")(
        input_data={"operation": "unknown"}
    )
    assert unsupported["status"] == "error"


class _SketchAdapterStub:
    """Test suite for SketchAdapterStub."""
    async def create_sketch(self, _plane):
        """Test helper for create sketch."""
        return _ok({"sketch_name": "Sketch1"})

    async def add_sketch_line(self, *_args):
        """Test helper for add sketch line."""
        return _ok({"entity_id": "Line1"})

    async def add_line(self, *_args):
        """Test helper for add line."""
        return _ok("Line2")

    async def add_sketch_circle(self, *_args):
        """Test helper for add sketch circle."""
        return _ok({"entity_id": "Circle1"})

    async def add_circle(self, *_args):
        """Test helper for add circle."""
        return _ok("Circle2")

    async def add_sketch_rectangle(self, *_args):
        """Test helper for add sketch rectangle."""
        return _ok({"entity_id": "Rect1"})

    async def add_rectangle(self, *_args):
        """Test helper for add rectangle."""
        return _ok("Rect2")

    async def exit_sketch(self):
        """Test helper for exit sketch."""
        return _ok(None)

    async def add_arc(self, *_args):
        """Test helper for add arc."""
        return _ok("Arc1")

    async def add_spline(self, *_args):
        """Test helper for add spline."""
        return _ok("Spline1")

    async def add_centerline(self, *_args):
        """Test helper for add centerline."""
        return _ok("CL1")

    async def add_polygon(self, *_args):
        """Test helper for add polygon."""
        return _ok("Poly1")

    async def add_ellipse(self, *_args):
        """Test helper for add ellipse."""
        return _ok("Ellipse1")

    async def add_sketch_constraint(self, *_args):
        """Test helper for add sketch constraint."""
        return _ok("Constraint1")

    async def add_sketch_dimension(self, *_args):
        """Test helper for add sketch dimension."""
        return _ok("Dim1")

    async def sketch_linear_pattern(self, *_args):
        """Test helper for sketch linear pattern."""
        return _ok("LP1")

    async def sketch_circular_pattern(self, *_args):
        """Test helper for sketch circular pattern."""
        return _ok("CP1")

    async def sketch_mirror(self, *_args):
        """Test helper for sketch mirror."""
        return _ok("Mirror1")

    async def sketch_offset(self, *_args):
        """Test helper for sketch offset."""
        return _ok("Offset1")

    async def create_cut(self, *_args):
        """Test helper for create cut."""
        return _ok("Cut1")


@pytest.mark.asyncio
async def test_sketching_tools_uncovered_paths(mcp_server, mock_config):
    """Test sketching tools uncovered paths."""
    await register_sketching_tools(mcp_server, _SketchAdapterStub(), mock_config)

    assert (
        await _tool(mcp_server, "create_sketch")(
            input_data=CreateSketchInput(plane="Top", sketch_name="S1")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_line")(
            input_data=AddLineInput(start_x=0, start_y=0, end_x=5, end_y=0)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_circle")(
            input_data=AddCircleInput(center_x=0, center_y=0, radius=2)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_rectangle")(
            input_data=AddRectangleInput(
                corner1_x=0, corner1_y=0, corner2_x=5, corner2_y=3
            )
        )
    )["status"] == "success"
    assert (await _tool(mcp_server, "exit_sketch")())["status"] == "success"
    assert (
        await _tool(mcp_server, "add_arc")(
            input_data=AddArcInput(
                center_x=0, center_y=0, start_x=1, start_y=0, end_x=0, end_y=1
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_spline")(
            input_data=AddSplineInput(
                points=[{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 0}]
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_centerline")(
            input_data=AddLineInput(x1=0, y1=0, x2=0, y2=5)
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_polygon")(input_data={"sides": 6, "radius": 5})
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_ellipse")(
            input_data={"major_axis": 10, "minor_axis": 5}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_sketch_constraint")(
            input_data=AddRelationInput(
                entity1="L1", entity2="L2", relation_type="parallel"
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_sketch_dimension")(
            input_data=SketchAddDimensionInput(
                entity1="L1", dimension_type="linear", value=10
            )
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "sketch_linear_pattern")(
            input_data={"entities": ["L1"], "count": 3}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "sketch_circular_pattern")(
            input_data={"entities": ["L1"], "count": 6}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "sketch_mirror")(
            input_data={"entities": ["L1"], "mirror_line": "CL1"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "sketch_offset")(
            input_data={"entities": ["L1"], "offset_distance": 1.5}
        )
    )["status"] == "success"
    assert (await _tool(mcp_server, "sketch_tutorial_simple_hole")())[
        "status"
    ] == "success"
    assert (
        await _tool(mcp_server, "tutorial_simple_hole")(
            input_data=TutorialSimpleHoleInput(
                plane="Top", center_x=0, center_y=0, diameter=5, depth=3
            )
        )
    )["status"] == "success"


@pytest.mark.asyncio
async def test_sketching_error_branches_with_exceptions(mcp_server, mock_config):
    """Test sketching error branches with exceptions."""
    adapter = _SketchAdapterStub()
    adapter.add_arc = AsyncMock(side_effect=RuntimeError("arc failed"))
    await register_sketching_tools(mcp_server, adapter, mock_config)

    result = await _tool(mcp_server, "add_arc")(
        input_data=AddArcInput(
            center_x=0, center_y=0, start_x=1, start_y=0, end_x=0, end_y=1
        )
    )
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_connection_pool_passthrough_methods_are_wired(monkeypatch):
    """Test connection pool passthrough methods are wired."""
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: _PoolAdapterStub(), pool_size=1
    )

    async def _fake_execute(name, operation):
        """Test helper for fake execute."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"op": name})

    monkeypatch.setattr(pool, "_execute_with_pool", _fake_execute)

    assert (await pool.open_model("a.sldprt")).is_success
    assert (await pool.close_model()).is_success
    assert (await pool.create_part()).is_success
    assert (await pool.create_assembly()).is_success
    assert (await pool.create_drawing()).is_success
    assert (await pool.create_extrusion({"depth": 1})).is_success
    assert (await pool.create_revolve({"angle": 90})).is_success
    assert (await pool.create_sweep({"path": "P"})).is_success
    assert (await pool.create_loft({"profiles": []})).is_success
    assert (await pool.create_sketch("Top")).is_success
    assert (await pool.add_line(0, 0, 1, 1)).is_success
    assert (await pool.add_circle(0, 0, 5)).is_success
    assert (await pool.add_rectangle(0, 0, 2, 3)).is_success
    assert (await pool.exit_sketch()).is_success
    assert (await pool.get_mass_properties()).is_success
    assert (await pool.export_file("x.step", "step")).is_success
    assert (await pool.get_dimension("D1@Sketch1")).is_success
    assert (await pool.set_dimension("D1@Sketch1", 12.0)).is_success


@pytest.mark.asyncio
async def test_mock_adapter_additional_feature_and_dimension_paths(mock_config):
    """Test mock adapter additional feature and dimension paths."""
    adapter = MockSolidWorksAdapter(mock_config)

    # Not connected path
    assert (await adapter.create_part()).is_error

    await adapter.connect()
    assert bool(adapter.is_connected)

    # Model creation paths
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.create_drawing()).is_success
    assert (await adapter.create_part("P1", "in")).is_success

    # Feature creation paths with and without active model
    adapter._current_model = None
    assert (
        await adapter.create_revolve(
            SimpleNamespace(
                angle=90,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_error
    assert (
        await adapter.create_sweep(
            SimpleNamespace(path="Sketch2", twist_along_path=False, twist_angle=0)
        )
    ).is_error
    assert (
        await adapter.create_loft(
            SimpleNamespace(
                profiles=["S1"], guide_curves=[], start_tangent=False, end_tangent=False
            )
        )
    ).is_error

    await adapter.create_part("P2")
    assert (await adapter.create_extrusion("Sketch1", 5.0, "blind")).is_success
    assert (
        await adapter.create_revolve(
            SimpleNamespace(
                angle=120,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_success
    assert (
        await adapter.create_sweep(
            SimpleNamespace(path="Sketch2", twist_along_path=True, twist_angle=30)
        )
    ).is_success
    assert (
        await adapter.create_loft(
            SimpleNamespace(
                profiles=["S1", "S2"],
                guide_curves=["G1"],
                start_tangent=True,
                end_tangent=False,
            )
        )
    ).is_success

    # Sketch wrapper and geometry failures/success
    adapter._current_sketch = None
    assert (await adapter.add_sketch_line(0, 0, 1, 1)).is_error
    assert (await adapter.add_circle(0, 0, 2)).is_error
    assert (await adapter.add_rectangle(0, 0, 2, 1)).is_error

    assert (await adapter.create_sketch("Top Plane")).is_success
    assert (await adapter.add_sketch_line(0, 0, 10, 0)).is_success
    assert (await adapter.add_circle(2, 2, 1)).is_success
    assert (await adapter.add_rectangle(-1, -1, 1, 1)).is_success

    # Mass properties and dimensions
    assert (await adapter.get_mass_properties()).is_success
    assert (await adapter.set_dimension("D123@Sketch9", 4.2)).is_success
    assert (await adapter.get_dimension("D123@Sketch9")).is_success


class _DrawingAndAnalysisAdapterStub:
    """Test suite for DrawingAndAnalysisAdapterStub."""
    async def create_technical_drawing(self, *_args, **_kwargs):
        """Test helper for create technical drawing."""
        return _ok({"drawing_path": "d.slddrw"})

    async def add_drawing_view(self, *_args, **_kwargs):
        """Test helper for add drawing view."""
        return _ok({"view_name": "Front"})

    async def add_annotation(self, *_args, **_kwargs):
        """Test helper for add annotation."""
        return _ok({"annotation": "ok"})

    async def update_title_block(self, *_args, **_kwargs):
        """Test helper for update title block."""
        return _ok({"title": "T"})

    async def analyze_drawing_comprehensive(self, *_args, **_kwargs):
        """Test helper for analyze drawing comprehensive."""
        return _ok({"score": 90})

    async def analyze_drawing_dimensions(self, *_args, **_kwargs):
        """Test helper for analyze drawing dimensions."""
        return _ok({"dims": 10})

    async def analyze_drawing_annotations(self, *_args, **_kwargs):
        """Test helper for analyze drawing annotations."""
        return _ok({"notes": 3})

    async def check_drawing_compliance(self, *_args, **_kwargs):
        """Test helper for check drawing compliance."""
        return _ok({"compliant": True})

    async def analyze_drawing_views(self, *_args, **_kwargs):
        """Test helper for analyze drawing views."""
        return _ok({"views": 4})

    async def generate_drawing_report(self, *_args, **_kwargs):
        """Test helper for generate drawing report."""
        return _ok({"report": "ok"})


@pytest.mark.asyncio
async def test_drawing_and_analysis_adapter_passthrough_success(
    mcp_server, mock_config
):
    """Test drawing and analysis adapter passthrough success."""
    adapter = _DrawingAndAnalysisAdapterStub()
    await register_drawing_tools(mcp_server, adapter, mock_config)
    await register_drawing_analysis_tools(mcp_server, adapter, mock_config)

    assert (
        await _tool(mcp_server, "create_technical_drawing")(
            input_data=DrawingCreationInput(output_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_drawing_view")(
            input_data=DrawingViewInput(view_name="Front")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "add_annotation")(
            input_data=AnnotationInput(text="n", annotation_type="Note")
        )
    )["status"] == "success"
    assert (await _tool(mcp_server, "update_title_block")(input_data={"title": "T"}))[
        "status"
    ] == "success"

    assert (
        await _tool(mcp_server, "analyze_drawing_comprehensive")(
            input_data=DrawingAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_dimensions")(
            input_data=DimensionAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_annotations")(
            input_data=AnnotationAnalysisInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "check_drawing_compliance")(
            input_data=ComplianceCheckInput(drawing_path="a.slddrw")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "analyze_drawing_views")(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "generate_drawing_report")(
            input_data={"drawing_path": "a.slddrw"}
        )
    )["status"] == "success"


class _ExportNativeAdapter:
    """Test suite for ExportNativeAdapter."""
    async def export_step(self, *_args, **_kwargs):
        """Test helper for export step."""
        return _ok({"fmt": "step"})

    async def export_iges(self, *_args, **_kwargs):
        """Test helper for export iges."""
        return _ok({"fmt": "iges"})

    async def export_stl(self, *_args, **_kwargs):
        """Test helper for export stl."""
        return _ok({"fmt": "stl"})

    async def export_pdf(self, *_args, **_kwargs):
        """Test helper for export pdf."""
        return _ok({"fmt": "pdf"})

    async def export_dwg(self, *_args, **_kwargs):
        """Test helper for export dwg."""
        return _ok({"fmt": "dwg"})

    async def export_image(self, *_args, **_kwargs):
        """Test helper for export image."""
        return _ok({"fmt": "image"})

    async def batch_export(self, *_args, **_kwargs):
        """Test helper for batch export."""
        return _ok({"count": 2})


@pytest.mark.asyncio
async def test_export_tools_native_adapter_methods(mcp_server, mock_config):
    """Test export tools native adapter methods."""
    await register_export_tools(mcp_server, _ExportNativeAdapter(), mock_config)

    assert (
        await _tool(mcp_server, "export_step")(
            input_data=ExportFileInput(file_path="a.step", format_type="step")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_iges")(
            input_data=ExportFileInput(file_path="a.igs", format_type="iges")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_stl")(
            input_data=ExportFileInput(file_path="a.stl", format_type="stl")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_pdf")(
            input_data=ExportFileInput(file_path="a.pdf", format_type="pdf")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_dwg")(
            input_data=ExportFileInput(file_path="a.dwg", format_type="dwg")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "export_image")(
            input_data=ExportImageInput(file_path="a.png", format_type="png")
        )
    )["status"] == "success"
    assert (
        await _tool(mcp_server, "batch_export")(
            input_data=BatchExportInput(
                source_directory="src", output_directory="out", format_type="step"
            )
        )
    )["status"] == "success"


@pytest.mark.asyncio
async def test_sketching_tool_error_return_branches(mcp_server, mock_config):
    """Test sketching tool error return branches."""
    adapter = _SketchAdapterStub()
    adapter.add_polygon = AsyncMock(
        return_value=SimpleNamespace(
            is_success=False, error="poly", execution_time=0.01
        )
    )
    adapter.add_ellipse = AsyncMock(
        return_value=SimpleNamespace(
            is_success=False, error="ellipse", execution_time=0.01
        )
    )
    adapter.sketch_mirror = AsyncMock(
        return_value=SimpleNamespace(
            is_success=False, error="mirror", execution_time=0.01
        )
    )
    adapter.sketch_offset = AsyncMock(
        return_value=SimpleNamespace(
            is_success=False, error="offset", execution_time=0.01
        )
    )
    await register_sketching_tools(mcp_server, adapter, mock_config)

    assert (await _tool(mcp_server, "add_polygon")(input_data={"sides": 5}))[
        "status"
    ] == "error"
    assert (
        await _tool(mcp_server, "add_ellipse")(
            input_data={"major_axis": 10, "minor_axis": 5}
        )
    )["status"] == "error"
    assert (
        await _tool(mcp_server, "sketch_mirror")(
            input_data={"entities": ["L1"], "mirror_line": "CL1"}
        )
    )["status"] == "error"
    assert (
        await _tool(mcp_server, "sketch_offset")(
            input_data={"entities": ["L1"], "offset_distance": 1.0}
        )
    )["status"] == "error"


@pytest.mark.asyncio
async def test_vba_generation_unsupported_branches(mcp_server, mock_config):
    """Test vba generation unsupported branches."""
    await register_vba_generation_tools(mcp_server, object(), mock_config)

    bad_part = await _tool(mcp_server, "generate_vba_part_modeling")(
        input_data={"operation": "does_not_exist"}
    )
    assert bad_part["status"] == "error"

    bad_macro = await _tool(mcp_server, "generate_vba_macro_recorder")(
        input_data={"operation": "nope"}
    )
    assert bad_macro["status"] == "error"


@pytest.mark.asyncio
async def test_pywin32_adapter_many_guard_paths(monkeypatch):
    """Test pywin32 adapter many guard paths."""
    class _ConcretePyWin32Adapter(PyWin32Adapter):
        """Test suite for ConcretePyWin32Adapter."""
        async def exit_sketch(self):
            """Test helper for exit sketch."""
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", True)
    monkeypatch.setattr(pywin32_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        pywin32_mod,
        "pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )

    adapter = _ConcretePyWin32Adapter({})

    # Disconnected guards
    assert adapter.is_connected() is False
    assert (await adapter.open_model("x.sldprt")).is_error
    assert (await adapter.create_part()).is_error
    assert (await adapter.create_assembly()).is_error
    assert (await adapter.create_drawing()).is_error

    # No active model guards
    assert (
        await adapter.create_extrusion(
            SimpleNamespace(
                depth=1,
                draft_angle=0,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_error
    assert (
        await adapter.create_revolve(
            SimpleNamespace(
                angle=90,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_error
    assert (
        await adapter.create_sweep(
            SimpleNamespace(path="P", twist_along_path=False, twist_angle=0)
        )
    ).is_error
    assert (
        await adapter.create_loft(
            SimpleNamespace(
                profiles=["S1"],
                guide_curves=[],
                start_tangent=False,
                end_tangent=False,
            )
        )
    ).is_error
