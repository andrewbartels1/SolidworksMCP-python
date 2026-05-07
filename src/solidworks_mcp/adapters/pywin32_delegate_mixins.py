"""Delegation mixins for PyWin32 adapter domain operations.

These mixins keep the main ``PyWin32Adapter`` focused on COM/session orchestration
while routing domain operations to extracted modules.
"""

from __future__ import annotations

from typing import Any

from . import pywin32_feature_ops, pywin32_io_ops, pywin32_sketch_ops
from .base import (
    AdapterResult,
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SolidWorksFeature,
    SolidWorksModel,
    SweepParameters,
)


class PyWin32FeatureOpsMixin:
    """Delegate feature-creation methods to ``pywin32_feature_ops``."""

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create an extrusion feature.

        Args:
            params: Extrusion parameters for the feature operation.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.create_extrusion(self, params)

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a revolve feature.

        Args:
            params: Revolve parameters for the feature operation.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.create_revolve(self, params)

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a sweep feature.

        Args:
            params: Sweep parameters for the feature operation.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.create_sweep(self, params)

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a loft feature.

        Args:
            params: Loft parameters for the feature operation.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.create_loft(self, params)

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a cut-extrude feature.

        Args:
            params: Extrusion parameters used for subtractive cut.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.create_cut_extrude(self, params)

    async def add_fillet(
        self, radius: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a fillet feature.

        Args:
            radius: Fillet radius in millimetres.
            edge_names: Named edges to fillet.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.add_fillet(self, radius, edge_names)

    async def add_chamfer(
        self, distance: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a chamfer feature.

        Args:
            distance: Chamfer distance in millimetres.
            edge_names: Named edges to chamfer.

        Returns:
            AdapterResult[SolidWorksFeature]: Created feature metadata on success.
        """
        return pywin32_feature_ops.add_chamfer(self, distance, edge_names)


class PyWin32SketchOpsMixin:
    """Delegate sketch methods to ``pywin32_sketch_ops``."""

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create a new sketch on a specified plane.

        Args:
            plane: Reference plane identifier.

        Returns:
            AdapterResult[str]: Registered sketch identifier.
        """
        return pywin32_sketch_ops.create_sketch(self, plane)

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a line to the active sketch.

        Args:
            x1: Start X in millimetres.
            y1: Start Y in millimetres.
            x2: End X in millimetres.
            y2: End Y in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_line(self, x1, y1, x2, y2)

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add a circle to the active sketch.

        Args:
            center_x: Circle center X in millimetres.
            center_y: Circle center Y in millimetres.
            radius: Circle radius in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_circle(self, center_x, center_y, radius)

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a rectangle to the active sketch.

        Args:
            x1: Corner 1 X in millimetres.
            y1: Corner 1 Y in millimetres.
            x2: Corner 2 X in millimetres.
            y2: Corner 2 Y in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_rectangle(self, x1, y1, x2, y2)

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> AdapterResult[str]:
        """Add an arc to the active sketch.

        Args:
            center_x: Arc center X in millimetres.
            center_y: Arc center Y in millimetres.
            start_x: Start point X in millimetres.
            start_y: Start point Y in millimetres.
            end_x: End point X in millimetres.
            end_y: End point Y in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_arc(
            self, center_x, center_y, start_x, start_y, end_x, end_y
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Add a spline to the active sketch.

        Args:
            points: Ordered spline points in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_spline(self, points)

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a centerline to the active sketch.

        Args:
            x1: Start X in millimetres.
            y1: Start Y in millimetres.
            x2: End X in millimetres.
            y2: End Y in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_centerline(self, x1, y1, x2, y2)

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Add a regular polygon to the active sketch.

        Args:
            center_x: Polygon center X in millimetres.
            center_y: Polygon center Y in millimetres.
            radius: Polygon radius in millimetres.
            sides: Number of polygon sides.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_polygon(self, center_x, center_y, radius, sides)

    async def add_ellipse(
        self, center_x: float, center_y: float, major_axis: float, minor_axis: float
    ) -> AdapterResult[str]:
        """Add an ellipse to the active sketch.

        Args:
            center_x: Ellipse center X in millimetres.
            center_y: Ellipse center Y in millimetres.
            major_axis: Major-axis length in millimetres.
            minor_axis: Minor-axis length in millimetres.

        Returns:
            AdapterResult[str]: Registered sketch entity identifier.
        """
        return pywin32_sketch_ops.add_ellipse(
            self, center_x, center_y, major_axis, minor_axis
        )

    async def add_sketch_constraint(
        self, entity1: str, entity2: str | None, relation_type: str
    ) -> AdapterResult[str]:
        """Add a geometric relation between sketch entities.

        Args:
            entity1: Primary sketch entity identifier.
            entity2: Optional secondary sketch entity identifier.
            relation_type: SolidWorks relation kind.

        Returns:
            AdapterResult[str]: Registered relation identifier.
        """
        return pywin32_sketch_ops.add_sketch_constraint(
            self, entity1, entity2, relation_type
        )

    async def add_sketch_dimension(
        self, entity1: str, entity2: str | None, dimension_type: str, value: float
    ) -> AdapterResult[str]:
        """Add a sketch dimension to selected entities.

        Args:
            entity1: Primary sketch entity identifier.
            entity2: Optional secondary sketch entity identifier.
            dimension_type: Dimension kind (e.g., linear, angular).
            value: Dimension value in millimetres (or degrees for angular).

        Returns:
            AdapterResult[str]: Registered dimension identifier.
        """
        return pywin32_sketch_ops.add_sketch_dimension(
            self, entity1, entity2, dimension_type, value
        )

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a linear sketch pattern.

        Args:
            entities: Sketch entity identifiers to pattern.
            direction_x: Pattern direction vector X component.
            direction_y: Pattern direction vector Y component.
            spacing: Spacing between instances in millimetres.
            count: Number of instances.

        Returns:
            AdapterResult[str]: Registered pattern identifier.
        """
        return pywin32_sketch_ops.sketch_linear_pattern(
            self, entities, direction_x, direction_y, spacing, count
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        center_x: float,
        center_y: float,
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        """Create a circular sketch pattern.

        Args:
            entities: Sketch entity identifiers to pattern.
            center_x: Pattern center X in millimetres.
            center_y: Pattern center Y in millimetres.
            angle: Sweep angle in degrees.
            count: Number of instances.

        Returns:
            AdapterResult[str]: Registered pattern identifier.
        """
        return pywin32_sketch_ops.sketch_circular_pattern(
            self, entities, center_x, center_y, angle, count
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Mirror sketch entities about a centerline.

        Args:
            entities: Sketch entity identifiers to mirror.
            mirror_line: Centerline entity identifier.

        Returns:
            AdapterResult[str]: Registered mirror-operation identifier.
        """
        return pywin32_sketch_ops.sketch_mirror(self, entities, mirror_line)

    async def sketch_offset(
        self, entities: list[str], offset_distance: float, reverse_direction: bool
    ) -> AdapterResult[str]:
        """Offset sketch entities.

        Args:
            entities: Sketch entity identifiers to offset.
            offset_distance: Offset distance in millimetres.
            reverse_direction: Whether to offset in reverse direction.

        Returns:
            AdapterResult[str]: Registered offset-operation identifier.
        """
        return pywin32_sketch_ops.sketch_offset(
            self, entities, offset_distance, reverse_direction
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit the current sketch editing mode.

        Returns:
            AdapterResult[None]: Success/warning/error status.
        """
        return pywin32_sketch_ops.exit_sketch(self)

    async def check_sketch_fully_defined(
        self, sketch_name: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Check whether a sketch is fully defined.

        Args:
            sketch_name: Optional sketch name. When omitted, the adapter decides
                the most relevant active/last sketch to inspect.

        Returns:
            AdapterResult[dict[str, Any]]: Sketch-definition status details.
        """
        return pywin32_sketch_ops.check_sketch_fully_defined(self, sketch_name)


class PyWin32IOOpsMixin:
    """Delegate model I/O and query methods to ``pywin32_io_ops``."""

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export the active model to a target file.

        Args:
            file_path: Destination file path.
            format_type: Export format key (e.g., stl, step, iges).

        Returns:
            AdapterResult[None]: Success/error status.
        """
        return pywin32_io_ops.export_file(self, file_path, format_type)

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Read a model dimension value.

        Args:
            name: Fully-qualified SolidWorks dimension name.

        Returns:
            AdapterResult[float]: Dimension value in millimetres.
        """
        return pywin32_io_ops.get_dimension(self, name)

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set a model dimension value.

        Args:
            name: Fully-qualified SolidWorks dimension name.
            value: New value in millimetres.

        Returns:
            AdapterResult[None]: Success/error status.
        """
        return pywin32_io_ops.set_dimension(self, name, value)

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save the active model.

        Args:
            file_path: Optional explicit destination path.

        Returns:
            AdapterResult[None]: Success/error status.
        """
        return pywin32_io_ops.save_file(self, file_path)

    async def rebuild_model(self) -> AdapterResult[None]:
        """Rebuild the active model.

        Returns:
            AdapterResult[None]: Success/error status.
        """
        return pywin32_io_ops.rebuild_model(self)

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Return metadata for the active model.

        Returns:
            AdapterResult[dict[str, Any]]: Model metadata payload.
        """
        return pywin32_io_ops.get_model_info(self)

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List feature-tree rows for the active model.

        Args:
            include_suppressed: Whether suppressed features are included.

        Returns:
            AdapterResult[list[dict[str, Any]]]: Feature-tree payload.
        """
        return pywin32_io_ops.list_features(self, include_suppressed)

    async def select_feature(self, feature_name: str) -> AdapterResult[dict[str, Any]]:
        """Select and highlight a named feature.

        Args:
            feature_name: Feature name to select.

        Returns:
            AdapterResult[dict[str, Any]]: Selection result payload.
        """
        return pywin32_io_ops.select_feature(self, feature_name)

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List configuration names for the active model.

        Returns:
            AdapterResult[list[str]]: Configuration names.
        """
        return pywin32_io_ops.list_configurations(self)

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model file.

        Args:
            file_path: Path to the SolidWorks document.

        Returns:
            AdapterResult[SolidWorksModel]: Opened model metadata.
        """
        return pywin32_io_ops.open_model(self, file_path)

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close the current model.

        Args:
            save: Whether to save before close.

        Returns:
            AdapterResult[None]: Success/error status.
        """
        return pywin32_io_ops.close_model(self, save)

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new part document.

        Args:
            name: Optional document label.
            units: Optional unit-system hint.

        Returns:
            AdapterResult[SolidWorksModel]: Created model metadata.
        """
        return pywin32_io_ops.create_part(self, name, units)

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new assembly document.

        Args:
            name: Optional document label.

        Returns:
            AdapterResult[SolidWorksModel]: Created model metadata.
        """
        return pywin32_io_ops.create_assembly(self, name)

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new drawing document.

        Args:
            name: Optional document label.

        Returns:
            AdapterResult[SolidWorksModel]: Created model metadata.
        """
        return pywin32_io_ops.create_drawing(self, name)
