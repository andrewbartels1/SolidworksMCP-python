"""Modelled threads on SolidWorks (queue item 43): the Thread feature.

Measured on SolidWorks 2026 (design.md of the ``modelled-threads`` change):

- the profiles are ``.SLDLFP`` files in the folder
  ``GetUserPreferenceStringValue(swFileLocationsThreadProfiles)`` names;
  each size is a configuration, read by ``ISldWorks.GetConfigurationNames``
  without opening the file;
- ``IFeatureManager.CreateDefinition(swFmSweepThread)`` gives an
  ``IThreadFeatureData``; after ``InitializeThreadData`` it takes the
  circular ``Edge``, the profile's name as ``Type`` (SolidWorks finds the
  file), a configuration as ``Size``, ``ThreadMethod`` 0 (cut),
  ``EndCondition`` 0 (blind) and ``BlindDepth`` in metres;
  ``CreateFeature`` makes "Thread1".

The thread is judged by the volume (``_measured``, direction -1): one that
cuts nothing is deleted and fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ...exceptions import InputRefused
from .. import sw_type_info
from .. import thread_rules as rules
from ..base import AdapterResult, AdapterResultStatus, ThreadParameters
from . import hole_library
from .features import _null_callout

#: ``swUserPreferenceStringValue_e.swFileLocationsThreadProfiles``.
_THREAD_PROFILES_FOLDER = 107
#: ``swFeatureNameID_e.swFmSweepThread``.
_SWEEP_THREAD = 87
#: ``swThreadMethod_e.swThreadMethod_Cut``.
_CUT = 0
#: ``swThreadEndCondition_e.swThreadEndCondition_Blind``.
_BLIND = 0
_PROFILE_SUFFIX = ".sldlfp"


class SolidWorksThreadsMixin:
    """``list_thread_sizes`` and ``create_thread`` on SolidWorks."""

    def _profile_path(self, profile: str) -> Path:
        """The profile's file, in the folder SolidWorks names for them.

        Raises:
            RuntimeError: SolidWorks names no folder holding the profile.
        """
        adapter: Any = self
        setting = adapter._attempt(
            lambda: adapter.swApp.GetUserPreferenceStringValue(_THREAD_PROFILES_FOLDER),
            default="",
        )
        for folder in str(setting or "").split(";"):
            if not folder.strip():
                continue
            for candidate in Path(folder.strip()).glob("*"):
                if candidate.name.lower() == profile.lower() + _PROFILE_SUFFIX:
                    return candidate
        raise RuntimeError(
            f"SolidWorks names no thread profile '{profile}' (Tools > Options > "
            f"File Locations > Thread Profiles: '{setting}')."
        )

    def _profile_sizes(self, standard: str, kind: str) -> list[str]:
        """The sizes (configurations) of a standard's die or tap profile."""
        adapter: Any = self
        path = self._profile_path(rules.PROFILES[(standard, kind)])
        names = adapter._attempt(lambda: adapter.swApp.GetConfigurationNames(str(path)))
        if not isinstance(names, (list, tuple)) or not names:
            raise RuntimeError(f"SolidWorks read no sizes from {path}.")
        return [str(name) for name in names]

    def _coarse_pitches(self, standard: str) -> dict[float, float]:
        """Metric coarse pitches from the installed Hole Wizard library.

        Empty for inch, or when the library can't be read; the size list
        then decides coarse and fine by itself.
        """
        adapter: Any = self
        if standard != "metric":
            return {}
        rows = adapter._attempt(
            lambda: hole_library.find_library().size_rows("iso", "DATA_HW_TappedHole"),
            default=[],
        )
        return rules.coarse_from_hole_rows(rows or [])

    def _circular_edge_at(self, point: list[float]) -> tuple[Any, float]:
        """The circular edge at ``point`` (mm) and its diameter (mm).

        Raises:
            InputRefused: No edge at the point, or one that isn't a circle.
        """
        adapter: Any = self
        model = adapter.currentModel
        # New edges are not selectable by coordinates until a rebuild
        # (COM pitfall #13).
        adapter._attempt(lambda: model.ForceRebuild3(True))
        adapter._attempt(lambda: model.ClearSelection2(True))
        extension = sw_type_info.flagged(model.Extension, "IModelDocExtension")
        x, y, z = (float(v) / 1000.0 for v in point)
        picked = adapter._attempt(
            lambda: extension.SelectByID2(
                "", "EDGE", x, y, z, False, 0, _null_callout(), 0
            ),
            default=False,
        )
        manager = sw_type_info.flagged(model.SelectionManager, "ISelectionMgr")
        edge = adapter._attempt(lambda: manager.GetSelectedObject6(1, -1))
        adapter._attempt(lambda: model.ClearSelection2(True))
        if not picked or edge is None:
            raise InputRefused(
                f"No edge at {list(point)} mm; give a point on the circular "
                "edge where the thread starts."
            )
        edge = sw_type_info.flagged(edge, "IEdge")
        curve = sw_type_info.flagged(
            adapter._attempt(lambda: edge.GetCurve()), "ICurve"
        )
        circle = adapter._attempt(lambda: curve.CircleParams)
        if not adapter._attempt(lambda: curve.IsCircle(), default=False) or not (
            isinstance(circle, (list, tuple)) and len(circle) >= 7
        ):
            raise InputRefused(
                f"The edge at {list(point)} mm is not a circle; a thread starts "
                "at a cylinder's circular edge."
            )
        return edge, round(float(circle[6]) * 2000.0, 4)

    async def list_thread_sizes(self, standard: str) -> AdapterResult[dict[str, Any]]:
        """The sizes SolidWorks's die profile holds for a standard.

        Args:
            standard: ``metric`` or ``inch``.

        Returns:
            AdapterResult[dict[str, Any]]: ``standard``, ``profile``,
            ``sizes`` (see :func:`..thread_rules.size_table`), ``count`` and
            ``runout_basis``.
        """
        adapter: Any = self

        def read() -> dict[str, Any]:
            if standard not in rules.STANDARDS:
                raise InputRefused(
                    f"standard must be one of {', '.join(rules.STANDARDS)}."
                )
            sizes = rules.size_table(
                self._profile_sizes(standard, "external"),
                self._coarse_pitches(standard),
            )
            return {
                "standard": standard,
                "profile": rules.PROFILES[(standard, "external")],
                "sizes": sizes,
                "count": len(sizes),
                "runout_basis": rules.RUNOUT_BASIS[standard],
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("list_thread_sizes", read),
        )

    async def create_thread(
        self, params: ThreadParameters
    ) -> AdapterResult[dict[str, Any]]:
        """A modelled thread, cut by SolidWorks's Thread feature, measured.

        Args:
            params: The kind, standard, size, edge, length and hand.

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, the size, pitch, depth,
            runout and edge diameter, plus the volume before, after and its
            change (``_measured``).
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def build() -> dict[str, Any]:
            rules.check_inputs(params)
            profile = rules.PROFILES[(params.standard, params.kind)]
            size = rules.match_size(
                self._profile_sizes(params.standard, params.kind), params.size
            )
            edge, diameter = self._circular_edge_at(params.edge_point)
            rules.check_diameter(size, params.kind, diameter)
            model = adapter.currentModel
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            data = sw_type_info.flagged(
                manager.CreateDefinition(_SWEEP_THREAD), "IThreadFeatureData"
            )
            data.InitializeThreadData()
            data.Edge = edge
            data.Type = profile
            data.Size = size.size
            data.ThreadMethod = _CUT
            data.EndCondition = _BLIND
            data.BlindDepth = params.length / 1000.0
            data.RightHanded = params.hand == "right"
            feature = manager.CreateFeature(data)
            if feature is None:
                raise RuntimeError(
                    f"SolidWorks made no thread ({profile} {size.size} on the "
                    f"{diameter:g} mm edge)."
                )
            entry = rules.size_entry(size, "")
            return {
                "name": str(sw_type_info.flagged(feature, "IFeature").Name),
                "kind": params.kind,
                "standard": params.standard,
                "profile": profile,
                "size": size.size,
                "pitch_mm": size.pitch_mm,
                "basic_depth_mm": entry["basic_depth_mm"],
                "runout_mm": entry["runout_mm"],
                "runout_basis": rules.RUNOUT_BASIS[params.standard],
                "length_mm": params.length,
                "hand": params.hand,
                "edge_diameter_mm": diameter,
                "turns": round(params.length / size.pitch_mm, 2),
            }

        return cast(
            AdapterResult[dict[str, Any]],
            await adapter._measured("create_thread", build, direction=-1),
        )
