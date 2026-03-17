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


class AdapterFactory:
    """Factory for creating SolidWorks adapters."""

    _adapter_registry: dict[AdapterType, type[SolidWorksAdapter]] = {}
    _adapters: dict[AdapterType, type[SolidWorksAdapter]] = _adapter_registry
    _instance: Union[AdapterFactory, None] = None

    def __new__(cls) -> "AdapterFactory":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_adapter(
        cls, adapter_type: AdapterType, adapter_class: type[SolidWorksAdapter]
    ) -> None:
        """Register an adapter implementation."""
        cls._adapter_registry[adapter_type] = adapter_class

    @classmethod
    def create_adapter(cls, config: SolidWorksMCPConfig) -> SolidWorksAdapter:
        """Create an adapter based on configuration."""
        factory = cls()
        return factory._create_adapter_impl(config)

    def _create_adapter_impl(self, config: SolidWorksMCPConfig) -> SolidWorksAdapter:
        """Internal adapter creation implementation."""
        # Determine the best adaptertype
        adapter_type = self._determine_adapter_type(config)

        # Get adapter class
        if adapter_type not in self._adapter_registry:
            raise ValueError(f"Adaptertype {adapter_type} not registered")

        adapter_class = self._adapter_registry[adapter_type]

        # Create base adapter
        if adapter_type == AdapterType.MOCK:
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
        """Determine the best adaptertype based on configuration and environment."""
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

    def _build_adapter_config(self, config: SolidWorksMCPConfig) -> dict[str, Any]:
        """Build adapter-specific configuration."""
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
        """Wrap adapter with circuit breaker pattern."""
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
        """Wrap adapter with connection pooling."""
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
