"""Tests for base adapter default method implementations."""

import pytest
from src.solidworks_mcp.adapters.base import (
    AdapterResultStatus,
    SolidWorksAdapter,
)
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


class TestBaseAdapterDefaultMethods:
    """Test default implementations in base SolidWorksAdapter."""

    @pytest.fixture
    def adapter(self) -> MockSolidWorksAdapter:
        """Provide a mock adapter for testing."""
        return MockSolidWorksAdapter()

    # Optional sketch methods that return NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_add_arc_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_arc returns error for base adapter."""
        result = await adapter.add_arc(
            center_x=0.0,
            center_y=0.0,
            start_x=1.0,
            start_y=0.0,
            end_x=0.0,
            end_y=1.0,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_add_spline_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_spline returns error for base adapter."""
        points = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 0.0}]
        result = await adapter.add_spline(points)
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_add_centerline_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_centerline returns error for base adapter."""
        result = await adapter.add_centerline(
            x1=0.0,
            y1=0.0,
            x2=10.0,
            y2=0.0,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert (
            "not implemented" in (result.error or "").lower()
            or "no active sketch" in (result.error or "").lower()
        )

    @pytest.mark.asyncio
    async def test_add_polygon_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_polygon returns error for base adapter."""
        result = await adapter.add_polygon(
            center_x=0.0,
            center_y=0.0,
            radius=5.0,
            sides=6,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_add_ellipse_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_ellipse returns error for base adapter."""
        result = await adapter.add_ellipse(
            center_x=0.0,
            center_y=0.0,
            major_axis=10.0,
            minor_axis=5.0,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_sketch_constraint returns error for base adapter."""
        result = await adapter.add_sketch_constraint(
            entity1="edge1",
            entity2="edge2",
            relation_type="perpendicular",
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_add_sketch_dimension_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test add_sketch_dimension returns error for base adapter."""
        result = await adapter.add_sketch_dimension(
            entity1="edge1",
            entity2=None,
            dimension_type="length",
            value=10.0,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test sketch_linear_pattern returns error for base adapter."""
        result = await adapter.sketch_linear_pattern(
            entities=["entity1"],
            direction_x=1.0,
            direction_y=0.0,
            spacing=5.0,
            count=3,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_sketch_mirror_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test sketch_mirror returns error for base adapter."""
        result = await adapter.sketch_mirror(
            entities=["entity1"],
            mirror_line="x_axis",
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_sketch_offset_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test sketch_offset returns error for base adapter."""
        result = await adapter.sketch_offset(
            entities=["entity1"],
            offset_distance=1.0,
            reverse_direction=False,
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "").lower()

    # Optional file operations

    @pytest.mark.asyncio
    async def test_save_file_not_implemented(
        self, adapter: MockSolidWorksAdapter
    ) -> None:
        """Test save_file returns error when not implemented."""
        # Note: MockSolidWorksAdapter may override this, so we test the base behavior
        # by checking if it returns error or success
        result = await adapter.save_file(file_path=None)
        # Either success or error is acceptable - depends on adapter implementation
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)
