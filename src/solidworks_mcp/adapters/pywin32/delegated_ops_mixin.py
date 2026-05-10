"""Delegated operation mixin for PyWin32 adapter.

This mixin groups high-level adapter API methods that delegate to extracted
operation modules (`pywin32_io_ops`, `pywin32_sketch_ops`, and
`pywin32_feature_ops`) or to the feature-selection collaborator.

The goal is to keep the main adapter class focused on COM/session lifecycle and
shared state while preserving the exact public API surface.
"""

from __future__ import annotations

from typing import Any

from ..solidworks.features import (
    _add_chamfer_impl,
    _add_fillet_impl,
    _create_cut_extrude_impl,
    _create_extrusion_impl,
    _create_loft_impl,
    _create_revolve_impl,
    _create_sweep_impl,
)
from ..solidworks.sketch import (
    _add_arc_impl,
    _add_centerline_impl,
    _add_circle_impl,
    _add_ellipse_impl,
    _add_line_impl,
    _add_polygon_impl,
    _add_rectangle_impl,
    _add_sketch_constraint_impl,
    _add_sketch_dimension_impl,
    _add_spline_impl,
    _create_sketch_impl,
    _sketch_circular_pattern_impl,
    _sketch_linear_pattern_impl,
    _sketch_mirror_impl,
    _sketch_offset_impl,
)
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    LoftParameters,
    MassProperties,
    RevolveParameters,
    SolidWorksFeature,
    SolidWorksModel,
    SweepParameters,
)


