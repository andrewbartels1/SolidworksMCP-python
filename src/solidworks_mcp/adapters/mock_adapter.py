"""
Mock SolidWorks adapter for testing and development.

This adapter simulates SolidWorks operations for testing on non-Windows
platforms or when SolidWorks is not available.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..exceptions import SolidWorksMCPError, SolidWorksOperationError
from .base import (
    SolidWorksAdapter,
    AdapterResult,
    AdapterHealth,
    AdapterResultStatus,
    SolidWorksModel,
    SolidWorksFeature,
    ExtrusionParameters,
    RevolveParameters,
    SweepParameters,
    LoftParameters,
    MassProperties,
)


class _BoolCallable:
    """Compatibility shim that behaves as both bool and callable."""

    def __init__(self, getter: Callable[[], bool]) -> None:
        """Initialize this object.
        
        Args:
            getter (Callable[[], bool]): Describe getter.
        
        """
        self._getter = getter

    def __call__(self) -> bool:
        """Execute call.
        
        Returns:
            bool: Describe the returned value.
        
        """
        return bool(self._getter())

    def __bool__(self) -> bool:
        """Execute bool.
        
        Returns:
            bool: Describe the returned value.
        
        """
        return bool(self._getter())


class MockSolidWorksAdapter(SolidWorksAdapter):
    """Mock adapter that simulates SolidWorks operations."""

    def __init__(self, config: object | None = None) -> None:
        """Initialize this object.
        
        Args:
            config (object | None): Describe config.
        
        """
        super().__init__(config)
        cfg: dict[str, Any] = dict(self.config_dict)
        self._connected = False
        self._current_model: SolidWorksModel | None = None
        self._models: dict[str, SolidWorksModel] = {}
        self._features: dict[str, SolidWorksFeature] = {}
        self._sketches: dict[str, str] = {}
        self._current_sketch: str | None = None
        self._dimensions: dict[str, float] = {}
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
        """Execute getattribute.
        
        Args:
            name (str): Describe name.
        
        Returns:
            Any: Describe the returned value.
        
        """
        if name == "is_connected":
            return object.__getattribute__(self, "_is_connected_proxy")
        return object.__getattribute__(self, name)

    async def connect(self) -> None:
        """Mock connection to SolidWorks."""
        await asyncio.sleep(self._delays["connect"])
        self._connected = True

        # Initialize some sample data
        self._dimensions = {
            "D1@Sketch1": 10.0,
            "D2@Sketch1": 20.0,
            "D1@Boss-Extrude1": 50.0,
        }

    async def disconnect(self) -> None:
        """Mock disconnection from SolidWorks."""
        self._connected = False
        self._current_model = None
        self._models.clear()
        self._features.clear()
        self._sketches.clear()
        self._current_sketch = None

    def is_connected(self) -> bool:
        """Check if mock connection is active."""
        return self._connected

    async def health_check(self) -> AdapterHealth:
        """Get mock health status."""
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
        """Mock opening a SolidWorks model."""
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
        """Mock closing the current model."""
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
        """Mock metadata for the currently active model."""
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
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        """Mock feature tree listing for the active model."""
        if not self._current_model:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )

        await asyncio.sleep(self._delays["feature_operation"] / 2)
        self._operation_count += 1

        # Seed realistic feature names for empty mock state.
        if not self._features:
            seeded = [
                {"name": "Origin", "type": "OriginProfileFeature", "suppressed": False},
                {"name": "Front Plane", "type": "RefPlane", "suppressed": False},
                {"name": "Right Plane", "type": "RefPlane", "suppressed": False},
                {"name": "Top Plane", "type": "RefPlane", "suppressed": False},
                {"name": "Sketch1", "type": "ProfileFeature", "suppressed": False},
            ]
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
            }
            if include_suppressed or not row["suppressed"]:
                feature_rows.append(row)

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature_rows,
            execution_time=self._delays["feature_operation"] / 2,
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """Mock configuration listing for the active model."""
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
        """Mock creating a new part."""
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
        """Mock creating a new assembly."""
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
        """Mock creating a new drawing."""
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
        """Mock creating an extrusion feature."""
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
        """Mock creating a revolve feature."""
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
        """Mock creating a sweep feature."""
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
        """Mock creating a loft feature."""
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

    async def create_sketch(self, plane: str) -> AdapterResult[dict[str, Any]]:
        """Mock creating a sketch."""
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
            data={"id": sketch_id, "name": sketch_id, "sketch_name": sketch_id, "plane": plane},
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
        """Legacy compatibility wrapper around add_line."""
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
        """Legacy compatibility save operation for tests."""
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
        """Mock adding a line to sketch."""
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        line_id = f"Line{random.randint(1000, 9999)}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=line_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Mock adding a construction centerline to sketch."""
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        centerline_id = f"Centerline{random.randint(1000, 9999)}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=centerline_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Mock adding a circle to sketch."""
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"] / 2)
        self._operation_count += 1

        circle_id = f"Circle{random.randint(1000, 9999)}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=circle_id,
            execution_time=self._delays["sketch_operation"] / 2,
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Mock adding a rectangle to sketch."""
        if not self._current_sketch:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        await asyncio.sleep(self._delays["sketch_operation"])
        self._operation_count += 1

        rect_id = f"Rectangle{random.randint(1000, 9999)}"

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=rect_id,
            execution_time=self._delays["sketch_operation"],
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Mock exiting sketch mode."""
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

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Mock getting mass properties."""
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

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Mock exporting a file."""
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
        }

        format_lower = format_type.lower()
        delay = export_times.get(format_lower, 1.0)

        await asyncio.sleep(delay)
        self._operation_count += 1

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=None,
            execution_time=delay,
            metadata={"exported_format": format_type, "file_path": file_path},
        )

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Mock getting a dimension value."""
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
        """Mock setting a dimension value."""
        await asyncio.sleep(0.1)  # Fast operation
        self._operation_count += 1

        self._dimensions[name] = value

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=None, execution_time=0.1
        )
