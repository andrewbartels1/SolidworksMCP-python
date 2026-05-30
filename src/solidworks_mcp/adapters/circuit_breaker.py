"""Circuit breaker adapter for SolidWorks operations.

Implements the circuit breaker pattern to prevent cascading failures when SolidWorks
operations fail repeatedly.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

from loguru import logger

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

T = TypeVar("T")


def _to_input_dict(params: Any) -> dict[str, Any]:
    """Convert a Pydantic model or plain dict to a flat dict for SoC logging."""
    if hasattr(params, "model_dump"):
        return params.model_dump()
    return params if isinstance(params, dict) else {}


class CircuitState(Enum):
    """Circuit breaker states.

    Attributes:
        CLOSED (Any): The closed value.
        HALF_OPEN (Any): The half open value.
        OPEN (Any): The open value.
    """

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, blocking requests
    HALF_OPEN = "half_open"  # Testing if service is back


class CircuitBreakerAdapter(SolidWorksAdapter):
    """Circuit breaker wrapper for SolidWorks adapters.

    Args:
        adapter (SolidWorksAdapter | None): Adapter instance used for the operation.
                                            Defaults to None.
        failure_threshold (int): The failure threshold value. Defaults to 5.
        recovery_timeout (int): The recovery timeout value. Defaults to 60.
        half_open_max_calls (int): The half open max calls value. Defaults to 3.
        config (dict[str, object] | None): Configuration values for the operation. Defaults
                                           to None.

    Attributes:
        adapter (Any): The adapter value.
        failure_count (Any): The failure count value.
        failure_threshold (Any): The failure threshold value.
        half_open_calls (Any): The half open calls value.
        half_open_max_calls (Any): The half open max calls value.
        recovery_timeout (Any): The recovery timeout value.
        state (Any): The state value.
    """

    def __init__(
        self,
        adapter: SolidWorksAdapter | None = None,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        config: dict[str, object] | None = None,
    ) -> None:
        """Initialize the circuit breaker adapter.

        Args:
            adapter (SolidWorksAdapter | None): Adapter instance used for the operation.
                                                Defaults to None.
            failure_threshold (int): The failure threshold value. Defaults to 5.
            recovery_timeout (int): The recovery timeout value. Defaults to 60.
            half_open_max_calls (int): The half open max calls value. Defaults to 3.
            config (dict[str, object] | None): Configuration values for the operation. Defaults
                                               to None.

        Returns:
            None: None.
        """
        if adapter is None:
            from .mock_adapter import MockSolidWorksAdapter

            adapter = MockSolidWorksAdapter(config or {})
        super().__init__(config)
        self.adapter = adapter
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0

    async def _invoke_with_optional_args(
        self,
        method: Callable[..., Awaitable[T]],
        *args: object,
    ) -> T:
        """Invoke adapter method with args, retrying without args on signature mismatch.

        Args:
            method (Callable[..., Awaitable[T]]): The method value.
            *args (object): Additional positional arguments forwarded to the call.

        Returns:
            T: The result produced by the operation.
        """
        try:
            return await method(*args)
        except TypeError:
            return await method()

    def _should_allow_request(self) -> bool:
        """Check if request should be allowed through circuit breaker.

        Returns:
            bool: True if should allow request, otherwise False.
        """
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            # Check if enough time has passed to try again
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls

    def _record_success(self) -> None:
        """Record successful operation.

        Returns:
            None: None.
        """
        if self.state == CircuitState.HALF_OPEN:
            # Reset circuit breaker on success in half-open state
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _record_failure(self) -> None:
        """Record failed operation.

        Returns:
            None: None.
        """
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Go back to open state
            self.state = CircuitState.OPEN
        elif (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            # Open circuit breaker
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

    async def _execute_with_circuit_breaker(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[AdapterResult[T]]],
        input_dict: dict[str, Any] | None = None,
    ) -> AdapterResult[T]:
        """Build internal execute with circuit breaker.

        Args:
            operation_name (str): The operation name value.
            operation (Callable[[], Awaitable[AdapterResult[T]]]): Callable object executed by
                                                                   the helper.
            input_dict (dict | None): Input parameters for SoC logging. Defaults to None.

        Returns:
            AdapterResult[T]: The result produced by the operation.
        """
        if not self._should_allow_request():
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker is {self.state.value} for {operation_name}",
                metadata={"circuit_state": self.state.value},
            )

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1

        t0 = time.time()
        try:
            result = await operation()
            latency_ms = (time.time() - t0) * 1000.0
            if result.is_success:
                self._record_success()
            else:
                self._record_failure()
            self._soc_log(operation_name, input_dict, result, latency_ms)
            return result
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            self._record_failure()
            err_result: AdapterResult[T] = AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker caught exception in {operation_name}: {e}",
                metadata={"circuit_state": self.state.value},
            )
            self._soc_log(operation_name, input_dict, err_result, latency_ms)
            return err_result

    def _soc_log(
        self,
        tool_name: str,
        input_dict: dict[str, Any] | None,
        result: AdapterResult[Any],
        latency_ms: float,
    ) -> None:
        """Write a ToolCallRecord if soc_session_id is set."""
        if not self.soc_session_id or input_dict is None:
            return
        try:
            from solidworks_mcp.agents.history_db import insert_tool_call_record

            output_data: dict[str, Any] = {}
            if result.data is not None:
                try:
                    output_data = {"data": result.data}
                except Exception:
                    output_data = {"data": str(result.data)}

            insert_tool_call_record(
                session_id=self.soc_session_id,
                tool_name=tool_name,
                input_json=json.dumps(input_dict, default=str),
                output_json=json.dumps(output_data, default=str),
                success=result.is_success,
                latency_ms=latency_ms,
                db_path=self.soc_db_path,
            )
        except Exception as exc:
            logger.debug(
                f"[soc_log] failed to write ToolCallRecord for {tool_name}: {exc}"
            )

    # Adapter interface implementation

    async def connect(self) -> None:
        """Connect through circuit breaker.

        Returns:
            None: None.

        Raises:
            Exception: If the operation cannot be completed.
        """
        if not self._should_allow_request():
            raise Exception(f"Circuit breaker is {self.state.value}")

        try:
            await self.adapter.connect()
            self._record_success()
        except Exception:
            self._record_failure()
            raise

    async def disconnect(self) -> None:
        """Disconnect - always allowed.

        Returns:
            None: None.
        """
        await self.adapter.disconnect()

    def is_connected(self) -> bool:
        """Check connection status.

        Returns:
            bool: True if connected, otherwise False.
        """
        return self.adapter.is_connected()

    async def health_check(self) -> AdapterHealth:
        """Get health check with circuit breaker status.

        Returns:
            AdapterHealth: The result produced by the operation.
        """
        base_health = await self.adapter.health_check()
        if base_health.metrics is None:
            base_health.metrics = {}
        base_health.metrics["circuit_breaker"] = {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
        }

        # Consider circuit as unhealthy if open
        if self.state == CircuitState.OPEN:
            base_health.healthy = False
            base_health.connection_status = "circuit_breaker_open"

        return base_health

    # Model operations

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open model through circuit breaker.

        Args:
            file_path (str): Path to the target file.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "open_model",
            lambda: self.adapter.open_model(file_path),
            input_dict={"file_path": file_path},
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close model through circuit breaker.

        Args:
            save (bool): The save value. Defaults to False.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "close_model",
            lambda: self.adapter.close_model(save),
            input_dict={"save": save},
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save model through circuit breaker.

        Args:
            file_path (str | None): Path to the target file. Defaults to None.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "save_file",
            lambda: self.adapter.save_file(file_path),
            input_dict={"file_path": file_path},
        )

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Provide execute macro support for the circuit breaker adapter.

        Args:
            params (dict[str, Any]): The params value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "execute_macro",
            lambda: self.adapter.execute_macro(params),  # type: ignore[attr-defined]
            input_dict=params,
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create part through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.
            units (str | None): The units value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
            """
            if name is None and units is None:
                return await self.adapter.create_part()
            return await self._invoke_with_optional_args(
                self.adapter.create_part,
                name,
                units,
            )

        return await self._execute_with_circuit_breaker(
            "create_part", _op, input_dict={"name": name, "units": units}
        )

    async def call(self, operation: Callable[[], object | Awaitable[object]]) -> object:
        """Legacy call API used by tests.

        Args:
            operation (Callable[[], object | Awaitable[object]]): Callable object executed by
                                                                  the helper.

        Returns:
            object: The result produced by the operation.

        Raises:
            RuntimeError: If the operation cannot be completed.
            Exception: Circuit breaker is open.
        """
        if not self._should_allow_request():
            raise Exception("Circuit breaker is open")
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            raise RuntimeError(str(exc)) from exc

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create assembly through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
            """
            if name is None:
                return await self.adapter.create_assembly()
            return await self._invoke_with_optional_args(
                self.adapter.create_assembly,
                name,
            )

        return await self._execute_with_circuit_breaker(
            "create_assembly", _op, input_dict={"name": name}
        )

    async def create_drawing(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create drawing through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_drawing",
            lambda: self.adapter.create_drawing(name),
            input_dict={"name": name},
        )

    # Feature operations

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create extrusion through circuit breaker.

        Args:
            params (ExtrusionParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_extrusion",
            lambda: self.adapter.create_extrusion(params),
            input_dict=_to_input_dict(params),
        )

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create cut-extrude through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_cut_extrude",
            lambda: self.adapter.create_cut_extrude(params),
            input_dict=_to_input_dict(params),
        )

    async def add_fillet(
        self, radius: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Add fillet through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_fillet",
            lambda: self.adapter.add_fillet(radius, edge_names),
            input_dict={"radius": radius, "edge_names": edge_names},
        )

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create revolve through circuit breaker.

        Args:
            params (RevolveParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_revolve",
            lambda: self.adapter.create_revolve(params),
            input_dict=_to_input_dict(params),
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create sweep through circuit breaker.

        Args:
            params (SweepParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_sweep",
            lambda: self.adapter.create_sweep(params),
            input_dict=_to_input_dict(params),
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create loft through circuit breaker.

        Args:
            params (LoftParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_loft",
            lambda: self.adapter.create_loft(params),
            input_dict=_to_input_dict(params),
        )

    # Sketch operations

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create sketch through circuit breaker.

        Args:
            plane (str): The plane value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_sketch",
            lambda: self.adapter.create_sketch(plane),
            input_dict={"plane": plane},
        )

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add line through circuit breaker.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_line",
            lambda: self.adapter.add_line(x1, y1, x2, y2),
            input_dict={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add centerline through circuit breaker.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_centerline",
            lambda: self.adapter.add_centerline(x1, y1, x2, y2),
            input_dict={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add circle through circuit breaker.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            radius (float): The radius value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_circle",
            lambda: self.adapter.add_circle(center_x, center_y, radius),
            input_dict={"center_x": center_x, "center_y": center_y, "radius": radius},
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add rectangle through circuit breaker.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_rectangle",
            lambda: self.adapter.add_rectangle(x1, y1, x2, y2),
            input_dict={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
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
        """Add arc through circuit breaker.

        Args:
            center_x (float): Arc center X coordinate.
            center_y (float): Arc center Y coordinate.
            start_x (float): Arc start X coordinate.
            start_y (float): Arc start Y coordinate.
            end_x (float): Arc end X coordinate.
            end_y (float): Arc end Y coordinate.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_arc",
            lambda: self.adapter.add_arc(
                center_x,
                center_y,
                start_x,
                start_y,
                end_x,
                end_y,
            ),
            input_dict={
                "center_x": center_x,
                "center_y": center_y,
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
            },
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        """Add spline through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_spline",
            lambda: self.adapter.add_spline(points),
            input_dict={"points": points},
        )

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        """Add polygon through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_polygon",
            lambda: self.adapter.add_polygon(center_x, center_y, radius, sides),
            input_dict={
                "center_x": center_x,
                "center_y": center_y,
                "radius": radius,
                "sides": sides,
            },
        )

    async def add_ellipse(
        self,
        center_x: float,
        center_y: float,
        major_axis: float,
        minor_axis: float,
    ) -> AdapterResult[str]:
        """Add ellipse through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_ellipse",
            lambda: self.adapter.add_ellipse(
                center_x, center_y, major_axis, minor_axis
            ),
            input_dict={
                "center_x": center_x,
                "center_y": center_y,
                "major_axis": major_axis,
                "minor_axis": minor_axis,
            },
        )

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        """Sketch linear pattern through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_linear_pattern",
            lambda: self.adapter.sketch_linear_pattern(
                entities, direction_x, direction_y, spacing, count
            ),
            input_dict={
                "entities": entities,
                "direction_x": direction_x,
                "direction_y": direction_y,
                "spacing": spacing,
                "count": count,
            },
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        """Sketch circular pattern through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_circular_pattern",
            lambda: self.adapter.sketch_circular_pattern(entities, angle, count),
            input_dict={"entities": entities, "angle": angle, "count": count},
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        """Sketch mirror through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_mirror",
            lambda: self.adapter.sketch_mirror(entities, mirror_line),
            input_dict={"entities": entities, "mirror_line": mirror_line},
        )

    async def sketch_offset(
        self,
        entities: list[str],
        offset_distance: float,
        reverse_direction: bool,
    ) -> AdapterResult[str]:
        """Sketch offset through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_offset",
            lambda: self.adapter.sketch_offset(
                entities, offset_distance, reverse_direction
            ),
            input_dict={
                "entities": entities,
                "offset_distance": offset_distance,
                "reverse_direction": reverse_direction,
            },
        )

    async def add_sketch_constraint(
        self,
        entity1: str,
        entity2: str | None,
        relation_type: str,
        entity3: str | None = None,
    ) -> AdapterResult[str]:
        """Add sketch constraint through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_sketch_constraint",
            lambda: self.adapter.add_sketch_constraint(
                entity1,
                entity2,
                relation_type,
                entity3,
            ),
            input_dict={
                "entity1": entity1,
                "entity2": entity2,
                "relation_type": relation_type,
                "entity3": entity3,
            },
        )

    async def add_sketch_dimension(
        self,
        entity1: str,
        entity2: str | None,
        dimension_type: str,
        value: float,
    ) -> AdapterResult[str]:
        """Add sketch dimension through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_sketch_dimension",
            lambda: self.adapter.add_sketch_dimension(
                entity1,
                entity2,
                dimension_type,
                value,
            ),
            input_dict={
                "entity1": entity1,
                "entity2": entity2,
                "dimension_type": dimension_type,
                "value": value,
            },
        )

    async def check_sketch_fully_defined(
        self, sketch_name: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Check sketch definition status through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "check_sketch_fully_defined",
            lambda: self.adapter.check_sketch_fully_defined(sketch_name),
            input_dict={"sketch_name": sketch_name},
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit sketch through circuit breaker.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "exit_sketch",
            lambda: self.adapter.exit_sketch(),
            input_dict={},
        )

    # Analysis operations

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties through circuit breaker.

        Returns:
            AdapterResult[MassProperties]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "get_mass_properties",
            lambda: self.adapter.get_mass_properties(),
            input_dict={},
        )

    async def get_model_info(self) -> AdapterResult[dict[str, object]]:
        """Get active model metadata through circuit breaker.

        Returns:
            AdapterResult[dict[str, object]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "get_model_info",
            lambda: self.adapter.get_model_info(),
            input_dict={},
        )

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, object]]]:
        """List model features through circuit breaker.

        Args:
            include_suppressed (bool): The include suppressed value. Defaults to False.

        Returns:
            AdapterResult[list[dict[str, object]]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_features",
            lambda: self.adapter.list_features(include_suppressed),
            input_dict={"include_suppressed": include_suppressed},
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List model configurations through circuit breaker.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_configurations",
            lambda: self.adapter.list_configurations(),
            input_dict={},
        )

    # Export operations

    async def export_image(self, payload: dict) -> AdapterResult[dict]:
        """Export viewport image through circuit breaker.

        Args:
            payload (dict): The payload value.

        Returns:
            AdapterResult[dict]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "export_image",
            lambda: self.adapter.export_image(payload),
            input_dict=payload,
        )

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export file through circuit breaker.

        Args:
            file_path (str): Path to the target file.
            format_type (str): The format type value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "export_file",
            lambda: self.adapter.export_file(file_path, format_type),
            input_dict={"file_path": file_path, "format_type": format_type},
        )

    # Dimension operations

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get dimension through circuit breaker.

        Args:
            name (str): The name value.

        Returns:
            AdapterResult[float]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "get_dimension",
            lambda: self.adapter.get_dimension(name),
            input_dict={"name": name},
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set dimension through circuit breaker.

        Args:
            name (str): The name value.
            value (float): The value value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "set_dimension",
            lambda: self.adapter.set_dimension(name, value),
            input_dict={"name": name, "value": value},
        )

    # SolidWorks-as-Code checkpoint

    async def soc_create_checkpoint(
        self,
        label: str,
        file_path: str,
        *,
        feature_tree: list[dict[str, Any]] | None = None,
    ) -> int | None:
        """Create a named SoC checkpoint after saving the model.

        Records a SoCCheckpoint row and a ModelStateSnapshot.  Call this
        immediately after ``save_file`` to mark a stable rollback point.

        Args:
            label (str): Short human name (e.g. "base-extrude").
            file_path (str): Path of the .sldprt that was just saved.
            feature_tree (list | None): Optional feature list from list_features().

        Returns:
            int | None: The new SoCCheckpoint.id, or None if soc_session_id is unset.
        """
        if not self.soc_session_id:
            return None
        try:
            from solidworks_mcp.agents.history_db import (
                create_soc_checkpoint,
                insert_model_state_snapshot,
                list_tool_call_records,
            )

            records = list_tool_call_records(
                self.soc_session_id, db_path=self.soc_db_path
            )
            last_id = records[-1]["id"] if records else None

            snapshot_id: int | None = None
            if feature_tree is not None:
                import json as _json

                insert_model_state_snapshot(
                    session_id=self.soc_session_id,
                    model_path=file_path,
                    feature_tree_json=_json.dumps(feature_tree, default=str),
                    db_path=self.soc_db_path,
                )
                from solidworks_mcp.agents.history_db import list_model_state_snapshots

                snaps = list_model_state_snapshots(
                    self.soc_session_id, db_path=self.soc_db_path
                )
                if snaps:
                    snapshot_id = snaps[0]["id"]

            return create_soc_checkpoint(
                session_id=self.soc_session_id,
                label=label,
                file_path=file_path,
                last_record_id=last_id,
                snapshot_id=snapshot_id,
                db_path=self.soc_db_path,
            )
        except Exception as exc:
            logger.debug(
                f"[soc_checkpoint] failed to create checkpoint {label!r}: {exc}"
            )
            return None


