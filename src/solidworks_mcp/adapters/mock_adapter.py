"""Mock SolidWorks adapter for testing and development.

This adapter simulates SolidWorks operations for testing on non-Windows platforms or
when SolidWorks is not available.
"""

from __future__ import annotations

import asyncio
import math
import random
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..exceptions import SolidWorksOperationError
from .base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    LoftParameters,
    MassProperties,
    RevolveParameters,
    SolidWorksAdapter,
    SolidWorksFeature,
    SolidWorksModel,
    SweepParameters,
)
from .solidworks.features import _AXIS_PLANE_PAIRS
from .solidworks.sketch import RELATION_NAME_MAP

#: Orientations the mock accepts for a drawing view. Kept in step with
#: ``_NAMED_VIEWS`` in ``adapters/solidworks/io.py`` by a test — the two lists
#: are maintained separately, and an orientation accepted live but rejected
#: here could never be covered, since the suite runs against the mock.
_MOCK_NAMED_VIEWS: frozenset[str] = frozenset(
    {
        "front",
        "back",
        "left",
        "right",
        "top",
        "bottom",
        "isometric",
        "iso",
        "trimetric",
        "dimetric",
        "current",
    }
)


#: Canned assembly component tree used by ``list_features`` when a mock
#: Assembly's ``_assembly_components`` hasn't been configured by a test.
#: Two top-level Part components plus one nested sub-assembly one level
#: deep, per ``docs/agents`` / OpenSpec change ``assembly-aware-list-features``.
_DEFAULT_ASSEMBLY_COMPONENTS: dict[str, dict[str, Any]] = {
    "PartA": {
        "type": "Part",
        "path": "Mock://PartA.sldprt",
        "features": [
            {"name": "Boss-Extrude1", "type": "Extrusion", "suppressed": False},
            {"name": "Fillet1", "type": "Fillet", "suppressed": False},
        ],
    },
    "PartB": {
        "type": "Part",
        "path": "Mock://PartB.sldprt",
        "features": [
            {"name": "Cut-Extrude1", "type": "Cut", "suppressed": False},
        ],
    },
    "SubAssembly1": {
        "type": "Assembly",
        "path": "Mock://SubAssembly1.sldasm",
        "features": [
            {"name": "Mate1", "type": "Mate", "suppressed": False},
        ],
        "components": {
            "PartC": {
                "type": "Part",
                "path": "Mock://PartC.sldprt",
                "features": [
                    {"name": "Boss-Extrude1", "type": "Extrusion", "suppressed": False},
                ],
            },
        },
    },
}


class _BoolCallable:
    """Compatibility shim that behaves as both bool and callable.

    Args:
        getter (Callable[[], bool]): The getter value.

    Attributes:
        _getter (Any): The getter value.
    """

    def __init__(self, getter: Callable[[], bool]) -> None:
        """Initialize the bool callable.

        Args:
            getter (Callable[[], bool]): The getter value.

        Returns:
            None: None.
        """
        self._getter = getter

    def __call__(self) -> bool:
        """Build internal call.

        Returns:
            bool: True if call, otherwise False.
        """
        return bool(self._getter())

    def __bool__(self) -> bool:
        """Build internal bool.

        Returns:
            bool: True if bool, otherwise False.
        """
        return bool(self._getter())


