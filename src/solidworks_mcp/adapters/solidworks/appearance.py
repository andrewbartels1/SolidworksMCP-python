"""Colours on SolidWorks: set, remove and read a part's, feature's, body's or face's.

A colour is SolidWorks's nine material values, passed as a ``VT_R8`` array
(a plain list is misread). Each level has its own call, measured on
SolidWorks 2026 (design.md of the ``appearance-and-reference-tools`` change):

- part: ``IModelDoc2.MaterialPropertyValues`` (a property);
- feature: ``IFeature.SetMaterialPropertyValues2`` /
  ``GetMaterialPropertyValues2`` / ``RemoveMaterialProperty2`` (nine ``-1``
  when it has none);
- body: ``IBody2.MaterialPropertyValues2`` / ``RemoveMaterialProperty``;
- face: ``IFace2.MaterialPropertyValues`` (``None`` when it has none) /
  ``RemoveMaterialProperty2``.

Every call runs inside :meth:`_handle_com_operation`, on the connect thread.
"""

from __future__ import annotations

from typing import Any, cast

from ...exceptions import InputRefused
from .. import appearance_rules as rules
from .. import body_rules, sw_type_info
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    AppearanceParameters,
    AppearanceTarget,
)
from .com_utils import double_array
from .features import _null_callout

#: ``swInConfigurationOpts_e.swThisConfiguration``.
_THIS_CONFIGURATION = 1


