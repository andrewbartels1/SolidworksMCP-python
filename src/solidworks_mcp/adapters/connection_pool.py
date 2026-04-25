"""Connection pool adapter for managing multiple SolidWorks connections.

Provides connection pooling capabilities to allow parallel SolidWorks operations when
multiple instances are available.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar, cast

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
    """Connection pool wrapper for SolidWorks adapters.

    Args:
        adapter_factory (Callable[[], SolidWorksAdapter] | None): Factory callable used to
                                                                  create adapter instances.
                                                                  Defaults to None.
        pool_size (int): Number of adapters to maintain in the pool. Defaults to 3.
        max_retries (int): Maximum number of retry attempts. Defaults to 3.
        create_connection (Callable[[], SolidWorksAdapter] | None): Factory callable used to
                                                                    create a connection.
                                                                    Defaults to None.
        max_size (int | None): Maximum number of items allowed in the pool. Defaults to
                               None.
        timeout (float | None): Maximum time to wait in seconds. Defaults to None.
        config (dict[str, object] | None): Configuration values for the operation. Defaults
                                           to None.

    Attributes:
        _lock (Any): The lock value.
        adapter_factory (Any): The adapter factory value.
        max_retries (Any): The max retries value.
        pool_initialized (Any): The pool initialized value.
        pool_size (Any): The pool size value.
        timeout (Any): The timeout value.
    """

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
        """Initialize the connection pool adapter.

        Args:
            adapter_factory (Callable[[], SolidWorksAdapter] | None): Factory callable used to
                                                                      create adapter instances.
                                                                      Defaults to None.
            pool_size (int): Number of adapters to maintain in the pool. Defaults to 3.
            max_retries (int): Maximum number of retry attempts. Defaults to 3.
            create_connection (Callable[[], SolidWorksAdapter] | None): Factory callable used to
                                                                        create a connection.
                                                                        Defaults to None.
            max_size (int | None): Maximum number of items allowed in the pool. Defaults to
                                   None.
            timeout (float | None): Maximum time to wait in seconds. Defaults to None.
            config (dict[str, object] | None): Configuration values for the operation. Defaults
                                               to None.

        Returns:
            None: None.
        """
        if adapter_factory is None and create_connection is not None:
            adapter_factory = create_connection
        if max_size is not None:
            pool_size = max_size
        if adapter_factory is None:
            from .mock_adapter import MockSolidWorksAdapter

            def adapter_factory():
                """Provide adapter factory support for the connection pool adapter.

                Returns:
                    Any: The result produced by the operation.
                """

                return MockSolidWorksAdapter(config or {})

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
        """Run an async operation and return default on failure.

        Args:
            operation (Callable[[], Awaitable[T]]): Callable object executed by the helper.
            default (T | None): Fallback value returned when the operation fails. Defaults to
                                None.

        Returns:
            T | None: The result produced by the operation.
        """
        try:
            return await operation()
        except Exception:
            return default

    async def _attempt_async_with_error(
        self, operation: Callable[[], Awaitable[T]]
    ) -> tuple[T | None, Exception | None]:
        """Run an async operation and return (result, error).

        Args:
            operation (Callable[[], Awaitable[T]]): Callable object executed by the helper.

        Returns:
            tuple[T | None, Exception | None]: A tuple containing the resulting values.
        """
        try:
            return await operation(), None
        except Exception as exc:
            return None, exc

    def _attempt_sync(
        self, operation: Callable[[], T], default: T | None = None
    ) -> T | None:
        """Run a sync operation and return default on failure.

        Args:
            operation (Callable[[], T]): Callable object executed by the helper.
            default (T | None): Fallback value returned when the operation fails. Defaults to
                                None.

        Returns:
            T | None: The result produced by the operation.
        """
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
        """Invoke adapter method with args, retrying without args on signature mismatch.

        Args:
            adapter (SolidWorksAdapter): Adapter instance used for the operation.
            method_name (str): Name of the method to invoke.
            *args (object): Additional positional arguments forwarded to the call.

        Returns:
            object: The result produced by the operation.
        """
        method = getattr(adapter, method_name)
        try:
            return await method(*args)
        except TypeError:
            return await method()

    async def _replace_failed_adapter(self) -> Exception | None:
        """Create, connect, and return a replacement adapter.

        Returns None on success, or the captured exception on failure.

        Returns:
            Exception | None: The result produced by the operation.
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
        """Provide size support for the connection pool adapter.

        Returns:
            int: The computed numeric result.
        """
        return len(self.pool)

    @property
    def active_connections(self) -> int:
        """Provide active connections support for the connection pool adapter.

        Returns:
            int: The computed numeric result.
        """
        return max(0, len(self.pool) - self.available_adapters.qsize())

    async def acquire(self) -> SolidWorksAdapter:
        """Provide acquire support for the connection pool adapter.

        Returns:
            SolidWorksAdapter: The result produced by the operation.
        """
        return await self._get_adapter(timeout=self.timeout)

    async def release(self, adapter: SolidWorksAdapter) -> None:
        """Provide release support for the connection pool adapter.

        Args:
            adapter (SolidWorksAdapter): Adapter instance used for the operation.

        Returns:
            None: None.
        """
        await self._return_adapter(adapter)

    async def cleanup(self) -> None:
        """Provide cleanup support for the connection pool adapter.

        Returns:
            None: None.
        """
        await self.disconnect()

    async def _initialize_pool(self) -> None:
        """Initialize the connection pool.

        Returns:
            None: None.
        """
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
        """Get an available adapter from the pool.

        Args:
            timeout (float): Maximum time to wait in seconds. Defaults to 30.0.

        Returns:
            SolidWorksAdapter: The result produced by the operation.

        Raises:
            Exception: If the operation cannot be completed.
        """
        await self._initialize_pool()

        try:
            adapter = await asyncio.wait_for(
                self.available_adapters.get(), timeout=timeout
            )
            return adapter
        except TimeoutError as err:
            raise Exception(f"No adapter available within {timeout} seconds") from err

    async def _return_adapter(self, adapter: SolidWorksAdapter) -> None:
        """Return an adapter to the pool.

        Args:
            adapter (SolidWorksAdapter): Adapter instance used for the operation.

        Returns:
            None: None.
        """
        await self.available_adapters.put(adapter)

    async def _execute_with_pool(
        self,
        operation_name: str,
        operation: Callable[[SolidWorksAdapter], Awaitable[AdapterResult[T]]],
    ) -> AdapterResult[T]:
        """Build internal execute with pool.

        Args:
            operation_name (str): The operation name value.
            operation (Callable[[SolidWorksAdapter], Awaitable[AdapterResult[T]]]): Callable
                                                                                    object
                                                                                    executed by
                                                                                    the helper.

        Returns:
            AdapterResult[T]: The result produced by the operation.
        """
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
                    await self._attempt_async(lambda a=adapter: a.disconnect())

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
        """Initialize the connection pool.

        Returns:
            None: None.
        """
        await self._initialize_pool()

    async def disconnect(self) -> None:
        """Disconnect all adapters in the pool.

        Returns:
            None: None.
        """
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
        """Check if pool is initialized.

        Returns:
            bool: True if connected, otherwise False.
        """
        return self.pool_initialized and len(self.pool) > 0

    async def health_check(self) -> AdapterHealth:
        """Get health status of the connection pool.

        Returns:
            AdapterHealth: The result produced by the operation.
        """
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
        """Open model using pool.

        Args:
            file_path (str): Path to the target file.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "open_model", lambda adapter: adapter.open_model(file_path)
        )

    async def close_model(self, save: bool = False) -> AdapterResult[None]:
        """Close model using pool.

        Args:
            save (bool): The save value. Defaults to False.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "close_model", lambda adapter: adapter.close_model(save)
        )

    async def save_file(self, file_path: str | None = None) -> AdapterResult[None]:
        """Save model using pool.

        Args:
            file_path (str | None): Path to the target file. Defaults to None.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "save_file", lambda adapter: adapter.save_file(file_path)
        )

    async def create_part(
        self, name: str | None = None, units: str | None = None
    ) -> AdapterResult[SolidWorksModel]:
        """Create part using pool.

        Args:
            name (str | None): The name value. Defaults to None.
            units (str | None): The units value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op(adapter: SolidWorksAdapter) -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Args:
                adapter (SolidWorksAdapter): Adapter instance used for the operation.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
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
        """Create assembly using pool.

        Args:
            name (str | None): The name value. Defaults to None.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """

        async def _op(adapter: SolidWorksAdapter) -> AdapterResult[SolidWorksModel]:
            """Build internal op.

            Args:
                adapter (SolidWorksAdapter): Adapter instance used for the operation.

            Returns:
                AdapterResult[SolidWorksModel]: The result produced by the operation.
            """
            if name is None:
                return await adapter.create_assembly()
            result = await self._invoke_with_optional_args(
                adapter, "create_assembly", name
            )
            return cast(AdapterResult[SolidWorksModel], result)

        return await self._execute_with_pool("create_assembly", _op)

    async def create_drawing(self) -> AdapterResult[SolidWorksModel]:
        """Create drawing using pool.

        Returns:
            AdapterResult[SolidWorksModel]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_drawing", lambda adapter: adapter.create_drawing()
        )

    # Feature operations

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create extrusion using pool.

        Args:
            params (ExtrusionParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_extrusion", lambda adapter: adapter.create_extrusion(params)
        )

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create revolve using pool.

        Args:
            params (RevolveParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_revolve", lambda adapter: adapter.create_revolve(params)
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create sweep using pool.

        Args:
            params (SweepParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_sweep", lambda adapter: adapter.create_sweep(params)
        )

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Create loft using pool.

        Args:
            params (LoftParameters): The params value.

        Returns:
            AdapterResult[SolidWorksFeature]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_loft", lambda adapter: adapter.create_loft(params)
        )

    # Sketch operations

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        """Create sketch using pool.

        Args:
            plane (str): The plane value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "create_sketch", lambda adapter: adapter.create_sketch(plane)
        )

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add line using pool.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "add_line", lambda adapter: adapter.add_line(x1, y1, x2, y2)
        )

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add centerline using pool.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "add_centerline",
            lambda adapter: adapter.add_centerline(x1, y1, x2, y2),
        )

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        """Add circle using pool.

        Args:
            center_x (float): The center x value.
            center_y (float): The center y value.
            radius (float): The radius value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "add_circle", lambda adapter: adapter.add_circle(center_x, center_y, radius)
        )

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        """Add rectangle using pool.

        Args:
            x1 (float): The x1 value.
            y1 (float): The y1 value.
            x2 (float): The x2 value.
            y2 (float): The y2 value.

        Returns:
            AdapterResult[str]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "add_rectangle", lambda adapter: adapter.add_rectangle(x1, y1, x2, y2)
        )

    async def exit_sketch(self) -> AdapterResult[None]:
        """Exit sketch using pool.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "exit_sketch", lambda adapter: adapter.exit_sketch()
        )

    # Analysis operations

    async def get_mass_properties(self) -> AdapterResult[MassProperties]:
        """Get mass properties using pool.

        Returns:
            AdapterResult[MassProperties]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "get_mass_properties", lambda adapter: adapter.get_mass_properties()
        )

    async def get_model_info(self) -> AdapterResult[dict[str, object]]:
        """Get active model metadata using pool.

        Returns:
            AdapterResult[dict[str, object]]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "get_model_info", lambda adapter: adapter.get_model_info()
        )

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, object]]]:
        """List model features using pool.

        Args:
            include_suppressed (bool): The include suppressed value. Defaults to False.

        Returns:
            AdapterResult[list[dict[str, object]]]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "list_features",
            lambda adapter: adapter.list_features(include_suppressed),
        )

    async def list_configurations(self) -> AdapterResult[list[str]]:
        """List model configurations using pool.

        Returns:
            AdapterResult[list[str]]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "list_configurations", lambda adapter: adapter.list_configurations()
        )

    async def execute_macro(
        self, params: dict[str, Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Provide execute macro support for the connection pool adapter.

        Args:
            params (dict[str, Any]): The params value.

        Returns:
            AdapterResult[dict[str, Any]]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "execute_macro", lambda adapter: adapter.execute_macro(params)
        )

    # Export operations

    async def export_image(self, payload: dict) -> AdapterResult[dict]:
        """Export viewport image using pool.

        Args:
            payload (dict): The payload value.

        Returns:
            AdapterResult[dict]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "export_image", lambda adapter: adapter.export_image(payload)
        )

    async def export_file(
        self, file_path: str, format_type: str
    ) -> AdapterResult[None]:
        """Export file using pool.

        Args:
            file_path (str): Path to the target file.
            format_type (str): The format type value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "export_file", lambda adapter: adapter.export_file(file_path, format_type)
        )

    # Dimension operations

    async def get_dimension(self, name: str) -> AdapterResult[float]:
        """Get dimension using pool.

        Args:
            name (str): The name value.

        Returns:
            AdapterResult[float]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "get_dimension", lambda adapter: adapter.get_dimension(name)
        )

    async def set_dimension(self, name: str, value: float) -> AdapterResult[None]:
        """Set dimension using pool.

        Args:
            name (str): The name value.
            value (float): The value value.

        Returns:
            AdapterResult[None]: The result produced by the operation.
        """
        return await self._execute_with_pool(
            "set_dimension", lambda adapter: adapter.set_dimension(name, value)
        )


