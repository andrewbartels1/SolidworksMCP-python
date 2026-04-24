"""SolidWorks adapter interfaces and factory.

This module provides the adapter pattern infrastructure for different SolidWorks
integration approaches (pywin32, mock, future edge.js, etc.)
"""

from .base import AdapterHealth, AdapterResult, SolidWorksAdapter
from .circuit_breaker import CircuitBreakerAdapter
from .complexity_analyzer import ComplexityAnalyzer, RoutingDecision
from .connection_pool import ConnectionPoolAdapter
from .factory import AdapterFactory, AdapterType, create_adapter
from .intelligent_router import IntelligentRouter
from .mock_adapter import MockSolidWorksAdapter
from .pywin32_adapter import PyWin32Adapter
from .vba_adapter import VbaGeneratorAdapter
from .vba_macro_executor import (
    MacroExecutionRequest,
    MacroExecutionResult,
    VbaMacroExecutor,
)

__all__ = [
    "SolidWorksAdapter",
    "AdapterResult",
    "AdapterHealth",
    "create_adapter",
    "AdapterType",
    "AdapterFactory",
    "PyWin32Adapter",
    "MockSolidWorksAdapter",
    "CircuitBreakerAdapter",
    "ConnectionPoolAdapter",
    "ComplexityAnalyzer",
    "RoutingDecision",
    "IntelligentRouter",
    "VbaGeneratorAdapter",
    "VbaMacroExecutor",
    "MacroExecutionRequest",
    "MacroExecutionResult",
]
