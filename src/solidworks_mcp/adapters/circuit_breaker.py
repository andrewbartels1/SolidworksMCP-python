"""
Circuit breaker adapter for SolidWorks operations.

Implements the circuit breaker pattern to prevent cascading failures
when SolidWorks operations fail repeatedly.
"""

import asyncio
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


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, blocking requests
    HALF_OPEN = "half_open"  # Testing if service is back


class CircuitBreakerAdapter(SolidWorksAdapter):
    """Circuit breaker wrapper for SolidWorks adapters."""

    def __init__(
        self,
        adapter: SolidWorksAdapter | None = None,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        config: dict[str, object] | None = None,
    ) -> None:
        """Initialize this object.

        Args:
            adapter (SolidWorksAdapter | None): Describe adapter.
            failure_threshold (int): Describe failure threshold.
            recovery_timeout (int): Describe recovery timeout.
            half_open_max_calls (int): Describe half open max calls.
            config (dict[str, object] | None): Describe config.

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
        """Invoke adapter method with args, retrying without args on signature mismatch."""
        try:
            return await method(*args)
        except TypeError:
            return await method()

    def _should_allow_request(self) -> bool:
        """Check if request should be allowed through circuit breaker."""
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
        """Record successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            # Reset circuit breaker on success in half-open state
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _record_failure(self) -> None:
        """Record failed operation."""
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
    ) -> AdapterResult[T]:
        """Execute operation with circuit breaker logic."""
        if not self._should_allow_request():
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker is {self.state.value} for {operation_name}",
                metadata={"circuit_state": self.state.value},
            )

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1

        try:
            result = await operation()
            if result.is_success:
                self._record_success()
            else:
                self._record_failure()
            return result
        except Exception as e:
            self._record_failure()
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Circuit breaker caught exception in {operation_name}: {e}",
                metadata={"circuit_state": self.state.value},
            )

    # Adapter interface implementation

    async def connect(self) -> None:
        """Connect through circuit breaker."""
        if not self._should_allow_request():
            raise Exception(f"Circuit breaker is {self.state.value}")

        try:
            await self.adapter.connect()
            self._record_success()
        except Exception as e:
            self._record_failure()
            raise

    async def disconnect(self) -> None:
        """Disconnect - always allowed."""
        await self.adapter.disconnect()

    def is_connected(self) -> bool:
        """Check connection status."""
        return self.adapter.is_connected()

    async def health_check(self) -> AdapterHealth:
        """Get health check with circuit breaker status."""
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
        """Open model through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "open_model", lambda: self.adapter.open_model(file_path)
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close model through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "close_model", lambda: self.adapter.close_model(save)
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save model through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "save_file", lambda: self.adapter.save_file(file_path)
        )

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Execute a macro through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "execute_macro", lambda: self.adapter.execute_macro(params)
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create part through circuit breaker."""

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Execute op.

            Returns:
                AdapterResult[SolidWorksModel]: Describe the returned value.

            """
            if name is None and units is None:
                return await self.adapter.create_part()
            return await self._invoke_with_optional_args(
                self.adapter.create_part,
                name,
                units,
            )

        return await self._execute_with_circuit_breaker("create_part", _op)

    async def call(self, operation: Callable[[], object | Awaitable[object]]) -> object:
        """Legacy call API used by tests."""
        if not self._should_allow_request():
            raise Exception("Circuit breaker is open")
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create assembly through circuit breaker."""

        async def _op() -> AdapterResult[SolidWorksModel]:
            """Execute op.

            Returns:
                AdapterResult[SolidWorksModel]: Describe the returned value.

            """
            if name is None:
                return await self.adapter.create_assembly()
            return await self._invoke_with_optional_args(
                self.adapter.create_assembly,
                name,
            )

        return await self._execute_with_circuit_breaker("create_assembly", _op)

    async def create_drawing(self) -> AdapterResult[SolidWorksModel]:
        """Create drawing through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_drawing", lambda: self.adapter.create_drawing()
        )

    # Feature operations

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create extrusion through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_extrusion", lambda: self.adapter.create_extrusion(params)
        )

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create revolve through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_revolve", lambda: self.adapter.create_revolve(params)
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create sweep through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_sweep", lambda: self.adapter.create_sweep(params)
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create loft through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_loft", lambda: self.adapter.create_loft(params)
        )

    # Sketch operations

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create sketch through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "create_sketch", lambda: self.adapter.create_sketch(plane)
        )

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add line through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_line", lambda: self.adapter.add_line(x1, y1, x2, y2)
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add centerline through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_centerline", lambda: self.adapter.add_centerline(x1, y1, x2, y2)
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add circle through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_circle", lambda: self.adapter.add_circle(center_x, center_y, radius)
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add rectangle through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "add_rectangle", lambda: self.adapter.add_rectangle(x1, y1, x2, y2)
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit sketch through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "exit_sketch", lambda: self.adapter.exit_sketch()
        )

    # Analysis operations

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_mass_properties", lambda: self.adapter.get_mass_properties()
        )

    async def get_model_info(self) -> AdapterResult[dict[str, object]]:
        """Get active model metadata through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_model_info", lambda: self.adapter.get_model_info()
        )

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, object]]]:
        """List model features through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_features",
            lambda: self.adapter.list_features(include_suppressed),
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List model configurations through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "list_configurations",
            lambda: self.adapter.list_configurations(),
        )

    # Export operations

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export file through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "export_file", lambda: self.adapter.export_file(file_path, format_type)
        )

    # Dimension operations

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get dimension through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "get_dimension", lambda: self.adapter.get_dimension(name)
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set dimension through circuit breaker."""
        return await self._execute_with_circuit_breaker(
            "set_dimension", lambda: self.adapter.set_dimension(name, value)
        )


class CircuitBreaker:
    """Legacy standalone circuit breaker class expected by tests."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        """Initialize this object.

        Args:
            failure_threshold (int): Describe failure threshold.
            recovery_timeout (float): Describe recovery timeout.
            expected_exception (type[Exception]): Describe expected exception.

        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0

    async def call(self, operation: Callable[[], object | Awaitable[object]]) -> object:
        """Execute call.

        Args:
            operation (Callable[[], object | Awaitable[object]]): Describe operation.

        Returns:
            object: Describe the returned value.

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