class MockSolidWorksAdapter(SolidWorksAdapter):
    """Mock adapter that simulates SolidWorks operations.

    Args:
        config (object | None): Configuration values for the operation. Defaults to None.

    Attributes:
        _connected (Any): The connected value.
        _delays (Any): The delays value.
        _is_connected_proxy (Any): The is connected proxy value.
        _operation_count (Any): The operation count value.
        _simulate_errors (Any): The simulate errors value.
    """

    def __init__(self, config: object | None = None) -> None:
        """Initialize the mock solid works adapter.

        Args:
            config (object | None): Configuration values for the operation. Defaults to None.

        Returns:
            None: None.
        """
        super().__init__(config)
        cfg: dict[str, Any] = dict(self.config_dict)
        self._connected = False
        self._current_model: SolidWorksModel | None = None
        self._models: dict[str, SolidWorksModel] = {}
        self._features: dict[str, SolidWorksFeature] = {}
        # Names suppressed via suppress_feature. Kept beside _features rather
        # than on SolidWorksFeature, which has no suppression field.
        self._suppressed_features: set[str] = set()
        # Component tree for an Assembly-type current model, keyed by
        # component name. See ``_flatten_assembly_components`` for shape.
        # Empty means "use the canned default fixture" (see list_features).
        self._assembly_components: dict[str, dict[str, Any]] = {}
        self._sketches: dict[str, str] = {}
        self._current_sketch: str | None = None
        # Tracks IDs returned by add_line/add_arc/add_circle/add_centerline/
        # add_rectangle/add_spline so add_sketch_constraint can validate
        # entity1/entity2 the same way the real adapter validates against
        # its sketch-entity registry.
        self._sketch_entity_ids: set[str] = set()
        self._dimensions: dict[str, float] = {}
        # Assembly components inserted via insert_component, keyed by
        # insertion order. See insert_component/list_components/add_mate.
        self._components: list[str] = []
        # Drawing views placed via create_drawing_view / add_drawing_view /
        # create_technical_drawing, in sheet order. See list_drawing_views.
        self._drawing_views: list[str] = []
        # Reference planes created via create_reference_plane, in creation
        # order, used to invent sequential "PlaneN" names. Shared feature
        # tree counter with create_axis mirrors the live adapter's
        # features_before/features_after pair (see _feature_count in
        # solidworks/features.py).
        self._reference_planes: list[str] = []
        self._feature_tree_count = 0
        # Volume tracked for mirror_feature, in mm^3. Seeded at the
        # live-measured 1819569.1 mm^3 wing volume from
        # _mirror_feature_impl in solidworks/features.py, then doubled on
        # each successful mirror so volume_before/volume_after/volume_ratio
        # stay self-consistent without a real geometry engine.
        self._mirror_volume: float = 1819569.1
        self._operation_count = 0

        # Configurable simulation delays (in seconds)
        self._delays = {
            "connect": cfg.get("mock_connect_delay", 0.1),
            "model_operation": cfg.get("mock_model_delay", 0.02),
            "feature_operation": cfg.get("mock_feature_delay", 0.03) if cfg else 0.03,
            "sketch_operation": cfg.get("mock_sketch_delay", 0.1),
        }
        self._is_connected_proxy = _BoolCallable(lambda: self._connected)
        self._simulate_errors = bool(cfg.get("simulate_errors", False))

    def __getattribute__(self, name: str) -> Any:
        """Build internal getattribute.

        Args:
            name (str): The name value.

        Returns:
            Any: The result produced by the operation.
        """
        if name == "is_connected":
            return object.__getattribute__(self, "_is_connected_proxy")
        return object.__getattribute__(self, name)

    async def connect(self) -> None:
        """Mock connection to SolidWorks.

        Returns:
            None: None.
        """
        await asyncio.sleep(self._delays["connect"])
        self._connected = True

        # Initialize some sample data
        self._dimensions = {
            "D1@Sketch1": 10.0,
            "D2@Sketch1": 20.0,
            "D1@Boss-Extrude1": 50.0,
        }

    async def disconnect(self) -> None:
        """Mock disconnection from SolidWorks.

        Returns:
            None: None.
        """
        self._connected = False
        self._current_model = None
        self._models.clear()
        self._features.clear()
        self._sketches.clear()
        self._current_sketch = None

    def is_connected(self) -> bool:
        """Check if mock connection is active.

        Returns:
            bool: True if connected, otherwise False.
        """
        return self._connected

    async def health_check(self) -> AdapterHealth:
        """Get mock health status.

        Returns:
            AdapterHealth: The result produced by the operation.
        """
        error_count = int(self._metrics["errors_count"])
        success_count = int(
            self._metrics["operations_count"] - self._metrics["errors_count"]
        )
        return AdapterHealth(
            healthy=self._connected,
            last_check=datetime.now(),
            error_count=error_count,
            success_count=success_count,
            average_response_time=self._metrics["average_response_time"],
            connection_status="connected" if self._connected else "disconnected",
            metrics={
                "adapter_type": "mock",
                "operations_count": self._operation_count,
                "models_count": len(self._models),
                "features_count": len(self._features),
                "sketches_count": len(self._sketches),
            },
        )

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Mock opening a SolidWorks model.

        Args:
            file_path (str): Path to the target file.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.

        Raises:
            SolidWorksOperationError: Simulated adapter failure.
        """
        if not self._connected:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        if self._simulate_errors:
            raise SolidWorksOperationError("Simulated adapter failure")

        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        # Determine model type from file extension
        file_path_lower = file_path.lower()
        if file_path_lower.endswith(".sldprt"):
            model_type = "Part"
        elif file_path_lower.endswith(".sldasm"):
            model_type = "Assembly"
        elif file_path_lower.endswith(".slddrw"):
            model_type = "Drawing"
        else:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Unsupported file type: {file_path}",
            )

        # Create mock model
        model_name = file_path.split("/")[-1].split("\\")[-1]
        model = SolidWorksModel(
            path=file_path,
            name=model_name,
            type=model_type,
            is_active=True,
            configuration="Default",
            properties={
                "created": datetime.now().isoformat(),
                "model_id": model_name or f"Part{len(self._models) + 1}",
                "file_size": random.randint(100000, 5000000),
            },
        )

        self._current_model = model
        self._models[file_path] = model

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=model,
            execution_time=self._delays["model_operation"],
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Mock closing the current model.

        Args:
            save (bool): The save value. Defaults to False.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active model to close"
            )

        await asyncio.sleep(self._delays["model_operation"] / 2)
        self._operation_count += 1

        if save:
            # Simulate save operation
            await asyncio.sleep(self._delays["model_operation"])

        self._current_model = None

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=None,
            execution_time=self._delays["model_operation"],
        )

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Mock metadata for the currently active model.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        await asyncio.sleep(self._delays["model_operation"] / 2)
        self._operation_count += 1

        model = self._current_model
        feature_count = len(self._features)
        info = {
            "title": model.name,
            "path": model.path,
            "type": model.type,
            "configuration": model.configuration or "Default",
            "is_dirty": False,
            "feature_count": feature_count,
            "rebuild_status": 0,
        }

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=info,
            execution_time=self._delays["model_operation"] / 2,
        )

    async def list_features(
        self, include_suppressed: bool = False, max_assembly_depth: int = 2
    ) -> AdapterResult[list[dict[str, Any]]]:
        """Mock feature tree listing for the active model.

        For an Assembly model, flattens in every configured component's
        features (see ``_assembly_components``) alongside the document's own
        features, tagged with ``component``/``component_path`` the same way
        the real adapter does. Falls back to a small canned two-component
        fixture (plus one nested sub-assembly) when no components have been
        configured, mirroring the existing "seed realistic feature names"
        behavior for an empty Part.

        Args:
            include_suppressed (bool): The include suppressed value. Defaults to False.
            max_assembly_depth (int): Sub-assembly recursion budget. Ignored
                for non-Assembly models. Defaults to 2.

        Returns:
            AdapterResult[list[dict[str, Any]]]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        await asyncio.sleep(self._delays["feature_operation"] / 2)
        self._operation_count += 1

        is_assembly = self._current_model.type == "Assembly"

        # Seed realistic feature names for empty mock state.
        if not self._features:
            seeded: list[dict[str, Any]] = [
                {
                    "name": "Origin",
                    "type": "OriginProfileFeature",
                    "suppressed": False,
                    "component": None,
                    "component_path": None,
                    "component_parent": None,
                },
                {
                    "name": "Front Plane",
                    "type": "RefPlane",
                    "suppressed": False,
                    "component": None,
                    "component_path": None,
                    "component_parent": None,
                },
                {
                    "name": "Right Plane",
                    "type": "RefPlane",
                    "suppressed": False,
                    "component": None,
                    "component_path": None,
                    "component_parent": None,
                },
                {
                    "name": "Top Plane",
                    "type": "RefPlane",
                    "suppressed": False,
                    "component": None,
                    "component_path": None,
                    "component_parent": None,
                },
                {
                    "name": "Sketch1",
                    "type": "ProfileFeature",
                    "suppressed": False,
                    "component": None,
                    "component_path": None,
                    "component_parent": None,
                },
            ]
            if is_assembly:
                components = self._assembly_components or _DEFAULT_ASSEMBLY_COMPONENTS
                seeded.extend(
                    self._flatten_assembly_components(
                        components, include_suppressed, max_assembly_depth - 1, None
                    )
                )
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data=seeded,
                execution_time=self._delays["feature_operation"] / 2,
            )

        feature_rows: list[dict[str, Any]] = []
        for i, feature in enumerate(self._features.values()):
            row = {
                "name": feature.name,
                "type": feature.type,
                "suppressed": bool((feature.properties or {}).get("suppressed", False)),
                "position": i,
                "component": None,
                "component_path": None,
                "component_parent": None,
            }
            if include_suppressed or not row["suppressed"]:
                feature_rows.append(row)

        if is_assembly:
            components = self._assembly_components or _DEFAULT_ASSEMBLY_COMPONENTS
            feature_rows.extend(
                self._flatten_assembly_components(
                    components,
                    include_suppressed,
                    max_assembly_depth - 1,
                    None,
                )
            )

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature_rows,
            execution_time=self._delays["feature_operation"] / 2,
        )

    def _flatten_assembly_components(
        self,
        components: dict[str, dict[str, Any]],
        include_suppressed: bool,
        depth_remaining: int,
        parent_component: str | None,
    ) -> list[dict[str, Any]]:
        """Flatten a mock component tree into tagged feature descriptors.

        Mirrors the real adapter's recursion rules: a sub-assembly component
        is expanded (its own features plus a recursive pass over its
        components) only while ``depth_remaining > 0``; beyond that it is
        represented by a single bare descriptor. An unresolvable component
        (``type: "Unresolved"`` in the fixture) always produces one
        ``UnresolvedComponent`` descriptor.

        Args:
            components: Mapping of component name to a fixture dict with
                ``type`` ("Part", "Assembly", or "Unresolved"), ``path``,
                ``features`` (list of ``{name, type, suppressed}``), and,
                for "Assembly" components, a nested ``components`` mapping.
            include_suppressed: Include suppressed entries when ``True``.
            depth_remaining: Sub-assembly recursion budget remaining.
            parent_component: Name of the component this level of
                ``components`` is nested inside, or ``None`` for top-level.

        Returns:
            list[dict[str, Any]]: Flattened, component-tagged descriptors.
        """
        results: list[dict[str, Any]] = []
        for name, comp in components.items():
            comp_type = comp.get("type")
            path = comp.get("path")

            if comp_type == "Unresolved":
                results.append(
                    {
                        "name": name,
                        "type": "UnresolvedComponent",
                        "suppressed": False,
                        "position": -1,
                        "component": name,
                        "component_path": None,
                        "component_parent": parent_component,
                    }
                )
                continue

            if comp_type == "Assembly" and depth_remaining <= 0:
                results.append(
                    {
                        "name": name,
                        "type": "Component",
                        "suppressed": False,
                        "position": -1,
                        "component": name,
                        "component_path": path,
                        "component_parent": parent_component,
                    }
                )
                continue

            for i, feature in enumerate(comp.get("features", [])):
                suppressed = bool(feature.get("suppressed", False))
                if not include_suppressed and suppressed:
                    continue
                results.append(
                    {
                        "name": feature["name"],
                        "type": feature["type"],
                        "suppressed": suppressed,
                        "position": i,
                        "component": name,
                        "component_path": path,
                        "component_parent": parent_component,
                    }
                )

            if comp_type == "Assembly":
                results.extend(
                    self._flatten_assembly_components(
                        comp.get("components", {}),
                        include_suppressed,
                        depth_remaining - 1,
                        name,
                    )
                )

        return results

    async def select_feature(self, feature_name: str) -> AdapterResult[dict[str, Any]]:
        """Mock feature selection/highlight — succeeds without COM side-effects.

        Args:
            feature_name (str): The feature name value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        await asyncio.sleep(self._delays["feature_operation"] / 4)
        self._operation_count += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "selected": True,
                "feature_name": feature_name,
                "entity_type": "mock",
            },
            execution_time=self._delays["feature_operation"] / 4,
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """Mock configuration listing for the active model.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        await asyncio.sleep(self._delays["model_operation"] / 2)
        self._operation_count += 1

        active = self._current_model.configuration or "Default"
        configs = [active] if active == "Default" else ["Default", active]

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=configs,
            execution_time=self._delays["model_operation"] / 2,
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Mock creating a new part.

        Args:
            name (str | None): The name value. Defaults to None.
            units (str | None): The units value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        if not self._connected:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        model_id = name or f"Part{len(self._models) + 1}"
        model = SolidWorksModel(
            path=f"Mock://{model_id}.sldprt",
            name=f"{model_id}",
            type="Part",
            is_active=True,
            configuration="Default",
            properties={
                "created": datetime.now().isoformat(),
                "mock": True,
                "units": units or "mm",
            },
        )

        self._current_model = model
        self._models[model.path] = model

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=model,
            execution_time=self._delays["model_operation"],
        )

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Mock creating a new assembly.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        if not self._connected:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        model_id = name or f"Assembly{len(self._models) + 1}"
        model = SolidWorksModel(
            path=f"Mock://{model_id}.sldasm",
            name=f"{model_id}",
            type="Assembly",
            is_active=True,
            configuration="Default",
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        self._current_model = model
        self._models[model.path] = model

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=model,
            execution_time=self._delays["model_operation"],
        )

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Mock creating a new drawing.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        if not self._connected:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )

        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        model_id = name or f"Drawing{len(self._models) + 1}"
        model = SolidWorksModel(
            path=f"Mock://{model_id}.slddrw",
            name=f"{model_id}",
            type="Drawing",
            is_active=True,
            configuration="Default",
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        self._current_model = model
        self._models[model.path] = model

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=model,
            execution_time=self._delays["model_operation"],
        )

    async def create_extrusion(
        self,
        params: ExtrusionParameters | str,
        depth: float | None = None,
        direction: str | None = None,
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock creating an extrusion feature.

        Args:
            params (ExtrusionParameters | str): The params value.
            depth (float | None): The depth value. Defaults to None.
            direction (str | None): The direction value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        if isinstance(params, str):
            params = ExtrusionParameters(depth=depth or 0.0)

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        feature_id = f"Boss-Extrude{len(self._features) + 1}"
        feature = SolidWorksFeature(
            name=feature_id,
            type="Extrusion",
            id=str(uuid.uuid4()),
            parameters={
                "depth": params.depth,
                "direction": direction or "blind",
                "draft_angle": params.draft_angle,
                "reverse_direction": params.reverse_direction,
                "both_directions": params.both_directions,
                "thin_feature": params.thin_feature,
                "thin_thickness": params.thin_thickness,
            },
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        feature_key = feature.id or feature.name
        self._features[feature_key] = feature

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature,
            execution_time=self._delays["feature_operation"],
        )

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock creating a revolve feature.

        Args:
            params (RevolveParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        feature_id = f"Boss-Revolve{len(self._features) + 1}"
        feature = SolidWorksFeature(
            name=feature_id,
            type="Revolve",
            id=str(uuid.uuid4()),
            parameters={
                "angle": params.angle,
                "reverse_direction": params.reverse_direction,
                "both_directions": params.both_directions,
                "thin_feature": params.thin_feature,
                "thin_thickness": params.thin_thickness,
            },
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        feature_key = feature.id or feature.name
        self._features[feature_key] = feature

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature,
            execution_time=self._delays["feature_operation"],
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock creating a sweep feature.

        Args:
            params (SweepParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        feature_id = f"Boss-Sweep{len(self._features) + 1}"
        feature = SolidWorksFeature(
            name=feature_id,
            type="Sweep",
            id=str(uuid.uuid4()),
            parameters={
                "path": params.path,
                "twist_along_path": params.twist_along_path,
                "twist_angle": params.twist_angle,
            },
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        feature_key = feature.id or feature.name
        self._features[feature_key] = feature

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature,
            execution_time=self._delays["feature_operation"],
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock creating a loft feature.

        Args:
            params (LoftParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        feature_id = f"Boss-Loft{len(self._features) + 1}"
        feature = SolidWorksFeature(
            name=feature_id,
            type="Loft",
            id=str(uuid.uuid4()),
            parameters={
                "profiles": params.profiles,
                "guide_curves": params.guide_curves,
                "start_tangent": params.start_tangent,
                "end_tangent": params.end_tangent,
            },
            properties={"created": datetime.now().isoformat(), "mock": True},
        )

        feature_key = feature.id or feature.name
        self._features[feature_key] = feature

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature,
            execution_time=self._delays["feature_operation"],
        )

    async def create_sketch(self, plane: str) -> AdapterResult[dict[str, Any]]:  # type: ignore[override]
        """Mock creating a sketch.

        Args:
            plane (str): The plane value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self._current_model:
            # Legacy tests start sketching immediately after connect.
            await self.create_part()

        await asyncio.sleep(self._delays["sketch_operation"])
        self._operation_count += 1

        sketch_id = f"Sketch{len(self._sketches) + 1}"
        self._sketches[sketch_id] = plane
        self._current_sketch = sketch_id

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "id": sketch_id,
                "name": sketch_id,
                "sketch_name": sketch_id,
                "plane": plane,
            },
            execution_time=self._delays["sketch_operation"],
        )

    async def add_sketch_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        construction: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Legacy compatibility wrapper around add_line.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.
            construction (bool): The construction value. Defaults to False.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        result = await self.add_line(x1, y1, x2, y2)
        if not result.is_success:
            return AdapterResult(
                status=result.status,
                error=result.error,
                execution_time=result.execution_time,
            )
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "id": result.data,
                "start": {"x": x1, "y": y1},
                "end": {"x": x2, "y": y2},
                "construction": construction,
            },
            execution_time=result.execution_time,
        )

    async def save_file(
        self, file_path: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Legacy compatibility save operation for tests.

        Args:
            file_path (str | None): Path to the target file. Defaults to None.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        await asyncio.sleep(0.02)
        self._operation_count += 1
        resolved_path = file_path or self._current_model.path
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"file_path": resolved_path, "saved": True},
            execution_time=0.02,
        )

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Mock adding a line to sketch.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        line_id = f"Line{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(line_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=line_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Mock adding a construction centerline to sketch.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        centerline_id = f"Centerline_{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(centerline_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=centerline_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Mock adding a NURBS spline through the supplied points.

        Args:
            points (list[dict[str, float]]): Ordered control points with
                ``"x"`` / ``"y"`` keys. Minimum 2 points.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )
        if len(points) < 2:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="add_spline requires at least 2 points",
            )
        # Match the real adapter's point contract: each dict must carry
        # both ``x`` and ``y`` keys, or the live impl raises KeyError on
        # ``point["x"]``. Validating here keeps mock/live parity so tests
        # that pass against the mock won't fail live on malformed input.
        for index, point in enumerate(points):
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"add_spline point at index {index} is missing "
                        "required 'x' and/or 'y' keys"
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        spline_id = f"Spline_{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(spline_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=spline_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Mock adding a circle to sketch.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            radius (float): The radius value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        circle_id = f"Circle{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(circle_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=circle_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> AdapterResult[str]:
        """Mock adding a circular arc to sketch.

        Args:
            center_x (float): Arc centre X.
            center_y (float): Arc centre Y.
            start_x (float): Arc start point X.
            start_y (float): Arc start point Y.
            end_x (float): Arc end point X.
            end_y (float): Arc end point Y.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        arc_id = f"Arc_{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(arc_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=arc_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Mock adding a rectangle to sketch.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"])
        self._operation_count += 1

        rect_id = f"Rectangle{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(rect_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=rect_id,
            execution_time=self._delays["sketch_operation"],
        )

    async def add_ellipse(
        self,
        center_x: float,
        center_y: float,
        major_axis: float,
        minor_axis: float,
    ) -> AdapterResult[str]:
        """Mock adding an axis-aligned ellipse to sketch.

        Args:
            center_x (float): Ellipse centre X in millimetres.
            center_y (float): Ellipse centre Y in millimetres.
            major_axis (float): Full major-axis length in millimetres.
            minor_axis (float): Full minor-axis length in millimetres.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        ellipse_id = f"Ellipse_{random.randint(1000, 9999)}"
        self._sketch_entity_ids.add(ellipse_id)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=ellipse_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Mock adding a regular polygon to sketch.

        Args:
            center_x (float): Polygon centre X in millimetres.
            center_y (float): Polygon centre Y in millimetres.
            radius (float): Circumradius in millimetres (distance from centre
                to each vertex; matches the real adapter's
                ``CreatePolygon(..., Inscribed=True)`` semantics).
            sides (int): Number of polygon sides.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        # ID format mirrors the real PyWin32 adapter, which uses
        # ``_register_sketch_entity("Polygon", ...)`` (counter-based) so the
        # returned ID is a valid input to downstream sketch_linear_pattern /
        # sketch_circular_pattern / sketch_mirror / sketch_offset calls.
        polygon_id = f"Polygon_{len(self._sketch_entity_ids) + 1}"
        self._sketch_entity_ids.add(polygon_id)
        _ = sides  # informational only; the sides count is no longer part of the ID

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=polygon_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        """Mock creating a linear sketch pattern.

        Mirrors the real adapter's validation rules — empty entities,
        count < 2, non-positive spacing, and a zero direction vector each
        produce a clear error without "creating" a pattern.

        Args:
            entities (list[str]): Seed entity IDs.
            direction_x (float): Pattern direction X component.
            direction_y (float): Pattern direction Y component.
            spacing (float): Distance between instances in millimetres.
            count (int): Total number of instances (including the seed).

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )
        if not entities:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_linear_pattern requires at least one entity",
            )
        if count < 2:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_linear_pattern requires count >= 2",
            )
        if spacing <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_linear_pattern requires spacing > 0",
            )
        if math.hypot(direction_x, direction_y) < 1e-9:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=("sketch_linear_pattern requires a non-zero direction vector"),
            )
        for ent in entities:
            if ent not in self._sketch_entity_ids:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Unknown sketch entity '{ent}'. Use IDs returned by "
                        "add_line/add_arc/add_circle/add_spline/add_centerline."
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        pattern_id = f"LinearPattern_{count}x{spacing}_{random.randint(1000, 9999)}"
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=pattern_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        """Mock creating a circular sketch pattern around the sketch origin.

        Args:
            entities (list[str]): Seed entity IDs.
            angle (float): Total swept angle in degrees.
            count (int): Total number of instances (including the seed).

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )
        if not entities:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_circular_pattern requires at least one entity",
            )
        if count < 2:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_circular_pattern requires count >= 2",
            )
        if angle <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_circular_pattern requires angle > 0",
            )
        for ent in entities:
            if ent not in self._sketch_entity_ids:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Unknown sketch entity '{ent}'. Use IDs returned by "
                        "add_line/add_arc/add_circle/add_spline/add_centerline."
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        pattern_id = f"CircularPattern_{count}x{angle}deg_{random.randint(1000, 9999)}"
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=pattern_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Mock mirroring sketch entities about a centerline.

        Args:
            entities (list[str]): IDs of segments to mirror.
            mirror_line (str): ID of the centerline to mirror across.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )
        if not entities:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_mirror requires at least one entity",
            )
        if not mirror_line:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "sketch_mirror requires a mirror_line entity ID (add_centerline)"
                ),
            )
        if mirror_line not in self._sketch_entity_ids:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Unknown mirror_line entity '{mirror_line}'. Use the "
                    "ID returned by add_centerline."
                ),
            )
        # Mirror the real adapter — IModelDoc2::SketchMirror needs a
        # centreline as the mirror axis; other segments silently no-op.
        if not mirror_line.startswith("Centerline_"):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"mirror_line must be a centerline (from add_centerline), "
                    f"got '{mirror_line}'"
                ),
            )
        for ent in entities:
            if ent not in self._sketch_entity_ids:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Unknown sketch entity '{ent}'. Use IDs returned by "
                        "add_line/add_arc/add_circle/add_spline/add_centerline."
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        mirror_id = f"Mirror_{mirror_line}_{random.randint(1000, 9999)}"
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=mirror_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def sketch_offset(
        self,
        entities: list[str],
        offset_distance: float,
        reverse_direction: bool,
    ) -> AdapterResult[str]:
        """Mock offsetting sketch entities by a fixed distance.

        Args:
            entities (list[str]): IDs of segments to offset.
            offset_distance (float): Distance in millimetres. Must be > 0.
            reverse_direction (bool): Flip the offset direction.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )
        if not entities:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="sketch_offset requires at least one entity",
            )
        if offset_distance <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "sketch_offset requires offset_distance > 0 — use "
                    "reverse_direction to flip the side"
                ),
            )
        for ent in entities:
            if ent not in self._sketch_entity_ids:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Unknown sketch entity '{ent}'. Use IDs returned by "
                        "add_line/add_arc/add_circle/add_spline/add_centerline."
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        direction = "inward" if reverse_direction else "outward"
        offset_id = f"Offset_{offset_distance}_{direction}_{random.randint(1000, 9999)}"
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=offset_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_sketch_constraint(
        self,
        entity1: str,
        entity2: str | None,
        relation_type: str,
        entity3: str | None = None,
    ) -> AdapterResult[str]:
        """Mock adding a geometric constraint between sketch entities.

        Args:
            entity1 (str): Primary sketch-entity ID.
            entity2 (str | None): Secondary sketch-entity ID, or None for
                single-entity relations (horizontal, vertical, fix).
            relation_type (str): Constraint name (see RELATION_NAME_MAP).
            entity3 (str | None): Third entity ID — only used by the
                ``symmetric`` relation (the centerline of symmetry). All
                other relation types reject a non-null ``entity3``.

        Returns:
            AdapterResult[str]: SUCCESS with a placeholder constraint ID, or
                ERROR if no active sketch, the relation_type is unsupported,
                arity is wrong, or an entity ID is unknown.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        rt_norm = (relation_type or "").strip().lower()
        if rt_norm not in RELATION_NAME_MAP:
            supported = ", ".join(sorted(RELATION_NAME_MAP))
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Unsupported relation type '{relation_type}'. "
                    f"Supported: {supported}"
                ),
            )

        # Arity validation — mirror the real adapter
        if rt_norm == "symmetric":
            if entity2 is None or entity3 is None:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Relation '{relation_type}' requires entity1, "
                        "entity2, and entity3 (the centerline of symmetry)"
                    ),
                )
        elif entity3 is not None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Relation '{relation_type}' does not accept entity3 — "
                    "only 'symmetric' takes a third entity (the centerline)"
                ),
            )

        # Validate entity IDs against the in-process sketch-entity registry
        # so the mock surfaces the same "Unknown sketch entity" error as the
        # real adapter (which checks adapter._sketch_entities).
        for ent in (entity1, entity2, entity3):
            if ent is not None and ent not in self._sketch_entity_ids:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Unknown sketch entity '{ent}'. Use IDs returned by "
                        "add_line/add_arc/add_circle/add_spline/add_centerline."
                    ),
                )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        constraint_id = f"Constraint_{relation_type}_{random.randint(1000, 9999)}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=constraint_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Mock exiting sketch mode.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active sketch to exit"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._current_sketch = None

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=None,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def check_sketch_fully_defined(
        self, sketch_name: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock check for sketch definition status.

        Args:
            sketch_name (str | None): Optional sketch name to inspect. Defaults to None.

        Returns:
            AdapterResult[dict[str, Any]]: Definition status payload.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 3)
        self._operation_count += 1

        resolved_name = sketch_name or self._current_sketch or "Sketch1"
        if sketch_name and sketch_name not in self._sketches:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Sketch not found: {sketch_name}",
            )

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "sketch_name": resolved_name,
                "is_fully_defined": True,
                "definition_state": "fully_defined",
                "source": "mock",
                "raw_status": True,
            },
            execution_time=self._delays["sketch_operation"] / 3,
        )

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Mock getting mass properties.

        Returns:
            AdapterResult[MassProperties]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        # Generate realistic mock data
        properties = MassProperties(
            volume=random.uniform(1000, 100000),  # mm³
            surface_area=random.uniform(1000, 50000),  # mm²
            mass=random.uniform(0.1, 50.0),  # kg (assuming typical density)
            center_of_mass=[
                random.uniform(-100, 100),
                random.uniform(-100, 100),
                random.uniform(-100, 100),
            ],
            moments_of_inertia={
                "Ixx": random.uniform(1e6, 1e9),
                "Iyy": random.uniform(1e6, 1e9),
                "Izz": random.uniform(1e6, 1e9),
                "Ixy": random.uniform(-1e8, 1e8),
                "Ixz": random.uniform(-1e8, 1e8),
                "Iyz": random.uniform(-1e8, 1e8),
            },
        )

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=properties,
            execution_time=self._delays["feature_operation"],
        )

    async def export_image(self, payload: dict) -> AdapterResult[dict]:
        """Mock export of a PNG/JPG viewport screenshot.

        Args:
            payload (dict): The payload value.

        Returns:
            AdapterResult[dict]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        import pathlib

        file_path = payload.get("file_path", "")
        width = int(payload.get("width", 1280))
        height = int(payload.get("height", 720))
        orientation = str(payload.get("view_orientation", "current"))

        await asyncio.sleep(0.3)
        self._operation_count += 1

        out = pathlib.Path(file_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Write a valid 1×1 white PNG binary so UI image tags don't break
        _PNG_1X1_WHITE = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR"  # IHDR chunk length+type
            b"\x00\x00\x00\x01\x00\x00\x00\x01"  # 1x1
            b"\x08\x02\x00\x00\x00\x90wS\xde"  # 8-bit RGB + CRC
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff\xff\x00\x05\xfe\x02\xfe\xdc\xcaY\xe7"  # IDAT
            b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
        )
        out.write_bytes(_PNG_1X1_WHITE)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "file_path": file_path,
                "format": "PNG",
                "dimensions": f"{width}x{height}",
                "view": orientation,
            },
            execution_time=0.3,
            metadata={"mock": True, "orientation": orientation},
        )

    async def pack_and_go_assembly(
        self,
        source_path: str,
        target_dir: str,
    ) -> AdapterResult[dict]:
        """Mock Pack-and-Go: simulate copying an assembly to a target directory.

        Args:
            source_path (str): Path to the source .sldasm file.
            target_dir (str): Directory to copy files into.

        Returns:
            AdapterResult[dict]: Simulated pack-and-go result.
        """
        import pathlib

        await asyncio.sleep(0.05)
        self._operation_count += 1

        source = pathlib.Path(source_path)
        out_dir = pathlib.Path(target_dir)
        mock_parts = [f"MockPart{i}.SLDPRT" for i in range(1, 3)]
        source_files = [str(source)] + [str(source.parent / p) for p in mock_parts]
        copied_files = [str(out_dir / source.name)] + [
            str(out_dir / p) for p in mock_parts
        ]
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "source_assembly": str(source),
                "target_dir": str(out_dir),
                "copied_files": copied_files,
                "source_files": source_files,
                "save_statuses": [0] * (len(mock_parts) + 1),
                "all_files_saved": True,
            },
            execution_time=0.05,
            metadata={"mock": True},
        )

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Mock exporting a file.

        Args:
            file_path (str): Path to the target file.
            format_type (str): The format type value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        # Simulate export time based on format
        export_times = {
            "step": 2.0,
            "iges": 1.5,
            "stl": 1.0,
            "pdf": 0.5,
            "jpg": 0.3,
            "glb": 1.2,
            "gltf": 1.2,
        }

        format_lower = format_type.lower()
        delay = export_times.get(format_lower, 1.0)

        await asyncio.sleep(delay)
        self._operation_count += 1

        # Write a minimal placeholder file so callers that check existence get a valid result
        if format_lower == "stl":
            import pathlib

            out = pathlib.Path(file_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            # Minimal ASCII STL — a single unit triangle (mock geometry placeholder)
            out.write_text(
                "solid mock\n"
                "  facet normal 0 0 1\n"
                "    outer loop\n"
                "      vertex 0 0 0\n"
                "      vertex 10 0 0\n"
                "      vertex 5 10 0\n"
                "    endloop\n"
                "  endfacet\n"
                "  facet normal 0 0 1\n"
                "    outer loop\n"
                "      vertex 0 0 0\n"
                "      vertex 10 0 0\n"
                "      vertex 5 0 10\n"
                "    endloop\n"
                "  endfacet\n"
                "endsolid mock\n",
                encoding="utf-8",
            )

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=None,
            execution_time=delay,
            metadata={"exported_format": format_type, "file_path": file_path},
        )

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Mock getting a dimension value.

        Args:
            name (str): The name value.

        Returns:
            AdapterResult[float]: The result produced by the operation.
        """
        await asyncio.sleep(0.05)  # Very fast operation
        self._operation_count += 1

        if name in self._dimensions:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data=self._dimensions[name],
                execution_time=0.05,
            )
        else:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Dimension '{name}' not found"
            )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Mock setting a dimension value.

        Args:
            name (str): The name value.
            value (float): The value value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        await asyncio.sleep(0.1)  # Fast operation
        self._operation_count += 1

        self._dimensions[name] = value

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=None, execution_time=0.1
        )

    async def insert_component(
        self, file_path: str, x: float = 0.0, y: float = 0.0, z: float = 0.0
    ) -> AdapterResult[dict[str, Any]]:
        """Mock inserting a component into the active assembly.

        Records the component in ``self._components`` so repeated inserts
        accumulate and ``list_components`` reflects them.

        Args:
            file_path (str): Path to the part or sub-assembly to insert.
            x (float): X position in millimetres. Defaults to 0.0.
            y (float): Y position in millimetres. Defaults to 0.0.
            z (float): Z position in millimetres. Defaults to 0.0.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        self._components.append(f"component-{len(self._components) + 1}")

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "component": self._components[-1],
                "file_path": file_path,
                "position": {"x": x, "y": y, "z": z},
                "components_before": len(self._components) - 1,
                "components_after": len(self._components),
            },
            execution_time=self._delays["model_operation"],
        )

    async def list_components(self) -> AdapterResult[list[str]]:
        """Mock listing the top-level components of the active assembly.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"] / 2)
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=list(self._components),
            execution_time=self._delays["model_operation"] / 2,
        )

    # Drawing Operations
    def _mock_place_view(self, payload: Any) -> AdapterResult[dict[str, Any]]:
        """Record a drawing view so ``list_drawing_views`` reflects it.

        Args:
            payload (Any): Tool payload, as the real adapter receives it.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        data = payload if isinstance(payload, dict) else {}
        model_path = data.get("model_path") or data.get("model_file")
        if not model_path:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="A model path is required (model_path or model_file)",
            )

        orientation = str(data.get("orientation") or data.get("view_type") or "front")
        if orientation.strip().lower() not in _MOCK_NAMED_VIEWS:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Unknown orientation '{orientation}'. Use one of: "
                    f"{', '.join(sorted(_MOCK_NAMED_VIEWS))}."
                ),
            )

        before = len(self._drawing_views)
        self._drawing_views.append(f"Drawing View{before + 1}")
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": self._drawing_views[-1],
                "model_path": model_path,
                "orientation": orientation,
                "position": {
                    "x": float(data.get("position_x", 100.0)),
                    "y": float(data.get("position_y", 150.0)),
                },
                "views_before": before,
                "views_after": len(self._drawing_views),
            },
            execution_time=self._delays["model_operation"],
        )

    async def create_drawing_view(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock placing a view of a model on the active drawing sheet.

        Args:
            payload (Any): Tool payload carrying the model path and orientation.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        return self._mock_place_view(payload)

    async def add_drawing_view(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock adding a view of a model to the active drawing sheet.

        Args:
            payload (Any): Tool payload carrying the model path and orientation.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        return self._mock_place_view(payload)

    async def create_technical_drawing(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock laying out the three standard views of a model.

        Args:
            payload (Any): Tool payload carrying the model path and projection.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        data = payload if isinstance(payload, dict) else {}
        model_path = data.get("model_path") or data.get("model_file")
        if not model_path:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="A model path is required (model_path or model_file)",
            )

        third_angle = bool(data.get("third_angle", True))
        if str(data.get("projection", "")).lower() in {"first", "first_angle"}:
            third_angle = False

        before = len(self._drawing_views)
        added = [f"Drawing View{before + offset}" for offset in (1, 2, 3)]
        self._drawing_views.extend(added)
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "views": added,
                "model_path": model_path,
                "projection": "third_angle" if third_angle else "first_angle",
                "views_before": before,
                "views_after": len(self._drawing_views),
            },
            execution_time=self._delays["model_operation"],
        )

    async def add_note(self, payload: Any = None) -> AdapterResult[dict[str, Any]]:
        """Mock placing a text note on the active drawing sheet.

        Args:
            payload (Any): Tool payload carrying the text and position.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        data = payload if isinstance(payload, dict) else {}
        text = data.get("text")
        if not text:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="add_note requires text"
            )

        self._operation_count += 1
        font_points = float(data.get("font_size") or 0.0)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "text": text,
                "position": {
                    "x": float(data.get("position_x", 100.0)),
                    "y": float(data.get("position_y", 50.0)),
                },
                # The real adapter sets this from IAnnotation::SetPosition's
                # return. Mock mode has no sheet to place anything on, so it
                # reports "not determinable" rather than claiming success at a
                # check it never performed.
                "positioned": None,
                "font_size_points": font_points or None,
            },
            execution_time=self._delays["model_operation"],
        )

    async def list_drawing_views(self) -> AdapterResult[list[str]]:
        """Mock listing the views on the active drawing.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"] / 2)
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=list(self._drawing_views),
            execution_time=self._delays["model_operation"] / 2,
        )

    async def check_interference(
        self, params: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock checking the active assembly for interfering components.

        Args:
            params (Any): Optional settings; ``coincident``, ``components``.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        options = params if isinstance(params, dict) else {}

        if len(self._components) < 2:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "Interference detection needs at least two components; the "
                    f"assembly has {len(self._components)}."
                ),
            )

        self._operation_count += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                # The real adapter gets this from SolidWorks' interference
                # engine. The mock has no geometry, so it cannot know whether
                # anything overlaps and says so rather than reporting a clean
                # assembly it never checked - a mock that always answered
                # False would make this tool useless wherever mock mode runs.
                "interference_found": None,
                "interference_count": None,
                "interferences": [],
                "coincident_treated_as_interference": bool(
                    options.get("coincident", False)
                ),
                "scope": "whole assembly",
                "tolerance_applied": None,
            },
            execution_time=self._delays["model_operation"],
        )

    # Feature Editing
    async def delete_feature(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Mock deleting a named feature from the active model.

        Args:
            name (str): Feature or sketch name.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])

        # _features is keyed by an internal id, so resolve by feature name.
        before = [f.name for f in self._features.values()]
        key = next((k for k, f in self._features.items() if f.name == name), None)
        if key is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Feature not found: {name}. "
                    f"Available: {', '.join(before) or 'none'}"
                ),
            )

        del self._features[key]
        self._suppressed_features.discard(name)
        self._operation_count += 1
        after = [f.name for f in self._features.values()]

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "deleted": name,
                "removed_features": [n for n in before if n not in after],
                "features_before": len(before),
                "features_after": len(after),
            },
            execution_time=self._delays["model_operation"],
        )

    async def suppress_feature(
        self, name: str, suppress: bool = True
    ) -> AdapterResult[dict[str, Any]]:
        """Mock suppressing or unsuppressing a named feature.

        Args:
            name (str): Feature name.
            suppress (bool): True to suppress, False to unsuppress.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])

        known = any(f.name == name for f in self._features.values())
        if not known:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Feature not found: {name}"
            )

        was = name in self._suppressed_features
        if suppress:
            self._suppressed_features.add(name)
        else:
            self._suppressed_features.discard(name)
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "feature": name,
                "requested": suppress,
                "suppressed": bool(suppress),
                "was_suppressed": was,
            },
            execution_time=self._delays["model_operation"],
        )

    async def undo(self, count: int = 1) -> AdapterResult[dict[str, Any]]:
        """Mock undoing the last operations in the active model.

        Removes the most recently added features, mirroring what an undo of
        feature-creation steps does to the tree. ``tree_changed`` is ``False``
        when there was nothing left to undo, which is what the real adapter
        reports too - SolidWorks accepts an undo on an empty stack quietly.

        Args:
            count (int): Number of steps to undo.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        await asyncio.sleep(self._delays["model_operation"])
        steps = max(1, int(count))

        keys = list(self._features)
        before = [self._features[k].name for k in keys]
        doomed = keys[-steps:] if steps <= len(keys) else list(keys)
        removed = [self._features[k].name for k in doomed]
        for key in doomed:
            self._suppressed_features.discard(self._features[key].name)
            del self._features[key]
        self._operation_count += 1
        after = [f.name for f in self._features.values()]

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "requested_steps": steps,
                "features_before": len(before),
                "features_after": len(after),
                "removed_features": removed,
                "tree_changed": before != after,
            },
            execution_time=self._delays["model_operation"],
        )

    async def add_mate(
        self,
        component_a: str,
        component_b: str,
        entity_a: str = "Front Plane",
        entity_b: str = "Front Plane",
        mate_type: str = "coincident",
        alignment: str = "aligned",
        distance: float = 0.0,
        angle: float = 0.0,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock mating two components in the active assembly.

        Args:
            component_a (str): First component instance name.
            component_b (str): Second component instance name.
            entity_a (str): Named feature on the first component. Defaults to
                "Front Plane".
            entity_b (str): Named feature on the second component. Defaults to
                "Front Plane".
            mate_type (str): Mate type. Defaults to "coincident".
            alignment (str): Mate alignment. Defaults to "aligned".
            distance (float): Distance in millimetres, for a distance mate.
                Defaults to 0.0.
            angle (float): Angle in degrees, for an angle mate. Defaults to 0.0.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        known_mate_types = {
            "coincident",
            "concentric",
            "perpendicular",
            "parallel",
            "tangent",
            "distance",
            "angle",
        }
        if mate_type not in known_mate_types:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Unknown mate type '{mate_type}'. "
                    f"Use one of: {', '.join(sorted(known_mate_types))}."
                ),
            )

        await asyncio.sleep(self._delays["model_operation"])
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "mate_type": mate_type,
                "alignment": alignment,
                "components": [component_a, component_b],
                "entities": [entity_a, entity_b],
                "distance": distance or None,
                "angle": angle or None,
                # The real adapter fills these by comparing every component's
                # Transform2 before and after the mate. The mock has no
                # geometry to move, so it reports "not determinable" rather
                # than True: this field exists precisely so a caller can tell
                # a mate that positioned something from one SolidWorks
                # accepted and ignored, and a mock that always answers True
                # would make that check useless wherever mock mode is used.
                "moved_components": [],
                "geometry_moved": None,
            },
            execution_time=self._delays["model_operation"],
        )

    async def create_reference_plane(
        self,
        reference: str,
        offset: float = 0.0,
        angle: float = 0.0,
        flip: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock creating a reference plane offset from an existing plane.

        Mirrors the live adapter's refusals rather than fabricating a
        result it cannot know: an angled plane needs a second reference this
        signature cannot supply, and an offset of zero would be coincident
        with its reference. See ``_create_reference_plane_impl`` in
        ``solidworks/features.py`` for the live contract this mirrors.

        On success, invents a sequential ``PlaneN`` name tracked on
        ``self._reference_planes`` and advances the shared mock feature-tree
        counter so ``features_before``/``features_after`` differ by exactly
        one, the same signal the live adapter derives from
        ``IFeatureManager::GetFeatureCount``.

        Args:
            reference (str): Name of the reference plane or planar face.
            offset (float): Offset distance in millimetres. Defaults to 0.0.
            angle (float): Angle in degrees; unsupported (non-zero errors).
                Defaults to 0.0.
            flip (bool): Reverse the offset direction. Defaults to False.

        Returns:
            AdapterResult[dict[str, Any]]: The new plane's name and
            parameters, or error.
        """
        if angle:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "create_reference_plane does not support 'angle' yet: an "
                    "angled plane needs a second reference (an axis or edge "
                    "to rotate about) which this signature cannot take. Use "
                    "'offset' for parallel planes."
                ),
            )

        if not offset:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "create_reference_plane requires a non-zero offset - a "
                    "plane coincident with its reference is not useful"
                ),
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        before = self._feature_tree_count
        self._feature_tree_count += 1
        after = self._feature_tree_count

        self._reference_planes.append(f"Plane{len(self._reference_planes) + 1}")

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": self._reference_planes[-1],
                "reference": reference,
                "offset": offset,
                "angle": None,
                "flip": flip,
                "features_before": before,
                "features_after": after,
            },
            execution_time=self._delays["feature_operation"],
        )

    async def create_axis(self, reference: str) -> AdapterResult[dict[str, Any]]:
        """Mock creating a reference axis along a principal direction.

        Mirrors the live adapter's plane-pair mapping (``_AXIS_PLANE_PAIRS``
        in ``solidworks/features.py``, imported here directly so the two can
        never drift apart) and validation: only ``x``/``y``/``z``
        (case-insensitive, leading +/- stripped) are accepted.

        Args:
            reference (str): "x", "y" or "z" (case-insensitive; leading +/-
                stripped).

        Returns:
            AdapterResult[dict[str, Any]]: The plane pair used and the
            feature counter before/after, or error for an unknown reference.
        """
        key = str(reference or "").strip().lower().lstrip("+-")
        if key not in _AXIS_PLANE_PAIRS:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"Unknown axis reference '{reference}'. "
                    f"Use one of: {', '.join(sorted(_AXIS_PLANE_PAIRS))}."
                ),
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        before = self._feature_tree_count
        self._feature_tree_count += 1
        after = self._feature_tree_count

        plane_a, plane_b = _AXIS_PLANE_PAIRS[key]

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "reference": key,
                "planes": [plane_a, plane_b],
                "features_before": before,
                "features_after": after,
            },
            execution_time=self._delays["feature_operation"],
        )

    #: Built-in planes every SolidWorks part starts with. Combined with
    #: ``self._reference_planes`` (planes created via create_reference_plane)
    #: this is the set of plane names ``mirror_feature`` will accept.
    _BUILTIN_PLANES = frozenset({"Front Plane", "Top Plane", "Right Plane"})

    async def mirror_feature(
        self,
        features: list[str],
        mirror_plane: str,
        merge: bool = True,
        mirror_bodies: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock mirroring solid bodies or features about a plane.

        The mock has no geometry engine, so it cannot measure a real volume
        change - it mirrors the live adapter's refusals instead of
        fabricating a result it cannot know. An empty source list or plane
        name is rejected outright (matching ``_mirror_feature_impl`` in
        ``solidworks/features.py`` verbatim), and a source or plane name
        that was never created in this session is rejected the same way
        ``_select_named_feature`` / ``_select_reference_entity`` would fail
        to select it there.

        On success, the tracked ``self._mirror_volume`` figure (seeded at
        the live-measured 1819569.1 mm^3 wing volume) is doubled, matching
        the ~2.0 ratio a correct mirror produces (measured live: 1.998528
        for a lofted wing, exactly 2.0 for a boss whose sketch sits on the
        plane).

        Args:
            features (list[str]): Body or feature names to mirror.
            mirror_plane (str): Plane name to mirror about.
            merge (bool): Merge the mirrored result with the original. Defaults to True.
            mirror_bodies (bool): Mirror whole bodies rather than features. Defaults to True.

        Returns:
            AdapterResult[dict[str, Any]]: The mirror feature's name, inputs
            and volume before/after, or error.
        """
        names = [n for n in (features or []) if n]
        if not names:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="mirror_feature requires at least one body or feature name",
            )
        if not mirror_plane:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="mirror_feature requires a mirror plane name",
            )

        known_sources = {feature.name for feature in self._features.values()} | set(
            self._components
        )
        for name in names:
            if name not in known_sources:
                kind = "body" if mirror_bodies else "feature"
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=f"Failed to select {kind} to mirror: {name}",
                )

        known_planes = self._BUILTIN_PLANES | set(self._reference_planes)
        if mirror_plane not in known_planes:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Failed to select mirror plane: {mirror_plane}",
            )

        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1

        volume_before = self._mirror_volume
        volume_after = volume_before * 2
        self._mirror_volume = volume_after

        self._feature_tree_count += 1
        feature_name = f"Mirror{self._feature_tree_count}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": feature_name,
                "mirrored": names,
                "mirror_plane": mirror_plane,
                "merge": bool(merge),
                "mirror_bodies": bool(mirror_bodies),
                "volume_before": volume_before,
                "volume_after": volume_after,
                "volume_ratio": round(volume_after / volume_before, 6),
            },
            execution_time=self._delays["feature_operation"],
        )
