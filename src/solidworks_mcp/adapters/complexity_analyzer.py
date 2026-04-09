"""Complexity analysis for routing operations between COM and VBA paths."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class OperationProfile:
    """Complexity profile metadata for an operation.

    Attributes:
        name: Operation name.
        base_complexity: Baseline complexity value in range ``[0.0, 1.0]``.
        vba_preferred: Whether operation naturally leans toward VBA path.
    """

    name: str
    base_complexity: float
    vba_preferred: bool = False


class RoutingDecision(BaseModel):
    """Complexity-based routing decision."""

    operation: str
    parameter_count: int
    complexity_score: float
    prefer_vba: bool
    reason: str


class ComplexityAnalyzer:
    """Analyze operation complexity and recommend COM or VBA execution path."""

    def __init__(
        self,
        parameter_threshold: int = 12,
        score_threshold: float = 0.6,
    ) -> None:
        """Initialize analyzer state.

        Args:
            parameter_threshold: Hard threshold where parameter count indicates
                VBA preference.
            score_threshold: Score threshold in range ``[0.0, 1.0]`` used for
                route recommendation.
        """
        self._parameter_threshold = max(parameter_threshold, 1)
        self._score_threshold = max(min(score_threshold, 1.0), 0.1)
        self._profiles: dict[str, OperationProfile] = self._default_profiles()
        self._history: dict[str, dict[str, int]] = {}

    def analyze(self, operation: str, payload: object) -> RoutingDecision:
        """Produce a routing recommendation for an operation call.

        Args:
            operation: Adapter operation name.
            payload: Operation payload or arguments.

        Returns:
            Structured routing decision.
        """
        profile = self._profiles.get(
            operation,
            OperationProfile(name=operation, base_complexity=0.2, vba_preferred=False),
        )
        parameter_count = self._count_parameters(payload)

        parameter_component = min(
            parameter_count / float(self._parameter_threshold), 1.0
        )
        history_component = self._history_bias(operation)
        complexity_score = min(
            1.0,
            (parameter_component * 0.45)
            + (profile.base_complexity * 0.40)
            + (history_component * 0.15),
        )

        prefer_vba = (
            parameter_count > self._parameter_threshold
            or profile.vba_preferred
            or complexity_score >= self._score_threshold
        )

        reason = (
            "parameter threshold exceeded"
            if parameter_count > self._parameter_threshold
            else "profile prefers VBA"
            if profile.vba_preferred
            else "complexity score exceeded threshold"
            if complexity_score >= self._score_threshold
            else "COM path preferred"
        )

        return RoutingDecision(
            operation=operation,
            parameter_count=parameter_count,
            complexity_score=complexity_score,
            prefer_vba=prefer_vba,
            reason=reason,
        )

    def record_result(self, operation: str, route: str, success: bool) -> None:
        """Record operation outcome for future routing influence.

        Args:
            operation: Operation name.
            route: Executed route identifier (``"com"`` or ``"vba"``).
            success: Whether execution succeeded.
        """
        history = self._history.setdefault(
            operation,
            {
                "com_success": 0,
                "com_failure": 0,
                "vba_success": 0,
                "vba_failure": 0,
            },
        )
        key = f"{route}_{'success' if success else 'failure'}"
        if key in history:
            history[key] += 1

    def _history_bias(self, operation: str) -> float:
        """Compute historical bias toward VBA based on COM reliability."""
        history = self._history.get(operation)
        if history is None:
            return 0.0

        com_success = history.get("com_success", 0)
        com_failure = history.get("com_failure", 0)
        com_total = com_success + com_failure
        if com_total == 0:
            return 0.0

        failure_ratio = com_failure / float(com_total)
        return max(min(failure_ratio, 1.0), 0.0)

    def _count_parameters(self, payload: object) -> int:
        """Count meaningful parameters in payload recursively."""
        if payload is None:
            return 0

        if isinstance(payload, BaseModel):
            return self._count_parameters(payload.model_dump(exclude_none=True))

        if isinstance(payload, Mapping):
            total = 0
            for value in payload.values():
                total += self._count_parameters(value)
            return max(total, len(payload))

        if isinstance(payload, (list, tuple, set)):
            return sum(self._count_parameters(item) for item in payload)

        return 1

    def _default_profiles(self) -> dict[str, OperationProfile]:
        """Return default complexity profiles for high-impact operations."""
        return {
            # Modeling operations - likely to benefit from VBA routing
            "create_extrusion": OperationProfile(
                name="create_extrusion", base_complexity=0.55, vba_preferred=False
            ),
            "create_revolve": OperationProfile(
                name="create_revolve", base_complexity=0.50, vba_preferred=False
            ),
            "create_sweep": OperationProfile(
                name="create_sweep", base_complexity=0.65, vba_preferred=True
            ),
            "create_loft": OperationProfile(
                name="create_loft", base_complexity=0.70, vba_preferred=True
            ),
            "create_assembly": OperationProfile(
                name="create_assembly", base_complexity=0.45, vba_preferred=False
            ),
            "create_part": OperationProfile(
                name="create_part", base_complexity=0.30, vba_preferred=False
            ),
            "create_drawing": OperationProfile(
                name="create_drawing", base_complexity=0.50, vba_preferred=False
            ),
            # Sketching operations - moderate complexity
            "create_sketch": OperationProfile(
                name="create_sketch", base_complexity=0.25, vba_preferred=False
            ),
            "add_circle": OperationProfile(
                name="add_circle", base_complexity=0.20, vba_preferred=False
            ),
            "add_rectangle": OperationProfile(
                name="add_rectangle", base_complexity=0.20, vba_preferred=False
            ),
            "add_line": OperationProfile(
                name="add_line", base_complexity=0.15, vba_preferred=False
            ),
            "add_arc": OperationProfile(
                name="add_arc", base_complexity=0.35, vba_preferred=False
            ),
            "add_spline": OperationProfile(
                name="add_spline", base_complexity=0.50, vba_preferred=True
            ),
            "add_polygon": OperationProfile(
                name="add_polygon", base_complexity=0.30, vba_preferred=False
            ),
            "add_sketch_constraint": OperationProfile(
                name="add_sketch_constraint", base_complexity=0.40, vba_preferred=False
            ),
            "add_sketch_dimension": OperationProfile(
                name="add_sketch_dimension", base_complexity=0.30, vba_preferred=False
            ),
            # Assembly operations
            "insert_component": OperationProfile(
                name="insert_component", base_complexity=0.40, vba_preferred=False
            ),
            "add_mate": OperationProfile(
                name="add_mate", base_complexity=0.55, vba_preferred=False
            ),
            # Drawing operations
            "create_drawing_view": OperationProfile(
                name="create_drawing_view", base_complexity=0.45, vba_preferred=False
            ),
            "add_drawing_annotation": OperationProfile(
                name="add_drawing_annotation", base_complexity=0.35, vba_preferred=False
            ),
            "add_dimension": OperationProfile(
                name="add_dimension", base_complexity=0.40, vba_preferred=False
            ),
        }
