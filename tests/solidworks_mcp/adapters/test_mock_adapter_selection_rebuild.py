"""Mock-adapter parity for the #106 selection / rebuild operations."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    """A connected mock with one sketch + extrusion on the active part."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0, 0, 40, 25)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=10))
    return adapter


# ---- select_feature -------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_select_known_feature_replaces_selection(part) -> None:
    """A created feature selects; without append it replaces the selection."""
    name = next(iter(part._features.values())).name
    assert (await part.select_feature("Sketch1")).is_success
    result = await part.select_feature(name)
    assert result.is_success
    assert result.data["selected_name"] == name
    assert result.data["selection_count"] == 1


@pytest.mark.asyncio
async def test_mock_select_append_counts(part) -> None:
    """append=True accumulates the selection."""
    await part.select_feature("Sketch1")
    result = await part.select_feature("Front Plane@Part1", append=True)
    assert result.is_success
    assert result.data["selected_name"] == "Front Plane"
    assert result.data["selection_count"] == 2


@pytest.mark.asyncio
async def test_mock_select_unknown_name_is_error(part) -> None:
    """An untracked name errors and names the feature."""
    result = await part.select_feature("NoSuchFeature")
    assert result.is_error
    assert "NoSuchFeature" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_select_without_model_is_error() -> None:
    """No active model -> ERROR."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    result = await adapter.select_feature("Front Plane")
    assert result.is_error
    assert result.error == "No active model"


# ---- select_face_edges ----------------------------------------------------


@pytest.mark.asyncio
async def test_mock_face_edges_by_side_all(part) -> None:
    """A side selects the face's four straight edges."""
    result = await part.select_face_edges(side="top")
    assert result.is_success
    assert result.data["face"]["normal"] == [0.0, 1.0, 0.0]
    assert result.data["selected_edges"] == 4
    assert result.data["selection_count"] == 4


@pytest.mark.asyncio
async def test_mock_face_edges_circular_needs_a_hole(part) -> None:
    """circular on +Z errors on a plain block, succeeds once a circle exists."""
    plain = await part.select_face_edges(side="+Z", edge_type="circular")
    assert plain.is_error and "no circular edges" in (plain.error or "")

    await part.create_sketch("Front")
    await part.add_circle(5, 5, 2)
    await part.exit_sketch()
    holed = await part.select_face_edges(side="+Z", edge_type="circular")
    assert holed.is_success
    assert [e["radius_mm"] for e in holed.data["edges"]] == [2.0]


@pytest.mark.asyncio
async def test_mock_face_edges_point_plane_and_append(part) -> None:
    """Point and Front Plane modes resolve; append accumulates the count."""
    by_point = await part.select_face_edges(point=[5, 5, 10])
    assert by_point.is_success and by_point.data["face"]["normal"] == [0.0, 0.0, 1.0]
    by_plane = await part.select_face_edges(plane="Front Plane", append=True)
    assert by_plane.is_success
    assert by_plane.data["face"]["normal"] == [0.0, 0.0, -1.0]
    assert by_plane.data["selection_count"] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"point": [50, 50, 50]}, "No face found"),
        ({"point": [5, 5, 5]}, "No face found"),
        ({"plane": "Top Plane"}, "No body face lies on"),
        ({"side": "top", "plane": "Front Plane"}, "exactly one"),
        ({"side": "diagonal"}, "Unknown side"),
    ],
)
async def test_mock_face_edges_errors(part, kwargs: dict, fragment: str) -> None:
    """Mock failure cases match the real adapter's messages."""
    result = await part.select_face_edges(**kwargs)
    assert result.is_error
    assert fragment in (result.error or "")


@pytest.mark.asyncio
async def test_mock_face_edges_requires_part() -> None:
    """No model, or a non-part, is refused."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    assert (await adapter.select_face_edges(side="top")).error == "No active model"
    await adapter.create_assembly()
    result = await adapter.select_face_edges(side="top")
    assert result.is_error and "part document" in (result.error or "")


# ---- rebuild_model --------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_rebuild_clean(part) -> None:
    """Default mock rebuild is clean."""
    result = await part.rebuild_model()
    assert result.is_success
    assert result.data["errors"] == [] and result.data["error_count"] == 0


@pytest.mark.asyncio
async def test_mock_rebuild_injected_error_and_warning(part) -> None:
    """Injected issues follow the real status rules and carry hints."""
    from solidworks_mcp.adapters.solidworks.rebuild_diagnostics import RawRebuildIssue

    part.injected_rebuild_issues = [RawRebuildIssue("Fillet1", "Fillet", 18, True)]
    warned = await part.rebuild_model()
    assert warned.is_success and warned.data["warning_count"] == 1

    part.injected_rebuild_issues.append(
        RawRebuildIssue("Cut-Extrude1", "Cut", 71, False)
    )
    failed = await part.rebuild_model(top_level_only=True)
    assert failed.is_error
    assert "Cut-Extrude1" in (failed.error or "")
    assert failed.data["top_level_only"] is True
    cut = failed.data["errors"][1]
    assert cut["code_name"] == "swFeatureErrorCutNotIntersectModel"
    assert "intersect" in cut["description"]


@pytest.mark.asyncio
async def test_mock_rebuild_without_model() -> None:
    """No model -> ERROR."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    result = await adapter.rebuild_model()
    assert result.is_error and result.error == "No active model"


# ---- add_fillet / add_chamfer use the live selection ---------------------


@pytest.mark.asyncio
async def test_mock_chamfer_on_live_selection_then_clears_it(part) -> None:
    """Empty edge_names consumes the selection made by select_face_edges."""
    await part.select_face_edges(side="top")
    result = await part.add_chamfer(0.5, [])
    assert result.is_success
    assert result.data.name == "Chamfer1"
    assert len(result.data.parameters["edges"]) == 4
    nothing = await part.add_fillet(1.0, [])
    assert nothing.is_error and "nothing is selected" in (nothing.error or "")


@pytest.mark.asyncio
async def test_mock_fillet_named_edges_and_bad_size(part) -> None:
    """Named edges work; non-positive sizes are refused."""
    assert (await part.add_fillet(1.0, ["Edge<1>"])).data.name == "Fillet1"
    bad = await part.add_chamfer(0, ["Edge<1>"])
    assert bad.is_error and "positive" in (bad.error or "")


@pytest.mark.asyncio
async def test_mock_selection_does_not_leak_across_documents(part) -> None:
    """A selection made on one part must not feed a fillet on the next (review #9)."""
    await part.select_face_edges(side="top")
    await part.create_part()
    result = await part.add_fillet(1.0, [])
    assert result.is_error and "nothing is selected" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_edge_features_without_model_are_errors() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    for result in (
        await adapter.add_fillet(1.0, ["Edge<1>"]),
        await adapter.add_chamfer(1.0, []),
    ):
        assert result.is_error
        assert result.error == "No active model"
