"""Feature selection mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import selection_count, strip_op_prefix
from .face_selection import FaceEdgeSelector, describe_edge, validate_face_query

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

    async def select_feature(
        self, feature_name: str, append: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Select a named feature, sketch, plane or component.

        Args:
            feature_name: Feature name, optionally ``@document`` qualified.
            append: Add to the current selection instead of replacing it.

        Returns:
            AdapterResult[dict[str, Any]]: The selector payload plus
            ``selection_count``. ERROR - never SUCCESS with
            ``selected: False`` - when no strategy could select the name.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _select() -> dict[str, Any]:
            payload = self._feature_selector.select_feature(feature_name, append)
            if not payload or not payload.get("selected"):
                raise LookupError(
                    f"Feature not found or could not be selected: {feature_name}"
                )
            payload["selection_count"] = selection_count(self, self.currentModel)
            return payload

        return self._run_clean("select_feature", _select)

    async def select_face_edges(
        self,
        point: list[float] | None = None,
        side: str | None = None,
        plane: str | None = None,
        edge_type: str = "all",
        append: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Multi-select every edge bounding one face of the active part.

        See ``SolidWorksAdapter.select_face_edges`` for the contract; the face
        resolution and selection live in ``face_selection.FaceEdgeSelector``.
        """
        problem = validate_face_query(point, side, plane, edge_type)
        if problem:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=problem)
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        from .io import _doc_type

        doc_type = _doc_type(self)
        if doc_type is not None and doc_type != 1:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "select_face_edges requires an active part document "
                    f"(active document type is {doc_type})."
                ),
            )

        def _select_edges() -> dict[str, Any]:
            selector = FaceEdgeSelector(self)
            faces = selector.resolve(point, side, plane)
            edges = selector.edges(faces, edge_type)
            if not edges:
                kind = "" if edge_type == "all" else f"{edge_type} "
                raise LookupError(
                    f"The selected face has no {kind}edges "
                    f"(face centre {faces[0].describe()['center_mm']} mm)."
                )
            count = selector.select(edges, append)
            described = [f.describe() for f in faces]
            return {
                "face": described[0],
                "faces": described,
                "edge_type": edge_type,
                "edges": [info for _edge, info in edges],
                "selected_edges": len(edges),
                "selection_count": count,
            }

        return self._run_clean("select_face_edges", _select_edges)

    def _run_clean(
        self, operation_name: str, operation: Callable[[], Any]
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``operation`` via ``_handle_com_operation`` with a clean error.

        Strips the generic ``"Error in <op>: "`` prefix so expected failures
        (not found, nothing to select) read as plain sentences for the LLM.
        """
        result = self._handle_com_operation(operation_name, operation)
        if not result.is_success:
            result.error = strip_op_prefix(result.error, operation_name)
        return cast("AdapterResult[dict[str, Any]]", result)



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
                    # Shared with select_face_edges: start/end/length plus
                    # curve kind and, for circles, centre/axis/radius.
                    entry.update(describe_edge(self, obj))

                elif type_name == "VERTEX":
                    point = self._attempt(lambda o=obj: o.GetPoint(), default=None)
                    if point:
                        entry["point_mm"] = [c * 1000 for c in point]

                results.append(entry)
            return results

        return self._handle_com_operation("get_selected_entities", _describe)