class SolidWorksAppearanceMixin:
    """``set_appearance`` and ``get_appearance`` on SolidWorks."""

    def _face_at(self, point: list[float]) -> Any:
        """The face at ``point`` (mm), with the selection cleared after.

        Args:
            point: ``[x, y, z]`` mm on the face.

        Returns:
            Any: The ``IFace2`` dispatch.

        Raises:
            InputRefused: No face lies at the point.
        """
        adapter: Any = self
        face = select_face_at(adapter, point)
        adapter._attempt(lambda: adapter.currentModel.ClearSelection2(True))
        return face

    def _feature_named(self, name: str) -> Any:
        """The feature ``name``, flagged, or a refusal."""
        adapter: Any = self
        feature = adapter._attempt(lambda: adapter.currentModel.FeatureByName(name))
        if feature is None:
            raise InputRefused(f"No feature named '{name}'; list_features names them.")
        return sw_type_info.flagged(feature, "IFeature")

    def _body_named(self, name: str) -> Any:
        """The body ``name`` (ignoring case), flagged, or a refusal listing them."""
        adapter: Any = self
        measured = adapter._measure_bodies()
        real = body_rules.resolve_bodies([state for state, _ in measured], [name])[0]
        body = next(body for state, body in measured if state.name == real)
        return sw_type_info.flagged(body, "IBody2")

    def _appearance_target(self, kind: str, target: AppearanceTarget) -> Any:
        """The dispatch a target names: the model, a feature, a body or a face."""
        adapter: Any = self
        if kind == "feature":
            return self._feature_named(str(target.feature))
        if kind == "body":
            return self._body_named(str(target.body))
        if kind == "face":
            return self._face_at(list(target.face_point or []))
        return adapter.currentModel

    def _own_values(self, kind: str, dispatch: Any) -> Any:
        """The target's own nine material values, or None/-1s when it has none."""
        adapter: Any = self
        readers = {
            "part": lambda: dispatch.MaterialPropertyValues,
            "feature": lambda: dispatch.GetMaterialPropertyValues2(
                _THIS_CONFIGURATION, None
            ),
            "body": lambda: dispatch.MaterialPropertyValues2,
            "face": lambda: dispatch.MaterialPropertyValues,
        }
        return adapter._attempt(readers[kind])

    def _write_values(self, kind: str, dispatch: Any, values: list[float]) -> None:
        """Set the target's own colour."""
        array = double_array(values)
        if kind == "feature":
            dispatch.SetMaterialPropertyValues2(array, _THIS_CONFIGURATION, None)
        elif kind == "body":
            dispatch.MaterialPropertyValues2 = array
        else:
            dispatch.MaterialPropertyValues = array

    def _remove_values(self, kind: str, dispatch: Any) -> None:
        """Remove a feature's, body's or face's own colour."""
        if kind == "body":
            dispatch.RemoveMaterialProperty(_THIS_CONFIGURATION, None)
        else:
            dispatch.RemoveMaterialProperty2(_THIS_CONFIGURATION, None)

    def _showing(self, kind: str, dispatch: Any) -> dict[str, Any]:
        """The colour a target shows and the level it comes from.

        Walks up from the target in SolidWorks's order (face, feature, body,
        part) until a level has a colour of its own.
        """
        adapter: Any = self
        chain: list[tuple[str, Any]] = [(kind, dispatch)]
        if kind == "face":
            feature = adapter._attempt(lambda: dispatch.GetFeature())
            body = adapter._attempt(lambda: dispatch.GetBody())
            if feature is not None:
                chain.append(("feature", sw_type_info.flagged(feature, "IFeature")))
            if body is not None:
                chain.append(("body", sw_type_info.flagged(body, "IBody2")))
        if kind != "part":
            chain.append(("part", adapter.currentModel))
        for level, item in chain:
            color = rules.color_reply(self._own_values(level, item))
            if color is not None:
                return {**color, "level": level}
        return {"color": None, "hex": None, "transparency": None, "level": None}

    def _appearance_call(
        self,
        operation: str,
        target: AppearanceTarget,
        act: Any,
        check: Any = rules.target_kind,
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``act(kind, dispatch)`` for the target inside the COM boundary.

        Args:
            operation: The operation's name, for the boundary and errors.
            target: The call's target fields.
            act: Does the work on the target's dispatch; returns reply fields.
            check: Refuses the call before anything is touched; returns the
                target's kind.

        Returns:
            AdapterResult[dict[str, Any]]: ``target``, its name or point and
            ``act``'s fields.
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def build() -> dict[str, Any]:
            kind = check(target)
            dispatch = self._appearance_target(kind, target)
            reply = act(kind, dispatch)
            adapter._attempt(lambda: adapter.currentModel.GraphicsRedraw2())
            return {"target": kind, **_target_name(kind, target), **reply}

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(operation, build),
        )

    async def set_appearance(
        self, params: AppearanceParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Colour the part, a feature, a body or a face, or remove a colour.

        Args:
            params: The target, the colour and transparency, or ``reset``.

        Returns:
            AdapterResult[dict[str, Any]]: The target and the colour read
            back; for a reset, ``color`` None and what now ``showing``.
        """

        def act(kind: str, dispatch: Any) -> dict[str, Any]:
            if params.reset:
                self._remove_values(kind, dispatch)
                return {"reset": True, "showing": self._showing(kind, dispatch)}
            rgb = rules.parse_color(params.color)
            self._write_values(
                kind, dispatch, rules.material_values(rgb, params.transparency)
            )
            read = rules.color_reply(self._own_values(kind, dispatch))
            if read is None:
                raise RuntimeError(f"SolidWorks did not keep the colour on the {kind}.")
            return read

        return self._appearance_call(
            "set_appearance", params, act, check=lambda _: rules.check_set(params)
        )

    async def get_appearance(
        self, params: AppearanceTarget
    ) -> AdapterResult[dict[str, Any]]:
        """Read the colour a target shows, and the level it comes from.

        Args:
            params: The target; none for the part.

        Returns:
            AdapterResult[dict[str, Any]]: ``color``, ``hex``,
            ``transparency`` and ``level``.
        """
        return self._appearance_call(
            "get_appearance",
            params,
            lambda kind, dispatch: self._showing(kind, dispatch),
        )


def _target_name(kind: str, target: AppearanceTarget) -> dict[str, Any]:
    """The reply field naming the target: its name or point."""
    if kind == "feature":
        return {"feature": target.feature}
    if kind == "body":
        return {"body": target.body}
    if kind == "face":
        return {"face_point": target.face_point}
    return {}


def select_face_at(adapter: Any, point: list[float]) -> Any:
    """Select the face at ``point`` (mm) and return it, left selected.

    Args:
        adapter: The connected adapter.
        point: ``[x, y, z]`` mm on the face.

    Returns:
        Any: The ``IFace2`` dispatch, still selected.

    Raises:
        InputRefused: No face lies at the point.
    """
    model = adapter.currentModel
    # New faces are not selectable by coordinates until a rebuild
    # (COM pitfall #13).
    adapter._attempt(lambda: model.ForceRebuild3(True))
    adapter._attempt(lambda: model.ClearSelection2(True))
    extension = sw_type_info.flagged(model.Extension, "IModelDocExtension")
    x, y, z = (float(v) / 1000.0 for v in point)
    picked = adapter._attempt(
        lambda: extension.SelectByID2(
            "", "FACE", x, y, z, False, 0, _null_callout(), 0
        ),
        default=False,
    )
    manager = sw_type_info.flagged(model.SelectionManager, "ISelectionMgr")
    face = adapter._attempt(lambda: manager.GetSelectedObject6(1, -1))
    if not picked or face is None:
        adapter._attempt(lambda: model.ClearSelection2(True))
        raise InputRefused(
            f"No face at {list(point)} mm; give a point on the face's surface."
        )
    return sw_type_info.flagged(face, "IFace2")
