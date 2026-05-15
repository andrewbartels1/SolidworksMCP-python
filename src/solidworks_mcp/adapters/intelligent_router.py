"""Intelligent router for COM/VBA execution with optional response caching."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..cache.response_cache import ResponseCache
from .base import AdapterResult, AdapterResultStatus
from .complexity_analyzer import ComplexityAnalyzer

OperationCallable = Callable[..., Awaitable[AdapterResult[Any]]]


@dataclass(frozen=True)
class RouteResult:
    """Route execution metadata.

    Attributes:
        route (str): The route value.
        used_cache (bool): The used cache value.
    """

    route: str
    used_cache: bool


class IntelligentRouter:
    """Route operations between COM and VBA paths using complexity analysis.

    Args:
        analyzer (ComplexityAnalyzer): The analyzer value.
        cache (ResponseCache): The cache value.
        cacheable_operations (set[str] | None): The cacheable operations value. Defaults to
                                                None.

    Attributes:
        _analyzer (Any): The analyzer value.
        _cache (Any): The cache value.
        _cacheable_operations (Any): The cacheable operations value.
    """

    def __init__(
        self,
        analyzer: ComplexityAnalyzer,
        cache: ResponseCache,
        cacheable_operations: set[str] | None = None,
    ) -> None:
        """Initialize router dependencies.

        Args:
            analyzer (ComplexityAnalyzer): The analyzer value.
            cache (ResponseCache): The cache value.
            cacheable_operations (set[str] | None): The cacheable operations value. Defaults to
                                                    None.

        Returns:
            None: None.
        """
        self._analyzer = analyzer
        self._cache = cache
        self._cacheable_operations = cacheable_operations or {
            # Lightweight metadata operations
            "get_model_info",
            "list_features",
            "list_configurations",
            "get_file_properties",
            "get_dimension",
            # Analysis operations — NOT cached: model state changes with
            # every feature-creation tool call and the router has no
            # automatic invalidation. Caching these produced stale
            # volumes mid-build.
            # "get_mass_properties",
            # "calculate_mass_properties",
            "get_material_properties",
            "analyze_geometry",
            "check_interference",
            # Drawing analysis operations
            "analyze_drawing_comprehensive",
            "analyze_drawing_dimensions",
            "analyze_drawing_views",
            "analyze_drawing_annotations",
            "check_drawing_compliance",
            "check_drawing_standards",
            "compare_drawing_versions",
            # Classification and indexing
            "classify_feature_tree",
            "discover_solidworks_docs",
        }

    async def execute(
        self,
        operation: str,
        payload: object,
        call_args: tuple[Any, ...],
        call_kwargs: dict[str, Any],
        com_operation: OperationCallable,
        vba_operation: OperationCallable | None,
        cache_ttl_seconds: int | None = None,
    ) -> tuple[AdapterResult[Any], RouteResult]:
        """Provide execute support for the intelligent router.

        Args:
            operation (str): Callable object executed by the helper.
            payload (object): The payload value.
            call_args (tuple[Any, ...]): The call args value.
            call_kwargs (dict[str, Any]): The call kwargs value.
            com_operation (OperationCallable): The com operation value.
            vba_operation (OperationCallable | None): The vba operation value.
            cache_ttl_seconds (int | None): The cache ttl seconds value. Defaults to None.

        Returns:
            tuple[AdapterResult[Any], RouteResult]: A tuple containing the resulting values.
        """
        if operation in self._cacheable_operations and self._cache.enabled:
            key = self._cache.make_key(operation, payload)
            cached = self._cache.get(key)
            if isinstance(cached, AdapterResult):
                return cached, RouteResult(route="cache", used_cache=True)

        decision = self._analyzer.analyze(operation=operation, payload=payload)

        if decision.prefer_vba and vba_operation is not None:
            vba_result = await self._safe_call(vba_operation, call_args, call_kwargs)
            self._analyzer.record_result(
                operation=operation,
                route="vba",
                success=vba_result.is_success,
            )
            if vba_result.is_success:
                self._cache_result(operation, payload, vba_result, cache_ttl_seconds)
                return vba_result, RouteResult(route="vba", used_cache=False)

        com_result = await self._safe_call(com_operation, call_args, call_kwargs)
        self._analyzer.record_result(
            operation=operation,
            route="com",
            success=com_result.is_success,
        )

        if com_result.is_success:
            self._cache_result(operation, payload, com_result, cache_ttl_seconds)
            return com_result, RouteResult(route="com", used_cache=False)

        if not decision.prefer_vba and vba_operation is not None:
            fallback_result = await self._safe_call(
                vba_operation,
                call_args,
                call_kwargs,
            )
            self._analyzer.record_result(
                operation=operation,
                route="vba",
                success=fallback_result.is_success,
            )
            if fallback_result.is_success:
                self._cache_result(
                    operation,
                    payload,
                    fallback_result,
                    cache_ttl_seconds,
                )
                return fallback_result, RouteResult(
                    route="vba-fallback", used_cache=False
                )

        return com_result, RouteResult(route="com-error", used_cache=False)

    async def _safe_call(
        self,
        operation_callable: OperationCallable,
        call_args: tuple[Any, ...],
        call_kwargs: dict[str, Any],
    ) -> AdapterResult[Any]:
        """Call adapter operation and normalize unexpected exceptions.

        Args:
            operation_callable (OperationCallable): The operation callable value.
            call_args (tuple[Any, ...]): The call args value.
            call_kwargs (dict[str, Any]): The call kwargs value.

        Returns:
            AdapterResult[Any]: The result produced by the operation.
        """
        try:
            return await operation_callable(*call_args, **call_kwargs)
        except Exception as exc:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"operation failed: {exc}",
            )

    def _cache_result(
        self,
        operation: str,
        payload: object,
        result: AdapterResult[Any],
        ttl_seconds: int | None,
    ) -> None:
        """Persist successful operation result in cache when eligible.

        Args:
            operation (str): Callable object executed by the helper.
            payload (object): The payload value.
            result (AdapterResult[Any]): The result value.
            ttl_seconds (int | None): The ttl seconds value.

        Returns:
            None: None.
        """
        if operation not in self._cacheable_operations:
            return
        key = self._cache.make_key(operation, payload)
        self._cache.set(key=key, value=result, ttl_seconds=ttl_seconds)
