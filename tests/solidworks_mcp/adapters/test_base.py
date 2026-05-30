"""Tests for base adapter defaults."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResultStatus, SolidWorksAdapter


class _Adapter(SolidWorksAdapter):
    """Minimal concrete adapter for testing defaults."""

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return False

    async def health_check(self):
        return None

    async def open_model(self, file_path):
        return None

    async def close_model(self, save=False):
        return None

    async def get_model_info(self):
        return None

    async def list_features(self, include_suppressed=True):
        return None

    async def list_configurations(self):
        return None

    async def create_part(self, part_name, template=None, units=None, material=None):
        return None

    async def create_assembly(self, assembly_name, template=None):
        return None

    async def create_drawing(self, drawing_name, template=None, sheet_size=None):
        return None

    async def create_extrusion(self, depth, direction=None, reverse=False, thin_feature=False, thin_thickness=0.0, both_directions=False, auto_fillet_corners=False, fillet_corners_radius=0.0):
        return None

    async def create_revolve(self, angle, direction=None):
        return None

    async def create_sweep(self, path_sketch, profile_sketch):
        return None

    async def create_loft(self, profile_sketches, guide_curves=None):
        return None

    async def create_sketch(self, plane):
        return None

    async def add_line(self, x1, y1, x2, y2):
        return None

    async def add_circle(self, cx, cy, radius):
        return None

    async def add_rectangle(self, x1, y1, x2, y2):
        return None

    async def exit_sketch(self):
        return None

    async def get_mass_properties(self):
        return None

    async def export_image(self, payload):
        return None

    async def export_file(self, file_path, file_format):
        return None

    async def get_dimension(self, name):
        return None

    async def set_dimension(self, name, value):
        return None


def test_base_config_normalizes_unknown_object() -> None:
    """Non-mapping config objects should normalize to empty dict."""
    # Pass a plain object without model_dump to hit the fallback branch.
    adapter = _Adapter(object())
    assert adapter.config_dict == {}


@pytest.mark.asyncio
async def test_base_default_sketch_helpers_return_error() -> None:
    """Default sketch helper methods should return not-implemented errors."""
    # Exercise default error responses for unimplemented sketch helpers.
    adapter = _Adapter({})

    result = await adapter.add_polygon(0.0, 0.0, 1.0, 5)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_ellipse(0.0, 0.0, 2.0, 1.0)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_sketch_constraint("e1", None, "coincident")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_linear_pattern(["e1"], 1.0, 0.0, 5.0, 2)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_circular_pattern(["e1"], 90.0, 4)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_mirror(["e1"], "line1")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_offset(["e1"], 1.0, False)
    assert result.status == AdapterResultStatus.ERROR
