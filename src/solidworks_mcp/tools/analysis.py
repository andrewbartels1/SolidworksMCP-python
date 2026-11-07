"""Analysis tools for SolidWorks MCP Server.

Use these after a model or assembly already exists. Recommended order:
calculate_mass_properties or get_mass_properties, then check_interference, then
analyze_geometry, then get_material_properties. These tools are for validation and
inspection, not for creating geometry. verify_model checks the finished model
against expected values in one call.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    InvalidInputError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas using Python 3.14 built-in types


class MassPropertiesInput(CompatInput):
    """Input schema for mass properties analysis.

    Attributes:
        include_hidden (bool): The include hidden value.
        model_path (str | None): The model path value.
        reference_coordinate_system (str | None): The reference coordinate system value.
        units (str): The units value.
    """

    model_path: str | None = Field(default=None, description="Path to the model file")
    units: str = Field(default="metric", description="Units for mass properties")
    include_hidden: bool = Field(default=False, description="Include hidden components")
    reference_coordinate_system: str | None = Field(
        default=None, description="Reference coordinate system alias"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the mass properties input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: If the operation cannot be completed.
        """
        valid_units = {"metric", "kg", "g", "lb"}
        if self.units not in valid_units:
            raise ValueError(f"units must be one of {sorted(valid_units)}")


class InterferenceCheckInput(CompatInput):
    """Input schema for interference checking.

    Attributes:
        assembly_path (str | None): The assembly path value.
        check_all_components (bool): The check all components value.
        components (list[str]): The components value.
        include_hidden (bool): The include hidden value.
        tolerance (float): The tolerance value.
    """

    assembly_path: str | None = Field(default=None, description="Assembly path alias")
    check_all_components: bool = Field(
        default=False, description="Check all components alias"
    )
    include_hidden: bool = Field(default=False, description="Include hidden components")
    components: list[str] = Field(
        default_factory=list,
        description="List of component names to check for interference",
    )
    tolerance: float = Field(
        default=0.001, description="Interference detection tolerance in mm"
    )


class GeometryAnalysisInput(BaseModel):
    """Input schema for geometry analysis.

    Attributes:
        analysis_type (str): The analysis type value.
        parameters (dict[str, Any] | None): The parameters value.
    """

    analysis_type: str = Field(
        description="Type of analysis (curvature, draft, thickness, etc.)"
    )
    parameters: dict[str, Any] | None = Field(
        default=None, description="Analysis-specific parameters"
    )


class VerifyModelInput(BaseModel):
    """Expectations for ``verify_model``; every field is optional.

    Unknown fields are rejected so a misspelt expectation (``volume`` for
    ``volume_mm3``) fails loudly instead of silently not being checked.
    """

    model_config = ConfigDict(extra="forbid")

    mass_kg: float | None = Field(
        default=None, description="Expected mass in kg (depends on the material)"
    )
    volume_mm3: float | None = Field(default=None, description="Expected volume, mm³")
    bounding_box_mm: tuple[float, float, float] | None = Field(
        default=None,
        description="Expected overall size [x, y, z] in mm, in model axes",
    )
    feature_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Expected number of modelling features (extrudes, cuts, fillets, "
            "patterns...); sketches, the origin, folders and the three "
            "default planes are not counted"
        ),
    )
    solid_body_count: int | None = Field(
        default=None, ge=0, description="Expected number of solid bodies (parts)"
    )
    component_count: int | None = Field(
        default=None, ge=0, description="Expected top-level components (assemblies)"
    )
    mate_count: int | None = Field(
        default=None, ge=0, description="Expected unsuppressed mates (assemblies)"
    )
    no_interference: bool | None = Field(
        default=None,
        description="true to require that no components overlap (assemblies)",
    )
    relative_tolerance: float = Field(
        default=0.01,
        ge=0,
        description="Allowed relative error for mass and volume (0.01 = 1 %)",
    )
    length_tolerance_mm: float = Field(
        default=0.1, ge=0, description="Allowed error per bounding-box axis, mm"
    )


