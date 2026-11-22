"""Assembly-depth mixin for PyWin32 SolidWorks operations (queue item 33).

Exploded views, component patterns and mirrors, replacing a component, and
balloons on a drawing view. Components are named by their instance name
(``pin-1``), found with the helpers ``io.py`` already uses. COM signatures and
enum values were read from SolidWorks 2026's type library.
"""

from __future__ import annotations

import math
import os
from typing import Any, cast

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import as_list, dispatch_array, long_array
from .features import _null_callout
from .io import (
    _box_from_metres,
    _byref_int,
    _component_names,
    _doc_type,
    _find_components,
    _resolve_drawing_view,
    _view_names,
)

#: The default plane whose normal is each explode direction.
_DIRECTION_PLANES = {"x": "Right Plane", "y": "Top Plane", "z": "Front Plane"}
#: ``AddExplodeStep2``'s ``ExplDirIndex`` picks an axis of the selected
#: plane's own frame: 0 and 1 lie in the plane (for the Top Plane, +x and -z),
#: 2 is its normal, which is +x, +y or +z for the planes above (checked live).
_EXPLODE_ALONG_NORMAL = 2
#: ``swFeatureNameID_e``: local (component) linear and circular patterns.
_LOCAL_LINEAR_PATTERN = 108
_LOCAL_CIRCULAR_PATTERN = 109
#: ``swMirrorComponentOrientation2_e.swOrientation_MirroredX_MirroredY``.
_MIRRORED_X_MIRRORED_Y = 0
#: ``swBalloonLayoutType_e`` by our layout name.
BALLOON_LAYOUTS = {
    "square": 1,
    "circle": 2,
    "top": 3,
    "bottom": 4,
    "right": 5,
    "left": 6,
}
#: ``IAutoBalloonOptions.Style``: ``swBS_Circular``.
_BALLOON_CIRCULAR = 1
#: ``SelectByID2`` marks: explode-step components, then its direction.
_MARK_COMPONENTS, _MARK_DIRECTION = 1, 2


def _need_assembly(adapter: Any, operation: str) -> AdapterResult[Any] | None:
    """The wrong-document error, or ``None`` when an assembly is active."""
    if _doc_type(adapter) == 2:
        return None
    return AdapterResult(
        status=AdapterResultStatus.ERROR,
        error=f"{operation} requires an assembly document",
    )


def _assembly(adapter: Any) -> Any:
    """The active document as ``IAssemblyDoc``."""
    return _sw_type_info.flagged(adapter.currentModel, "IAssemblyDoc")


def _box_size(adapter: Any, assembly: Any) -> list[float] | None:
    """The assembly's bounding box size ``[x, y, z]`` in mm."""
    box = _box_from_metres(
        adapter._attempt(lambda: assembly.GetBox(0), default=None), "assembly_box"
    )
    return None if box is None else [round(v, 4) for v in box["size"]]


def _select_data(adapter: Any, mark: int) -> Any:
    """An ``ISelectData`` carrying ``mark``."""
    sel_mgr = _sw_type_info.flagged(
        adapter.currentModel.SelectionManager, "ISelectionMgr"
    )
    data = sel_mgr.CreateSelectData()
    data.Mark = mark
    return data


def _select_components(adapter: Any, components: list[Any], mark: int) -> None:
    """Select each component, appending, under ``mark``."""
    data = _select_data(adapter, mark)
    for component in components:
        if not component.Select4(True, data, False):
            raise Exception(f"Couldn't select {component.Name2}")


def _select_named(adapter: Any, name: str, kind: str, mark: int) -> None:
    """Select a plane or axis by its name, appending, under ``mark``.

    Raises:
        Exception: ``<Kind> '<name>' not found``, when nothing was selected.
    """
    picked = adapter.currentModel.Extension.SelectByID2(
        name, kind, 0, 0, 0, True, mark, _null_callout(), 0
    )
    if not picked:
        raise Exception(f"{kind.title()} '{name}' not found in the assembly")


def _selected(adapter: Any, index: int = 1) -> Any:
    """The ``index``-th selected object (1-based)."""
    sel_mgr = _sw_type_info.flagged(
        adapter.currentModel.SelectionManager, "ISelectionMgr"
    )
    return sel_mgr.GetSelectedObject6(index, -1)