class PyWin32DelegatedOpsMixin:
    """Provide grouped delegated operations for the PyWin32 adapter."""

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open a SolidWorks model file."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        return self._handle_com_operation(
            "open_model", self._model_io.open_model, self, file_path
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close the current active model, optionally saving first."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.WARNING, error="No active model to close"
            )
        model = self.currentModel
        app = self.swApp
        if model is None or app is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="SolidWorks application is not connected",
            )
        return self._handle_com_operation(
            "close_model", self._model_io.close_model, self, save
        )

    def _resolve_template_path(
        self, preferred_indices: list[int], extension: str
    ) -> str | None:
        """Resolve a SolidWorks template path from user preferences."""
        return self._model_io.resolve_template_path(self, preferred_indices, extension)

    def _read_model_title(self, model: Any) -> str:
        """Read model title regardless of COM exposing method or value."""
        return self._model_io.read_model_title(self, model)

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new part document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        return self._handle_com_operation(
            "create_part", self._model_io.create_part, self, name, units
        )

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new assembly document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        return self._handle_com_operation(
            "create_assembly", self._model_io.create_assembly, self, name
        )

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create a new drawing document."""
        if not self.is_connected():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        return self._handle_com_operation(
            "create_drawing", self._model_io.create_drawing, self, name
        )

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create an extrusion feature."""
        return _create_extrusion_impl(self, params)

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a revolve feature."""
        return _create_revolve_impl(self, params)

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a sweep feature."""
        return _create_sweep_impl(self, params)

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a loft feature."""
        return _create_loft_impl(self, params)

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create a cut extrude feature."""
        return _create_cut_extrude_impl(self, params)

    async def add_fillet(
        self, radius: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a fillet feature."""
        return _add_fillet_impl(self, radius, edge_names)

    async def add_chamfer(
        self, distance: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add a chamfer feature."""
        return _add_chamfer_impl(self, distance, edge_names)

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create a new sketch on the specified plane."""
        return _create_sketch_impl(self, plane)

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a line to the current sketch."""
        return _add_line_impl(self, x1, y1, x2, y2)

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add a circle to the current sketch."""
        return _add_circle_impl(self, center_x, center_y, radius)

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a rectangle to the current sketch."""
        return _add_rectangle_impl(self, x1, y1, x2, y2)

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
        return _add_arc_impl(
            self, center_x, center_y, start_x, start_y, end_x, end_y
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Add a spline to the current sketch."""
        return _add_spline_impl(self, points)

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add a centerline to the current sketch."""
        return _add_centerline_impl(self, x1, y1, x2, y2)

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Add a polygon to the current sketch."""
        return _add_polygon_impl(self, center_x, center_y, radius, sides)

    async def add_ellipse(
        self, center_x: float, center_y: float, major_axis: float, minor_axis: float
    ) -> AdapterResult[str]:
        """Add an ellipse to the current sketch."""
        return _add_ellipse_impl(
            self, center_x, center_y, major_axis, minor_axis
        )

    async def add_sketch_constraint(
        self, entity1: str, entity2: str | None, relation_type: str
    ) -> AdapterResult[str]:
        """Add a geometric constraint between sketch entities."""
        return _add_sketch_constraint_impl(
            self, entity1, entity2, relation_type
        )

    async def add_sketch_dimension(
        self, entity1: str, entity2: str | None, dimension_type: str, value: float
    ) -> AdapterResult[str]:
        """Add a dimension to sketch entities."""
        return _add_sketch_dimension_impl(
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
        """Create a linear pattern of sketch entities."""
        return _sketch_linear_pattern_impl(
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
        """Create a circular pattern of sketch entities."""
        return _sketch_circular_pattern_impl(
            self, entities, center_x, center_y, angle, count
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Mirror sketch entities about a centerline."""
        return _sketch_mirror_impl(self, entities, mirror_line)

    async def sketch_offset(
        self, entities: list[str], offset_distance: float, reverse_direction: bool
    ) -> AdapterResult[str]:
        """Create an offset of sketch entities."""
        return _sketch_offset_impl(
            self, entities, offset_distance, reverse_direction
        )

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties of the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "get_mass_properties", self._model_io.get_mass_properties, self
        )

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get the value of a dimension."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "get_dimension", self._model_io.get_dimension, self, name
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set the value of a dimension."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "set_dimension", self._model_io.set_dimension, self, name, value
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save the current model to current or specified path."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "save_file", self._model_io.save_file, self, file_path
        )

    async def rebuild_model(self) -> AdapterResult[None]:
        """Rebuild the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "rebuild_model", self._model_io.rebuild_model, self
        )

    async def get_model_info(self) -> AdapterResult[dict[str, Any]]:
        """Get information about the current model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "get_model_info", self._model_io.get_model_info, self
        )

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List features in the active model feature tree."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        return self._handle_com_operation(
            "list_features", self._feature_selector.list_features, include_suppressed
        )

    @staticmethod
    def _normalize_feature_name(raw_name: str | None) -> str:
        """Normalise a feature/component name for case-insensitive matching."""
        return str(raw_name or "").strip().strip('"').casefold()

    def _build_feature_candidate_names(
        self, feature_name: str, target_doc: Any
    ) -> list[str]:
        """Build candidate feature names (bare and qualified)."""
        return self._feature_selector.build_feature_candidate_names(
            feature_name, target_doc
        )

    def _try_select_by_extension(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        """Try feature selection via Extension.SelectByID2."""
        return self._feature_selector.try_select_by_extension(
            target_doc, candidate_names, feature_name
        )

    def _try_select_by_component(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        """Try feature selection via component-level selector methods."""
        return self._feature_selector.try_select_by_component(
            target_doc, candidate_names, feature_name
        )

    def _try_select_by_feature_tree(
        self,
        target_doc: Any,
        feature_name: str,
        candidate_names: list[str],
    ) -> dict[str, Any] | None:
        """Try feature selection by traversing the feature tree."""
        return self._feature_selector.try_select_by_feature_tree(
            target_doc, feature_name, candidate_names
        )

    async def select_feature(self, feature_name: str) -> AdapterResult[dict[str, Any]]:
        """Select a named feature in the active model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "select_feature", self._feature_selector.select_feature, feature_name
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List all configuration names in the active model."""
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        return self._handle_com_operation(
            "list_configurations", self._model_io.list_configurations, self
        )

    def _get_document_type(self) -> str:
        """Get active document type as Part/Assembly/Drawing/Unknown."""
        if not self.currentModel:
            return "Unknown"
        doc_type = self.currentModel.GetType()
        return {1: "Part", 2: "Assembly", 3: "Drawing"}.get(doc_type, "Unknown")