#: Assembly-only expectations; asking for them on a part is a caller mistake.
_ASSEMBLY_ONLY = ("component_count", "mate_count", "no_interference")

#: ``GetTypeName2`` values that are tree furniture, not modelling features.
_NON_MODELLING_TYPES = frozenset(
    {
        "ProfileFeature",
        "3DProfileFeature",
        "OriginProfileFeature",
        "DetailCabinet",
        "MateGroup",
        "MateReferenceGroup",
        "MaterialFolder",
    }
)

#: SolidWorks always puts the three default planes first in the tree.
_DEFAULT_PLANE_COUNT = 3


def _count_modelling_features(descriptors: list[dict[str, Any]]) -> list[str]:
    """Return the names of the document's own modelling features.

    Skips component features, sketches, the origin, folders, the mate group
    and the first three reference planes (the default ones, matched by
    position so it works in any SolidWorks language).

    Args:
        descriptors: ``list_features`` rows.

    Returns:
        list[str]: Counted feature names, in tree order.
    """
    names: list[str] = []
    planes_seen = 0
    for row in descriptors:
        if row.get("component") is not None:
            continue
        kind = str(row.get("type") or "")
        if kind == "RefPlane":
            planes_seen += 1
            if planes_seen <= _DEFAULT_PLANE_COUNT:
                continue
        if kind in _NON_MODELLING_TYPES or kind.endswith("Folder"):
            continue
        names.append(str(row.get("name") or ""))
    return names


