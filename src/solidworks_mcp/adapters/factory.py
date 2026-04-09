"""
Adapter factory for creating SolidWorks adapters.

Provides centralized adapter creation with configuration-based selection
and automatic fallback strategies.
"""

from __future__ import annotations

import platform
from enum import Enum
from typing import Any, Type, Union

from ..config import AdapterType, SolidWorksMCPConfig
from .base import SolidWorksAdapter
from .mock_adapter import MockSolidWorksAdapter
from .vba_adapter import VbaGeneratorAdapter


class AdapterFactory:
    """Factory-pattern adapter creator with singleton and fallback strategies.
    
    Manages adapter registration and creation with configuration-based selection.
    Automatically wraps adapters with decorators (circuit breaker, connection pool)
    based on configuration. Implements singleton pattern for consistency.
    
    Attributes:
        _adapter_registry (dict[AdapterType, type[SolidWorksAdapter]]): Registry
            mapping adapter types to implementation classes.
        _instance (AdapterFactory | None): Singleton instance.
    
    Examples:
        >>> factory = AdapterFactory()
        >>> config = SolidWorksMCPConfig(adapter_type=AdapterType.PYWIN32)
        >>> adapter = factory.create_adapter(config)
        >>> await adapter.connect()
    """

    _adapter_registry: dict[AdapterType, type[SolidWorksAdapter]] = {}
    _adapters: dict[AdapterType, type[SolidWorksAdapter]] = _adapter_registry
    _instance: Union[AdapterFactory, None] = None

    def __new__(cls) -> "AdapterFactory":
        """Initialize or return singleton AdapterFactory instance.
        
        Enforces singleton pattern to ensure single adapter registry and
        consistent factory behavior across application lifetime.
        
        Returns:
            AdapterFactory: The singleton factory instance.
        
        Examples:
            >>> factory1 = AdapterFactory()
            >>> factory2 = AdapterFactory()
            >>> factory1 is factory2
            True
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_adapter(
        cls, adapter_type: AdapterType, adapter_class: type[SolidWorksAdapter]
    ) -> None:
        """Register an adapter class for a given adapter type.
        
        Updates the adapter registry to map a specific AdapterType enum value
        to a SolidWorksAdapter implementation class. Called during initialization
        to register built-in adapters (PyWin32, Mock, etc.).
        
        Args:
            adapter_type (AdapterType): The adapter type enum value.
            adapter_class (type[SolidWorksAdapter]): The adapter implementation
                class to instantiate when this type is requested.
        
        Returns:
            None
        
        Examples:
            >>> from adapters.pywin32_adapter import PyWin32Adapter
            >>> AdapterFactory.register_adapter(
            ...     AdapterType.PYWIN32, PyWin32Adapter
            ... )
        """
        cls._adapter_registry[adapter_type] = adapter_class

    @classmethod
    def create_adapter(cls, config: SolidWorksMCPConfig) -> SolidWorksAdapter:
        """Create and configure a SolidWorks adapter instance.
        
        Determines the best adapter type based on configuration and environment.
        Selects implementation, applies wrappers (circuit breaker, connection pool),
        and returns a fully-initialized adapter ready for connection.
        
        The adapter is automatically downgraded to Mock on non-Windows platforms
        or when testing is enabled, with fallback to configured type otherwise.
        
        Args:
            config (SolidWorksMCPConfig): Server configuration specifying adapter
                type, features, and deployment mode.
        
        Returns:
            SolidWorksAdapter: Initialized adapter instance, possibly wrapped.
        
        Raises:
            ValueError: If the determined adapter type is not registered.
            SolidWorksMCPError: If adapter initialization fails.
        
        Examples:
            >>> config = SolidWorksMCPConfig(mock_solidworks=True)
            >>> adapter = AdapterFactory.create_adapter(config)
            >>> isinstance(adapter, MockSolidWorksAdapter)
            True
        """
        factory = cls()
        return factory._create_adapter_impl(config)

    def _create_adapter_impl(self, config: SolidWorksMCPConfig) -> SolidWorksAdapter:
        """Internal implementation for adapter creation and wrapping.
        
        Handles the core logic of creating base adapter, applying optional
        wrappers (circuit breaker, connection pooling), and returning final
        adapter configured for use.
        
        Args:
            config (SolidWorksMCPConfig): Configuration with adapter selection
                and wrapper preferences.
        
        Returns:
            SolidWorksAdapter: Base or wrapped adapter ready for use.
        
        Raises:
            ValueError: If adapter type not registered in registry.
        """
        # Determine the best adaptertype
        adapter_type = self._determine_adapter_type(config)

        # Get adapter class
        if adapter_type not in self._adapter_registry:
            raise ValueError(f"Adaptertype {adapter_type} not registered")

        adapter_class = self._adapter_registry[adapter_type]

        # Create base adapter
        if adapter_type == AdapterType.VBA:
            backing_type = self._determine_vba_backing_type(config)
            if backing_type not in self._adapter_registry:
                raise ValueError(f"Backing adapter type {backing_type} not registered")

            backing_class = self._adapter_registry[backing_type]
            if backing_type == AdapterType.MOCK:
                backing_adapter = backing_class(config)
            else:
                backing_adapter = backing_class(self._build_adapter_config(config))
            base_adapter = VbaGeneratorAdapter(backing_adapter=backing_adapter)
        elif adapter_type == AdapterType.MOCK:
            base_adapter = adapter_class(config)
        else:
            adapter_config = self._build_adapter_config(config)
            base_adapter = adapter_class(adapter_config)

        # Wrap with additional features if enabled
        adapter = base_adapter

        # Keep mock/testing adapters simple and deterministic.
        if adapter_type != AdapterType.MOCK and config.enable_circuit_breaker:
            adapter = self._wrap_with_circuit_breaker(adapter, config)

        if adapter_type != AdapterType.MOCK and config.enable_connection_pooling:
            adapter = self._wrap_with_connection_pool(adapter, config)

        return adapter

    def _determine_adapter_type(self, config: SolidWorksMCPConfig) -> AdapterType:
        """Determine optimal adapter type based on environment and config.
        
        Applies decision logic to select best adapter implementation:
        1. Force Mock if testing or mock_solidworks flag set
        2. Fall back to Mock if PyWin32 requested but not on Windows
        3. Use configured adapter_type otherwise
        
        Args:
            config (SolidWorksMCPConfig): Configuration with adapter preferences.
        
        Returns:
            AdapterType: The adapter type to instantiate.
        
        Examples:
            >>> config = SolidWorksMCPConfig(adapter_type=AdapterType.PYWIN32)
            >>> factory = AdapterFactory()
            >>> adapter_type = factory._determine_adapter_type(config)
            >>> # On non-Windows: AdapterType.MOCK
            >>> # On Windows: AdapterType.PYWIN32
        """
        # Force mock adapter for testing
        if config.testing or config.mock_solidworks:
            return AdapterType.MOCK

        # Check platform compatibility
        if (
            platform.system() != "Windows"
            and config.adapter_type == AdapterType.PYWIN32
        ):
            # Fallback to mock on non-Windows platforms
            return AdapterType.MOCK

        # Use configured adaptertype
        return config.adapter_type

    def _determine_vba_backing_type(self, config: SolidWorksMCPConfig) -> AdapterType:
        """Determine which adapter should back the VBA wrapper.

        Args:
            config: Active server configuration.

        Returns:
            Concrete non-VBA adapter type used to execute operations.
        """
        if config.testing or config.mock_solidworks:
            return AdapterType.MOCK
        if platform.system() != "Windows":
            return AdapterType.MOCK
        return AdapterType.PYWIN32

    def _build_adapter_config(self, config: SolidWorksMCPConfig) -> dict[str, Any]:
        """Extract and transform config for adapter instantiation.
        
        Creates adapter-specific configuration dict from main config object.
        Includes SolidWorks paths, validation settings, and timeouts/retries.
        
        Args:
            config (SolidWorksMCPConfig): Main server configuration.
        
        Returns:
            dict[str, Any]: Adapter-specific config with defaults applied.
        
        Examples:
            >>> main_config = SolidWorksMCPConfig(solidworks_path='/sw/sw.exe')
            >>> factory = AdapterFactory()
            >>> adapter_cfg = factory._build_adapter_config(main_config)
            >>> adapter_cfg['timeout']
            30
        """
        return {
            "solidworks_path": config.solidworks_path,
            "enable_windows_validation": config.enable_windows_validation,
            "debug": config.debug,
            "timeout": 30,  # Default timeout in seconds
            "retry_attempts": 3,
            "retry_delay": 1.0,
        }

    def _wrap_with_circuit_breaker(
        self, adapter: SolidWorksAdapter, config: SolidWorksMCPConfig
    ) -> SolidWorksAdapter:
        """Wrap adapter with circuit breaker for fault tolerance.
        
        Applies circuit breaker decorator to handle COM failures, timeouts,
        and transient errors. Automatically opens circuit after threshold
        failures and enters half-open recovery state.
        
        Args:
            adapter (SolidWorksAdapter): Base adapter to wrap.
            config (SolidWorksMCPConfig): Config with circuit breaker settings.
        
        Returns:
            SolidWorksAdapter: The same adapter wrapped with CircuitBreakerAdapter.
        
        Examples:
            >>> from adapters.mock_adapter import MockSolidWorksAdapter
            >>> base = MockSolidWorksAdapter()
            >>> config = SolidWorksMCPConfig()
            >>> wrapped = factory._wrap_with_circuit_breaker(base, config)
        """
        from .circuit_breaker import CircuitBreakerAdapter

        return CircuitBreakerAdapter(
            adapter=adapter,
            failure_threshold=config.circuit_breaker_threshold,
            recovery_timeout=config.circuit_breaker_timeout,
            half_open_max_calls=3,
        )

    def _wrap_with_connection_pool(
        self, adapter: SolidWorksAdapter, config: SolidWorksMCPConfig
    ) -> SolidWorksAdapter:
        """Wrap adapter with connection pooling for performance.
        
        Applies connection pool decorator to reuse SolidWorks COM connections,
        reducing connection overhead for repeated operations. Pool size and
        timeout configured via config object.
        
        Args:
            adapter (SolidWorksAdapter): Base adapter to wrap.
            config (SolidWorksMCPConfig): Config with pool settings.
        
        Returns:
            SolidWorksAdapter: The same adapter wrapped with ConnectionPoolAdapter.
        
        Examples:
            >>> from adapters.mock_adapter import MockSolidWorksAdapter
            >>> base = MockSolidWorksAdapter()
            >>> config = SolidWorksMCPConfig()
            >>> pooled = factory._wrap_with_connection_pool(base, config)
        """
        from .connection_pool import ConnectionPoolAdapter

        return ConnectionPoolAdapter(
            adapter_factory=lambda: adapter,
            pool_size=config.connection_pool_size,
            max_retries=3,
        )


async def create_adapter(config: SolidWorksMCPConfig) -> SolidWorksAdapter:
    """Async factory function for creating SolidWorks adapters."""
    # Register adapters if not already done
    _register_default_adapters()

    # Create adapter using factory
    adapter = AdapterFactory.create_adapter(config)

    return adapter


def _register_default_adapters() -> None:
    """Register default adapter implementations."""
    # Always register mock adapter
    AdapterFactory.register_adapter(AdapterType.MOCK, MockSolidWorksAdapter)
    AdapterFactory.register_adapter(AdapterType.VBA, VbaGeneratorAdapter)

    # Register pywin32 adapter if on Windows
    if platform.system() == "Windows":
        try:
            from .pywin32_adapter import PyWin32Adapter

            AdapterFactory.register_adapter(AdapterType.PYWIN32, PyWin32Adapter)
        except ImportError:
            # pywin32 not available, will fall back to mock
            pass

    # Future adapters can be registered here
    # AdapterFactory.register_adapter(AdapterType.EDGE_DOTNET, EdgeDotNetAdapter)
    # AdapterFactory.register_adapter(AdapterType.POWERSHELL, PowerShellAdapter)