def _exploded_views(adapter: Any, assembly: Any) -> list[str]:
    """The active configuration's exploded views' names."""
    names = adapter._attempt(lambda: assembly.GetExplodedViewNames(), default=None)
    return [str(n) for n in as_list(names)]


class SolidWorksAssemblyMixin:
    """Exploded views, component patterns, mirrors, replace and balloons."""

    @staticmethod
    def _adapter(obj: Any) -> Any:
        """Return the runtime adapter object for dynamic attribute access."""
        return cast(Any, obj)

    async def create_exploded_view(
        self, steps: list[dict[str, Any]] | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Explode the active assembly, automatically or step by step, and show it.

        With no ``steps``, ``IAssemblyDoc.AutoExplode``. Each step moves its
        ``components`` ``distance`` mm along ``x``, ``y`` or ``z``
        (``reverse`` for the other way): the components are selected under
        mark 1 and the default plane normal to the direction under mark 2,
        then ``IConfiguration.AddExplodeStep2``.

        Args:
            steps: ``components``, ``direction``, ``distance``, ``reverse``.

        Returns:
            AdapterResult[dict[str, Any]]: The exploded view's ``view``,
            ``steps`` added, and the bounding box ``size_before_mm`` and
            ``size_after_mm``.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "create_exploded_view"):
            return wrong

        def run() -> dict[str, Any]:
            model = adapter.currentModel
            assembly = _assembly(adapter)
            before = _box_size(adapter, assembly)
            if not steps:
                if not assembly.AutoExplode():
                    raise Exception("SolidWorks didn't explode the assembly")
            else:
                names = sorted({n for step in steps for n in step["components"]})
                found = _find_components(adapter, assembly, names)
                config = _sw_type_info.flagged(
                    model.GetActiveConfiguration(), "IConfiguration"
                )
                if not _exploded_views(adapter, assembly):
                    assembly.CreateExplodedView()
                for number, step in enumerate(steps, start=1):
                    model.ClearSelection2(True)
                    _select_components(
                        adapter,
                        [found[n] for n in step["components"]],
                        _MARK_COMPONENTS,
                    )
                    _select_named(
                        adapter,
                        _DIRECTION_PLANES[step["direction"]],
                        "PLANE",
                        _MARK_DIRECTION,
                    )
                    made = config.AddExplodeStep2(
                        step["distance"] / 1000.0,
                        _EXPLODE_ALONG_NORMAL,
                        bool(step.get("reverse", False)),
                        0.0,
                        0,
                        False,
                        False,
                        False,
                        _byref_int(),
                    )
                    model.ClearSelection2(True)
                    if made is None:
                        raise Exception(f"SolidWorks refused explode step {number}")
            views = _exploded_views(adapter, assembly)
            view = views[-1] if views else ""
            assembly.ShowExploded2(True, view)
            return {
                "view": view,
                "steps": len(steps or []),
                "automatic": not steps,
                "size_before_mm": before,
                "size_after_mm": _box_size(adapter, assembly),
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("create_exploded_view", run),
        )

    async def set_exploded_view(self, exploded: bool) -> AdapterResult[dict[str, Any]]:
        """Show the active configuration's exploded view, or collapse it.

        Args:
            exploded: ``True`` to explode, ``False`` to collapse.

        Returns:
            AdapterResult[dict[str, Any]]: The ``view``, ``exploded`` read back
            (``IModelDoc2.IsExploded``) and the bounding box ``size_mm``.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "set_exploded_view"):
            return wrong

        def run() -> dict[str, Any]:
            assembly = _assembly(adapter)
            views = _exploded_views(adapter, assembly)
            if not views:
                raise Exception(
                    "No exploded view found in the active configuration; "
                    "make one with create_exploded_view"
                )
            assembly.ShowExploded2(exploded, views[0])
            model = _sw_type_info.flagged(adapter.currentModel, "IModelDoc2")
            return {
                "view": views[0],
                "exploded": bool(model.IsExploded()),
                "size_mm": _box_size(adapter, assembly),
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("set_exploded_view", run),
        )

    async def pattern_components(
        self,
        components: list[str],
        axis: str,
        count: int,
        kind: str = "linear",
        spacing: float | None = None,
        angle: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Repeat components along or around a reference axis.

        A component pattern feature from a definition
        (``IFeatureManager.CreateDefinition``, local linear or circular):
        the seeds, the axis, ``count`` (seeds included) and the spacing (mm)
        or the angle (degrees; 360 spaces them equally).

        Returns:
            AdapterResult[dict[str, Any]]: The ``feature``, the component
            counts before and after, and the ``added`` instances.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "pattern_components"):
            return wrong

        def run() -> dict[str, Any]:
            model = adapter.currentModel
            assembly = _assembly(adapter)
            found = _find_components(adapter, assembly, components)
            before = _component_names(adapter, assembly)
            # The definition takes its seeds and axis from the selection
            # (seeds under mark 1, the axis under mark 2): set as properties
            # instead, SolidWorks 2026 reads the axis as unset and refuses.
            model.ClearSelection2(True)
            _select_components(
                adapter, [found[name] for name in components], _MARK_COMPONENTS
            )
            _select_named(adapter, axis, "AXIS", _MARK_DIRECTION)
            manager = _sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            if kind == "circular":
                data = _sw_type_info.flagged(
                    manager.CreateDefinition(_LOCAL_CIRCULAR_PATTERN),
                    "ILocalCircularPatternFeatureData",
                )
                data.TotalInstances = count
                data.EqualSpacing = math.isclose(float(angle or 360.0), 360.0)
                data.Spacing = math.radians(float(angle or 360.0))
            else:
                data = _sw_type_info.flagged(
                    manager.CreateDefinition(_LOCAL_LINEAR_PATTERN),
                    "ILocalLinearPatternFeatureData",
                )
                data.D1TotalInstances = count
                data.D1Spacing = float(spacing or 0.0) / 1000.0
            feature = manager.CreateFeature(data)
            model.ClearSelection2(True)
            if feature is None:
                raise Exception("SolidWorks refused the component pattern")
            after = _component_names(adapter, assembly)
            added = [name for name in after if name not in before]
            expected = (count - 1) * len(components)
            if len(added) != expected:
                raise Exception(
                    f"The component pattern added {len(added)} components, "
                    f"not {expected}"
                )
            return {
                "feature": str(feature.Name),
                "components_before": len(before),
                "components_after": len(after),
                "added": added,
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("pattern_components", run),
        )

    async def mirror_components(
        self, components: list[str], plane: str
    ) -> AdapterResult[dict[str, Any]]:
        """Mirror components about a plane, as instances of the same parts.

        ``IAssemblyDoc.MirrorComponents3`` with the components as
        ``ComponentsToInstance`` and nothing mirrored into new files.

        Returns:
            AdapterResult[dict[str, Any]]: The ``plane`` and the ``added``
            instances' names.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "mirror_components"):
            return wrong

        def run() -> dict[str, Any]:
            model = adapter.currentModel
            assembly = _assembly(adapter)
            found = _find_components(adapter, assembly, components)
            before = _component_names(adapter, assembly)
            model.ClearSelection2(True)
            _select_named(adapter, plane, "PLANE", 0)
            plane_object = _selected(adapter)
            model.ClearSelection2(True)
            assembly.MirrorComponents3(
                plane_object,
                dispatch_array([found[name] for name in components]),
                long_array([_MIRRORED_X_MIRRORED_Y] * len(components)),
                False,
                dispatch_array([]),
                False,
                dispatch_array([]),
                0,
                "",
                "",
                0,
                False,
                False,
                False,
            )
            added = [n for n in _component_names(adapter, assembly) if n not in before]
            if len(added) != len(components):
                raise Exception(
                    f"Mirroring about {plane} added {len(added)} components, "
                    f"not {len(components)}"
                )
            return {"plane": plane, "added": added}

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("mirror_components", run),
        )

    async def replace_component(
        self, component: str, file_path: str, all_instances: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Swap a component for another part or assembly file.

        Selects the component and calls ``IAssemblyDoc.ReplaceComponents2``
        (the file's active configuration, mates re-attached). The file must
        exist; names and files are read back afterwards.

        Returns:
            AdapterResult[dict[str, Any]]: ``component``, ``file_path``, the
            ``replaced`` instances with their files after, and the component
            names before and after.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "replace_component"):
            return wrong
        if not os.path.isfile(file_path):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"No file at {file_path} to replace {component} with",
            )

        def run() -> dict[str, Any]:
            model = adapter.currentModel
            assembly = _assembly(adapter)
            target = _find_components(adapter, assembly, [component])[component]
            old_file = str(target.GetPathName())
            before = _component_names(adapter, assembly)
            model.ClearSelection2(True)
            _select_components(adapter, [target], 0)
            done = assembly.ReplaceComponents2(file_path, "", all_instances, 0, True)
            model.ClearSelection2(True)
            if not done:
                raise Exception(f"SolidWorks refused to replace {component}")
            after = _component_names(adapter, assembly)
            replaced = {
                name: str(found.GetPathName())
                for name, found in _find_components(adapter, assembly, after).items()
                if os.path.normcase(str(found.GetPathName()))
                == os.path.normcase(file_path)
            }
            if not replaced:
                raise Exception(f"{component} still uses {old_file}")
            return {
                "component": component,
                "file_path": file_path,
                "replaced": replaced,
                "components_before": before,
                "components_after": after,
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("replace_component", run),
        )

    async def set_component_appearance(
        self,
        component: str,
        visible: bool | None = None,
        transparent: bool | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Hide or show a component, and make it transparent or opaque.

        Visibility is ``IComponent2.Visible`` (1 shown, 0 hidden);
        transparency selects the component and calls
        ``IAssemblyDoc.SetComponentTransparent``. Both are read back.

        Returns:
            AdapterResult[dict[str, Any]]: ``visible`` and ``transparent``
            after.
        """
        adapter = self._adapter(self)
        if wrong := _need_assembly(adapter, "set_component_state"):
            return wrong

        def run() -> dict[str, Any]:
            model = adapter.currentModel
            assembly = _assembly(adapter)
            target = _find_components(adapter, assembly, [component])[component]
            if visible is not None:
                target.Visible = 1 if visible else 0
            if transparent is not None:
                model.ClearSelection2(True)
                _select_components(adapter, [target], 0)
                assembly.SetComponentTransparent(transparent)
                model.ClearSelection2(True)
            shown = int(target.Visible) == 1
            if visible is not None and shown is not visible:
                raise Exception(
                    f"{component} is still {'hidden' if visible else 'shown'}"
                )
            return {
                "visible": shown,
                "transparent": transparent,
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("set_component_state", run),
        )

    async def add_balloons(
        self, view_name: str, layout: str = "square"
    ) -> AdapterResult[dict[str, Any]]:
        """Number a drawing view's parts with balloons, one per part.

        Selects the view and calls ``IDrawingDoc.AutoBalloon5`` with
        options from ``CreateAutoBalloonOptions``: the ``layout``,
        circular balloons, one per part (``IgnoreMultiple``).

        Returns:
            AdapterResult[dict[str, Any]]: The ``view``, ``layout``,
            balloon ``count`` and their ``items`` (the numbers shown).
        """
        adapter = self._adapter(self)
        if _doc_type(adapter) != 3:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="add_balloons requires a drawing document",
            )

        def run() -> dict[str, Any]:
            drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
            if _resolve_drawing_view(adapter, drawing, view_name) is None:
                raise Exception(
                    f"No view named {view_name!r}. Views: "
                    f"{', '.join(_view_names(adapter, drawing)) or 'none'}"
                )
            adapter.currentModel.ClearSelection2(True)
            _select_named(adapter, view_name, "DRAWINGVIEW", 0)
            options = drawing.CreateAutoBalloonOptions()
            options.Layout = BALLOON_LAYOUTS[layout]
            options.IgnoreMultiple = True
            options.Style = _BALLOON_CIRCULAR
            notes = as_list(drawing.AutoBalloon5(options))
            adapter.currentModel.ClearSelection2(True)
            if not notes:
                raise Exception(f"SolidWorks added no balloons to {view_name}")
            items = [
                str(_sw_type_info.flagged(note, "INote").GetText()) for note in notes
            ]
            return {
                "view": view_name,
                "layout": layout,
                "count": len(notes),
                "items": items,
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("add_balloons", run),
        )