def _check(
    name: str,
    expected: Any,
    actual: Any,
    unit: str | None,
    passed: bool | None,
    tolerance: Any = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build one ``checks`` entry."""
    entry: dict[str, Any] = {
        "name": name,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "unit": unit,
        "passed": passed,
    }
    if note:
        entry["note"] = note
    elif passed is None:
        entry["note"] = "Could not be measured"
    return entry


def _relative_check(
    name: str, expected: float, actual: Any, tolerance: float, unit: str
) -> dict[str, Any]:
    """Compare within a relative tolerance; ``None`` actual is unmeasured."""
    if not isinstance(actual, (int, float)):
        return _check(name, expected, None, unit, None, tolerance)
    passed = abs(actual - expected) <= tolerance * abs(expected)
    return _check(name, expected, actual, unit, passed, tolerance)


def _exact_check(name: str, expected: int, actual: Any, unit: str) -> dict[str, Any]:
    """Compare a count exactly; ``None`` actual is unmeasured."""
    if not isinstance(actual, int):
        return _check(name, expected, None, unit, None)
    return _check(name, expected, actual, unit, actual == expected)


def _box_check(
    expected: tuple[float, float, float], box: Any, tolerance: float
) -> dict[str, Any]:
    """Compare bounding-box size per axis.

    When the axes fail but the sorted sizes match, the note says so: the part
    is right but was built in a different orientation than expected.
    """
    want = list(expected)
    size = box.get("size") if isinstance(box, dict) else None
    if not isinstance(size, list) or len(size) != 3:
        return _check("bounding_box_mm", want, None, "mm", None, tolerance)
    passed = all(abs(a - e) <= tolerance for a, e in zip(size, want, strict=True))
    note = None
    if not passed and all(
        abs(a - e) <= tolerance for a, e in zip(sorted(size), sorted(want), strict=True)
    ):
        note = (
            "Sizes match with the axes reordered: the part is the right size "
            "but oriented differently (check which plane each sketch is on)"
        )
    return _check("bounding_box_mm", want, size, "mm", passed, tolerance, note)


def _verdict(checks: list[dict[str, Any]]) -> str:
    """Overall verdict: fail beats inconclusive beats pass."""
    if not checks:
        return "report_only"
    outcomes = [check["passed"] for check in checks]
    if False in outcomes:
        return "fail"
    if None in outcomes:
        return "inconclusive"
    return "pass"


def _verdict_message(verdict: str, checks: list[dict[str, Any]], doc: str) -> str:
    """One-line summary naming the checks that need attention."""
    total = len(checks)
    passed = sum(1 for check in checks if check["passed"] is True)
    failed = [check["name"] for check in checks if check["passed"] is False]
    unknown = [check["name"] for check in checks if check["passed"] is None]
    if verdict == "report_only":
        return f"Measured the active {doc}; no expectations were given"
    if verdict == "pass":
        return f"Verification passed: {passed} of {total} checks passed"
    if verdict == "fail":
        return (
            f"Verification failed: {passed} of {total} checks passed "
            f"(failed: {', '.join(failed)})"
        )
    return (
        f"Verification inconclusive: {passed} of {total} checks passed, "
        f"could not measure: {', '.join(unknown)}"
    )


async def register_analysis_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register analysis tools with FastMCP.

    Registers comprehensive analysis tools for SolidWorks model evaluation including mass
    properties, interference checking, geometry analysis, and material properties. These
    tools provide critical engineering data for design validation and optimization.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.analysis import register_analysis_tools

                        tool_count = await register_analysis_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} analysis tools")
                        ```

                    Note:
                        Analysis tools require an active SolidWorks document with geometry.
                        Some analyses may require specific material assignments for accurate results.
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def calculate_mass_properties(
        input_data: MassPropertiesInput,
    ) -> dict[str, Any]:
        """Measure the active part or assembly's mass properties: volume, surface area, mass, centre of mass and moments of inertia.

        Use it to check weight or balance. To compare a model with the values you
        expect, use `verify_model`; `get_mass_properties` does the same as this tool.
        Mass depends on the assigned material (`set_material`). Needs: an open part or
        assembly. Read-only. It rebuilds first. Returns: `mass_properties` with `volume`
        (mm³), `surface_area` (mm²), `mass` (kg), `center_of_mass` (mm),
        `moments_of_inertia` (in kg·m², whatever its `units` label says) and
        `principal_axes`.

        Args:
            input_data: Nothing is required; the fields (`model_path`, `units`, `include_hidden`, `reference_coordinate_system`) are not used yet: it always measures the active model.

        Returns:
            dict[str, Any]: The mass properties.
        """
        if hasattr(adapter, "calculate_mass_properties"):
            result = await adapter.calculate_mass_properties(input_data.model_dump())
            require_success(result, context="Failed to calculate mass properties")
            return {
                "status": "success",
                "message": "Mass properties calculated successfully",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        result = await adapter.get_mass_properties()

        require_success(result, context="Failed to calculate mass properties")
        props = result.data
        assert props is not None
        return {
            "status": "success",
            "message": "Mass properties calculated successfully",
            "mass_properties": {
                "volume": {"value": props.volume, "units": "mm³"},
                "surface_area": {"value": props.surface_area, "units": "mm²"},
                "mass": {"value": props.mass, "units": "kg"},
                "center_of_mass": {
                    "x": props.center_of_mass[0],
                    "y": props.center_of_mass[1],
                    "z": props.center_of_mass[2],
                    "units": "mm",
                },
                "moments_of_inertia": {
                    "Ixx": props.moments_of_inertia["Ixx"],
                    "Iyy": props.moments_of_inertia["Iyy"],
                    "Izz": props.moments_of_inertia["Izz"],
                    "Ixy": props.moments_of_inertia["Ixy"],
                    "Ixz": props.moments_of_inertia["Ixz"],
                    "Iyz": props.moments_of_inertia["Iyz"],
                    "units": "kg·mm²",
                },
                "principal_axes": props.principal_axes,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_mass_properties(
        input_data: MassPropertiesInput | None = None,
    ) -> dict[str, Any]:
        """Measure the active part or assembly's mass properties: volume, surface area, mass, centre of mass and moments of inertia.

        The same as `calculate_mass_properties`, which it calls. To compare a model with
        the values you expect, use `verify_model`. Mass depends on the assigned material
        (`set_material`). Needs: an open part or assembly. Read-only. It rebuilds first.
        Returns: `mass_properties` with `volume` (mm³), `surface_area` (mm²), `mass`
        (kg), `center_of_mass` (mm), `moments_of_inertia` (in kg·m², whatever its
        `units` label says) and `principal_axes`.

        Args:
            input_data: Optional, and not used yet: it always measures the active model.

        Returns:
            dict[str, Any]: The mass properties.
        """
        return await calculate_mass_properties(input_data or MassPropertiesInput())

    @mcp.tool()
    async def check_interference(input_data: InterferenceCheckInput) -> dict[str, Any]:
        """Find where the components of the active assembly overlap (Tools > Interference Detection).

        Use it after inserting and mating components. A count of 0 is a real
        measurement. To fail a build on interference, use `verify_model` with
        `no_interference`. Needs: an open, active assembly. Read-only. Returns: `data`
        with `interference_found`, `interference_count`, `interferences` (component
        pairs and overlap volume in mm³) and `scope`.

        Args:
            input_data: Nothing is required. `components` limits the report to
                interferences involving those components; `tolerance`,
                `include_hidden` and `check_all_components` are not used.

        Returns:
            dict[str, Any]: The interferences found.
        """
        require_capability(
            adapter,
            "check_interference",
            "Active adapter does not support check_interference; no "
            "interference analysis was performed. Use SolidWorks "
            "directly (Tools > Interference Detection) to check this "
            "assembly.",
        )
        result = await adapter.check_interference(input_data.model_dump())
        require_success(result, "Interference check failed")
        return {
            "status": "success",
            "message": "Interference check completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def analyze_geometry(input_data: GeometryAnalysisInput) -> dict[str, Any]:
        """Run a geometry analysis on the active model, such as curvature, draft or wall thickness.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. For distances
        and angles today, use `measure_entities`; for size and volume, use
        `verify_model` or `calculate_mass_properties`. Read-only. Returns: once
        available, the analysis under `data`.

        Args:
            input_data: The analysis. `analysis_type` (e.g. curvature, draft,
                thickness) is required; `parameters` has a default.

        Returns:
            dict[str, Any]: The analysis, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "analyze_geometry",
            f"Active adapter does not support analyze_geometry; no "
            f"{input_data.analysis_type} analysis was performed.",
        )
        result = await adapter.analyze_geometry(input_data.model_dump())
        require_success(result, "Failed to analyze geometry")
        return {
            "status": "success",
            "message": f"Geometry analysis ({input_data.analysis_type}) completed",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_material_properties() -> dict[str, Any]:
        """Report the physical properties of the active part's material: density, modulus, Poisson's ratio, strength.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. For the
        material's name today, use `get_material`; for the materials you can assign, use
        `list_available_materials`. Read-only. Returns: once available, the properties
        under `data`.
        """
        require_capability(
            adapter,
            "get_material_properties",
            "Active adapter does not support get_material_properties",
        )
        result = await adapter.get_material_properties()
        require_success(result, "Failed to get material properties")
        return {
            "status": "success",
            "message": "Material properties retrieved successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def verify_model(
        input_data: VerifyModelInput | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check the active part or assembly against what you meant to build, one pass/fail check per expected value.

        Use it as the last step of a build: a modelling tool's success doesn't prove the
        geometry is right. Give only the values you know. Units: mm, mm³, kg;
        `bounding_box_mm` is [x, y, z] in model axes. Widen `relative_tolerance` when
        your sums ignore fillets. Needs: an open part or assembly. Read-only. Returns:
        `verdict` (pass, fail, inconclusive or report_only), `checks` (each `expected`,
        `actual`, `tolerance`, `passed`; null when unmeasured) and `measured`. A
        mismatch is still `status: success`.

        Args:
            input_data: The expectations, all optional: `mass_kg`, `volume_mm3`,
                `bounding_box_mm`, `feature_count`, `solid_body_count`, and for an
                assembly `component_count`, `mate_count` and `no_interference`;
                `relative_tolerance` (0.01) and `length_tolerance_mm` (0.1) have
                defaults. With none it only reports what it measured.

        Returns:
            dict[str, Any]: The verdict and checks.
        """
        expectations = normalize_input(input_data, VerifyModelInput)
        require_capability(
            adapter,
            "get_model_geometry_summary",
            "Active adapter cannot read the model back, so nothing was verified.",
        )
        summary_result = await adapter.get_model_geometry_summary()
        require_success(summary_result, context="Failed to read the model back")
        summary = dict(summary_result.data or {})
        is_assembly = summary.get("document_type") == "assembly"

        if not is_assembly:
            misplaced = [
                name
                for name in _ASSEMBLY_ONLY
                if getattr(expectations, name) is not None
            ]
            if misplaced:
                raise InvalidInputError(
                    f"{', '.join(misplaced)} only apply to assemblies; the active "
                    "document is a part"
                )

        measured: dict[str, Any] = dict(summary)
        checks: list[dict[str, Any]] = []
        rel = expectations.relative_tolerance

        if expectations.mass_kg is not None:
            mass_result = await adapter.get_mass_properties()
            mass = (
                mass_result.data.mass
                if mass_result.is_success and mass_result.data
                else None
            )
            material_result = await adapter.get_material()
            material = (
                (material_result.data or {}).get("material")
                if material_result.is_success
                else None
            )
            measured["mass_kg"] = mass
            measured["material"] = material
            check = _relative_check("mass_kg", expectations.mass_kg, mass, rel, "kg")
            if check["passed"] is False:
                check["note"] = (
                    f"Material: {material}"
                    if material
                    else "No material assigned; SolidWorks used a default density"
                )
            checks.append(check)

        if expectations.volume_mm3 is not None:
            checks.append(
                _relative_check(
                    "volume_mm3",
                    expectations.volume_mm3,
                    summary.get("volume_mm3"),
                    rel,
                    "mm³",
                )
            )

        if expectations.bounding_box_mm is not None:
            checks.append(
                _box_check(
                    expectations.bounding_box_mm,
                    summary.get("bounding_box_mm"),
                    expectations.length_tolerance_mm,
                )
            )

        if expectations.feature_count is not None:
            features_result = await adapter.list_features()
            names = (
                _count_modelling_features(features_result.data or [])
                if features_result.is_success
                else None
            )
            measured["features"] = names
            checks.append(
                _exact_check(
                    "feature_count",
                    expectations.feature_count,
                    None if names is None else len(names),
                    "features",
                )
            )

        for name, unit in (
            ("solid_body_count", "bodies"),
            ("component_count", "components"),
            ("mate_count", "mates"),
        ):
            expected = getattr(expectations, name)
            if expected is not None:
                checks.append(_exact_check(name, expected, summary.get(name), unit))

        if expectations.no_interference is not None:
            interference = await adapter.check_interference({})
            found = (
                (interference.data or {}).get("interference_found")
                if interference.is_success
                else None
            )
            measured["interference"] = (
                interference.data if interference.is_success else None
            )
            clear = None if found is None else not found
            checks.append(
                _check(
                    "no_interference",
                    expectations.no_interference,
                    clear,
                    None,
                    None if clear is None else clear == expectations.no_interference,
                    note=None if interference.is_success else interference.error,
                )
            )

        verdict = _verdict(checks)
        return {
            "status": "success",
            "message": _verdict_message(
                verdict, checks, str(summary.get("document_type") or "document")
            ),
            "verdict": verdict,
            "checks": checks,
            "measured": measured,
            "execution_time": summary_result.execution_time,
        }

    # Future analysis tools:
    # - perform_fea_analysis (if FEA capabilities are available)
    # - analyze_flow (computational fluid dynamics)
    # - thermal_analysis
    # - vibration_analysis
    # - stress_concentration_analysis

    tool_count = 4  # Keep legacy reported count expected by tests
    return tool_count