class ConnectionPool:
    """Legacy alias class expected by tests.

    Args:
        create_connection (Callable[[], object | Awaitable[object]]): Factory callable used
                                                                      to create a
                                                                      connection.
        max_size (int): Maximum number of items allowed in the pool. Defaults to 3.
        timeout (float): Maximum time to wait in seconds. Defaults to 30.0.

    Attributes:
        _create_connection (Any): The create connection value.
        _max_size (Any): The max size value.
        _timeout (Any): The timeout value.
    """

    def __init__(
        self,
        create_connection: Callable[[], object | Awaitable[object]],
        max_size: int = 3,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the connection pool.

        Args:
            create_connection (Callable[[], object | Awaitable[object]]): Factory callable used
                                                                          to create a
                                                                          connection.
            max_size (int): Maximum number of items allowed in the pool. Defaults to 3.
            timeout (float): Maximum time to wait in seconds. Defaults to 30.0.

        Returns:
            None: None.
        """
        self._create_connection = create_connection
        self._max_size = max_size
        self._timeout = timeout
        self._available: list[object] = []
        self._in_use: set[int] = set()
        self._all_connections: list[object] = []

    @property
    def size(self) -> int:
        """Provide size support for the connection pool.

        Returns:
            int: The computed numeric result.
        """
        return len(self._all_connections)

    @property
    def active_connections(self) -> int:
        """Provide active connections support for the connection pool.

        Returns:
            int: The computed numeric result.
        """
        return len(self._in_use)

    async def _new_connection(self) -> object:
        """Build internal new connection.

        Returns:
            object: The result produced by the operation.
        """
        conn = self._create_connection()
        if asyncio.iscoroutine(conn):
            conn = await conn
        self._all_connections.append(conn)
        return conn

    async def acquire(self) -> object:
        """Provide acquire support for the connection pool.

        Returns:
            object: The result produced by the operation.

        Raises:
            TimeoutError: No connection available within timeout.
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
        """Provide release support for the connection pool.

        Args:
            conn (object): The conn value.

        Returns:
            None: None.
        """
        conn_id = id(conn)
        if conn_id in self._in_use:
            self._in_use.remove(conn_id)
            self._available.append(conn)

    async def cleanup(self) -> None:
        """Provide cleanup support for the connection pool.

        Returns:
            None: None.
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
