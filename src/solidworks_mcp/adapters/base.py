"""
Base adapter interface for SolidWorks integration.

Defines the common interface that all SolidWorks adapters must implement,
following the adapter pattern from the original TypeScript implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class AdapterHealth(BaseModel):
    """Health status information for adapters."""

    healthy: bool
    last_check: datetime
    error_count: int
    success_count: int
    average_response_time: float
    connection_status: str
    metrics: dict[str, Any] | None = None

    def __getitem__(self, key: str) -> Any:
        """Execute getitem.
        
        Args:
            key (str): Describe key.
        
        Returns:
            Any: Describe the returned value.
        
        """
        if key == "status":
            return "healthy" if self.healthy else "unhealthy"
        if key == "connected":
            return self.connection_status == "connected"
        if key == "adapter_type":
            return (self.metrics or {}).get("adapter_type")
        if key == "version":
            return (self.metrics or {}).get("version", "mock-1.0")
        if key == "uptime":
            return (self.metrics or {}).get("uptime", 0.0)
        return self.model_dump().get(key)

    def __contains__(self, key: str) -> bool:
        """Execute contains.
        
        Args:
            key (str): Describe key.
        
        Returns:
            bool: Describe the returned value.
        
        """
        legacy_keys = {"status", "connected", "adapter_type", "version", "uptime"}
        if key in legacy_keys:
            return True
        return key in self.model_dump()


class AdapterResultStatus(str, Enum):
    """Result status for adapter operations."""

    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    TIMEOUT = "timeout"


@dataclass
class AdapterResult(Generic[T]):
    """Result wrapper for adapter operations."""

    status: AdapterResultStatus
    data: T | None = None
    error: str | None = None
    execution_time: float | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_success(self) -> bool:
        """Check if operation was successful."""
        return self.status == AdapterResultStatus.SUCCESS

    @property
    def is_error(self) -> bool:
        """Check if operation had an error."""
        return self.status == AdapterResultStatus.ERROR


# SolidWorks data models
class SolidWorksModel(BaseModel):
    """SolidWorks model information."""

    path: str
    name: str
    type: str  # "Part", "Assembly", "Drawing"
    is_active: bool
    configuration: str | None = None
    properties: dict[str, Any] | None = None

    def __getitem__(self, key: str) -> Any:
        """Execute getitem.
        
        Args:
            key (str): Describe key.
        
        Returns:
            Any: Describe the returned value.
        
        """
        if key == "title":
            return self.name
        if key == "units":
            return (self.properties or {}).get("units")
        return self.model_dump().get(key)


class SolidWorksFeature(BaseModel):
    """SolidWorks feature information."""

    name: str
    type: str
    id: str | None = None
    parent: str | None = None
    properties: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None

    def __getitem__(self, key: str) -> Any:
        """Execute getitem.
        
        Args:
            key (str): Describe key.
        
        Returns:
            Any: Describe the returned value.
        
        """
        if self.parameters and key in self.parameters:
            return self.parameters.get(key)
        return self.model_dump().get(key)


class ExtrusionParameters(BaseModel):
    """Parameters for extrusion operations."""

    depth: float
    draft_angle: float = 0.0
    reverse_direction: bool = False
    both_directions: bool = False
    thin_feature: bool = False
    thin_thickness: float | None = None
    end_condition: str = "Blind"
    up_to_surface: str | None = None
    merge_result: bool = True
    feature_scope: bool = False
    auto_select: bool = True


class RevolveParameters(BaseModel):
    """Parameters for revolve operations."""

    angle: float
    reverse_direction: bool = False
    both_directions: bool = False
    thin_feature: bool = False
    thin_thickness: float | None = None
    merge_result: bool = True


class SweepParameters(BaseModel):
    """Parameters for sweep operations."""

    path: str
    twist_along_path: bool = False
    twist_angle: float = 0.0
    merge_result: bool = True


class LoftParameters(BaseModel):
    """Parameters for loft operations."""

    profiles: list[str]
    guide_curves: list[str] | None = None
    start_tangent: str | None = None
    end_tangent: str | None = None
    merge_result: bool = True


class MassProperties(BaseModel):
    """Mass properties information."""

    volume: float
    surface_area: float
    mass: float
    center_of_mass: list[float]  # [x, y, z]
    moments_of_inertia: dict[str, float]
    principal_axes: dict[str, list[float]] | None = None


class SolidWorksAdapter(ABC):
    """Base adapter interface for SolidWorks integration."""

    def __init__(self, config: object | None = None):
        """Initialize adapter with configuration."""
        if config is None:
            normalized_config: dict[str, Any] = {}
        elif isinstance(config, Mapping):
            normalized_config = dict(config)
        elif hasattr(config, "model_dump"):
            normalized_config = dict(getattr(config, "model_dump")())
        else:
            normalized_config = {}

        # Preserve original config object for compatibility with tests and
        # call sites that compare object identity/equality.
        self.config = config
        # Keep a normalized mapping for adapter internals.
        self.config_dict = normalized_config
        self._metrics = {
            "operations_count": 0,
            "errors_count": 0,
            "average_response_time": 0.0,
        }

    # Connection Management
    @abstractmethod
    async def connect(self) -> None:
        """Connect to SolidWorks application."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from SolidWorks application."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to SolidWorks."""
        pass

    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """Get adapter health status."""
        pass

    # Model Operations
    @abstractmethod
    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model (part, assembly, or drawing)."""
        pass

    @abstractmethod
    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close the current model."""
        pass

    async def save_file(self, file_path: str | None = None) -> AdapterResult[Any]:
        """Save the active model to the existing path or the provided path."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="save_file is not implemented by this adapter",
        )

    @abstractmethod
    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Get metadata for the active model."""
        pass

    @abstractmethod
    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List model features from the feature tree."""
        pass

    @abstractmethod
    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List configuration names for the active model."""
        pass

    @abstractmethod
    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new part document."""
        pass

    @abstractmethod
    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new assembly document."""
        pass

    @abstractmethod
    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new drawing document."""
        pass

    # Feature Operations
    @abstractmethod
    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create an extrusion feature."""
        pass

    @abstractmethod
    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a revolve feature."""
        pass

    @abstractmethod
    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a sweep feature."""
        pass

    @abstractmethod
    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a loft feature."""
        pass

    # Sketch Operations
    @abstractmethod
    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create a new sketch on the specified plane."""
        pass

    @abstractmethod
    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a line to the current sketch."""
        pass

    @abstractmethod
    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add a circle to the current sketch."""
        pass

    @abstractmethod
    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a rectangle to the current sketch."""
        pass

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> AdapterResult[str]:
        """Add an arc to the current sketch."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_arc is not implemented by this adapter",
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Add a spline through the provided points."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_spline is not implemented by this adapter",
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a centerline to the current sketch."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_centerline is not implemented by this adapter",
        )

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Add a regular polygon to the current sketch."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_polygon is not implemented by this adapter",
        )

    async def add_ellipse(
        self,
        center_x: float,
        center_y: float,
        major_axis: float,
        minor_axis: float,
    ) -> AdapterResult[str]:
        """Add an ellipse to the current sketch."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_ellipse is not implemented by this adapter",
        )

    async def add_sketch_constraint(
        self, entity1: str, entity2: str | None, relation_type: str
    ) -> AdapterResult[str]:
        """Apply a geometric constraint between sketch entities."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_sketch_constraint is not implemented by this adapter",
        )

    async def add_sketch_dimension(
        self,
        entity1: str,
        entity2: str | None,
        dimension_type: str,
        value: float,
    ) -> AdapterResult[str]:
        """Add a sketch dimension."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="add_sketch_dimension is not implemented by this adapter",
        )

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a linear pattern of sketch entities."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="sketch_linear_pattern is not implemented by this adapter",
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        center_x: float,
        center_y: float,
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a circular pattern of sketch entities."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="sketch_circular_pattern is not implemented by this adapter",
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Mirror sketch entities about a mirror line."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="sketch_mirror is not implemented by this adapter",
        )

    async def sketch_offset(
        self,
        entities: list[str],
        offset_distance: float,
        reverse_direction: bool,
    ) -> AdapterResult[str]:
        """Offset sketch entities."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="sketch_offset is not implemented by this adapter",
        )

    async def add_sketch_circle(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        construction: bool = False,
    ) -> AdapterResult[str]:
        """Alias for add_circle used by some tool flows."""
        return await self.add_circle(center_x, center_y, radius)

    async def create_cut(self, sketch_name: str, depth: float) -> AdapterResult[str]:
        """Create a cut feature from an existing sketch."""
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="create_cut is not implemented by this adapter",
        )

    @abstractmethod
    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit sketch editing mode."""
        pass

    # Analysis Operations
    @abstractmethod
    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties of the current model."""
        pass

    # Export Operations
    @abstractmethod
    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export the current model to a file."""
        pass

    # Dimension Operations
    @abstractmethod
    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get the value of a dimension."""
        pass

    @abstractmethod
    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set the value of a dimension."""
        pass

    # Utility Methods
    def update_metrics(self, operation_time: float, success: bool) -> None:
        """Update adapter metrics."""
        self._metrics["operations_count"] += 1
        if not success:
            self._metrics["errors_count"] += 1

        # Update average response time
        current_avg = self._metrics["average_response_time"]
        count = self._metrics["operations_count"]
        self._metrics["average_response_time"] = (
            current_avg * (count - 1) + operation_time
        ) / count

    def get_metrics(self) -> dict[str, Any]:
        """Get adapter metrics."""
        return self._metrics.copy()
