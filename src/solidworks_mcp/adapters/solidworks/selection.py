"""Feature selection mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus

# swSelectType_e values actually observed on this SW install for the entity
# kinds this method cares about (EDGE=1, FACE=2 confirmed live 2026-09-18 by
# selecting each kind and checking which methods resolve on the returned
# object -- IEdge.GetStartVertex for EDGE, IFace2.GetBox for FACE. VERTEX=3
# is the documented swSelectType_e value but has not been live-verified the
# same way; treat it as a good guess, not a fact, if it ever misbehaves.
_SELECTED_ENTITY_TYPE_NAMES = {1: "EDGE", 2: "FACE", 3: "VERTEX"}


class SolidWorksSelectionMixin:
    """Expose feature-selection and feature-list methods through a mixin."""

    if TYPE_CHECKING:  # pragma: no cover
        # Mixin protocol: declare attributes that must exist on the parent class
        currentModel: Any
        swApp: Any
        _feature_selector: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], *, default: Any = None
        ) -> Any: ...

    async def list_features(
        self, include_suppressed: bool = False, max_assembly_depth: int = 2
    ) -> AdapterResult[list[dict[str, Any]]]:
        sw_app = getattr(self, "swApp", None)
        active_model = getattr(sw_app, "ActiveDoc", None) if sw_app else None
        if active_model is not None:
            self.currentModel = active_model
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No active model",
            )
        return self._handle_com_operation(
            "list_features",
            self._feature_selector.list_features,
            include_suppressed,
            max_assembly_depth,
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

    async def get_selected_entities(self) -> AdapterResult[list[dict[str, Any]]]:
        """Report the faces/edges/vertices currently highlighted in the live
        SolidWorks UI, so an agent can see exactly what the user clicked on
        instead of guessing from a screenshot (see com-api-pitfalls.md #21 for
        why a screenshot alone is not reliable proof of document/view state).

        Refreshes ``currentModel`` from ``swApp.ActiveDoc`` first, the same
        way ``list_features`` does, since the user's selection lives on
        whatever document is actually active in the UI right now -- which
        may not be the document this adapter last created or touched.

        Returns:
            AdapterResult[list[dict[str, Any]]]: One entry per selected
            entity, each with at least ``index`` and ``type``
            (``"FACE"``/``"EDGE"``/``"VERTEX"``/``"UNKNOWN(<n>)"``). Faces
            additionally carry ``bounding_box_mm``, ``center_mm``,
            ``area_mm2`` and ``normal`` (when planar). Edges carry
            ``start_mm``/``end_mm`` and a straight-line ``length_mm``
            (the true length of a curved edge will be longer). Vertices
            carry ``point_mm``. Any field that fails to resolve is simply
            omitted rather than failing the whole call -- a partial
            description is more useful than none.
        """
        sw_app = getattr(self, "swApp", None)
        active_model = getattr(sw_app, "ActiveDoc", None) if sw_app else None
        if active_model is not None:
            self.currentModel = active_model
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _describe() -> list[dict[str, Any]]:
            model = self.currentModel
            sel_mgr = model.SelectionManager
            self._attempt(
                lambda: _sw_type_info.flag_methods(sel_mgr, "ISelectionMgr"),
                default=0,
            )
            count = (
                self._attempt(
                    lambda: sel_mgr.GetSelectedObjectCount2(-1), default=0
                )
                or 0
            )

            results: list[dict[str, Any]] = []
            for i in range(1, int(count) + 1):
                raw_type = self._attempt(
                    lambda i=i: sel_mgr.GetSelectedObjectType3(i, -1), default=None
                )
                obj = self._attempt(
                    lambda i=i: sel_mgr.GetSelectedObject6(i, -1), default=None
                )
                if obj is None:
                    continue
                self._attempt(
                    lambda o=obj: _sw_type_info.flag_methods(
                        o, "IFace2", "IEdge", "IVertex"
                    ),
                    default=0,
                )

                type_name = _SELECTED_ENTITY_TYPE_NAMES.get(
                    int(raw_type) if isinstance(raw_type, (int, float)) else -1,
                    f"UNKNOWN({raw_type})",
                )
                entry: dict[str, Any] = {"index": i, "type": type_name}

                if type_name == "FACE":
                    box = self._attempt(lambda o=obj: o.GetBox(), default=None)
                    if box and len(box) == 6:
                        entry["bounding_box_mm"] = {
                            "min": [c * 1000 for c in box[0:3]],
                            "max": [c * 1000 for c in box[3:6]],
                        }
                        entry["center_mm"] = [
                            (box[j] + box[j + 3]) / 2 * 1000 for j in range(3)
                        ]
                    area = self._attempt(lambda o=obj: o.GetArea(), default=None)
                    if area is not None:
                        entry["area_mm2"] = area * 1e6
                    normal = self._attempt(lambda o=obj: o.Normal, default=None)
                    if normal:
                        entry["normal"] = [round(float(n), 6) for n in normal]

                elif type_name == "EDGE":
                    start_v = self._attempt(
                        lambda o=obj: o.GetStartVertex(), default=None
                    )
                    end_v = self._attempt(lambda o=obj: o.GetEndVertex(), default=None)
                    self._attempt(
                        lambda v=start_v: _sw_type_info.flag_methods(v, "IVertex"),
                        default=0,
                    )
                    self._attempt(
                        lambda v=end_v: _sw_type_info.flag_methods(v, "IVertex"),
                        default=0,
                    )
                    start = (
                        self._attempt(lambda v=start_v: v.GetPoint(), default=None)
                        if start_v is not None
                        else None
                    )
                    end = (
                        self._attempt(lambda v=end_v: v.GetPoint(), default=None)
                        if end_v is not None
                        else None
                    )
                    if start:
                        entry["start_mm"] = [c * 1000 for c in start]
                    if end:
                        entry["end_mm"] = [c * 1000 for c in end]
                    if start and end:
                        entry["length_mm"] = (
                            sum((a - b) ** 2 for a, b in zip(start, end, strict=True))
                            ** 0.5
                            * 1000
                        )

                elif type_name == "VERTEX":
                    point = self._attempt(lambda o=obj: o.GetPoint(), default=None)
                    if point:
                        entry["point_mm"] = [c * 1000 for c in point]

                results.append(entry)
            return results

        return self._handle_com_operation("get_selected_entities", _describe)
