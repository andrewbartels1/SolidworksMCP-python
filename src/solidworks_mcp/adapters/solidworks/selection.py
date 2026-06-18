"""Feature selection mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

from ..base import AdapterResult, AdapterResultStatus


class SolidWorksSelectionMixin:
    """Expose feature-selection and feature-list methods through a mixin."""

    if TYPE_CHECKING:  # pragma: no cover
        # Mixin protocol: declare attributes that must exist on the parent class
        currentModel: Any
        _feature_selector: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

    async def list_features(
        self, include_suppressed: bool = False
    ) -> AdapterResult[list[dict[str, Any]]]:
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        return self._handle_com_operation(
            "list_features", self._feature_selector.list_features, include_suppressed
        )

    @staticmethod
    def _normalize_feature_name(raw_name: str | None) -> str:
        return str(raw_name or "").strip().strip('"').casefold()

    def _build_feature_candidate_names(
        self, feature_name: str, target_doc: Any
    ) -> list[str]:
        return cast(
            list[str],
            self._feature_selector.build_feature_candidate_names(
                feature_name, target_doc
            ),
        )

    def _try_select_by_extension(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        return cast(
            "dict[str, Any] | None",
            self._feature_selector.try_select_by_extension(
                target_doc, candidate_names, feature_name
            ),
        )

    def _try_select_by_component(
        self,
        target_doc: Any,
        candidate_names: list[str],
        feature_name: str,
    ) -> dict[str, Any] | None:
        return cast(
            "dict[str, Any] | None",
            self._feature_selector.try_select_by_component(
                target_doc, candidate_names, feature_name
            ),
        )

    def _try_select_by_feature_tree(
        self,
        target_doc: Any,
        feature_name: str,
        candidate_names: list[str],
    ) -> dict[str, Any] | None:
        return cast(
            "dict[str, Any] | None",
            self._feature_selector.try_select_by_feature_tree(
                target_doc, feature_name, candidate_names
            ),
        )

    async def select_feature(self, feature_name: str) -> AdapterResult[dict[str, Any]]:
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return self._handle_com_operation(
            "select_feature", self._feature_selector.select_feature, feature_name
        )
