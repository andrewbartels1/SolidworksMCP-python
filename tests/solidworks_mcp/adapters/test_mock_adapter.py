"""Tests for ``solidworks_mcp.adapters.mock_adapter``."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import AdapterResultStatus, ExtrusionParameters
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter, _BoolCallable
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.exceptions import SolidWorksOperationError


class TestMockAdapterCoveragePush:
    """Cover the uncovered branches in MockSolidWorksAdapter."""

    @pytest.mark.asyncio
    async def test_select_feature_no_model(self, mock_adapter) -> None:
        """select_feature returns ERROR when no model is active (line 386-388)."""
        # Disconnect resets _current_model; we can also clear it directly.
        mock_adapter._current_model = None
        result = await mock_adapter.select_feature("Extrude1")
        assert not result.is_success
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_get_selected_entities_no_model(self, mock_adapter) -> None:
        """get_selected_entities returns ERROR when no model is active."""
        mock_adapter._current_model = None
        result = await mock_adapter.get_selected_entities()
        assert not result.is_success
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_get_selected_entities_success(self, mock_adapter) -> None:
        """get_selected_entities reports canned face/edge fixtures when a model is active."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        result = await mock_adapter.get_selected_entities()
        assert result.is_success
        assert len(result.data) == 2
        assert result.data[0]["type"] == "FACE"
        assert result.data[1]["type"] == "EDGE"

    @pytest.mark.asyncio
    async def test_add_spline_malformed_point(self, mock_adapter) -> None:
        """add_spline returns ERROR when a point dict is missing x/y (line 901)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        # Provide a bad point — missing 'y' key
        result = await mock_adapter.add_spline([{"x": 0}, {"x": 10, "y": 5}])
        assert not result.is_success
        assert "missing" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_sketch_mirror_non_centerline_mirror_line(self, mock_adapter) -> None:
        """sketch_mirror returns ERROR when mirror_line is not a centerline (line 1255)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        # Add a regular line so we have a valid entity ID
        line_result = await mock_adapter.add_line(0, 0, 10, 0)
        assert line_result.is_success
        line_id = line_result.data

        # Register a fake non-centerline ID as mirror_line
        mock_adapter._sketch_entity_ids.add("NotACenterline_999")

        result = await mock_adapter.sketch_mirror(
            entities=[line_id], mirror_line="NotACenterline_999"
        )
        assert not result.is_success
        assert "centerline" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_check_sketch_fully_defined_unknown_sketch(
        self, mock_adapter
    ) -> None:
        """check_sketch_fully_defined returns ERROR for unknown sketch (lines 1460-1464)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        result = await mock_adapter.check_sketch_fully_defined(
            sketch_name="NonExistent"
        )
        assert not result.is_success
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_export_image_creates_png(self, mock_adapter, tmp_path) -> None:
        """export_image writes a minimal PNG to disk (lines 1532-1556)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        img_path = tmp_path / "test_img.png"
        result = await mock_adapter.export_image(
            {
                "file_path": str(img_path),
                "format_type": "png",
                "width": 800,
                "height": 600,
                "view_orientation": "isometric",
            }
        )
        assert result.is_success
        assert img_path.exists()
        assert img_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_pack_and_go_assembly_mock(self, mock_adapter, tmp_path) -> None:
        """pack_and_go_assembly returns a simulated SUCCESS payload (lines 1582-1605)."""
        await mock_adapter.connect()
        # Create a minimal assembly SLDASM file so source.exists() passes
        source = tmp_path / "test.sldasm"
        source.write_text("mock")
        out_dir = tmp_path / "pkg"

        result = await mock_adapter.pack_and_go_assembly(
            source_path=str(source), target_dir=str(out_dir)
        )
        assert result.is_success
        assert result.data["all_files_saved"] is True
        assert len(result.data["copied_files"]) >= 1

    @pytest.mark.asyncio
    async def test_export_file_stl_creates_file(self, mock_adapter, tmp_path) -> None:
        """export_file with 'stl' format writes a placeholder STL (lines 1643-1654)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        stl_path = tmp_path / "output.stl"
        result = await mock_adapter.export_file(str(stl_path), "stl")
        assert result.is_success
        assert stl_path.exists()
        content = stl_path.read_text()
        assert "solid" in content

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_full_path(self, mock_adapter) -> None:
        """add_sketch_constraint success path (lines 1360-1416)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        line1 = (await mock_adapter.add_line(0, 0, 10, 0)).data
        line2 = (await mock_adapter.add_line(10, 0, 10, 10)).data

        result = await mock_adapter.add_sketch_constraint(
            entity1=line1, entity2=line2, relation_type="perpendicular"
        )
        assert result.is_success

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_symmetric_path(self, mock_adapter) -> None:
        """add_sketch_constraint symmetric with entity3 (line 1377-1385)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        line1 = (await mock_adapter.add_line(5, 0, 10, 0)).data
        line2 = (await mock_adapter.add_line(-5, 0, -10, 0)).data
        cline = (await mock_adapter.add_centerline(0, -20, 0, 20)).data

        result = await mock_adapter.add_sketch_constraint(
            entity1=line1, entity2=line2, relation_type="symmetric", entity3=cline
        )
        assert result.is_success

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_entity3_rejected(self, mock_adapter) -> None:
        """Non-symmetric relation with entity3 returns ERROR (lines 1386-1393)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        line1 = (await mock_adapter.add_line(0, 0, 10, 0)).data
        line2 = (await mock_adapter.add_line(10, 0, 10, 10)).data
        cline = (await mock_adapter.add_centerline(0, -20, 0, 20)).data

        result = await mock_adapter.add_sketch_constraint(
            entity1=line1, entity2=line2, relation_type="perpendicular", entity3=cline
        )
        assert not result.is_success
        assert "entity3" in (result.error or "").lower()