class CircuitBreaker:
    """Legacy standalone circuit breaker class expected by tests.

    Args:
        failure_threshold (int): The failure threshold value. Defaults to 5.
        recovery_timeout (float): The recovery timeout value. Defaults to 60.0.
        expected_exception (type[Exception]): The expected exception value. Defaults to
                                              Exception.

    Attributes:
        expected_exception (Any): The expected exception value.
        failure_count (Any): The failure count value.
        failure_threshold (Any): The failure threshold value.
        last_failure_time (Any): The last failure time value.
        recovery_timeout (Any): The recovery timeout value.
        state (Any): The state value.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            failure_threshold (int): The failure threshold value. Defaults to 5.
            recovery_timeout (float): The recovery timeout value. Defaults to 60.0.
            expected_exception (type[Exception]): The expected exception value. Defaults to
                                                  Exception.

        Returns:
            None: None.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    async def call(self, operation: Callable[[], object | Awaitable[object]]) -> object:
        """Provide call support for the circuit breaker.

        Args:
            operation (Callable[[], object | Awaitable[object]]): Callable object executed by
                                                                  the helper.

        Returns:
            object: The result produced by the operation.

        Raises:
            Exception: Circuit breaker is open.
        """
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time < self.recovery_timeout:
                raise Exception("Circuit breaker is open")
            self.state = CircuitState.HALF_OPEN

        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            return result
        except self.expected_exception:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            raise
