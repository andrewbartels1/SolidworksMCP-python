"""Circuit breaker adapter for SolidWorks operations.

Implements the circuit breaker pattern to prevent cascading failures when SolidWorks
operations fail repeatedly.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar, cast

from loguru import logger

from .base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    HelixParameters,
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
        return cast(dict[str, Any], params.model_dump())
    return cast(dict[str, Any], params) if isinstance(params, dict) else {}


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


class _BreakerBucket:
    """Per-operation circuit breaker state.

    Attributes:
        state (CircuitState): The current state of this bucket.
        failure_count (int): Consecutive failures recorded in ``CLOSED``/``OPEN``.
        last_failure_time (float): ``time.time()`` of the most recent failure.
        half_open_calls (int): Calls let through since entering ``HALF_OPEN``.
    """

    __slots__ = ("state", "failure_count", "last_failure_time", "half_open_calls")

    def __init__(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0


class CircuitBreakerAdapter(SolidWorksAdapter):
    """Circuit breaker wrapper for SolidWorks adapters.

    Each named operation (``create_cut_extrude``, ``list_features``, ...) gets
    its own independent breaker bucket, keyed by the ``operation_name`` passed
    to ``_execute_with_circuit_breaker``. A run of failures on one tool (e.g.
    every ``create_cut_extrude`` attempt failing while a wrong argument count
    is being worked out) trips only that tool's breaker — unrelated read-only
    tools like ``list_features`` or ``get_model_info`` keep working. Before
    this, a single shared ``CircuitState`` meant one failing tool blocked
    every other tool on the adapter, including reads, until the shared
    recovery timeout elapsed.

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
        failure_threshold (Any): The failure threshold value.
        half_open_max_calls (Any): The half open max calls value.
        recovery_timeout (Any): The recovery timeout value.
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

        # Legacy/default bucket, used by connect() and the generic call() API.
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0

        # Per-operation buckets, keyed by operation_name, used by every named
        # method that goes through _execute_with_circuit_breaker.
        self._buckets: dict[str, _BreakerBucket] = {}

    def _get_bucket(self, operation_name: str) -> _BreakerBucket:
        """Get (creating if needed) the breaker bucket for one operation name.

        Args:
            operation_name (str): The operation name value.

        Returns:
            _BreakerBucket: That operation's independent breaker state.
        """
        bucket = self._buckets.get(operation_name)
        if bucket is None:
            bucket = _BreakerBucket()
            self._buckets[operation_name] = bucket
        return bucket

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

    def _should_allow_request(self, bucket: Any = None) -> bool:
        """Check if request should be allowed through circuit breaker.

        Args:
            bucket (Any): The breaker bucket to check. Defaults to ``self``
                (the legacy/default bucket used by ``connect()``/``call()``).

        Returns:
            bool: True if should allow request, otherwise False.
        """
        if bucket is None:
            bucket = self
        if bucket.state == CircuitState.CLOSED:
            return True
        elif bucket.state == CircuitState.OPEN:
            # Check if enough time has passed to try again
            if time.time() - bucket.last_failure_time >= self.recovery_timeout:
                bucket.state = CircuitState.HALF_OPEN
                bucket.half_open_calls = 0
                return True
            return False
        # HALF_OPEN, the only state left.
        return bool(bucket.half_open_calls < self.half_open_max_calls)

    def _record_success(self, bucket: Any = None) -> None:
        """Record successful operation.

        Args:
            bucket (Any): The breaker bucket to update. Defaults to ``self``.

        Returns:
            None: None.
        """
        if bucket is None:
            bucket = self
        if bucket.state == CircuitState.HALF_OPEN:
            # Reset circuit breaker on success in half-open state
            bucket.state = CircuitState.CLOSED
            bucket.failure_count = 0
            bucket.half_open_calls = 0
        elif bucket.state == CircuitState.CLOSED:
            # Reset failure count on success
            bucket.failure_count = 0

    def _record_failure(self, bucket: Any = None) -> None:
        """Record failed operation.

        Args:
            bucket (Any): The breaker bucket to update. Defaults to ``self``.

        Returns:
            None: None.
        """
        if bucket is None:
            bucket = self
        bucket.failure_count += 1
        bucket.last_failure_time = time.time()

        if bucket.state == CircuitState.HALF_OPEN:
            # Go back to open state
            bucket.state = CircuitState.OPEN
        elif (
            bucket.state == CircuitState.CLOSED
            and bucket.failure_count >= self.failure_threshold
        ):
            # Open circuit breaker
            bucket.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {bucket.failure_count} failures"
            )

    async def _execute_with_circuit_breaker(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[AdapterResult[T]]],
        input_dict: dict[str, Any] | None = None,
        error_results_are_failures: bool = True,
    ) -> AdapterResult[T]:
        """Build internal execute with circuit breaker.

        Args:
            operation_name (str): The operation name value.
            operation (Callable[[], Awaitable[AdapterResult[T]]]): Callable object executed by
                                                                   the helper.
            input_dict (dict | None): Input parameters for SoC logging. Defaults to None.
            error_results_are_failures (bool): When False, an ERROR result
                returned by the operation counts as a healthy round trip, not a
                breaker failure - only exceptions trip the breaker. For
                diagnostic/lookup operations whose ERROR is an expected answer
                ("the model has rebuild errors", "no such feature"); otherwise
                they would lock themselves out exactly when needed.

        Returns:
            AdapterResult[T]: The result produced by the operation.
        """
        bucket = self._get_bucket(operation_name)
        if not self._should_allow_request(bucket):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker is {bucket.state.value} for {operation_name}",
                metadata={"circuit_state": bucket.state.value},
            )

        if bucket.state == CircuitState.HALF_OPEN:
            bucket.half_open_calls += 1

        t0 = time.time()
        try:
            result = await operation()
            latency_ms = (time.time() - t0) * 1000.0
            if result.is_success or not error_results_are_failures:
                self._record_success(bucket)
            else:
                self._record_failure(bucket)
            self._soc_log(operation_name, input_dict, result, latency_ms)
            return result
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            self._record_failure(bucket)
            err_result: AdapterResult[T] = AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker caught exception in {operation_name}: {e}",
                metadata={"circuit_state": bucket.state.value},
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
                output_data = {"data": result.data}

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

    def reset(self, operation: str | None = None) -> list[str]:
        """Close the breaker for one operation, or for all of them.

        Args:
            operation: The operation to reset; ``None`` resets every one.

        Returns:
            list[str]: The operations that were open or half-open.
        """
        if operation is None:
            buckets = dict(self._buckets)
        else:
            buckets = (
                {operation: self._buckets[operation]}
                if operation in self._buckets
                else {}
            )
        was_open = [
            name
            for name, bucket in buckets.items()
            if bucket.state != CircuitState.CLOSED
        ]
        for bucket in buckets.values():
            bucket.state = CircuitState.CLOSED
            bucket.failure_count = 0
            bucket.half_open_calls = 0
        if operation is None:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        return sorted(was_open)

    async def reset_circuit_breakers(
        self, operation: str | None = None
    ) -> AdapterResult[dict[str, list[str]]]:
        """Reset breakers through the adapter interface (see :meth:`reset`).

        Args:
            operation: The operation to reset; ``None`` resets every one.

        Returns:
            AdapterResult[dict[str, list[str]]]: ``reset``, the operations that were open.
        """
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"reset": self.reset(operation)}
        )

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

        ``circuit_breaker`` reports the legacy/default bucket (used by
        ``connect()``), which is what "connection health" means here.
        ``circuit_breaker_operations`` reports every per-tool bucket, so a
        tripped tool-specific breaker is visible even while the connection
        itself is healthy.

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
        base_health.metrics["circuit_breaker_operations"] = {
            name: {
                "state": bucket.state.value,
                "failure_count": bucket.failure_count,
                "last_failure_time": bucket.last_failure_time,
                "half_open_calls": bucket.half_open_calls,
            }
            for name, bucket in self._buckets.items()
        }

        # Consider circuit as unhealthy if the connection breaker or any
        # per-operation breaker is open.
        open_operations = [
            name
            for name, bucket in self._buckets.items()
            if bucket.state == CircuitState.OPEN
        ]
        if self.state == CircuitState.OPEN:
            base_health.healthy = False
            base_health.connection_status = "circuit_breaker_open"
        elif open_operations:
            base_health.healthy = False
            base_health.connection_status = (
                f"circuit_breaker_open_for: {', '.join(sorted(open_operations))}"
            )

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

    # Added in 2.2.0 (#276).
    async def save_copy(self, file_path: str) -> AdapterResult[dict[str, Any]]:
        """Write a copy and keep the original open, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "save_copy",
            lambda: self.adapter.save_copy(file_path),
            input_dict={"file_path": file_path},
        )

    async def create_base_flange(
        self,
        thickness: float,
        bend_radius: float,
        k_factor: float = 0.5,
        depth: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """A sheet-metal base flange from a sketch. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_base_flange",
            lambda: self.adapter.create_base_flange(
                thickness, bend_radius, k_factor, depth, sketch, reverse
            ),
        )

    async def add_edge_flange(
        self,
        edge_point: list[float],
        length: float,
        angle: float = 90.0,
        bend_radius: float | None = None,
        flip: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """A flange off the sheet edge nearest a point. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_edge_flange",
            lambda: self.adapter.add_edge_flange(
                edge_point, length, angle, bend_radius, flip
            ),
        )

    async def create_sketched_bend(
        self,
        angle: float = 90.0,
        bend_radius: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Bend the sheet along a sketched line. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_sketched_bend",
            lambda: self.adapter.create_sketched_bend(
                angle, bend_radius, sketch, reverse
            ),
        )

    async def set_flat_pattern(self, flat: bool) -> AdapterResult[dict[str, Any]]:
        """Flatten the sheet-metal part, or fold it back. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_flat_pattern",
            lambda: self.adapter.set_flat_pattern(flat),
        )

    async def get_template_folders(self) -> AdapterResult[dict[str, Any]]:
        """Read the template folders through circuit breaker.

        Returns:
            AdapterResult[dict[str, Any]]: The folders and the template extension.
        """
        return await self._execute_with_circuit_breaker(
            "get_template_folders",
            lambda: self.adapter.get_template_folders(),
            error_results_are_failures=False,
        )

    async def save_as_template(self, file_path: str) -> AdapterResult[dict[str, Any]]:
        """Save the active document as a template through circuit breaker.

        Args:
            file_path: The template's full path.

        Returns:
            AdapterResult[dict[str, Any]]: The template written.
        """
        return await self._execute_with_circuit_breaker(
            "save_as_template",
            lambda: self.adapter.save_as_template(file_path),
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
        self,
        name: str | None = None,
        units: str | None = None,
        template: str | None = None,
    ) -> AdapterResult[SolidWorksModel]:
        """Create part through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.
            units (str | None): The units value. Defaults to None.
            template (str | None): Template file path. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
            """
            if template is not None:
                # No zero-arg retry: dropping the template would silently
                # build the document from a different one.
                return await self.adapter.create_part(name, units, template)
            if name is None and units is None:
                return await self.adapter.create_part()
            return await self._invoke_with_optional_args(
                self.adapter.create_part,
                name,
                units,
            )

        return await self._execute_with_circuit_breaker(
            "create_part",
            _op,
            input_dict={"name": name, "units": units, "template": template},
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
        self, name: str | None = None, template: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create assembly through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.
            template (str | None): Template file path. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
            """
            if template is not None:
                return await self.adapter.create_assembly(name, template)
            if name is None:
                return await self.adapter.create_assembly()
            return await self._invoke_with_optional_args(
                self.adapter.create_assembly,
                name,
            )

        return await self._execute_with_circuit_breaker(
            "create_assembly", _op, input_dict={"name": name, "template": template}
        )

    async def create_drawing(
        self, name: str | None = None, template: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create drawing through circuit breaker.

        Args:
            name (str | None): The name value. Defaults to None.
            template (str | None): Template file path. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_drawing",
            lambda: self.adapter.create_drawing(name, template),
            input_dict={"name": name, "template": template},
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

    async def add_chamfer(
        self,
        distance: float,
        edge_names: list[str],
        angle: float = 45.0,
        flip: bool = False,
    ) -> AdapterResult[SolidWorksFeature]:
        """Add chamfer through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_chamfer",
            lambda: self.adapter.add_chamfer(distance, edge_names, angle, flip),
            input_dict={
                "distance": distance,
                "edge_names": edge_names,
                "angle": angle,
                "flip": flip,
            },
        )

    async def get_selected_entities(self) -> AdapterResult[list[dict[str, Any]]]:
        """Report the current UI selection through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_selected_entities",
            lambda: self.adapter.get_selected_entities(),
            input_dict={},
        )

    async def select_feature(
        self, feature_name: str, append: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Select a named feature through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "select_feature",
            lambda: self.adapter.select_feature(feature_name, append),
            input_dict={"feature_name": feature_name, "append": append},
            error_results_are_failures=False,
        )

    async def select_face_edges(
        self,
        point: list[float] | None = None,
        side: str | None = None,
        plane: str | None = None,
        edge_type: str = "all",
        append: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Multi-select a face's edges through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "select_face_edges",
            lambda: self.adapter.select_face_edges(
                point, side, plane, edge_type, append
            ),
            input_dict={
                "point": point,
                "side": side,
                "plane": plane,
                "edge_type": edge_type,
                "append": append,
            },
            error_results_are_failures=False,
        )

    async def rebuild_model(
        self, top_level_only: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Force a rebuild through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "rebuild_model",
            lambda: self.adapter.rebuild_model(top_level_only),
            input_dict={"top_level_only": top_level_only},
            error_results_are_failures=False,
        )

    async def create_reference_plane(
        self,
        reference: str,
        offset: float = 0.0,
        angle: float = 0.0,
        flip: bool = False,
        axis: str | None = None,
        face_point: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Create reference plane through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_reference_plane",
            lambda: self.adapter.create_reference_plane(
                reference, offset, angle, flip, axis, face_point
            ),
            input_dict={
                "reference": reference,
                "offset": offset,
                "angle": angle,
                "flip": flip,
                "axis": axis,
                "face_point": face_point,
            },
        )

    async def create_axis(self, reference: str) -> AdapterResult[dict[str, Any]]:
        """Create reference axis through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_axis",
            lambda: self.adapter.create_axis(reference),
            input_dict={"reference": reference},
        )

    async def create_reference_point(
        self,
        mode: str,
        x: float,
        y: float,
        z: float,
        distance: float | None = None,
        percent: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Create a reference point through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_reference_point",
            lambda: self.adapter.create_reference_point(
                mode, x, y, z, distance, percent
            ),
            input_dict={
                "mode": mode,
                "x": x,
                "y": y,
                "z": z,
                "distance": distance,
                "percent": percent,
            },
        )

    async def mirror_feature(
        self,
        features: list[str],
        mirror_plane: str,
        merge: bool = True,
        mirror_bodies: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Mirror solid bodies or features through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "mirror_feature",
            lambda: self.adapter.mirror_feature(
                features, mirror_plane, merge, mirror_bodies
            ),
            input_dict={
                "features": features,
                "mirror_plane": mirror_plane,
                "merge": merge,
                "mirror_bodies": mirror_bodies,
            },
        )

    async def pattern_circular(
        self,
        features: list[str],
        axis: str,
        count: int,
        angle: float = 360.0,
        equal_spacing: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Pattern features around an axis through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "pattern_circular",
            lambda: self.adapter.pattern_circular(
                features, axis, count, angle, equal_spacing
            ),
            input_dict={
                "features": features,
                "axis": axis,
                "count": count,
                "angle": angle,
                "equal_spacing": equal_spacing,
            },
        )

    async def pattern_linear(
        self,
        features: list[str],
        direction: list[float] | str,
        count: int,
        spacing: float,
        direction2: list[float] | str | None = None,
        count2: int = 1,
        spacing2: float = 0.0,
        reverse: bool = False,
        reverse2: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Repeat features along one or two directions through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "pattern_linear",
            lambda: self.adapter.pattern_linear(
                features,
                direction,
                count,
                spacing,
                direction2,
                count2,
                spacing2,
                reverse,
                reverse2,
            ),
            input_dict={
                "features": features,
                "direction": direction,
                "count": count,
                "spacing": spacing,
                "direction2": direction2,
                "count2": count2,
                "spacing2": spacing2,
                "reverse": reverse,
                "reverse2": reverse2,
            },
        )

    async def create_shell(
        self,
        thickness: float,
        faces: list[list[float]],
        outward: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Hollow the body to a wall thickness through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_shell",
            lambda: self.adapter.create_shell(thickness, faces, outward),
            input_dict={
                "thickness": thickness,
                "faces": faces,
                "outward": outward,
            },
        )

    async def add_draft(
        self,
        angle: float,
        faces: list[list[float]],
        neutral_face: list[float],
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Draft faces against a neutral face through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_draft",
            lambda: self.adapter.add_draft(angle, faces, neutral_face, reverse),
            input_dict={
                "angle": angle,
                "faces": faces,
                "neutral_face": neutral_face,
                "reverse": reverse,
            },
        )

    async def create_rib(
        self,
        sketch: str,
        thickness: float,
        both_sides: bool = True,
        flip_material: bool = False,
        normal_to_sketch: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a rib from an open sketch through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_rib",
            lambda: self.adapter.create_rib(
                sketch, thickness, both_sides, flip_material, normal_to_sketch
            ),
            input_dict={
                "sketch": sketch,
                "thickness": thickness,
                "both_sides": both_sides,
                "flip_material": flip_material,
                "normal_to_sketch": normal_to_sketch,
            },
        )

    async def list_hole_sizes(
        self,
        standard: str,
        hole_type: str,
        fastener: str | None = None,
        size: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """List the Hole Wizard hole types and sizes through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_hole_sizes",
            lambda: self.adapter.list_hole_sizes(standard, hole_type, fastener, size),
            input_dict={
                "standard": standard,
                "hole_type": hole_type,
                "fastener": fastener,
                "size": size,
            },
        )

    async def create_hole(
        self,
        face_point: list[float],
        hole_type: str,
        standard: str,
        size: str,
        end_condition: str = "through_all",
        depth: float | None = None,
        positions: list[list[float]] | None = None,
        fastener: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a Hole Wizard hole at a point on a flat face through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_hole",
            lambda: self.adapter.create_hole(
                face_point,
                hole_type,
                standard,
                size,
                end_condition,
                depth,
                positions,
                fastener,
            ),
            input_dict={
                "face_point": face_point,
                "hole_type": hole_type,
                "standard": standard,
                "size": size,
                "end_condition": end_condition,
                "depth": depth,
                "positions": positions,
                "fastener": fastener,
            },
        )

    async def add_cosmetic_thread(
        self,
        edge_point: list[float],
        size: str,
        diameter: float,
        end_type: str = "blind",
        depth: float | None = None,
        standard: str = "iso",
    ) -> AdapterResult[dict[str, Any]]:
        """Add a cosmetic thread on a circular edge through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_cosmetic_thread",
            lambda: self.adapter.add_cosmetic_thread(
                edge_point, size, diameter, end_type, depth, standard
            ),
            input_dict={
                "edge_point": edge_point,
                "size": size,
                "diameter": diameter,
                "end_type": end_type,
                "depth": depth,
                "standard": standard,
            },
        )

    async def sketch_convert_entities(
        self,
        edge_points: list[list[float]] | None = None,
        face_point: list[float] | None = None,
        construction: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Copy model edges or a face outline into the open sketch through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_convert_entities",
            lambda: self.adapter.sketch_convert_entities(
                edge_points, face_point, construction
            ),
            input_dict={
                "edge_points": edge_points,
                "face_point": face_point,
                "construction": construction,
            },
        )

    async def create_configuration(
        self,
        name: str,
        parent: str | None = None,
        description: str = "",
        activate: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a configuration to the active model through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_configuration",
            lambda: self.adapter.create_configuration(
                name, parent, description, activate
            ),
            input_dict={
                "name": name,
                "parent": parent,
                "description": description,
                "activate": activate,
            },
        )

    async def activate_configuration(
        self,
        name: str,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a configuration active through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "activate_configuration",
            lambda: self.adapter.activate_configuration(name),
            input_dict={
                "name": name,
            },
        )

    async def delete_configuration(
        self,
        name: str,
    ) -> AdapterResult[dict[str, Any]]:
        """Delete a configuration through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "delete_configuration",
            lambda: self.adapter.delete_configuration(name),
            input_dict={
                "name": name,
            },
        )

    async def list_equations(self) -> AdapterResult[list[dict[str, Any]]]:
        """List the active model's equations through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_equations", lambda: self.adapter.list_equations()
        )

    async def set_equation(
        self,
        name: str,
        expression: str,
        configurations: str | list[str] = "all",
    ) -> AdapterResult[dict[str, Any]]:
        """Add or change an equation through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_equation",
            lambda: self.adapter.set_equation(name, expression, configurations),
            input_dict={
                "name": name,
                "expression": expression,
                "configurations": configurations,
            },
        )

    async def delete_equation(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Delete an equation through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "delete_equation",
            lambda: self.adapter.delete_equation(name),
            input_dict={"name": name},
        )

    async def active_configuration(
        self,
    ) -> AdapterResult[str]:
        """Read the active configuration's name through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "active_configuration",
            lambda: self.adapter.active_configuration(),
            input_dict={},
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

    async def create_cut_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """A sweep that removes material. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_cut_sweep",
            lambda: self.adapter.create_cut_sweep(params),
            input_dict=_to_input_dict(params),
        )

    async def create_helix(
        self, params: HelixParameters
    ) -> AdapterResult[dict[str, Any]]:
        """A helix or a flat spiral. Through the circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_helix",
            lambda: self.adapter.create_helix(params),
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

    async def create_sketch(
        self,
        plane: str | None,
        face_point: tuple[float, float, float] | None = None,
    ) -> AdapterResult[str]:
        """Create sketch through circuit breaker.

        Args:
            plane (str | None): The plane's name; None with ``face_point``.
            face_point (tuple[float, float, float] | None): A point in mm on a
                flat face, in place of ``plane``.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_sketch",
            lambda: self.adapter.create_sketch(plane, face_point),
            input_dict={"plane": plane, "face_point": face_point},
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
        self, x1: float, y1: float, x2: float, y2: float, from_center: bool = False
    ) -> AdapterResult[str]:
        """Add rectangle through circuit breaker.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.
            from_center (bool): ``x1``/``y1`` is the centre, ``x2``/``y2`` a corner.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_rectangle",
            lambda: self.adapter.add_rectangle(x1, y1, x2, y2, from_center),
            input_dict={
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "from_center": from_center,
            },
        )

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        kind: str = "center",
        through: tuple[float, float] | None = None,
    ) -> AdapterResult[str]:
        """Add arc through circuit breaker.

        Args:
            center_x (float): Arc center X coordinate.
            center_y (float): Arc center Y coordinate.
            start_x (float): Arc start X coordinate.
            start_y (float): Arc start Y coordinate.
            end_x (float): Arc end X coordinate.
            end_y (float): Arc end Y coordinate.
            kind (str): ``center``, ``three_point`` or ``tangent``.
            through (tuple[float, float] | None): A point on a three-point arc.

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
                kind,
                through,
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
        self,
        center_x: float,
        center_y: float,
        radius: float,
        sides: int,
        angle: float = 0.0,
    ) -> AdapterResult[str]:
        """Add polygon through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_polygon",
            lambda: self.adapter.add_polygon(center_x, center_y, radius, sides, angle),
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
        angle: float = 0.0,
    ) -> AdapterResult[str]:
        """Add ellipse through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_ellipse",
            lambda: self.adapter.add_ellipse(
                center_x, center_y, major_axis, minor_axis, angle
            ),
            input_dict={
                "center_x": center_x,
                "center_y": center_y,
                "major_axis": major_axis,
                "minor_axis": minor_axis,
            },
        )

    async def add_sketch_text(
        self,
        text: str,
        x: float = 0.0,
        y: float = 0.0,
        height: float = 3.5,
        center_at: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add sketch text through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_sketch_text",
            lambda: self.adapter.add_sketch_text(text, x, y, height, center_at),
        )

    async def set_sketch_text(
        self, sketch_name: str, text: str
    ) -> AdapterResult[dict[str, Any]]:
        """Rewrite sketch text through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_sketch_text", lambda: self.adapter.set_sketch_text(sketch_name, text)
        )

    async def add_sketch_fillet(
        self, corners: list[list[float]], radius: float
    ) -> AdapterResult[dict[str, Any]]:
        """Round sketch corners through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_sketch_fillet", lambda: self.adapter.add_sketch_fillet(corners, radius)
        )

    async def add_sketch_chamfer(
        self,
        corners: list[list[float]],
        distance: float,
        distance2: float | None = None,
        angle: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Bevel sketch corners through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_sketch_chamfer",
            lambda: self.adapter.add_sketch_chamfer(
                corners, distance, distance2, angle
            ),
        )

    async def add_slot(
        self,
        kind: str,
        width: float,
        start: list[float],
        end: list[float],
        center: list[float] | None = None,
    ) -> AdapterResult[str]:
        """Draw a slot through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_slot", lambda: self.adapter.add_slot(kind, width, start, end, center)
        )

    async def sketch_trim(self, point: list[float]) -> AdapterResult[dict[str, Any]]:
        """Trim a sketch entity through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_trim", lambda: self.adapter.sketch_trim(point)
        )

    async def sketch_extend(self, point: list[float]) -> AdapterResult[dict[str, Any]]:
        """Extend a sketch entity through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "sketch_extend", lambda: self.adapter.sketch_extend(point)
        )

    async def set_construction_geometry(
        self, entities: list[str], construction: bool = True
    ) -> AdapterResult[dict[str, Any]]:
        """Set construction geometry through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_construction_geometry",
            lambda: self.adapter.set_construction_geometry(entities, construction),
        )

    async def create_exploded_view(
        self, steps: list[dict[str, Any]] | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Explode the active assembly, automatically or step by step, and show it, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_exploded_view", lambda: self.adapter.create_exploded_view(steps)
        )

    async def set_exploded_view(self, exploded: bool) -> AdapterResult[dict[str, Any]]:
        """Show the assembly's exploded view, or collapse it, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_exploded_view", lambda: self.adapter.set_exploded_view(exploded)
        )

    async def pattern_components(
        self,
        components: list[str],
        axis: str,
        count: int,
        kind: str = "linear",
        spacing: float | None = None,
        angle: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Repeat components along or around a reference axis, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "pattern_components",
            lambda: self.adapter.pattern_components(
                components, axis, count, kind, spacing, angle
            ),
        )

    async def mirror_components(
        self, components: list[str], plane: str
    ) -> AdapterResult[dict[str, Any]]:
        """Mirror components about a plane, as instances of the same parts, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "mirror_components",
            lambda: self.adapter.mirror_components(components, plane),
        )

    async def replace_component(
        self, component: str, file_path: str, all_instances: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Swap a component for another part or assembly file, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "replace_component",
            lambda: self.adapter.replace_component(component, file_path, all_instances),
        )

    # Forwarded since 2.2.0 (#267: it raised AttributeError before reaching
    # SolidWorks).
    async def pack_and_go_assembly(
        self, source_path: str, target_dir: str
    ) -> AdapterResult[dict[str, Any]]:
        """Copy an assembly and its files into one folder, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "pack_and_go_assembly",
            lambda: self.adapter.pack_and_go_assembly(source_path, target_dir),
        )

    async def set_component_appearance(
        self,
        component: str,
        visible: bool | None = None,
        transparent: bool | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Hide or show a component, and make it transparent or opaque, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_component_appearance",
            lambda: self.adapter.set_component_appearance(
                component, visible, transparent
            ),
        )

    async def add_balloons(
        self, view_name: str, layout: str = "square"
    ) -> AdapterResult[dict[str, Any]]:
        """Number a drawing view's parts with balloons, one per part, through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_balloons", lambda: self.adapter.add_balloons(view_name, layout)
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
        self, include_suppressed: bool = False, max_assembly_depth: int = 2
    ) -> AdapterResult[list[dict[str, object]]]:
        """List model features through circuit breaker.

        Args:
            include_suppressed (bool): The include suppressed value. Defaults to False.
            max_assembly_depth (int): Sub-assembly recursion depth. Defaults to 2.

        Returns:
            AdapterResult[list[dict[str, object]]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_features",
            lambda: self.adapter.list_features(include_suppressed, max_assembly_depth),
            input_dict={
                "include_suppressed": include_suppressed,
                "max_assembly_depth": max_assembly_depth,
            },
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

    async def get_dimension(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Get dimension through circuit breaker.

        Args:
            name (str): The name value.

        Returns:
            AdapterResult[dict[str, Any]]: ``value`` and ``units`` (mm, deg or None).
        """
        return await self._execute_with_circuit_breaker(
            "get_dimension",
            lambda: self.adapter.get_dimension(name),
            input_dict={"name": name},
        )

    async def set_dimension(
        self, name: str, value: float, configurations: str | list[str] = "this"
    ) -> AdapterResult[dict[str, Any]]:
        """Set dimension through circuit breaker.

        Args:
            name (str): The name value.
            value (float): The value value.
            configurations (str | list[str]): "this", "all" or names.

        Returns:
            AdapterResult[dict[str, Any]]: ``configurations``, the names set in.
        """
        return await self._execute_with_circuit_breaker(
            "set_dimension",
            lambda: self.adapter.set_dimension(name, value, configurations),
            input_dict={"name": name, "value": value, "configurations": configurations},
        )

    async def set_units(self, unit_system: str) -> AdapterResult[dict[str, Any]]:
        """Set document units through circuit breaker.

        Args:
            unit_system (str): One of ``mm``, ``cm``, ``m``, ``in``, ``ft``.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "set_units",
            lambda: self.adapter.set_units(unit_system),
            input_dict={"unit_system": unit_system},
        )

    async def list_open_documents(self) -> AdapterResult[list[dict[str, Any]]]:
        """List open documents through circuit breaker.

        Returns:
            AdapterResult[list[dict[str, Any]]]: The result produced by the
            operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_open_documents",
            lambda: self.adapter.list_open_documents(),
            input_dict={},
        )

    async def activate_document(
        self, title_or_path: str
    ) -> AdapterResult[dict[str, Any]]:
        """Activate an open document through circuit breaker.

        Args:
            title_or_path (str): Title, full path, or file name of an open
                document.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "activate_document",
            lambda: self.adapter.activate_document(title_or_path),
            input_dict={"title_or_path": title_or_path},
        )

    # Assembly operations

    async def insert_component(
        self, file_path: str, x: float = 0.0, y: float = 0.0, z: float = 0.0
    ) -> AdapterResult[dict[str, Any]]:
        """Insert component through circuit breaker.

        Args:
            file_path (str): Path to the target file.
            x (float): X position in millimetres. Defaults to 0.0.
            y (float): Y position in millimetres. Defaults to 0.0.
            z (float): Z position in millimetres. Defaults to 0.0.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "insert_component",
            lambda: self.adapter.insert_component(file_path, x, y, z),
            input_dict={"file_path": file_path, "x": x, "y": y, "z": z},
        )

    async def list_components(self) -> AdapterResult[list[str]]:
        """List components through circuit breaker.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_components",
            lambda: self.adapter.list_components(),
            input_dict={},
        )

    async def get_model_geometry_summary(self) -> AdapterResult[dict[str, Any]]:
        """Summarise the active document through circuit breaker.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "get_model_geometry_summary",
            lambda: self.adapter.get_model_geometry_summary(),
            input_dict={},
        )

    async def get_application_info(self) -> AdapterResult[dict[str, Any]]:
        """Describe the connected SolidWorks through circuit breaker.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "get_application_info",
            lambda: self.adapter.get_application_info(),
            input_dict={},
        )

    async def create_drawing_view(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Create a drawing view through circuit breaker.

        Args:
            payload (Any): Tool payload for the drawing view.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_drawing_view",
            lambda: self.adapter.create_drawing_view(payload),
            input_dict=payload if isinstance(payload, dict) else {},
        )

    async def add_drawing_view(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Add a drawing view through circuit breaker.

        Args:
            payload (Any): Tool payload for the drawing view.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_drawing_view",
            lambda: self.adapter.add_drawing_view(payload),
            input_dict=payload if isinstance(payload, dict) else {},
        )

    async def create_technical_drawing(
        self, payload: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Create standard views through circuit breaker.

        Args:
            payload (Any): Tool payload for the technical drawing.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "create_technical_drawing",
            lambda: self.adapter.create_technical_drawing(payload),
            input_dict=payload if isinstance(payload, dict) else {},
        )

    async def add_note(self, payload: Any = None) -> AdapterResult[dict[str, Any]]:
        """Add a drawing note through circuit breaker.

        Args:
            payload (Any): Tool payload for the note.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_note",
            lambda: self.adapter.add_note(payload),
            input_dict=payload if isinstance(payload, dict) else {},
        )

    async def create_section_view(
        self,
        view: str,
        line_start: list[float],
        line_end: list[float],
        position: list[float],
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a section view cut along a line across a drawing view through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_section_view",
            lambda: self.adapter.create_section_view(
                view, line_start, line_end, position, label
            ),
            input_dict={
                "view": view,
                "line_start": line_start,
                "line_end": line_end,
                "position": position,
                "label": label,
            },
        )

    async def create_detail_view(
        self,
        view: str,
        center: list[float],
        radius: float,
        position: list[float],
        scale: str = "2:1",
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a detail view of a circle in a drawing view through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_detail_view",
            lambda: self.adapter.create_detail_view(
                view, center, radius, position, scale, label
            ),
            input_dict={
                "view": view,
                "center": center,
                "radius": radius,
                "position": position,
                "scale": scale,
                "label": label,
            },
        )

    async def add_dimension(
        self,
        dimension_type: str,
        entity1_point: list[float],
        position: list[float],
        entity2_point: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add one dimension between drawing entities picked at sheet points through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_dimension",
            lambda: self.adapter.add_dimension(
                dimension_type, entity1_point, position, entity2_point
            ),
            input_dict={
                "dimension_type": dimension_type,
                "entity1_point": entity1_point,
                "position": position,
                "entity2_point": entity2_point,
            },
        )

    async def auto_dimension_view(
        self,
        view: str,
        scheme: str = "baseline",
    ) -> AdapterResult[dict[str, Any]]:
        """Auto-dimension one drawing view through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "auto_dimension_view",
            lambda: self.adapter.auto_dimension_view(view, scheme),
            input_dict={"view": view, "scheme": scheme},
        )

    async def update_sheet_format(
        self,
        sheet_format: str,
        paper_size: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Change the active sheet's format and paper size, keeping its views through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "update_sheet_format",
            lambda: self.adapter.update_sheet_format(sheet_format, paper_size),
            input_dict={"sheet_format": sheet_format, "paper_size": paper_size},
        )

    async def update_title_block(
        self,
        fields: dict[str, str],
    ) -> AdapterResult[dict[str, Any]]:
        """Write title-block fields on the active drawing through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "update_title_block",
            lambda: self.adapter.update_title_block(fields),
            input_dict={"fields": fields},
        )

    async def drawing_report(self) -> AdapterResult[dict[str, Any]]:
        """Read what check_drawing judges on the active drawing through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "drawing_report",
            lambda: self.adapter.drawing_report(),
            input_dict={},
        )

    async def list_drawing_views(self) -> AdapterResult[list[str]]:
        """List drawing views through circuit breaker.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "list_drawing_views",
            lambda: self.adapter.list_drawing_views(),
            input_dict={},
        )

    async def auto_center_marks(
        self,
        view_name: str,
        mark_holes: bool = True,
        mark_fillets: bool = False,
        mark_slots: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Auto-insert drawing centre marks through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "auto_center_marks",
            lambda: self.adapter.auto_center_marks(
                view_name, mark_holes, mark_fillets, mark_slots
            ),
            input_dict={
                "view_name": view_name,
                "mark_holes": mark_holes,
                "mark_fillets": mark_fillets,
                "mark_slots": mark_slots,
            },
        )

    async def save_body_as_part(
        self, body_name: str, file_path: str
    ) -> AdapterResult[dict[str, Any]]:
        """Save a body to a new part through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "save_body_as_part",
            lambda: self.adapter.save_body_as_part(body_name, file_path),
            input_dict={"body_name": body_name, "file_path": file_path},
        )

    async def check_interference(
        self, params: Any = None
    ) -> AdapterResult[dict[str, Any]]:
        """Check interference through circuit breaker.

        Args:
            params (Any): Optional interference-detection settings.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "check_interference",
            lambda: self.adapter.check_interference(params),
            input_dict=params if isinstance(params, dict) else {},
        )

    async def delete_feature(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Delete a feature through circuit breaker.

        Args:
            name (str): Feature or sketch name.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "delete_feature",
            lambda: self.adapter.delete_feature(name),
            input_dict={"name": name},
        )

    async def suppress_feature(
        self, name: str, suppress: bool = True, configurations: str | list[str] = "this"
    ) -> AdapterResult[dict[str, Any]]:
        """Suppress or unsuppress a feature through circuit breaker.

        Args:
            name (str): Feature name.
            suppress (bool): True to suppress, False to unsuppress.
            configurations (str | list[str]): "this", "all" or names.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "suppress_feature",
            lambda: self.adapter.suppress_feature(name, suppress, configurations),
            input_dict={
                "name": name,
                "suppress": suppress,
                "configurations": configurations,
            },
        )

    async def rename_feature(
        self, old_name: str, new_name: str
    ) -> AdapterResult[dict[str, Any]]:
        """Rename a feature through circuit breaker.

        Args:
            old_name (str): Current feature name.
            new_name (str): New feature name.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "rename_feature",
            lambda: self.adapter.rename_feature(old_name, new_name),
            input_dict={"old_name": old_name, "new_name": new_name},
        )

    async def undo(self, count: int = 1) -> AdapterResult[dict[str, Any]]:
        """Undo through circuit breaker.

        Args:
            count (int): Number of steps to undo.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "undo",
            lambda: self.adapter.undo(count),
            input_dict={"count": count},
        )

    async def set_component_state(
        self,
        component: str,
        fixed: bool | None = None,
        flexible: bool | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Set a component's state through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_component_state",
            lambda: self.adapter.set_component_state(component, fixed, flexible),
            input_dict={"component": component, "fixed": fixed, "flexible": flexible},
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
        face_a: list[float] | None = None,
        face_b: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add mate through circuit breaker.

        Args:
            component_a (str): First component instance name.
            component_b (str): Second component instance name.
            entity_a (str): Named feature on the first component. Defaults to
                "Front Plane".
            entity_b (str): Named feature on the second component. Defaults to
                "Front Plane".
            mate_type (str): Mate type. Defaults to "coincident".
            alignment (str): Mate alignment. Defaults to "aligned".
            distance (float): Distance in millimetres. Defaults to 0.0.
            angle (float): Angle in degrees. Defaults to 0.0.
            face_a (list[float] | None): A point on a face of the first
                component, in its part coordinates (mm), instead of entity_a.
            face_b (list[float] | None): The same for the second component.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_circuit_breaker(
            "add_mate",
            lambda: self.adapter.add_mate(
                component_a,
                component_b,
                entity_a,
                entity_b,
                mate_type,
                alignment,
                distance,
                angle,
                face_a,
                face_b,
            ),
            input_dict={
                "component_a": component_a,
                "component_b": component_b,
                "entity_a": entity_a,
                "entity_b": entity_b,
                "mate_type": mate_type,
                "alignment": alignment,
                "distance": distance,
                "angle": angle,
                "face_a": face_a,
                "face_b": face_b,
            },
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

    # --- Engineering-data and drawing-documentation methods ---

    async def list_model_dimensions(
        self,
        feature_name: str | None = None,
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List every dimension in the active part or assembly through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_model_dimensions",
            lambda: self.adapter.list_model_dimensions(feature_name),
            input_dict={"feature_name": feature_name},
            error_results_are_failures=False,
        )

    async def measure_entities(
        self,
        entities: list[str],
    ) -> AdapterResult[dict[str, Any]]:
        """Measure one or two selected entities through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "measure_entities",
            lambda: self.adapter.measure_entities(entities),
            input_dict={"entities": entities},
            error_results_are_failures=False,
        )

    async def get_material(
        self,
        configuration: str | None = None,
        material: str | None = None,
        database: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Read a part's or a library material through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_material",
            lambda: self.adapter.get_material(configuration, material, database),
            input_dict={
                "configuration": configuration,
                "material": material,
                "database": database,
            },
            error_results_are_failures=False,
        )

    async def set_material(
        self,
        material_name: str,
        database: str | None = None,
        configuration: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Assign a material to the active part through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_material",
            lambda: self.adapter.set_material(material_name, database, configuration),
            input_dict={
                "material_name": material_name,
                "database": database,
                "configuration": configuration,
            },
        )

    async def list_available_materials(
        self,
        search: str | None = None,
    ) -> AdapterResult[list[dict[str, str]]]:
        """List materials from the configured material libraries through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_available_materials",
            lambda: self.adapter.list_available_materials(search),
            input_dict={"search": search},
            error_results_are_failures=False,
        )

    async def get_custom_properties(
        self,
        configuration: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Read the custom properties of the active document through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_custom_properties",
            lambda: self.adapter.get_custom_properties(configuration),
            input_dict={"configuration": configuration},
            error_results_are_failures=False,
        )

    async def set_custom_property(
        self,
        name: str,
        value: str,
        configuration: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Create or overwrite one custom property through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_custom_property",
            lambda: self.adapter.set_custom_property(name, value, configuration),
            input_dict={"name": name, "value": value, "configuration": configuration},
        )

    async def export_flat_pattern(
        self,
        file_path: str,
    ) -> AdapterResult[dict[str, Any]]:
        """Export the active sheet-metal part's flat pattern through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "export_flat_pattern",
            lambda: self.adapter.export_flat_pattern(file_path),
            input_dict={"file_path": file_path},
        )

    async def insert_model_dimensions(
        self,
        view_name: str | None = None,
        include_hole_wizard: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Bring model dimensions into drawing views through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "insert_model_dimensions",
            lambda: self.adapter.insert_model_dimensions(
                view_name, include_hole_wizard
            ),
            input_dict={
                "view_name": view_name,
                "include_hole_wizard": include_hole_wizard,
            },
        )

    async def arrange_dimensions(
        self,
        view_name: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Move drawing dimensions so none overlaps, then verify through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "arrange_dimensions",
            lambda: self.adapter.arrange_dimensions(view_name),
            input_dict={"view_name": view_name},
        )

    async def insert_bom_table(
        self,
        view_name: str,
        template_path: str | None = None,
        bom_type: str = "top_level_only",
        x_mm: float | None = None,
        y_mm: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Insert a BOM table anchored to an assembly drawing view through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "insert_bom_table",
            lambda: self.adapter.insert_bom_table(
                view_name, template_path, bom_type, x_mm, y_mm
            ),
            input_dict={
                "view_name": view_name,
                "template_path": template_path,
                "bom_type": bom_type,
                "x_mm": x_mm,
                "y_mm": y_mm,
            },
        )

    async def set_sheet_scale(
        self,
        numerator: float,
        denominator: float,
    ) -> AdapterResult[dict[str, Any]]:
        """Set the active drawing sheet's scale through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_sheet_scale",
            lambda: self.adapter.set_sheet_scale(numerator, denominator),
            input_dict={"numerator": numerator, "denominator": denominator},
        )

    async def add_gtol(
        self,
        characteristic: str,
        tolerance: float,
        x_mm: float,
        y_mm: float,
        diameter_zone: bool = False,
        material_condition: str = "none",
        datums: list[str] | None = None,
        attach_at_mm: tuple[float, float] | None = None,
        dimension: tuple[str, str] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a GD&T feature control frame through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_gtol",
            lambda: self.adapter.add_gtol(
                characteristic,
                tolerance,
                x_mm,
                y_mm,
                diameter_zone,
                material_condition,
                datums,
                attach_at_mm,
                dimension,
            ),
            input_dict={
                "characteristic": characteristic,
                "tolerance": tolerance,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "diameter_zone": diameter_zone,
                "material_condition": material_condition,
                "datums": datums,
                "attach_at_mm": attach_at_mm,
                "dimension": dimension,
            },
        )

    async def add_datum_tag(
        self,
        label: str,
        attach_at_mm: tuple[float, float],
        x_mm: float,
        y_mm: float,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a datum feature symbol through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_datum_tag",
            lambda: self.adapter.add_datum_tag(label, attach_at_mm, x_mm, y_mm),
            input_dict={
                "label": label,
                "attach_at_mm": attach_at_mm,
                "x_mm": x_mm,
                "y_mm": y_mm,
            },
        )

    async def create_standard_drawing(
        self,
        model_path: str,
        output_dir: str | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        drawing_number: str | None = None,
        author: str = "",
        revision: str = "A",
        company: str = "",
        drawn_date: str | None = None,
        notes: list[str] | None = None,
        include_isometric: bool = True,
        write_model_properties: bool = True,
        title_block_text_height_mm: float | None = None,
        include_bom: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Create a complete standard A3 drawing through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_standard_drawing",
            lambda: self.adapter.create_standard_drawing(
                model_path,
                output_dir,
                title,
                subtitle,
                drawing_number,
                author,
                revision,
                company,
                drawn_date,
                notes,
                include_isometric,
                write_model_properties,
                title_block_text_height_mm,
                include_bom,
            ),
            input_dict={
                "model_path": model_path,
                "output_dir": output_dir,
                "title": title,
                "subtitle": subtitle,
                "drawing_number": drawing_number,
                "author": author,
                "revision": revision,
                "company": company,
                "drawn_date": drawn_date,
                "notes": notes,
                "include_isometric": include_isometric,
                "write_model_properties": write_model_properties,
                "title_block_text_height_mm": title_block_text_height_mm,
                "include_bom": include_bom,
            },
        )


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
