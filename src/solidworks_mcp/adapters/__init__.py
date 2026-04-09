"""
SolidWorks adapter interfaces and factory.

This module provides the adapter pattern infrastructure for different
SolidWorks integration approaches (pywin32, mock, future edge.js, etc.)
"""

from .base import SolidWorksAdapter, AdapterResult, AdapterHealth
from .factory import create_adapter, AdapterType, AdapterFactory
from .pywin32_adapter import PyWin32Adapter
from .mock_adapter import MockSolidWorksAdapter
from .circuit_breaker import CircuitBreakerAdapter
from .connection_pool import ConnectionPoolAdapter
from .complexity_analyzer import ComplexityAnalyzer, RoutingDecision
from .intelligent_router import IntelligentRouter
from .vba_adapter import VbaGeneratorAdapter
from .vba_macro_executor import (
    VbaMacroExecutor,
    MacroExecutionRequest,
    MacroExecutionResult,
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
