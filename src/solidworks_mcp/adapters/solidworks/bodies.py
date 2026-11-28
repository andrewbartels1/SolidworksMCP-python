"""Multi-body operations on SolidWorks: list, combine, split, move, delete, scale.

Each operation reads the part's solid bodies (``IPartDoc.GetBodies2``), acts,
reads them again and is judged by :mod:`..body_rules`; a feature whose result
breaks its rule is deleted and the call fails. How each SolidWorks call takes
its bodies was measured by four probes on SolidWorks 2026 (design.md of the
``multi-body-tools`` change, Decision 1):

- combine: bodies passed directly, as a ``VT_DISPATCH`` array; add and
  common need every body in the array, the main one included;
- split: the plane or sketch selected, ``PreSplitBody2`` for the pieces, then
  ``PostSplitBody2`` with equal-length body, origin and path arrays;
- move/copy: bodies selected with mark 1; SolidWorks applies only the
  rotation when both are given, so a call takes one or the other;
- delete/keep: bodies selected with mark 0; scale: with mark 1.

Every step runs inside :meth:`_handle_com_operation`, on the connect thread
with its settle pause.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, cast

from ...exceptions import InputRefused
from .. import body_rules as rules
from .. import sw_type_info
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SplitBodyParameters,
)
from ..body_rules import BodyState
from .com_utils import as_list, dispatch_array, string_array
from .features import _delete_feature_impl

#: ``swBodyType_e.swSolidBody``.
_SOLID_BODY = 0
#: ``swDocumentTypes_e.swDocPART``.
_PART = 1
#: ``swBodyOperationType_e`` for each combine.
_COMBINE_CODES = {"add": 15903, "subtract": 15902, "common": 15901}
#: The selection marks the probes found.
_MARK_MOVE = 1
_MARK_DELETE = 0
_MARK_SCALE = 1
#: ``swScaleType_e``: about the centroid or the origin.
_SCALE_TYPES = {"centroid": 0, "origin": 1}

#: A measured body and its ``IBody2`` dispatch.
Measured = tuple[BodyState, Any]


class SolidWorksBodiesMixin:
    """``list_bodies`` and the five body operations on SolidWorks."""

    def _measure_bodies(self) -> list[Measured]:
        """The active part's solid bodies, measured.

        Returns:
            list[Measured]: Each body's state and dispatch, as SolidWorks lists
            them (newest first).

        Raises:
            InputRefused: The active document isn't a part.
            RuntimeError: A body's volume or box can't be read.
        """
        adapter: Any = self
        model = adapter.currentModel
        # GetType is read as a property or a call: a document not flagged for
        # its interfaces (COM pitfall #5) gives the value itself.
        kind = adapter._attempt(
            lambda: adapter._get_attr_or_call(model, "GetType"), default=None
        )
        if kind != _PART:
            raise InputRefused(
                "The body tools read a part's solid bodies; make a part the "
                "active document (an assembly or drawing has none)."
            )
        part = sw_type_info.flagged(model, "IPartDoc")
        raw = adapter._attempt(
            lambda: part.GetBodies2(_SOLID_BODY, False), default=None
        )
        measured: list[Measured] = []
        for item in as_list(raw):
            body = sw_type_info.flagged(item, "IBody2")
            props = as_list(adapter._attempt(lambda b=body: b.GetMassProperties(1.0)))
            box = as_list(adapter._attempt(lambda b=body: b.GetBodyBox()))
            name = str(adapter._attempt(lambda b=body: b.Name, default="") or "")
            if len(props) < 4 or len(box) < 6:
                raise RuntimeError(
                    f"Could not read the volume and size of body '{name}'."
                )
            mm = [float(v) * 1000 for v in box]
            measured.append(
                (
                    BodyState(
                        name,
                        float(props[3]) * 1e9,
                        (mm[0], mm[1], mm[2]),
                        (mm[3], mm[4], mm[5]),
                    ),
                    body,
                )
            )
        return measured

    async def list_bodies(self) -> AdapterResult[dict[str, Any]]:
        """The active part's solid bodies: name, volume and box.

        Returns:
            AdapterResult[dict[str, Any]]: As :func:`body_rules.listing`.
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(
                "list_bodies",
                lambda: rules.listing([state for state, _ in self._measure_bodies()]),
            ),
        )

    def _select_bodies(self, bodies: list[Any], mark: int) -> None:
        """Select bodies with a selection mark, replacing the selection.

        Args:
            bodies: ``IBody2`` dispatches.
            mark: The mark the feature reads them by.

        Raises:
            RuntimeError: SolidWorks refused to select one.
        """
        adapter: Any = self
        model = adapter.currentModel
        adapter._attempt(lambda: model.ClearSelection2(True))
        manager = sw_type_info.flagged(model.SelectionManager, "ISelectionMgr")
        for index, body in enumerate(bodies):
            data = manager.CreateSelectData()
            data.Mark = mark
            if not adapter._attempt(
                lambda b=body, d=data, i=index: b.Select2(i > 0, d)
            ):
                raise RuntimeError("SolidWorks would not select a body.")

    def _feature_name(self, feature: Any) -> str:
        """A new feature's name."""
        adapter: Any = self
        return str(
            adapter._attempt(
                lambda: sw_type_info.flagged(feature, "IFeature").Name, default=""
            )
            or ""
        )

    def _body_operation(
        self,
        operation: str,
        act: Callable[[list[Measured]], tuple[Any, str]],
        verdict: Callable[[list[BodyState], list[BodyState]], tuple[str, bool]],
        extra: Callable[[list[BodyState], list[BodyState]], dict[str, Any]],
    ) -> AdapterResult[dict[str, Any]]:
        """Measure, act, measure again and judge one body operation.

        Args:
            operation: The tool's name.
            act: Makes the feature from the bodies before; returns it (None
                when SolidWorks made nothing) and what it did in words, for
                the "made nothing" message. Raises InputRefused to refuse.
            verdict: The rule: the expectation in words and whether it held.
            extra: The reply's own fields, from the bodies before and after.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply, or the refusal.
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        model = adapter.currentModel

        def build() -> dict[str, Any]:
            measured = self._measure_bodies()
            before = [state for state, _ in measured]
            feature, what = act(measured)
            adapter._attempt(lambda: model.ClearSelection2(True))
            if feature is None:
                raise RuntimeError(
                    f"SolidWorks {what} nothing; the bodies are unchanged."
                )
            name = self._feature_name(feature)
            after = [state for state, _ in self._measure_bodies()]
            expected, ok = verdict(before, after)
            failed = rules.judge(operation, expected, before, after, ok=ok)
            if failed:
                if name:
                    _delete_feature_impl(adapter, name)
                raise RuntimeError(failed)
            return {
                **rules.measured_reply(name, before, after),
                **extra(before, after),
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(operation, build),
        )

    @staticmethod
    def _dispatches(measured: list[Measured], names: list[str]) -> list[Any]:
        """The named bodies' dispatches, in the order named."""
        by_name = {state.name: body for state, body in measured}
        return [by_name[name] for name in names]

    async def combine_bodies(
        self, params: CombineBodiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Add, subtract or keep the common volume of bodies.

        Args:
            params: The operation, the main body and the tool bodies.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``operation``.
        """
        adapter: Any = self
        names: list[str] = []

        def act(measured: list[Measured]) -> tuple[Any, str]:
            main, tools = rules.check_combine(params, [s for s, _ in measured])
            names.extend([main, *tools])
            main_body = self._dispatches(measured, [main])[0]
            # Subtract takes the tools alone; add and common need every body,
            # the main one included (probe answer).
            listed = tools if params.operation == "subtract" else [main, *tools]
            manager = sw_type_info.flagged(
                adapter.currentModel.FeatureManager, "IFeatureManager"
            )
            feature = manager.InsertCombineFeature(
                _COMBINE_CODES[params.operation],
                main_body,
                dispatch_array(self._dispatches(measured, listed)),
            )
            return feature, f"combined ({params.operation})"

        return self._body_operation(
            "combine_bodies",
            act,
            lambda before, after: rules.combine_ok(
                params.operation, names[0], names[1:], before, after
            ),
            lambda before, after: {"operation": params.operation},
        )

    async def split_body(
        self, params: SplitBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Split the bodies a plane or sketch crosses, keeping every piece.

        Args:
            params: The plane or sketch.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``tool``
            and ``made``, the bodies the split made.
        """
        adapter: Any = self

        def act(measured: list[Measured]) -> tuple[Any, str]:
            model = adapter.currentModel
            tool = adapter._attempt(lambda: model.FeatureByName(params.tool))
            if tool is None:
                raise InputRefused(
                    f"No plane or sketch named '{params.tool}' to split with."
                )
            adapter._attempt(lambda: model.ClearSelection2(True))
            sw_type_info.flagged(tool, "IFeature").Select2(False, 0)
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            pieces = as_list(adapter._attempt(lambda: manager.PreSplitBody2()))
            if len(pieces) < 2:
                raise RuntimeError(
                    f"SolidWorks split nothing at '{params.tool}': it must cross "
                    "a body all the way."
                )
            feature = manager.PostSplitBody2(
                dispatch_array(pieces),
                False,
                dispatch_array([None] * len(pieces)),
                string_array([""] * len(pieces)),
                "",
            )
            return feature, "split"

        return self._body_operation(
            "split_body",
            act,
            rules.split_ok,
            lambda before, after: {
                "tool": params.tool,
                "made": [
                    b.name for b in after if b.name not in {s.name for s in before}
                ],
            },
        )

    async def move_copy_body(
        self, params: MoveCopyBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Move bodies, or copy them, by a translation or a rotation.

        Args:
            params: The bodies, the translation or rotation, and the copies.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``as_copy``
            and ``copies``.
        """
        adapter: Any = self
        moved: list[str] = []

        def act(measured: list[Measured]) -> tuple[Any, str]:
            rules.check_move(params)
            moved.extend(rules.resolve_bodies([s for s, _ in measured], params.bodies))
            self._select_bodies(self._dispatches(measured, moved), _MARK_MOVE)
            t = [v / 1000 for v in params.translate]
            p = [v / 1000 for v in params.rotation_point]
            r = [math.radians(v) for v in params.rotate]
            manager = sw_type_info.flagged(
                adapter.currentModel.FeatureManager, "IFeatureManager"
            )
            feature = manager.InsertMoveCopyBody2(
                t[0], t[1], t[2], 0.0, p[0], p[1], p[2], r[0], r[1], r[2],
                params.as_copy, params.copies if params.as_copy else 1,
            )  # fmt: skip
            return feature, "copied" if params.as_copy else "moved"

        return self._body_operation(
            "move_copy_body",
            act,
            lambda before, after: rules.move_ok(params, moved, before, after),
            lambda before, after: {
                "as_copy": params.as_copy,
                "copies": params.copies if params.as_copy else 0,
            },
        )

    async def delete_bodies(
        self, params: DeleteBodiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Delete bodies, or keep only them.

        Args:
            params: The bodies and whether to keep them.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``keep``
            and ``removed``.
        """
        adapter: Any = self
        removed: list[str] = []

        def act(measured: list[Measured]) -> tuple[Any, str]:
            states = [s for s, _ in measured]
            removed.extend(rules.check_delete(params, states))
            named = rules.resolve_bodies(states, params.bodies)
            self._select_bodies(self._dispatches(measured, named), _MARK_DELETE)
            manager = sw_type_info.flagged(
                adapter.currentModel.FeatureManager, "IFeatureManager"
            )
            return manager.InsertDeleteBody2(params.keep), "deleted"

        return self._body_operation(
            "delete_bodies",
            act,
            lambda before, after: rules.delete_ok(removed, before, after),
            lambda before, after: {"keep": params.keep, "removed": list(removed)},
        )

    async def scale_body(
        self, params: ScaleBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Scale bodies, uniformly or per axis, about their centroid or the origin.

        Args:
            params: The factors, the centre and the bodies (all when None).

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``factors``
            and ``about``.
        """
        adapter: Any = self
        scaled: list[str] = []
        factors: list[float] = []

        def act(measured: list[Measured]) -> tuple[Any, str]:
            factors.extend(rules.scale_factors(params))
            states = [s for s, _ in measured]
            scaled.extend(
                rules.resolve_bodies(states, params.bodies)
                if params.bodies
                else [s.name for s in states]
            )
            self._select_bodies(self._dispatches(measured, scaled), _MARK_SCALE)
            manager = sw_type_info.flagged(
                adapter.currentModel.FeatureManager, "IFeatureManager"
            )
            uniform = factors[0] == factors[1] == factors[2]
            feature = manager.InsertScale(
                _SCALE_TYPES[params.about], uniform, factors[0], factors[1], factors[2]
            )
            return feature, "scaled"

        return self._body_operation(
            "scale_body",
            act,
            lambda before, after: rules.scale_ok(
                (factors[0], factors[1], factors[2]), scaled, before, after
            ),
            lambda before, after: {"factors": list(factors), "about": params.about},
        )