class TestMockAdapterDelayBranches:
    """Cover the success-path 'delay' statements and remaining add_sketch_constraint paths."""

    @pytest.mark.asyncio
    async def test_select_feature_with_active_model(self, mock_adapter) -> None:
        """select_feature success path: asyncio.sleep + increment + return (lines 386-388)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        result = await mock_adapter.select_feature("Front Plane")
        assert result.is_success
        assert result.data["selected"] is True
        assert result.data["feature_name"] == "Front Plane"

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_no_active_sketch(self, mock_adapter) -> None:
        """add_sketch_constraint returns ERROR when no sketch is open (lines 1361-1363)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        # Do NOT call create_sketch — _current_sketch stays None
        result = await mock_adapter.add_sketch_constraint(
            "Line_1", "Line_2", "perpendicular"
        )
        assert not result.is_success
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_unsupported_relation(
        self, mock_adapter
    ) -> None:
        """add_sketch_constraint returns ERROR for unsupported relation type (lines 1367-1368)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        line1 = (await mock_adapter.add_line(0, 0, 10, 0)).data
        result = await mock_adapter.add_sketch_constraint(line1, None, "diagonal")
        assert not result.is_success
        assert "Unsupported relation type" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_symmetric_missing_entity2(
        self, mock_adapter
    ) -> None:
        """symmetric relation without entity2 returns arity ERROR (line 1379)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        line1 = (await mock_adapter.add_line(0, 0, 10, 0)).data
        # entity2=None triggers the arity guard inside the symmetric branch
        result = await mock_adapter.add_sketch_constraint(
            line1, None, "symmetric", entity3="anything"
        )
        assert not result.is_success
        assert (
            "entity2" in (result.error or "").lower()
            or "requires" in (result.error or "").lower()
        )

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_unknown_entity(self, mock_adapter) -> None:
        """add_sketch_constraint returns ERROR for entity ID not in registry (line 1400)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        result = await mock_adapter.add_sketch_constraint(
            "FAKE_ID_999", None, "horizontal"
        )
        assert not result.is_success
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_check_sketch_fully_defined_success(self, mock_adapter) -> None:
        """check_sketch_fully_defined success path returns is_fully_defined=True (line 1466)."""
        await mock_adapter.connect()
        await mock_adapter.create_part()
        await mock_adapter.create_sketch("Front")
        # call without sketch_name so it resolves to _current_sketch
        result = await mock_adapter.check_sketch_fully_defined()
        assert result.is_success
        assert result.data["is_fully_defined"] is True


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


class TestBoolCallableCoverage:
    """Test bool callable coverage."""

    def test_call_returns_bool(self):
        """Line 52 — __call__ returns bool(getter())."""
        bc = _BoolCallable(lambda: True)
        assert bc() is True

    def test_call_false(self):
        """Test call false."""

        bc = _BoolCallable(lambda: False)
        assert bc() is False


class TestMockAdapterSuccessPaths:
    """Test mock adapter success paths."""

    @pytest.mark.asyncio
    async def test_get_model_info_success(self):
        """Lines 237-255 — get_model_info with active model."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part(name="TestPart")

        result = await adapter.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS
        assert "title" in result.data
        assert "feature_count" in result.data

    @pytest.mark.asyncio
    async def test_list_features_with_actual_features(self):
        """Lines 286-300 — list_features with features in the tree (non-empty)."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        await adapter.exit_sketch()
        await adapter.create_extrusion(ExtrusionParameters(depth=10.0))

        result = await adapter.list_features(include_suppressed=False)
        assert result.status == AdapterResultStatus.SUCCESS
        assert isinstance(result.data, list)

    @pytest.mark.asyncio
    async def test_list_features_seeded_when_empty(self):
        """Lines 272-284 — list_features with no real features returns seeded list."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.list_features()
        assert result.status == AdapterResultStatus.SUCCESS
        assert len(result.data) > 0
        assert any(f["name"] == "Origin" for f in result.data)

    @pytest.mark.asyncio
    async def test_list_configurations_non_default_config(self):
        """Lines 314-316 — non-Default active config produces [Default, active]."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        # Create a model with a non-default config name
        await adapter.create_part()
        # Directly set configuration to a custom name
        adapter._current_model.configuration = "HighTolerance"

        result = await adapter.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS
        assert "Default" in result.data
        assert "HighTolerance" in result.data

    @pytest.mark.asyncio
    async def test_add_centerline_success(self):
        """Lines 662-670 — add_centerline with active sketch returns centerline id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_centerline(0.0, 0.0, 1.0, 1.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert "Centerline" in result.data

    @pytest.mark.asyncio
    async def test_add_arc_success(self):
        """Mock add_arc returns an Arc* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_arc(0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Arc")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_arc_error_when_no_sketch(self):
        """Mock add_arc returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_arc(0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_spline_success(self):
        """Mock add_spline returns a Spline* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_spline(
            [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 2.5}, {"x": 10.0, "y": 0.0}]
        )
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Spline")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_spline_error_when_no_sketch(self):
        """Mock add_spline returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_spline([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}])
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_spline_error_when_too_few_points(self):
        """Mock add_spline rejects single-point input."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_spline([{"x": 0.0, "y": 0.0}])
        assert result.status == AdapterResultStatus.ERROR
        assert "at least 2 points" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_ellipse_success(self):
        """Mock add_ellipse returns an Ellipse_* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_ellipse(0.0, 0.0, 60.0, 30.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Ellipse_")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_ellipse_error_when_no_sketch(self):
        """Mock add_ellipse returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_ellipse(0.0, 0.0, 60.0, 30.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_polygon_success(self):
        """Mock add_polygon returns a Polygon_<sides>sided_* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_polygon(0.0, 0.0, 15.0, 6)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Polygon_")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_polygon_error_when_no_sketch(self):
        """Mock add_polygon returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_polygon(0.0, 0.0, 15.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_success(self):
        """Mock sketch_linear_pattern returns a LinearPattern_* id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(0.0, 0.0, 3.0)

        result = await adapter.sketch_linear_pattern([circle.data], 1.0, 0.0, 10.0, 4)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("LinearPattern_4x10.0_")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_error_when_no_sketch(self):
        """Mock sketch_linear_pattern returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_linear_pattern(["Line1"], 1.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_rejects_unknown_entity(self):
        """Mock sketch_linear_pattern surfaces a clear error for missing IDs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.sketch_linear_pattern(["Bogus_123"], 1.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_input_validation(self):
        """Empty entities / count<2 / spacing<=0 / zero direction → ERROR."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(0.0, 0.0, 3.0)

        # Empty entities
        result = await adapter.sketch_linear_pattern([], 1.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        # count < 2
        result = await adapter.sketch_linear_pattern([circle.data], 1.0, 0.0, 10.0, 1)
        assert result.status == AdapterResultStatus.ERROR
        assert "count >= 2" in (result.error or "")

        # spacing <= 0
        result = await adapter.sketch_linear_pattern([circle.data], 1.0, 0.0, 0.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "spacing > 0" in (result.error or "")

        # zero direction vector
        result = await adapter.sketch_linear_pattern([circle.data], 0.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "non-zero direction" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_success(self):
        """Mock sketch_circular_pattern returns a CircularPattern_* id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([circle.data], 360.0, 6)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("CircularPattern_6x360.0deg_")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_error_when_no_sketch(self):
        """Mock sketch_circular_pattern returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_circular_pattern(["Circle1"], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_rejects_unknown_entity(self):
        """Mock sketch_circular_pattern surfaces error for missing IDs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.sketch_circular_pattern(["Bogus_999"], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_input_validation(self):
        """Empty entities / count<2 / angle<=0 → ERROR with descriptive message."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_circular_pattern([circle.data], 360.0, 1)
        assert result.status == AdapterResultStatus.ERROR
        assert "count >= 2" in (result.error or "")

        result = await adapter.sketch_circular_pattern([circle.data], 0.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "angle > 0" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_partial_sweep(self):
        """Mock handles partial sweeps (e.g. 180° with 3 instances) the
        same way as a full pattern — the mock only synthesises an ID, but
        the real impl uses ``angle / (count - 1)`` for partial sweeps so
        the last instance lands at the requested total angle.
        """
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([circle.data], 180.0, 3)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("CircularPattern_3x180.0deg_")

    @pytest.mark.asyncio
    async def test_sketch_mirror_success(self):
        """Mock sketch_mirror returns a Mirror_* id with valid inputs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)
        line = await adapter.add_line(5.0, 0.0, 25.0, 0.0)

        result = await adapter.sketch_mirror([line.data], cl.data)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith(f"Mirror_{cl.data}_")

    @pytest.mark.asyncio
    async def test_sketch_mirror_error_when_no_sketch(self):
        """Mock sketch_mirror returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_mirror(["Line1"], "Centerline1")
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_mirror_rejects_unknown_entity(self):
        """Mock sketch_mirror surfaces error for unknown source entities."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)

        result = await adapter.sketch_mirror(["Bogus_999"], cl.data)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_mirror_input_validation(self):
        """Empty entities and missing/unknown mirror_line each error."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)
        line = await adapter.add_line(5.0, 0.0, 25.0, 0.0)

        result = await adapter.sketch_mirror([], cl.data)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_mirror([line.data], "")
        assert result.status == AdapterResultStatus.ERROR
        assert "mirror_line entity ID" in (result.error or "")

        result = await adapter.sketch_mirror([line.data], "NotACenterline_42")
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown mirror_line entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_offset_outward_success(self):
        """Mock sketch_offset returns Offset_*_outward_* with reverse=False."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 0.0, 50.0, 0.0)

        result = await adapter.sketch_offset([line.data], 5.0, False)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Offset_5.0_outward_")

    @pytest.mark.asyncio
    async def test_sketch_offset_inward_success(self):
        """Mock sketch_offset returns Offset_*_inward_* with reverse=True."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 20.0, 50.0, 20.0)

        result = await adapter.sketch_offset([line.data], 3.0, True)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Offset_3.0_inward_")

    @pytest.mark.asyncio
    async def test_sketch_offset_error_when_no_sketch(self):
        """Mock sketch_offset returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_offset(["Line1"], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_offset_input_validation(self):
        """Empty entities / non-positive distance / unknown entity each error."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 0.0, 50.0, 0.0)

        result = await adapter.sketch_offset([], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_offset([line.data], 0.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "offset_distance > 0" in (result.error or "")

        result = await adapter.sketch_offset([line.data], -1.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "offset_distance > 0" in (result.error or "")

        result = await adapter.sketch_offset(["Bogus_42"], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")


class TestMockAdapter:
    """Test suite for mock SolidWorks adapter."""

    @pytest.mark.asyncio
    async def test_mock_adapter_initialization(self, mock_config):
        """Test mock adapter initialization."""
        adapter = MockSolidWorksAdapter(mock_config)
        assert adapter.config == mock_config
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_mock_adapter_connect_disconnect(self, mock_adapter):
        """Test mock adapter connection lifecycle."""
        # Connect
        await mock_adapter.connect()
        assert mock_adapter.is_connected

        # Disconnect
        await mock_adapter.disconnect()
        assert not mock_adapter.is_connected

    @pytest.mark.asyncio
    async def test_mock_adapter_health_check(self, mock_adapter):
        """Test mock adapter health check."""
        await mock_adapter.connect()
        health = await mock_adapter.health_check()

        assert health["status"] == "healthy"
        assert health["adapter_type"] == "mock"
        assert health["connected"] is True
        assert "version" in health
        assert "uptime" in health

    @pytest.mark.asyncio
    async def test_mock_adapter_file_operations(self, mock_adapter):
        """Test mock adapter file operations."""
        await mock_adapter.connect()

        # Test open model
        result = await mock_adapter.open_model("test.sldprt")
        assert result.is_success
        assert "test.sldprt" in result.data["title"]

        # Test save file
        result = await mock_adapter.save_file("test_saved.sldprt")
        assert result.is_success
        assert result.data["file_path"] == "test_saved.sldprt"

    @pytest.mark.asyncio
    async def test_mock_adapter_modeling_operations(self, mock_adapter):
        """Test mock adapter modeling operations."""
        await mock_adapter.connect()

        # Test create part

        result = await mock_adapter.create_part("TestPart", "mm")
        assert result.is_success
        assert result.data["name"] == "TestPart"

        assert result.data["units"] == "mm"

        # Test create extrusion

        result = await mock_adapter.create_extrusion("Sketch1", 10.0, "blind")
        assert result.is_success

        assert result.data["depth"] == 10.0
        assert result.data["direction"] == "blind"

    @pytest.mark.asyncio
    async def test_mock_adapter_sketch_operations(self, mock_adapter):
        """Test mock adapter sketch operations."""

        await mock_adapter.connect()

        # Test create sketch
        result = await mock_adapter.create_sketch("Front Plane")
        assert result.is_success
        assert result.data["plane"] == "Front Plane"

        # Test add sketch line
        result = await mock_adapter.add_sketch_line(0, 0, 10, 10, False)
        assert result.is_success

        assert result.data["start"] == {"x": 0, "y": 0}
        assert result.data["end"] == {"x": 10, "y": 10}

    @pytest.mark.asyncio
    async def test_mock_adapter_error_simulation(self, mock_config):
        """Test mock adapter error simulation."""

        config = mock_config
        config.simulate_errors = True
        adapter = MockSolidWorksAdapter(config)

        await adapter.connect()

        # Some operations should fail when error simulation is enabled
        with pytest.raises(SolidWorksOperationError):
            await adapter.open_model("nonexistent.sldprt")


class TestMockAdapterAdditionalCoverage:
    """Target additional edge paths for mock adapter coverage."""

    @pytest.mark.asyncio
    async def test_uncovered_mock_adapter_branches(self):
        """Test uncovered mock adapter branches."""
        adapter = MockSolidWorksAdapter({})

        # Cover bool/callable compatibility shim and direct method path.
        assert bool(adapter.is_connected) is False
        assert MockSolidWorksAdapter.is_connected(adapter) is False

        await adapter.connect()
        opened_asm = await adapter.open_model("C:/Models/a.sldasm")
        opened_drw = await adapter.open_model("C:/Models/a.slddrw")
        unsupported = await adapter.open_model("C:/Models/a.txt")
        assert opened_asm.is_success
        assert opened_drw.is_success
        assert unsupported.is_error

        closed_with_save = await adapter.close_model(save=True)
        assert closed_with_save.is_success

        no_sketch_exit = await adapter.exit_sketch()
        no_mass = await adapter.get_mass_properties()
        assert no_sketch_exit.status == AdapterResultStatus.WARNING
        assert no_mass.is_error

        await adapter.create_part("ExportPart", "mm")
        exported_default_delay = await adapter.export_file("C:/tmp/out.obj", "obj")
        assert exported_default_delay.is_success
        assert exported_default_delay.execution_time == pytest.approx(1.0)


class TestAdapterCompatibilityFixes:
    """Coverage for adapter compatibility fixes used by real integration tests."""

    @pytest.mark.asyncio
    async def test_pywin32_health_check_with_property_revision_number(
        self, monkeypatch
    ):
        """Test pywin32 health check with property revision number."""
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Windows",
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=RuntimeError),
            raising=False,
        )

        adapter = PyWin32Adapter({})
        adapter.swApp = SimpleNamespace(RevisionNumber="33.2.1")
        health = await adapter.health_check()

        assert health.healthy is True
        assert health.metrics["sw_version"] == "33.2.1"

    @pytest.mark.asyncio
    async def test_circuit_breaker_create_part_accepts_optional_args(self):
        """Test circuit breaker create part accepts optional args."""
        base = MockSolidWorksAdapter({})
        await base.connect()
        cb = CircuitBreakerAdapter(base)

        result = await cb.create_part("CompatPart", "mm")

        assert result.is_success
        assert result.data.name == "CompatPart"

    @pytest.mark.asyncio
    async def test_circuit_breaker_create_assembly_name_fallback(self):
        """Test circuit breaker create assembly name fallback."""

        class NoArgAssemblyAdapter(MockSolidWorksAdapter):
            """Test suite for NoArgAssemblyAdapter."""

            async def create_assembly(self):  # type: ignore[override]
                """Test helper for create assembly."""
                return await super().create_assembly()

        base = NoArgAssemblyAdapter({})
        await base.connect()
        cb = CircuitBreakerAdapter(base)

        result = await cb.create_assembly("NamedAssembly")

        assert result.is_success

    @pytest.mark.asyncio
    async def test_circuit_breaker_exposes_save_file_passthrough(self):
        """Test circuit breaker exposes save file passthrough."""
        base = MockSolidWorksAdapter({})
        await base.connect()
        await base.create_part("SaveCompat", "mm")
        cb = CircuitBreakerAdapter(base)

        result = await cb.save_file("C:/tmp/save_compat.sldprt")

        assert result.is_success


class TestAdapterIntegration:
    """Integration tests for adapter components."""

    @pytest.mark.asyncio
    async def test_adapter_with_circuit_breaker(self, mock_config):
        """Test adapter with circuit breaker protection."""
        mock_config.circuit_breaker_enabled = True
        adapter = await create_adapter(mock_config)

        await adapter.connect()

        # Normal operations should work
        result = await adapter.open_model("test.sldprt")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_adapter_with_connection_pooling(self, mock_config):
        """Test adapter with connection pooling."""
        mock_config.connection_pooling = True
        mock_config.max_connections = 3

        adapter = await create_adapter(mock_config)
        await adapter.connect()

        # Test that operations work with pooled connections
        result = await adapter.create_part("TestPart")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_adapter_error_handling(self, mock_adapter):
        """Test comprehensive adapter error handling."""
        await mock_adapter.connect()

        # Test operation error — mock_adapter has no RuntimeError wrapping, so
        # the original exception propagates as-is.
        with patch.object(
            mock_adapter, "open_model", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await mock_adapter.open_model("test.sldprt")

        # Adapter should still be connected after error
        assert mock_adapter.is_connected

    @pytest.mark.asyncio
    async def test_adapter_performance_monitoring(self, mock_adapter, perf_monitor):
        """Test adapter operation performance."""
        await mock_adapter.connect()

        perf_monitor.start()
        result = await mock_adapter.create_part("PerfTestPart")
        perf_monitor.stop()

        assert result.is_success
        # Mock operations should be very fast
        perf_monitor.assert_max_time(0.1)


@pytest.mark.asyncio
async def test_mock_insert_component_records_and_lists() -> None:
    """insert_component records state that list_components reflects back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    first = await adapter.insert_component("C:/parts/a.sldprt")
    assert first.is_success
    assert first.data["component"] == "component-1"
    assert first.data["components_before"] == 0
    assert first.data["components_after"] == 1

    second = await adapter.insert_component("C:/parts/b.sldprt", x=10.0)
    assert second.is_success
    assert second.data["component"] == "component-2"
    assert second.data["components_before"] == 1
    assert second.data["components_after"] == 2

    listed = await adapter.list_components()
    assert listed.is_success
    assert listed.data == ["component-1", "component-2"]


@pytest.mark.asyncio
async def test_mock_add_mate_reports_the_mate() -> None:
    """add_mate on the mock reports the components and mate type back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2", mate_type="concentric")
    assert result.is_success
    assert result.data["components"] == ["part-1", "part-2"]
    assert result.data["mate_type"] == "concentric"


@pytest.mark.asyncio
async def test_mock_does_not_claim_geometry_moved() -> None:
    """The mock must not answer the "did it really work" question with True.

    ``geometry_moved`` is the field that separates a mate which positioned
    a component from one SolidWorks accepted and ignored. The mock has no
    geometry, so the only honest answer is "not determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2")
    assert result.is_success
    assert result.data["geometry_moved"] is None, (
        "the mock reported a geometry check it cannot perform"
    )
    assert result.data["moved_components"] == []


@pytest.mark.asyncio
async def test_mock_add_mate_rejects_unknown_mate_type() -> None:
    """An unknown mate type is a validation error, not a fabricated success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2", mate_type="bogus")
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_delete_removes_the_feature() -> None:
    """delete_feature removes the named feature and reports the change."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    assert created.is_success
    name = created.data.name

    result = await adapter.delete_feature(name)
    assert result.is_success
    assert result.data["features_after"] < result.data["features_before"]

    listed = await adapter.list_features()
    remaining = [
        (f.get("name") if isinstance(f, dict) else getattr(f, "name", None))
        for f in listed.data or []
    ]
    assert name not in remaining


@pytest.mark.asyncio
async def test_mock_delete_of_a_missing_feature_is_an_error() -> None:
    """Deleting something absent must fail, not report a silent success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.delete_feature("NoSuchFeature")
    assert not result.is_success
    assert "NoSuchFeature" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_suppress_round_trips() -> None:
    """suppress then unsuppress reports the state each way."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    name = created.data.name

    on = await adapter.suppress_feature(name, True)
    assert on.is_success
    assert on.data["suppressed"] is True
    assert on.data["was_suppressed"] is False

    off = await adapter.suppress_feature(name, False)
    assert off.is_success
    assert off.data["suppressed"] is False
    assert off.data["was_suppressed"] is True


@pytest.mark.asyncio
async def test_mock_suppress_of_a_missing_feature_is_an_error() -> None:
    """Suppressing something absent must fail."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.suppress_feature("NoSuchFeature", True)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_rename_round_trips() -> None:
    """rename_feature changes the name and the feature resolves under it."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    name = created.data.name

    result = await adapter.rename_feature(name, "RenamedBoss")
    assert result.is_success
    assert result.data["renamed"] is True
    assert result.data["new_name"] == "RenamedBoss"

    listed = await adapter.list_features()
    names = [
        (f.get("name") if isinstance(f, dict) else getattr(f, "name", None))
        for f in listed.data or []
    ]
    assert "RenamedBoss" in names
    assert name not in names


@pytest.mark.asyncio
async def test_mock_rename_of_a_missing_feature_is_an_error() -> None:
    """Renaming something absent must fail."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.rename_feature("NoSuchFeature", "Whatever")
    assert not result.is_success
    assert "NoSuchFeature" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_rename_onto_an_existing_name_is_an_error() -> None:
    """A name collision is silently ignored by SolidWorks, so it must error."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    first = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    await adapter.create_sketch("Top")
    await adapter.add_rectangle(0.0, 0.0, 4.0, 4.0)
    await adapter.exit_sketch()
    second = await adapter.create_extrusion(ExtrusionParameters(depth=2.0))

    result = await adapter.rename_feature(second.data.name, first.data.name)
    assert not result.is_success
    assert "already exists" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_rename_to_same_name_is_a_noop_success() -> None:
    """Renaming a feature to its current name changes nothing but does not fail."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    name = created.data.name

    result = await adapter.rename_feature(name, name)
    assert result.is_success
    assert result.data["renamed"] is False


@pytest.mark.asyncio
async def test_mock_rename_rejects_blank_new_name() -> None:
    """An all-whitespace new_name is rejected before any lookup."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))

    result = await adapter.rename_feature(created.data.name, "   ")
    assert not result.is_success
    assert "new_name must not be empty" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_rename_carries_suppressed_state_to_the_new_name() -> None:
    """Renaming a suppressed feature must keep it tracked as suppressed
    under its new name, not silently un-suppress it."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    created = await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    name = created.data.name
    await adapter.suppress_feature(name, True)
    assert name in adapter._suppressed_features

    result = await adapter.rename_feature(name, "RenamedSuppressed")
    assert result.is_success
    assert "RenamedSuppressed" in adapter._suppressed_features
    assert name not in adapter._suppressed_features


@pytest.mark.asyncio
async def test_mock_undo_with_nothing_to_undo_reports_no_change() -> None:
    """An undo that changed nothing must say so.

    SolidWorks accepts an undo on an empty stack without complaining, so
    ``tree_changed`` is the only way a caller can tell. A mock that always
    reported ``True`` would make that check worthless.
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.undo(1)
    assert result.is_success
    assert result.data["tree_changed"] is False, result.data


@pytest.mark.asyncio
async def test_mock_undo_removes_the_last_feature() -> None:
    """An undo with something to undo reports the change."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await adapter.exit_sketch()
    from solidworks_mcp.adapters.base import ExtrusionParameters

    await adapter.create_extrusion(ExtrusionParameters(depth=5.0))

    result = await adapter.undo(1)
    assert result.is_success
    assert result.data["tree_changed"] is True
    assert result.data["features_after"] < result.data["features_before"]


@pytest.mark.asyncio
async def test_mock_does_not_claim_a_clean_assembly() -> None:
    """The mock must not answer a question it cannot answer.

    ``interference_found: False`` from a mock would read as "checked and
    clean". The mock has no geometry, so the only honest answer is "not
    determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.insert_component("C:/parts/a.sldprt")
    await adapter.insert_component("C:/parts/b.sldprt")

    result = await adapter.check_interference({})
    assert result.is_success
    assert result.data["interference_found"] is None, (
        "the mock reported an interference verdict it never computed"
    )
    assert result.data["interference_count"] is None


@pytest.mark.asyncio
async def test_mock_refuses_with_fewer_than_two_components() -> None:
    """One component cannot interfere with anything."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.insert_component("C:/parts/a.sldprt")

    result = await adapter.check_interference({})
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_mirror_feature_rejects_empty_features() -> None:
    """An empty source list is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.mirror_feature([], "Right Plane")
    assert not result.is_success
    assert "at least one body or feature name" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_mirror_feature_rejects_empty_mirror_plane() -> None:
    """An empty mirror plane name is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.mirror_feature(["Boss-Extrude1"], "")
    assert not result.is_success
    assert "requires a mirror plane name" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_mirror_feature_rejects_unknown_source_name() -> None:
    """A source name that was never created in this session cannot be selected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.mirror_feature(["NoSuchBody"], "Right Plane")
    assert not result.is_success
    assert "NoSuchBody" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_mirror_feature_rejects_unknown_mirror_plane() -> None:
    """A plane name that is neither built-in nor created cannot be selected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success

    result = await adapter.mirror_feature([feature.data.name], "Diagonal Plane")
    assert not result.is_success
    assert "Diagonal Plane" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_mirror_feature_success_volume_ratio() -> None:
    """Success doubles the tracked volume figure, giving a ratio well above 1.5."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success
    source_name = feature.data.name

    result = await adapter.mirror_feature([source_name], "Right Plane")
    assert result.is_success
    assert result.data["mirrored"] == [source_name]
    assert result.data["mirror_plane"] == "Right Plane"
    assert result.data["volume_ratio"] > 1.5
    assert result.data["volume_after"] > result.data["volume_before"]


@pytest.mark.asyncio
async def test_mock_save_body_writes_a_file(tmp_path) -> None:
    """A valid request writes a placeholder file and echoes the body list."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    target = tmp_path / "body.sldprt"

    result = await adapter.save_body_as_part("Boss-Extrude1", str(target))
    assert result.is_success
    assert os.path.exists(target)
    assert result.data["body"] == "Boss-Extrude1"
    assert result.data["solid_bodies"] == ["Boss-Extrude1"]


@pytest.mark.asyncio
async def test_mock_save_body_rejects_missing_parent_dir(tmp_path) -> None:
    """A target under a non-existent directory is refused, as it is live."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.save_body_as_part(
        "B1", str(tmp_path / "no_such_dir" / "b.sldprt")
    )
    assert not result.is_success
    assert "Parent directory does not exist" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_a_part(tmp_path) -> None:
    """Called on a drawing, it refuses before touching anything."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()

    result = await adapter.save_body_as_part("B1", str(tmp_path / "b.sldprt"))
    assert not result.is_success
    assert "requires an active part" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_body_name(tmp_path) -> None:
    """A blank body name is rejected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.save_body_as_part("  ", str(tmp_path / "b.sldprt"))
    assert not result.is_success
    assert "body_name is required" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_an_active_model(tmp_path) -> None:
    """With no document open at all, it refuses before touching anything."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.save_body_as_part("B1", str(tmp_path / "b.sldprt"))
    assert not result.is_success
    assert "No active model" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_file_path(tmp_path) -> None:
    """A blank file_path is rejected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.save_body_as_part("Boss-Extrude1", "   ")
    assert not result.is_success
    assert "file_path is required" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_list_open_documents_reports_active() -> None:
    """The mock marks only the most recently created model active."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    first = await adapter.create_part()
    second = await adapter.create_part()

    listed = await adapter.list_open_documents()
    assert listed.is_success
    by_title = {d["title"]: d for d in listed.data}
    assert by_title[first.data.name]["is_active"] is False
    assert by_title[second.data.name]["is_active"] is True


@pytest.mark.asyncio
async def test_mock_activate_document_switches_active() -> None:
    """activate_document makes the named model active in the mock."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    first = await adapter.create_part()
    await adapter.create_part()  # this one is active now

    result = await adapter.activate_document(first.data.name)
    assert result.is_success
    assert result.data["activated"] == first.data.name

    listed = await adapter.list_open_documents()
    active = [d["title"] for d in listed.data if d["is_active"]]
    assert active == [first.data.name]


@pytest.mark.asyncio
async def test_mock_activate_document_unknown_is_an_error() -> None:
    """Activating a model the mock never created is an error."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.activate_document("no-such-doc.SLDPRT")
    assert not result.is_success
    assert "No open document matches" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_activate_document_blank_is_an_error() -> None:
    """A blank target is rejected before any lookup."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.activate_document("   ")
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_activate_document_requires_connection() -> None:
    """Calling activate_document before connect() is an error, not a crash."""
    adapter = MockSolidWorksAdapter({})

    result = await adapter.activate_document("Part1")
    assert not result.is_success
    assert "Not connected to SolidWorks" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_empty_features() -> None:
    """An empty feature list is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular([], "Axis1", 4)
    assert not result.is_success
    assert "at least one feature name" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_empty_axis() -> None:
    """An empty axis name is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular(["Boss-Extrude1"], "", 4)
    assert not result.is_success
    assert "requires an axis name to rotate about" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_count_below_two() -> None:
    """A count under 2 is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 1)
    assert not result.is_success
    assert "needs a count of at least 2" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_unknown_axis() -> None:
    """An axis name that was never created in this session cannot be selected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success

    result = await adapter.pattern_circular([feature.data.name], "Axis99", 4)
    assert not result.is_success
    assert "Axis99" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_success_volume_ratio() -> None:
    """Success grows the tracked volume figure, giving a ratio well above 1.5.

    Reproduces the live measurement exactly: a hub+blade part at 48431.5
    mm^3, patterned to 4 blades (3 extra instances), gave 75916.4 mm^3 -
    ratio 1.5677.
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success
    source_name = feature.data.name

    axis = await adapter.create_axis("z")
    assert axis.is_success
    axis_name = axis.data["name"]

    result = await adapter.pattern_circular([source_name], axis_name, 4)
    assert result.is_success
    assert result.data["patterned"] == [source_name]
    assert result.data["axis"] == axis_name
    assert result.data["count"] == 4
    assert result.data["volume_ratio"] > 1.5
    assert result.data["volume_after"] > result.data["volume_before"]


@pytest.mark.asyncio
async def test_mock_create_reference_plane_rejects_nonzero_angle() -> None:
    """An angled plane needs a second reference this signature cannot supply."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_reference_plane("Front Plane", offset=10.0, angle=15.0)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_reference_plane_rejects_zero_offset() -> None:
    """A plane coincident with its reference is not a useful result."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_reference_plane("Front Plane", offset=0.0)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_axis_rejects_unknown_reference() -> None:
    """Only x/y/z are valid axis directions."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_axis("diagonal")
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_reference_plane_success_shape() -> None:
    """Success invents a sequential plane name and a features_before/after pair."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    first = await adapter.create_reference_plane("Front Plane", offset=76.2)
    assert first.is_success
    assert first.data["name"] == "Plane1"
    assert first.data["reference"] == "Front Plane"
    assert first.data["offset"] == 76.2
    assert first.data["angle"] is None
    assert first.data["flip"] is False
    assert first.data["features_after"] == first.data["features_before"] + 1

    second = await adapter.create_reference_plane("Top Plane", offset=-10.0, flip=True)
    assert second.is_success
    assert second.data["name"] == "Plane2"
    assert second.data["flip"] is True
    assert second.data["features_after"] == second.data["features_before"] + 1
    # The mock's feature-tree counter accumulates across calls, same as a
    # live SolidWorks model whose feature count only grows.
    assert second.data["features_before"] == first.data["features_after"]


@pytest.mark.asyncio
async def test_mock_create_axis_success_shape() -> None:
    """Success reports the plane pair and a features_before/after pair that differ by 1."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_axis("+X")
    assert result.is_success
    assert result.data["reference"] == "x"
    assert result.data["planes"] == ["Top Plane", "Front Plane"]
    assert result.data["features_after"] == result.data["features_before"] + 1


@pytest.mark.asyncio
async def test_mock_create_reference_point_along_curve_success_shape() -> None:
    """Success invents a sequential point name and bumps the feature tree."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    first = await adapter.create_reference_point("along_curve", 10, 0, 5, percent=50)
    assert first.is_success
    assert first.data["name"] == "Point1"
    assert first.data["mode"] == "along_curve"
    assert first.data["percent"] == 50
    assert first.data["distance_mm"] is None
    assert first.data["features_after"] == first.data["features_before"] + 1

    second = await adapter.create_reference_point(
        "along_curve", 0, 0, 0, distance=3.0
    )
    assert second.is_success
    assert second.data["name"] == "Point2"
    assert second.data["distance_mm"] == 3.0
    assert second.data["features_before"] == first.data["features_after"]


@pytest.mark.asyncio
async def test_mock_create_reference_point_face_center_success_shape() -> None:
    """face_center needs no distance/percent and reports neither."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.create_reference_point("face_center", 1, 2, 3)
    assert result.is_success
    assert result.data["mode"] == "face_center"
    assert result.data["distance_mm"] is None
    assert result.data["percent"] is None
    assert result.data["at_mm"] == [1, 2, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "distance", "percent", "needle"),
    [
        ("spiral", None, None, "Unknown mode"),
        ("along_curve", None, None, "exactly one"),
        ("along_curve", 5.0, 50.0, "exactly one"),
        ("along_curve", -1.0, None, "distance must be positive"),
        ("along_curve", None, 150.0, "between 0 and 100"),
    ],
)
async def test_mock_create_reference_point_refusals(
    mode: str, distance: float | None, percent: float | None, needle: str
) -> None:
    """Bad mode / distance / percent combinations mirror the live refusals."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.create_reference_point(
        mode, 0, 0, 0, distance=distance, percent=percent
    )
    assert not result.is_success
    assert needle in (result.error or "")


@pytest.mark.asyncio
async def test_mock_set_units_records_on_current_model() -> None:
    """The mock stores the normalised token on the current model's properties."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.set_units("inch")
    assert result.is_success
    assert result.data["unit_system"] == "in"

    info = await adapter.get_model_info()
    assert (info.data or {}).get("units") == "in" or adapter._current_model.properties[
        "units"
    ] == "in"


@pytest.mark.asyncio
async def test_mock_set_units_rejects_unknown_token() -> None:
    """An unrecognised token is an error in the mock, as it is live."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.set_units("cubits")
    assert not result.is_success
    assert "Unrecognised" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_set_units_errors_without_active_model() -> None:
    """Calling set_units with no current model is an error."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.set_units("mm")
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_part_applies_and_validates_units() -> None:
    """create_part(units=...) normalises a valid token and rejects a bad one."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    ok = await adapter.create_part(units="Millimeters")
    assert ok.is_success
    assert ok.data.properties["units"] == "mm"

    bad = await adapter.create_part(units="smoots")
    assert not bad.is_success


@pytest.mark.asyncio
async def test_mock_view_placement_accumulates_and_lists() -> None:
    """Placing views records state that list_drawing_views reflects back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    empty = await adapter.list_drawing_views()
    assert empty.is_success
    assert empty.data == []

    first = await adapter.create_drawing_view(
        {"model_path": "C:/parts/a.sldprt", "orientation": "front"}
    )
    assert first.is_success
    assert first.data["views_before"] == 0
    assert first.data["views_after"] == 1

    second = await adapter.add_drawing_view(
        {"model_file": "C:/parts/a.sldprt", "view_type": "top"}
    )
    assert second.is_success
    assert second.data["views_after"] == 2

    listed = await adapter.list_drawing_views()
    assert listed.is_success
    assert len(listed.data) == 2


@pytest.mark.asyncio
async def test_mock_technical_drawing_adds_three_views() -> None:
    """create_technical_drawing lays out front, top and side."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_technical_drawing({"model_file": "C:/parts/a.sldprt"})
    assert result.is_success
    assert len(result.data["views"]) == 3
    assert result.data["projection"] == "third_angle"

    listed = await adapter.list_drawing_views()
    assert len(listed.data) == 3


@pytest.mark.asyncio
async def test_mock_technical_drawing_requires_a_model_path() -> None:
    """No model_path/model_file in the payload is refused, not fabricated."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_technical_drawing({})
    assert not result.is_success
    assert "A model path is required" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_first_angle_projection_is_honoured() -> None:
    """A first-angle request must not silently produce third-angle."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_technical_drawing(
        {"model_file": "C:/parts/a.sldprt", "projection": "first_angle"}
    )
    assert result.is_success
    assert result.data["projection"] == "first_angle"


@pytest.mark.asyncio
async def test_mock_auto_center_marks_adds_once_then_holds() -> None:
    """First run on a view adds marks; a second run on it adds none."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()
    await adapter.create_technical_drawing({"model_file": "C:/parts/a.sldprt"})
    view = (await adapter.list_drawing_views()).data[0]

    first = await adapter.auto_center_marks(view, mark_holes=True, mark_slots=False)
    assert first.is_success
    assert first.data["feature_types"] == ["holes"]
    assert first.data["center_marks_before"] == 0
    assert first.data["center_marks_added"] > 0

    second = await adapter.auto_center_marks(view, mark_holes=True, mark_slots=False)
    assert second.is_success
    assert second.data["center_marks_added"] == 0
    assert second.data["center_marks_before"] == first.data["center_marks_after"]


@pytest.mark.asyncio
async def test_mock_auto_center_marks_mirrors_the_live_refusals() -> None:
    """Not a drawing, no feature type, and an unknown view are all errors."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    await adapter.create_part()
    not_drawing = await adapter.auto_center_marks("Drawing View1")
    assert not not_drawing.is_success
    assert "requires an active drawing" in (not_drawing.error or "")

    await adapter.create_drawing()
    await adapter.create_technical_drawing({"model_file": "C:/parts/a.sldprt"})
    view = (await adapter.list_drawing_views()).data[0]

    none_selected = await adapter.auto_center_marks(
        view, mark_holes=False, mark_fillets=False, mark_slots=False
    )
    assert not none_selected.is_success
    assert "at least one feature type" in (none_selected.error or "")

    unknown = await adapter.auto_center_marks("No Such View")
    assert not unknown.is_success
    assert "No view named" in (unknown.error or "")


@pytest.mark.asyncio
async def test_mock_does_not_claim_the_note_was_positioned() -> None:
    """The mock must not answer a placement check it cannot perform.

    ``positioned`` comes from ``IAnnotation::SetPosition`` on the real
    adapter. The mock has no sheet, so the only honest answer is "not
    determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_note({"text": "MATERIAL: AISI 1018"})
    assert result.is_success
    assert result.data["positioned"] is None, (
        "the mock reported a placement check it cannot perform"
    )


@pytest.mark.asyncio
async def test_mock_rejects_a_note_with_no_text() -> None:
    """An empty note is a validation error, not a fabricated success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_note({"text": ""})
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_rejects_an_unknown_orientation() -> None:
    """An unknown orientation must fail rather than default to front."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_drawing_view(
        {"model_path": "C:/parts/a.sldprt", "orientation": "sideways"}
    )
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_view_placement_requires_a_model_path() -> None:
    """A view of nothing is an error, not an empty success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_drawing_view({})
    assert not result.is_success


def test_mock_orientations_match_the_com_layer() -> None:
    """The mock's accepted orientations must match the COM implementation.

    The two lists are maintained separately, so an orientation added to the
    COM layer alone would be rejected in mock mode and accepted live — and the
    whole test suite runs against the mock.
    """
    from solidworks_mcp.adapters.mock_adapter import _MOCK_NAMED_VIEWS
    from solidworks_mcp.adapters.solidworks.io import _NAMED_VIEWS

    assert set(_NAMED_VIEWS) == set(_MOCK_NAMED_VIEWS), (
        "orientation lists have drifted between io.py and mock_adapter.py"
    )
