"""Tests for the verify_model analysis tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    MassProperties,
)
from solidworks_mcp.tools.analysis import (
    _count_modelling_features,
    _verdict,
    register_analysis_tools,
)


def _ok(data: Any) -> AdapterResult[Any]:
    return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


def _err(message: str) -> AdapterResult[Any]:
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _part_summary(**overrides: Any) -> dict[str, Any]:
    summary = {
        "document_type": "part",
        "volume_mm3": 50000.0,
        "bounding_box_mm": {
            "min": [0.0, 0.0, 0.0],
            "max": [100.0, 50.0, 10.0],
            "size": [100.0, 50.0, 10.0],
        },
        "bounding_box_method": "extreme_points",
        "solid_body_count": 1,
    }
    summary.update(overrides)
    return summary


def _assembly_summary(**overrides: Any) -> dict[str, Any]:
    summary = {
        "document_type": "assembly",
        "volume_mm3": 80000.0,
        "bounding_box_mm": None,
        "bounding_box_method": None,
        "solid_body_count": None,
        "component_count": 3,
        "mate_count": 2,
    }
    summary.update(overrides)
    return summary


def _feature(name: str, kind: str, component: str | None = None) -> dict[str, Any]:
    return {"name": name, "type": kind, "component": component}


#: A realistic part tree: furniture, default planes, two sketches, three features.
_PART_TREE = [
    _feature("Comments", "CommentsFolder"),
    _feature("Sensors", "SensorFolder"),
    _feature("Annotations", "DetailCabinet"),
    _feature("Material <not specified>", "MaterialFolder"),
    _feature("Front Plane", "RefPlane"),
    _feature("Top Plane", "RefPlane"),
    _feature("Right Plane", "RefPlane"),
    _feature("Origin", "OriginProfileFeature"),
    _feature("Sketch1", "ProfileFeature"),
    _feature("Boss-Extrude1", "Extrusion"),
    _feature("Sketch2", "ProfileFeature"),
    _feature("Boss-Extrude2", "Extrusion"),
    _feature("Fillet1", "Fillet"),
]


async def _verify(mcp_server, adapter, **expectations: Any) -> dict[str, Any]:
    await register_analysis_tools(mcp_server, adapter, {})
    tool = next(t for t in await mcp_server.list_tools() if t.name == "verify_model")
    return await tool.fn(input_data=expectations or None)


@pytest.fixture
def part_adapter(mock_adapter):
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_ok(_part_summary())
    )
    mock_adapter.list_features = AsyncMock(return_value=_ok(_PART_TREE))
    return mock_adapter


@pytest.mark.asyncio
async def test_part_matching_every_expectation_passes(mcp_server, part_adapter):
    result = await _verify(
        mcp_server,
        part_adapter,
        volume_mm3=50200,
        bounding_box_mm=[100, 50, 10.05],
        feature_count=3,
        solid_body_count=1,
    )

    assert result["status"] == "success"
    assert result["verdict"] == "pass"
    assert [c["name"] for c in result["checks"]] == [
        "volume_mm3",
        "bounding_box_mm",
        "feature_count",
        "solid_body_count",
    ]
    assert all(c["passed"] is True for c in result["checks"])
    assert result["message"] == "Verification passed: 4 of 4 checks passed"
    assert result["measured"]["features"] == [
        "Boss-Extrude1",
        "Boss-Extrude2",
        "Fillet1",
    ]


@pytest.mark.asyncio
async def test_volume_out_of_tolerance_fails_but_status_is_success(
    mcp_server, part_adapter
):
    result = await _verify(mcp_server, part_adapter, volume_mm3=40000)

    assert result["status"] == "success"
    assert result["verdict"] == "fail"
    check = result["checks"][0]
    assert check == {
        "name": "volume_mm3",
        "expected": 40000,
        "actual": 50000.0,
        "tolerance": 0.01,
        "unit": "mm³",
        "passed": False,
    }
    assert "failed: volume_mm3" in result["message"]


@pytest.mark.asyncio
async def test_no_expectations_reports_only(mcp_server, part_adapter):
    result = await _verify(mcp_server, part_adapter)

    assert result["verdict"] == "report_only"
    assert result["checks"] == []
    assert result["measured"]["volume_mm3"] == 50000.0
    assert result["message"] == "Measured the active part; no expectations were given"
    part_adapter.list_features.assert_not_awaited()


@pytest.mark.asyncio
async def test_bounding_box_fails_on_one_axis(mcp_server, part_adapter):
    result = await _verify(mcp_server, part_adapter, bounding_box_mm=[100, 50, 12])

    check = result["checks"][0]
    assert check["passed"] is False
    assert check["expected"] == [100, 50, 12]
    assert check["actual"] == [100.0, 50.0, 10.0]
    assert "note" not in check


@pytest.mark.asyncio
async def test_bounding_box_in_other_orientation_explains_why(mcp_server, part_adapter):
    result = await _verify(mcp_server, part_adapter, bounding_box_mm=[10, 100, 50])

    check = result["checks"][0]
    assert check["passed"] is False
    assert "oriented differently" in check["note"]


@pytest.mark.asyncio
async def test_unmeasured_values_are_inconclusive_never_pass(mcp_server, mock_adapter):
    # The mock adapter's own summary: no geometry, so nothing is measurable.
    await mock_adapter.open_model("C:\\mock\\Bracket.sldprt")

    result = await _verify(
        mcp_server, mock_adapter, volume_mm3=1000, bounding_box_mm=[1, 2, 3]
    )

    assert result["verdict"] == "inconclusive"
    assert [c["passed"] for c in result["checks"]] == [None, None]
    assert all(c["note"] == "Could not be measured" for c in result["checks"])
    assert "could not measure: volume_mm3, bounding_box_mm" in result["message"]


@pytest.mark.asyncio
async def test_failure_beats_inconclusive(mcp_server, part_adapter):
    part_adapter.get_model_geometry_summary.return_value = _ok(
        _part_summary(bounding_box_mm=None)
    )

    result = await _verify(
        mcp_server, part_adapter, volume_mm3=1, bounding_box_mm=[1, 1, 1]
    )

    assert result["verdict"] == "fail"


@pytest.mark.asyncio
async def test_feature_list_failure_is_unmeasured(mcp_server, part_adapter):
    part_adapter.list_features.return_value = _err("tree walk failed")

    result = await _verify(mcp_server, part_adapter, feature_count=3)

    assert result["checks"][0]["passed"] is None
    assert result["measured"]["features"] is None


@pytest.mark.asyncio
async def test_mass_check_names_the_material_when_it_fails(mcp_server, part_adapter):
    part_adapter.get_mass_properties = AsyncMock(
        return_value=_ok(
            MassProperties(
                volume=50000,
                surface_area=1,
                mass=0.39,
                center_of_mass=[0, 0, 0],
                moments_of_inertia={},
            )
        )
    )
    part_adapter.get_material = AsyncMock(return_value=_ok({"material": "AISI 1020"}))

    passing = await _verify(mcp_server, part_adapter, mass_kg=0.39)
    failing = await _verify(mcp_server, part_adapter, mass_kg=0.135)

    assert passing["checks"][0]["passed"] is True
    assert passing["measured"]["material"] == "AISI 1020"
    assert failing["checks"][0]["passed"] is False
    assert failing["checks"][0]["note"] == "Material: AISI 1020"


@pytest.mark.asyncio
async def test_mass_without_material_says_default_density(mcp_server, part_adapter):
    part_adapter.get_mass_properties = AsyncMock(return_value=_err("no model"))
    part_adapter.get_material = AsyncMock(return_value=_err("no material"))

    unmeasured = await _verify(mcp_server, part_adapter, mass_kg=1.0)
    assert unmeasured["checks"][0]["passed"] is None

    part_adapter.get_mass_properties = AsyncMock(
        return_value=_ok(
            MassProperties(
                volume=1,
                surface_area=1,
                mass=0.05,
                center_of_mass=[0, 0, 0],
                moments_of_inertia={},
            )
        )
    )
    failing = await _verify(mcp_server, part_adapter, mass_kg=1.0)
    assert "default density" in failing["checks"][0]["note"]


@pytest.mark.asyncio
async def test_assembly_counts_and_interference(mcp_server, mock_adapter):
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_ok(_assembly_summary())
    )
    mock_adapter.check_interference = AsyncMock(
        return_value=_ok({"interference_found": False, "interference_count": 0})
    )

    result = await _verify(
        mcp_server,
        mock_adapter,
        component_count=3,
        mate_count=2,
        no_interference=True,
    )

    assert result["verdict"] == "pass"
    assert result["measured"]["interference"]["interference_count"] == 0


@pytest.mark.asyncio
async def test_interference_found_fails(mcp_server, mock_adapter):
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_ok(_assembly_summary())
    )
    mock_adapter.check_interference = AsyncMock(
        return_value=_ok({"interference_found": True, "interference_count": 1})
    )

    result = await _verify(mcp_server, mock_adapter, no_interference=True)

    assert result["checks"][0]["actual"] is False
    assert result["verdict"] == "fail"


@pytest.mark.asyncio
async def test_interference_not_determinable_is_inconclusive(mcp_server, mock_adapter):
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_ok(_assembly_summary())
    )
    mock_adapter.check_interference = AsyncMock(
        return_value=_ok({"interference_found": None})
    )

    result = await _verify(mcp_server, mock_adapter, no_interference=True)

    assert result["checks"][0]["passed"] is None
    assert result["verdict"] == "inconclusive"


@pytest.mark.asyncio
async def test_interference_error_is_unmeasured_with_reason(mcp_server, mock_adapter):
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_ok(_assembly_summary(component_count=1))
    )
    mock_adapter.check_interference = AsyncMock(
        return_value=_err("Interference detection needs at least two components")
    )

    result = await _verify(mcp_server, mock_adapter, no_interference=True)

    check = result["checks"][0]
    assert check["passed"] is None
    assert "at least two components" in check["note"]
    assert result["measured"]["interference"] is None


@pytest.mark.asyncio
async def test_assembly_only_expectation_on_a_part_is_an_error(
    mcp_server, part_adapter
):
    result = await _verify(mcp_server, part_adapter, mate_count=2, component_count=1)

    assert result["status"] == "error"
    assert "component_count, mate_count only apply to assemblies" in result["message"]


@pytest.mark.asyncio
async def test_negative_tolerance_is_an_error(mcp_server, part_adapter):
    result = await _verify(mcp_server, part_adapter, relative_tolerance=-0.1)

    assert result["status"] == "error"
    assert "relative_tolerance" in result["message"]


@pytest.mark.asyncio
async def test_misspelt_expectation_is_an_error(mcp_server, part_adapter):
    result = await _verify(mcp_server, part_adapter, volume=50000)

    assert result["status"] == "error"
    assert "volume" in result["message"]


@pytest.mark.asyncio
async def test_drawing_is_an_error(mcp_server, mock_adapter):
    await mock_adapter.open_model("C:\\mock\\Sheet.slddrw")

    result = await _verify(mcp_server, mock_adapter, volume_mm3=1)

    assert result["status"] == "error"
    assert "Failed to read the model back" in result["message"]


@pytest.mark.asyncio
async def test_adapter_without_the_read_is_an_error(mcp_server, mock_adapter):
    class _NoSummary:
        pass

    result = await _verify(mcp_server, _NoSummary(), volume_mm3=1)

    assert result["status"] == "error"
    assert "cannot read the model back" in result["message"]


@pytest.mark.asyncio
async def test_zero_expected_volume_needs_zero(mcp_server, part_adapter):
    part_adapter.get_model_geometry_summary.return_value = _ok(
        _part_summary(volume_mm3=0.0)
    )
    zero = await _verify(mcp_server, part_adapter, volume_mm3=0)

    part_adapter.get_model_geometry_summary.return_value = _ok(
        _part_summary(volume_mm3=0.5)
    )
    nonzero = await _verify(mcp_server, part_adapter, volume_mm3=0)

    assert zero["checks"][0]["passed"] is True
    assert nonzero["checks"][0]["passed"] is False


def test_feature_filter_skips_furniture_and_default_planes() -> None:
    tree = [
        *_PART_TREE,
        _feature("Plane1", "RefPlane"),
        _feature("Boss-Extrude1", "Extrusion", component="Pin-1"),
        _feature("3DSketch1", "3DProfileFeature"),
    ]

    assert _count_modelling_features(tree) == [
        "Boss-Extrude1",
        "Boss-Extrude2",
        "Fillet1",
        "Plane1",
    ]


def test_verdict_order() -> None:
    assert _verdict([]) == "report_only"
    assert _verdict([{"passed": True}, {"passed": None}]) == "inconclusive"
    assert _verdict([{"passed": None}, {"passed": False}]) == "fail"
    assert _verdict([{"passed": True}]) == "pass"
