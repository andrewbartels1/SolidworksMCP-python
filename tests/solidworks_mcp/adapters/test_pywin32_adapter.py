"""Tests for solidworks_mcp.adapters.pywin32_adapter module-level behaviour."""

from __future__ import annotations


def test_pywin32_adapter_imports_without_pywin32(import_without) -> None:
    """Non-Windows CI: the module imports and reports pywin32 as unavailable."""
    attrs = import_without(
        "solidworks_mcp.adapters.pywin32_adapter",
        [
            "pythoncom",
            "pywintypes",
            "win32com",
            "win32com.client",
            "win32com.client.dynamic",
        ],
        ["PYWIN32_AVAILABLE", "pywintypes"],
    )

    assert attrs["PYWIN32_AVAILABLE"] is False
    assert "com_error" in attrs["pywintypes"]


# ---- _SketchGeometryService edge cases --------------------------------------

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


@pytest.fixture
def geometry(monkeypatch):
    """The sketch-geometry service of an adapter that believes it is on Windows."""
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system", lambda: "Windows"
    )
    return PyWin32Adapter({})._sketch_geometry


def _line(start: tuple, end: tuple) -> SimpleNamespace:
    return SimpleNamespace(GetStartPoint=start, GetEndPoint=end)


def _point(xyz: tuple | None) -> SimpleNamespace:
    if xyz is None:
        return SimpleNamespace(GetCoords=lambda: [])  # unreadable point
    return SimpleNamespace(X=xyz[0], Y=xyz[1], Z=xyz[2])


def test_set_display_dimension_value_falls_back_to_legacy_objects(geometry) -> None:
    legacy = SimpleNamespace(SetSystemValue3=lambda *_a: True)
    via_get_dimension = SimpleNamespace(
        GetDimension2=lambda _i: None, GetDimension=lambda: legacy
    )
    calls: list[float] = []
    bare = SimpleNamespace(
        GetDimension2=lambda _i: None,
        GetDimension=lambda: None,
        SetSystemValue3=lambda value, *_a: calls.append(value) or True,
    )

    geometry.set_display_dimension_value(via_get_dimension, 5.0)
    geometry.set_display_dimension_value(bare, 7.0)

    assert calls == [pytest.approx(0.007)]


def test_point_helpers_tolerate_missing_points(geometry) -> None:
    assert geometry.set_point_xyz(None, 0.0, 0.0, 0.0) is False
    assert geometry.read_segment_endpoints(SimpleNamespace()) is None


def test_shared_segment_vertex_skips_unreadable_and_reports_no_match(
    geometry,
) -> None:
    corner = (0.01, 0.0, 0.0)
    shared = SimpleNamespace(GetStartPoint2=_point(None), GetEndPoint2=_point(corner))
    other = SimpleNamespace(GetStartPoint2=_point(None), GetEndPoint2=_point(corner))
    apart = SimpleNamespace(
        GetStartPoint2=_point((1.0, 1.0, 0.0)),
        GetEndPoint2=_point((2.0, 1.0, 0.0)),
    )

    found = geometry.shared_segment_vertex(shared, other)

    assert found is not None
    assert geometry.shared_segment_vertex(shared, apart) is None


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (SimpleNamespace(), _line((0, 0, 0), (0.01, 0, 0))),  # unreadable first
        (_line((0, 0, 0), (0, 0, 0)), _line((0, 0, 0), (0.01, 0, 0))),  # zero length
    ],
)
def test_angular_placement_rejects_unusable_geometry(geometry, first, second) -> None:
    assert geometry.angular_dimension_placement(first, second) is None


def test_angular_placement_for_opposite_rays_uses_a_perpendicular(geometry) -> None:
    """Collinear, opposite legs: the bisector vanishes, so place off the line."""
    left = _line((0.0, 0.0, 0.0), (-0.02, 0.0, 0.0))
    right = _line((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))

    text_x, text_y, _z, _direction = geometry.angular_dimension_placement(left, right)

    assert abs(text_x) < 1e-9
    assert abs(text_y) > 0.0  # pushed perpendicular to the straight line


def test_single_line_placement_needs_endpoints(geometry) -> None:
    assert geometry.single_line_dimension_placement(SimpleNamespace()) is None


# ---- _DocumentRoutingService / assembly / screenshot edge cases --------------


@pytest.fixture
def adapter(monkeypatch, geometry):
    """The PyWin32Adapter behind the geometry fixture (same Windows patches)."""
    return geometry._adapter


def test_document_identity_of_none(adapter) -> None:
    assert adapter._document_routing.document_identity(None) == (None, None)


def test_export_target_falls_back_to_whichever_document_exists(adapter) -> None:
    active, current = object(), object()
    adapter.swApp = SimpleNamespace(ActiveDoc=active)
    adapter.currentModel = None
    assert adapter._document_routing.resolve_export_target_doc() is active

    adapter.swApp = SimpleNamespace(ActiveDoc=None)
    adapter.currentModel = current
    assert adapter._document_routing.resolve_export_target_doc() is current


def test_assembly_without_components_lists_nothing(adapter) -> None:
    assembly = SimpleNamespace(GetComponents=lambda _top_level: None)

    assert (
        adapter._feature_selector._list_assembly_component_features(
            assembly, False, 1, None
        )
        == []
    )


@pytest.mark.asyncio
async def test_screenshot_replaces_an_existing_file_without_prompting(
    adapter, tmp_path, monkeypatch
) -> None:
    """SolidWorks would show a 'replace?' dialog; the old file is deleted first."""
    target = tmp_path / "shot.png"
    target.write_bytes(b"stale")
    seen_before_save: list[bool] = []

    def _save(_doc, path, _w, _h):
        seen_before_save.append(target.exists())
        target.write_bytes(b"fresh")
        return True

    adapter.swApp = SimpleNamespace(ActiveDoc=None)
    adapter.currentModel = SimpleNamespace()
    monkeypatch.setattr(adapter, "_resolve_export_target_doc", lambda: object())
    monkeypatch.setattr(adapter, "_document_identity", lambda _doc: (None, None))
    monkeypatch.setattr(adapter, "_zoom_to_fit", lambda _doc: None)
    monkeypatch.setattr(adapter, "_save_screenshot_with_modelview", _save)

    result = await adapter.export_image({"file_path": str(target)})

    assert result.is_success, result.error
    assert seen_before_save == [False]
    assert target.read_bytes() == b"fresh"
