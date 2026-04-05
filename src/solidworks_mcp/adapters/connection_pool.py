"""
Connection pool adapter for managing multiple SolidWorks connections.

Provides connection pooling capabilities to allow parallel SolidWorks operations
when multiple instances are available.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar, cast, Any
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


class ConnectionPoolAdapter(SolidWorksAdapter):
    """Connection pool wrapper for SolidWorks adapters."""

    def __init__(
        self,
        adapter_factory: Callable[[], SolidWorksAdapter] | None = None,
        pool_size: int = 3,
        max_retries: int = 3,
        create_connection: Callable[[], SolidWorksAdapter] | None = None,
        max_size: int | None = None,
        timeout: float | None = None,
        config: dict[str, object] | None = None,
    ) -> None:
        """Initialize this object.

        Args:
            adapter_factory (Callable[[], SolidWorksAdapter] | None): Describe adapter factory.
            pool_size (int): Describe pool size.
            max_retries (int): Describe max retries.
            create_connection (Callable[[], SolidWorksAdapter] | None): Describe create connection.
            max_size (int | None): Describe max size.
            timeout (float | None): Describe timeout.
            config (dict[str, object] | None): Describe config.

        """
        if adapter_factory is None and create_connection is not None:
            adapter_factory = create_connection
        if max_size is not None:
            pool_size = max_size
        if adapter_factory is None:
            from .mock_adapter import MockSolidWorksAdapter

            adapter_factory = lambda: MockSolidWorksAdapter(config or {})
        super().__init__(config)
        self.adapter_factory = adapter_factory
        self.pool_size = pool_size
        self.max_retries = max_retries

        self.pool: list[SolidWorksAdapter] = []
        self.available_adapters: asyncio.Queue[SolidWorksAdapter] = asyncio.Queue()
        self.pool_initialized = False
        self._lock = asyncio.Lock()
        self.timeout = timeout if timeout is not None else 30.0

    async def _attempt_async(
        self, operation: Callable[[], Awaitable[T]], default: T | None = None
    ) -> T | None:
        """Run an async operation and return default on failure."""
        try:
            return await operation()
        except Exception:
            return default

    async def _attempt_async_with_error(
        self, operation: Callable[[], Awaitable[T]]
    ) -> tuple[T | None, Exception | None]:
        """Run an async operation and return (result, error)."""
        try:
            return await operation(), None
        except Exception as exc:
            return None, exc

    def _attempt_sync(
        self, operation: Callable[[], T], default: T | None = None
    ) -> T | None:
        """Run a sync operation and return default on failure."""
        try:
            return operation()
        except Exception:
            return default

    async def _invoke_with_optional_args(
        self,
        adapter: SolidWorksAdapter,
        method_name: str,
        *args: object,
    ) -> object:
        """Invoke adapter method with args, retrying without args on signature mismatch."""
        method = getattr(adapter, method_name)
        try:
            return await method(*args)
        except TypeError:
            return await method()

    async def _replace_failed_adapter(self) -> Exception | None:
        """Create, connect, and return a replacement adapter.

        Returns None on success, or the captured exception on failure.
        """
        try:
            new_adapter = self.adapter_factory()
            await new_adapter.connect()
            await self._return_adapter(new_adapter)
            return None
        except Exception as exc:
            return exc

    @property
    def size(self) -> int:
        """Execute size.

        Returns:
            int: Describe the returned value.

        """
        return len(self.pool)

    @property
    def active_connections(self) -> int:
        """Execute active connections.

        Returns:
            int: Describe the returned value.

        """
        return max(0, len(self.pool) - self.available_adapters.qsize())

    async def acquire(self) -> SolidWorksAdapter:
        """Execute acquire.

        Returns:
            SolidWorksAdapter: Describe the returned value.

        """
        return await self._get_adapter(timeout=self.timeout)

    async def release(self, adapter: SolidWorksAdapter) -> None:
        """Execute release.

        Args:
            adapter (SolidWorksAdapter): Describe adapter.

        Returns:
            None: Describe the returned value.

        """
        await self._return_adapter(adapter)

    async def cleanup(self) -> None:
        """Execute cleanup.

        Returns:
            None: Describe the returned value.

        """
        await self.disconnect()

    async def _initialize_pool(self) -> None:
        """Initialize the connection pool."""
        if self.pool_initialized:
            return

        async with self._lock:
            if self.pool_initialized:
                return

            logger.info(f"Initializing connection pool with {self.pool_size} adapters")

            for i in range(self.pool_size):
                try:
                    adapter = self.adapter_factory()
                    await adapter.connect()
                    self.pool.append(adapter)
                    await self.available_adapters.put(adapter)
                    logger.debug(f"Initialized adapter {i + 1}/{self.pool_size}")
                except Exception as e:
                    logger.warning(f"Failed to initialize adapter {i + 1}: {e}")

            self.pool_initialized = True
            logger.info(f"Connection pool initialized with {len(self.pool)} adapters")

    async def _get_adapter(self, timeout: float = 30.0) -> SolidWorksAdapter:
        """Get an available adapter from the pool."""
        await self._initialize_pool()

        try:
            adapter = await asyncio.wait_for(
                self.available_adapters.get(), timeout=timeout
            )
            return adapter
        except asyncio.TimeoutError:
            raise Exception(f"No adapter available within {timeout} seconds")

    async def _return_adapter(self, adapter: SolidWorksAdapter) -> None:
        """Return an adapter to the pool."""
        await self.available_adapters.put(adapter)

    async def _execute_with_pool(
        self,
        operation_name: str,
        operation: Callable[[SolidWorksAdapter], Awaitable[AdapterResult[T]]],
    ) -> AdapterResult[T]:
        """Execute operation using an adapter from the pool."""
        retries = 0
        last_error = None

        while retries <= self.max_retries:
            adapter = None
            try:
                adapter = await self._get_adapter()
                result = await operation(adapter)

                # Return adapter to pool
                await self._return_adapter(adapter)

                return result

            except Exception as e:
                last_error = e
                retries += 1

                logger.warning(
                    f"Operation {operation_name} failed (attempt {retries}): {e}"
                )

                if adapter:
                    # Don't return failed adapter to pool, create a new one
                    await self._attempt_async(lambda: adapter.disconnect())

                    replacement_error = await self._attempt_async(
                        self._replace_failed_adapter
                    )
                    if replacement_error is not None:
                        logger.error(
                            f"Failed to create replacement adapter: {replacement_error}"
                        )

                if retries <= self.max_retries:
                    await asyncio.sleep(1.0 * retries)  # Exponential backoff

        # All retries exhausted
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=f"Operation {operation_name} failed after {self.max_retries} retries: {last_error}",
        )

    # Adapter interface implementation

    async def connect(self) -> None:
        """Initialize the connection pool."""
        await self._initialize_pool()

    async def disconnect(self) -> None:
        """Disconnect all adapters in the pool."""
        for adapter in self.pool:
            _, error = await self._attempt_async_with_error(
                lambda current_adapter=adapter: current_adapter.disconnect()
            )
            if error is not None:
                logger.warning(f"Error disconnecting adapter: {error}")

        self.pool.clear()

        # Clear the queue
        while not self.available_adapters.empty():
            try:
                self.available_adapters.get_nowait()
            except asyncio.QueueEmpty:
                break

        self.pool_initialized = False

    def is_connected(self) -> bool:
        """Check if pool is initialized."""
        return self.pool_initialized and len(self.pool) > 0

    async def health_check(self) -> AdapterHealth:
        """Get health status of the connection pool."""
        healthy_count = 0
        total_response_time = 0

        if not self.pool_initialized:
            return AdapterHealth(
                healthy=False,
                last_check=datetime.now(),
                error_count=0,
                success_count=0,
                average_response_time=0,
                connection_status="pool_not_initialized",
                metrics={
                    "pool_size": 0,
                    "available_adapters": 0,
                    "healthy_adapters": 0,
                },
            )

        # Check health of all adapters
        for adapter in self.pool:
            health = await self._attempt_async(
                lambda current_adapter=adapter: current_adapter.health_check()
            )
            if not health:
                continue
            if health.healthy:
                healthy_count += 1
            total_response_time += health.average_response_time

        avg_response_time = total_response_time / len(self.pool) if self.pool else 0

        return AdapterHealth(
            healthy=healthy_count > 0,
            last_check=datetime.now(),
            error_count=len(self.pool) - healthy_count,
            success_count=healthy_count,
            average_response_time=avg_response_time,
            connection_status="pooled",
            metrics={
                "pool_size": len(self.pool),
                "available_adapters": self.available_adapters.qsize(),
                "healthy_adapters": healthy_count,
            },
        )

    # Model operations

    async def open_model(self, file_path: str) -> AdapterResult[SolidWorksModel]:
        """Open model using pool."""
        return await self._execute_with_pool(
            "open_model", lambda adapter: adapter.open_model(file_path)
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close model using pool."""
        return await self._execute_with_pool(
            "close_model", lambda adapter: adapter.close_model(save)
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save model using pool."""
        return await self._execute_with_pool(
            "save_file", lambda adapter: adapter.save_file(file_path)
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create part using pool."""

        async def _op(adapter: SolidWorksAdapter) -> AdapterResult[SolidWorksModel]:
            """Execute op.

            Args:
                adapter (SolidWorksAdapter): Describe adapter.

            Returns:
                AdapterResult[SolidWorksModel]: Describe the returned value.

            """
            if name is None and units is None:
                return await adapter.create_part()
            result = await self._invoke_with_optional_args(
                adapter, "create_part", name, units
            )
            return cast(AdapterResult[SolidWorksModel], result)

        return await self._execute_with_pool("create_part", _op)

    async def create_assembly(
        self, name: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create assembly using pool."""

        async def _op(adapter: SolidWorksAdapter) -> AdapterResult[SolidWorksModel]:
            """Execute op.

            Args:
                adapter (SolidWorksAdapter): Describe adapter.

            Returns:
                AdapterResult[SolidWorksModel]: Describe the returned value.

            """
            if name is None:
                return await adapter.create_assembly()
            result = await self._invoke_with_optional_args(
                adapter, "create_assembly", name
            )
            return cast(AdapterResult[SolidWorksModel], result)

        return await self._execute_with_pool("create_assembly", _op)

    async def create_drawing(self) -> AdapterResult[SolidWorksModel]:
        """Create drawing using pool."""
        return await self._execute_with_pool(
            "create_drawing", lambda adapter: adapter.create_drawing()
        )

    # Feature operations

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create extrusion using pool."""
        return await self._execute_with_pool(
            "create_extrusion", lambda adapter: adapter.create_extrusion(params)
        )

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create revolve using pool."""
        return await self._execute_with_pool(
            "create_revolve", lambda adapter: adapter.create_revolve(params)
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create sweep using pool."""
        return await self._execute_with_pool(
            "create_sweep", lambda adapter: adapter.create_sweep(params)
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create loft using pool."""
        return await self._execute_with_pool(
            "create_loft", lambda adapter: adapter.create_loft(params)
        )

    # Sketch operations

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create sketch using pool."""
        return await self._execute_with_pool(
            "create_sketch", lambda adapter: adapter.create_sketch(plane)
        )

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add line using pool."""
        return await self._execute_with_pool(
            "add_line", lambda adapter: adapter.add_line(x1, y1, x2, y2)
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add centerline using pool."""
        return await self._execute_with_pool(
            "add_centerline",
            lambda adapter: adapter.add_centerline(x1, y1, x2, y2),
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add circle using pool."""
        return await self._execute_with_pool(
            "add_circle", lambda adapter: adapter.add_circle(center_x, center_y, radius)
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add rectangle using pool."""
        return await self._execute_with_pool(
            "add_rectangle", lambda adapter: adapter.add_rectangle(x1, y1, x2, y2)
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit sketch using pool."""
        return await self._execute_with_pool(
            "exit_sketch", lambda adapter: adapter.exit_sketch()
        )

    # Analysis operations

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties using pool."""
        return await self._execute_with_pool(
            "get_mass_properties", lambda adapter: adapter.get_mass_properties()
        )

    async def get_model_info(self) -> AdapterResult[dict[str, object]]:
        """Get active model metadata using pool."""
        return await self._execute_with_pool(
            "get_model_info", lambda adapter: adapter.get_model_info()
        )

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, object]]]:
        """List model features using pool."""
        return await self._execute_with_pool(
            "list_features",
            lambda adapter: adapter.list_features(include_suppressed),
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List model configurations using pool."""
        return await self._execute_with_pool(
            "list_configurations", lambda adapter: adapter.list_configurations()
        )

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Execute a macro using pool."""
        return await self._execute_with_pool(
            "execute_macro", lambda adapter: adapter.execute_macro(params)
        )

    # Export operations

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export file using pool."""
        return await self._execute_with_pool(
            "export_file", lambda adapter: adapter.export_file(file_path, format_type)
        )

    # Dimension operations

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get dimension using pool."""
        return await self._execute_with_pool(
            "get_dimension", lambda adapter: adapter.get_dimension(name)
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set dimension using pool."""
        return await self._execute_with_pool(
            "set_dimension", lambda adapter: adapter.set_dimension(name, value)
        )


class ConnectionPool:
    """Legacy alias class expected by tests."""

    def __init__(
        self,
        create_connection: Callable[[], object | Awaitable[object]],
        max_size: int = 3,
        timeout: float = 30.0,
    ) -> None:
        """Initialize this object.

        Args:
            create_connection (Callable[[], object | Awaitable[object]]): Describe create connection.
            max_size (int): Describe max size.
            timeout (float): Describe timeout.

        """
        self._create_connection = create_connection
        self._max_size = max_size
        self._timeout = timeout
        self._available: list[object] = []
        self._in_use: set[int] = set()
        self._all_connections: list[object] = []

    @property
    def size(self) -> int:
        """Execute size.

        Returns:
            int: Describe the returned value.

        """
        return len(self._all_connections)

    @property
    def active_connections(self) -> int:
        """Execute active connections.

        Returns:
            int: Describe the returned value.

        """
        return len(self._in_use)

    async def _new_connection(self) -> object:
        """Execute new connection.

        Returns:
            object: Describe the returned value.

        """
        conn = self._create_connection()
        if asyncio.iscoroutine(conn):
            conn = await conn
        self._all_connections.append(conn)
        return conn

    async def acquire(self) -> object:
        """Execute acquire.

        Returns:
            object: Describe the returned value.

        """
        if self._available:
            conn = self._available.pop()
            self._in_use.add(id(conn))
            return conn

        if len(self._all_connections) < self._max_size:
            conn = await self._new_connection()
            self._in_use.add(id(conn))
            return conn

        end_time = time.time() + self._timeout
        while time.time() < end_time:
            if self._available:
                conn = self._available.pop()
                self._in_use.add(id(conn))
                return conn
            await asyncio.sleep(0.01)

        raise TimeoutError("No connection available within timeout")

    async def release(self, conn: object) -> None:
        """Execute release.

        Args:
            conn (object): Describe conn.

        Returns:
            None: Describe the returned value.

        """
        conn_id = id(conn)
        if conn_id in self._in_use:
            self._in_use.remove(conn_id)
            self._available.append(conn)

    async def cleanup(self) -> None:
        """Execute cleanup.

        Returns:
            None: Describe the returned value.

        """
        for conn in self._all_connections:
            close = getattr(conn, "close", None)
            if close is None:
                continue
            result = close()
            if asyncio.iscoroutine(result):
                await result

        self._available.clear()
        self._in_use.clear()
        self._all_connections.clear()
