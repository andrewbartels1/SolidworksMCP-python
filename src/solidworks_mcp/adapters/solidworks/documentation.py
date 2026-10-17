"""Model-data and drawing-documentation mixin for PyWin32 SolidWorks operations.

Covers the engineering data a drawing or BOM is built from - model dimensions,
measurements, material, custom properties, sheet-metal flat patterns - and the
drawing steps that consume it: importing model dimensions into views, placing a
BOM table, and setting sheet scale.

Every method name, argument order and enum value below was read from the
SOLIDWORKS 2025 type libraries (``sldworks.tlb`` via gen_py, ``swconst.tlb``
via ``pythoncom.LoadTypeLib``), not from memory. Live behaviour is covered by
``tests/live/test_live_sw_documentation_tools.py``.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, cast

from ..base import AdapterResult, AdapterResultStatus
from . import dimension_layout as _layout
from .features import _null_callout, _parse_edge_spec, _select_edge_by_coord
from .io import _as_com, _doc_type, _resolve_drawing_view, _sw_type_info, _view_names

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

# swUserPreferenceStringValue_e
_SW_PREF_MATERIAL_DATABASES = 28
_SW_PREF_BOM_TEMPLATES = 22
# swInsertAnnotation_e
_SW_INSERT_DIMENSIONS = 8
_SW_INSERT_DIMENSIONS_MARKED_FOR_DRAWING = 32768
_SW_INSERT_HOLE_WIZARD_LOCATION_DIMS = 131072
# swImportModelItemsSource_e
_SW_IMPORT_FROM_ENTIRE_MODEL = 0
# swAutodimEntities_e / swAutodimScheme_e / placements
_SW_AUTODIM_ENTITIES_ALL = 1
_SW_AUTODIM_SCHEME_BASELINE = 1
_SW_AUTODIM_HORIZONTAL_BELOW = -1
_SW_AUTODIM_VERTICAL_LEFT = -1
_SW_AUTODIM_STATUS_SUCCESS = 0
# swBomType_e
_SW_BOM_TYPES = {"parts_only": 1, "top_level_only": 2, "indented": 3, "flattened": 4}
# swBOMConfigurationAnchorType_e
_SW_BOM_ANCHOR_TOP_LEFT = 1
# swNumberingType_e
_SW_NUMBERING_NONE = 0
# swCustomInfoType_e / swCustomPropertyAddOption_e
_SW_CUSTOM_INFO_TEXT = 30
_SW_CUSTOM_PROPERTY_REPLACE_VALUE = 2
# swExportToDWG_e
_SW_EXPORT_SHEET_METAL = 1
# swBodyType_e
_SW_SOLID_BODY = 0
# swAnnotationType_e
_SW_ANNOTATION_DISPLAY_DIMENSION = 4


class _DimensionOverlapError(Exception):
    """Raised by arrange_dimensions when the no-overlap rule still fails."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        kinds = sorted({o["kind"] for o in result.get("remaining_overlaps", [])})
        sample = "; ".join(
            f"{o['dimension']} vs {o['conflicts_with']} ({o['kind']})"
            for o in result.get("remaining_overlaps", [])[:5]
        )
        super().__init__(
            f"{result['overlaps_after']} dimension overlap(s) remain after arranging "
            f"{result['dimensions']} dimension(s) ({', '.join(kinds)}): {sample}. "
            "Try a smaller sheet scale or a larger sheet so the views have room."
        )


_DEFAULT_MATERIAL_DATABASE = "SOLIDWORKS Materials"

# SelectByID2 entity types accepted by measure_entities, keyed by spec prefix.
_MEASURE_PREFIXES = {"face": "FACE", "edge": "EDGE", "vertex": "VERTEX"}


def _parse_measure_spec(spec: str) -> tuple[str, float, float, float, str]:
    """Parse a ``measure_entities`` entity spec into SelectByID2 arguments.

    Accepts the same ``"face:x,y,z"`` / ``"x,y,z"`` / ``"Edge<1>"`` forms as
    ``add_fillet`` (via :func:`_parse_edge_spec`), plus ``"edge:x,y,z"`` and
    ``"vertex:x,y,z"``. Coordinates are in metres.

    Args:
        spec: The entity spec.

    Returns:
        tuple[str, float, float, float, str]: name, x, y, z and entity type.
    """
    prefix, sep, rest = spec.partition(":")
    kind = _MEASURE_PREFIXES.get(prefix.strip().lower()) if sep else None
    if kind in {"EDGE", "VERTEX"}:
        parts = rest.split(",")
        if len(parts) == 3:
            try:
                return "", float(parts[0]), float(parts[1]), float(parts[2]), kind
            except ValueError:
                pass
        return rest, 0.0, 0.0, 0.0, kind
    return _parse_edge_spec(spec)


def _parse_material_library(path: str) -> list[dict[str, str]]:
    """Read material names and classifications from one ``.sldmat`` file.

    ``.sldmat`` is XML: ``<classification name=...>`` elements hold
    ``<material name=...>`` children. Tags are matched by local name because
    the root element carries a namespace.

    Args:
        path: Path to the ``.sldmat`` file.

    Returns:
        list[dict[str, str]]: ``name``, ``classification`` and ``database``
        for each material; empty when the file cannot be parsed.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    database = os.path.splitext(os.path.basename(path))[0]
    materials: list[dict[str, str]] = []
    for classification in root.iter():
        if classification.tag.rsplit("}", 1)[-1] != "classification":
            continue
        class_name = classification.get("name", "")
        for child in classification:
            if child.tag.rsplit("}", 1)[-1] == "material" and child.get("name"):
                materials.append(
                    {
                        "name": child.get("name", ""),
                        "classification": class_name,
                        "database": database,
                    }
                )
    return materials


def _unpack_custom_property(raw: Any) -> tuple[str, str]:
    """Pull (value, resolved value) out of an ``ICustomPropertyManager::Get6`` result.

    Under late binding the out-parameters come back as a tuple that may or may
    not lead with the integer return code, depending on the pywin32 build.

    Args:
        raw: Whatever ``Get6`` returned.

    Returns:
        tuple[str, str]: The raw (possibly ``$PRP:`` linked) value and the
        resolved value; empty strings when the shape is unrecognised.
    """
    if not isinstance(raw, (list, tuple)):
        return ("", "")
    items = list(raw)
    if items and isinstance(items[0], int) and not isinstance(items[0], bool):
        items = items[1:]
    strings = [str(item) for item in items if isinstance(item, str)]
    if not strings:
        return ("", "")
    value = strings[0]
    resolved = strings[1] if len(strings) > 1 else value
    return (value, resolved)


def _read_custom_property(adapter: Any, manager: Any, name: str) -> tuple[str, str]:
    """Read one custom property's (value, resolved value).

    Tries ``Get6`` (value and resolved value) first; under late binding on
    SW 2025 its out-parameters raise ``Parameter not optional``, so it falls
    back to ``Get(name)``, which returns the stored text only.
    """
    value, resolved = _unpack_custom_property(
        adapter._attempt(lambda: manager.Get6(name, False), default=None)
    )
    if value:
        return value, resolved
    plain = adapter._attempt(lambda: manager.Get(name), default=None)
    text = str(plain) if isinstance(plain, str) else ""
    return text, text


def _strip_document_suffix(full_name: Any) -> str | None:
    """Turn ``"D1@Sketch1@Part10.Part"`` into ``"D1@Sketch1"``.

    Live SW 2025 appends ``@<document title>`` to ``IDimension::FullName``;
    ``IModelDoc2::Parameter`` (behind ``set_dimension``) takes the short form.
    """
    if not isinstance(full_name, str):
        return None
    parts = full_name.split("@")
    if len(parts) >= 3 and "." in parts[-1]:
        return "@".join(parts[:-1])
    return full_name


def _sequence(raw: Any) -> list[Any]:
    """Normalise a COM array return (``None``, scalar or tuple) into a list."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [item for item in raw if item is not None]
    return [raw]


class SolidWorksDocumentationMixin:
    """Expose model-data and drawing-documentation methods through a mixin."""

    if TYPE_CHECKING:  # pragma: no cover
        currentModel: Any
        swApp: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], default: Any = None
        ) -> Any: ...

        def _require_drawing(self) -> AdapterResult[Any] | None: ...

    def _require_doc_type(
        self, allowed: set[int], operation: str
    ) -> AdapterResult[Any] | None:
        """Return an error result unless the active document type is allowed.

        Args:
            allowed: Accepted ``swDocumentTypes_e`` values (1 part, 2 assembly,
                3 drawing).
            operation: Operation name for the error message.

        Returns:
            AdapterResult[Any] | None: ``None`` when allowed, else the error.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        names = {1: "part", 2: "assembly", 3: "drawing"}
        doc_type = _doc_type(self)
        if doc_type not in allowed:
            wanted = " or ".join(names[t] for t in sorted(allowed))
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"{operation} needs an active {wanted} document "
                    f"(active document is {names.get(doc_type or 0, 'unknown')})."
                ),
            )
        return None

    # ------------------------------------------------------------------
    # Model data
    # ------------------------------------------------------------------

    async def list_model_dimensions(
        self, feature_name: str | None = None
    ) -> AdapterResult[list[dict[str, Any]]]:
        """List every dimension in the active part or assembly.

        Walks ``IModelDoc2::FirstFeature`` / ``IFeature::GetNextFeature`` and
        each feature's ``GetFirstDisplayDimension`` chain. ``full_name`` (e.g.
        ``"D1@Sketch1"``) is the name ``set_dimension`` accepts, so the pair
        gives edit-by-name access to every driving parameter in the model.

        Args:
            feature_name: Only list dimensions of this feature (case-insensitive).

        Returns:
            AdapterResult[list[dict[str, Any]]]: ``full_name``, ``feature``,
            ``value`` (document units), ``system_value`` (metres / radians)
            and ``read_only`` per dimension.
        """
        guard = self._require_doc_type({1, 2}, "list_model_dimensions")
        if guard is not None:
            return cast("AdapterResult[list[dict[str, Any]]]", guard)
        target = (feature_name or "").strip().lower()

        def _list() -> list[dict[str, Any]]:
            model = self.currentModel
            dims: list[dict[str, Any]] = []
            feature = self._attempt(lambda: model.FirstFeature(), default=None)
            guard_count = 0
            while feature is not None and guard_count < 20000:
                guard_count += 1
                feat = _sw_type_info.flagged(feature, "IFeature")
                name = str(self._attempt(lambda f=feat: f.Name, default="") or "")
                if not target or name.lower() == target:
                    display = self._attempt(
                        lambda f=feat: f.GetFirstDisplayDimension(), default=None
                    )
                    while display is not None:
                        disp = _sw_type_info.flagged(display, "IDisplayDimension")
                        dim = self._attempt(
                            lambda d=disp: d.GetDimension2(0), default=None
                        )
                        if dim is not None:
                            dim = _sw_type_info.flagged(dim, "IDimension")
                            dims.append(
                                {
                                    "full_name": _strip_document_suffix(
                                        self._attempt(
                                            lambda d=dim: d.FullName, default=None
                                        )
                                    ),
                                    "feature": name,
                                    "value": self._attempt(
                                        lambda d=dim: d.Value, default=None
                                    ),
                                    "system_value": self._attempt(
                                        lambda d=dim: d.SystemValue, default=None
                                    ),
                                    "read_only": bool(
                                        self._attempt(
                                            lambda d=dim: d.ReadOnly, default=False
                                        )
                                    ),
                                }
                            )
                        display = self._attempt(
                            lambda f=feat, d=display: f.GetNextDisplayDimension(d),
                            default=None,
                        )
                feature = self._attempt(lambda f=feat: f.GetNextFeature(), default=None)
            if target and not dims:
                raise Exception(f"No dimensions found on feature {feature_name!r}")
            return dims

        return cast(
            "AdapterResult[list[dict[str, Any]]]",
            self._handle_com_operation("list_model_dimensions", _list),
        )

    async def measure_entities(
        self, entities: list[str]
    ) -> AdapterResult[dict[str, Any]]:
        """Measure one or more entities with SolidWorks' Measure tool.

        Selects each entity by spec (see :func:`_parse_measure_spec`), then runs
        ``IModelDocExtension::CreateMeasure`` + ``IMeasure::Calculate(None)``,
        which measures the current selection. Values SolidWorks reports as
        ``-1`` (not applicable to the selection) are dropped.

        Args:
            entities: One or two entity specs, e.g. ``["face:0,0.01,0"]`` for a
                face area, or two edge/face specs for distance and angle.

        Returns:
            AdapterResult[dict[str, Any]]: Measured values in metres, square
            metres and radians, plus ``selected``.
        """
        guard = self._require_doc_type({1, 2}, "measure_entities")
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if not entities or len(entities) > 2:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="measure_entities takes one or two entity specs",
            )

        def _measure() -> dict[str, Any]:
            model = self.currentModel
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            for index, spec in enumerate(entities):
                name, x, y, z, kind = _parse_measure_spec(spec)
                append = index > 0
                if name:
                    ok = bool(
                        self._attempt(
                            lambda n=name, k=kind, a=append: (
                                model.Extension.SelectByID2(
                                    n, k, 0.0, 0.0, 0.0, a, 0, _null_callout(), 0
                                )
                            ),
                            default=False,
                        )
                    )
                else:
                    ok = _select_edge_by_coord(self, x, y, z, append, 0, kind)
                if not ok:
                    raise Exception(f"Could not select {spec!r}")

            measure = self._attempt(
                lambda: model.Extension.CreateMeasure(), default=None
            )
            if measure is None:
                raise Exception("CreateMeasure returned nothing")
            measure = _sw_type_info.flagged(measure, "IMeasure")
            if not self._attempt(lambda: measure.Calculate(None), default=False):
                raise Exception("IMeasure.Calculate failed for this selection")

            result: dict[str, Any] = {"selected": list(entities)}
            for prop, key in (
                ("Distance", "distance_m"),
                ("CenterDistance", "center_distance_m"),
                ("Angle", "angle_rad"),
                ("Radius", "radius_m"),
                ("Diameter", "diameter_m"),
                ("Length", "length_m"),
                ("ArcLength", "arc_length_m"),
                ("Area", "area_m2"),
                ("Perimeter", "perimeter_m"),
                ("DeltaX", "delta_x_m"),
                ("DeltaY", "delta_y_m"),
                ("DeltaZ", "delta_z_m"),
            ):
                value = self._attempt(lambda p=prop: getattr(measure, p), default=None)
                if isinstance(value, (int, float)) and value != -1:
                    result[key] = float(value)
            parallel = self._attempt(lambda: measure.IsParallel, default=None)
            if isinstance(parallel, bool):
                result["is_parallel"] = parallel
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            return result

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("measure_entities", _measure),
        )

    async def get_material(
        self, configuration: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Read the material assigned to the active part.

        Wraps ``IPartDoc::GetMaterialPropertyName2``, whose ``Database`` is an
        out-parameter: the late-bound call returns ``(name, database)``.

        Args:
            configuration: Configuration name; the active one when omitted.

        Returns:
            AdapterResult[dict[str, Any]]: ``material`` (``None`` when unset)
            and ``database``.
        """
        guard = self._require_doc_type({1}, "get_material")
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)

        def _get() -> dict[str, Any]:
            part = _sw_type_info.flagged(self.currentModel, "IPartDoc")
            raw = part.GetMaterialPropertyName2(configuration or "")
            name, database = "", ""
            if isinstance(raw, (list, tuple)):
                strings = [str(s) for s in raw if isinstance(s, str)]
                name = strings[0] if strings else ""
                database = strings[1] if len(strings) > 1 else ""
            elif isinstance(raw, str):
                name = raw
            return {
                "material": name or None,
                "database": database or None,
                "configuration": configuration,
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("get_material", _get),
        )

    async def set_material(
        self,
        material_name: str,
        database: str | None = None,
        configuration: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Assign a material to the active part.

        Wraps ``IPartDoc::SetMaterialPropertyName2`` (a ``void`` call), then
        reads the material back - the read-back is the only proof it applied.

        Args:
            material_name: Material name exactly as in the library, e.g.
                ``"AISI 1020"`` or ``"6061-T6 (SS)"``.
            database: Library name; ``"SOLIDWORKS Materials"`` when omitted.
            configuration: Configuration name; ``""`` (all) when omitted.

        Returns:
            AdapterResult[dict[str, Any]]: Requested and applied material.
        """
        guard = self._require_doc_type({1}, "set_material")
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if not material_name.strip():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="material_name is required"
            )
        library = database or _DEFAULT_MATERIAL_DATABASE

        def _set() -> dict[str, Any]:
            part = _sw_type_info.flagged(self.currentModel, "IPartDoc")
            part.SetMaterialPropertyName2(configuration or "", library, material_name)
            self._attempt(lambda: self.currentModel.EditRebuild3(), default=None)
            raw = self._attempt(
                lambda: part.GetMaterialPropertyName2(configuration or ""), default=None
            )
            strings = [str(s) for s in _sequence(raw) if isinstance(s, str)]
            applied = strings[0] if strings else ""
            if applied.lower() != material_name.lower():
                raise Exception(
                    f"Material {material_name!r} from {library!r} was not applied "
                    f"(part reports {applied or 'no material'}). Check the exact "
                    "name with list_available_materials."
                )
            return {
                "material": applied,
                "database": library,
                "configuration": configuration,
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("set_material", _set),
        )

    async def list_available_materials(
        self, search: str | None = None
    ) -> AdapterResult[list[dict[str, str]]]:
        """List materials from the configured SolidWorks material libraries.

        Reads the library folders from ``swFileLocationsMaterialDatabases``
        (a ``;``-separated list) and parses every ``.sldmat`` file in them.

        Args:
            search: Case-insensitive substring filter on name or classification.

        Returns:
            AdapterResult[list[dict[str, str]]]: ``name``, ``classification``
            and ``database`` per material.
        """
        app = getattr(self, "swApp", None)
        if app is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        needle = (search or "").strip().lower()

        def _list() -> list[dict[str, str]]:
            folders = str(
                self._attempt(
                    lambda: app.GetUserPreferenceStringValue(
                        _SW_PREF_MATERIAL_DATABASES
                    ),
                    default="",
                )
                or ""
            )
            if not folders.strip():
                # Measured live on SW 2025: swFileLocationsMaterialDatabases
                # reads back "" although the libraries exist, so fall back to
                # <install>\lang\<language>\sldmaterials beside the executable.
                exe_dir = str(
                    self._attempt(lambda: app.GetExecutablePath(), default="") or ""
                )
                language = str(
                    self._attempt(lambda: app.GetCurrentLanguage(), default="")
                    or "english"
                )
                if exe_dir.lower().endswith(".exe"):
                    exe_dir = os.path.dirname(exe_dir)
                folders = os.path.join(exe_dir, "lang", language, "sldmaterials")
            materials: list[dict[str, str]] = []
            for folder in filter(None, (f.strip() for f in folders.split(";"))):
                if not os.path.isdir(folder):
                    continue
                for entry in sorted(os.listdir(folder)):
                    if entry.lower().endswith(".sldmat"):
                        materials.extend(
                            _parse_material_library(os.path.join(folder, entry))
                        )
            if not materials:
                raise Exception(
                    f"No .sldmat libraries found in: {folders or 'no folders configured'}"
                )
            if needle:
                materials = [
                    m
                    for m in materials
                    if needle in m["name"].lower()
                    or needle in m["classification"].lower()
                ]
            return materials

        return cast(
            "AdapterResult[list[dict[str, str]]]",
            self._handle_com_operation("list_available_materials", _list),
        )

    async def get_custom_properties(
        self, configuration: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Read the custom properties of the active document.

        Wraps ``IModelDocExtension::CustomPropertyManager(config)`` with
        ``GetNames`` + ``Get6``. ``""`` reads the file-level properties a
        drawing title block usually links to.

        Args:
            configuration: Configuration name; file-level when omitted.

        Returns:
            AdapterResult[dict[str, Any]]: ``properties`` mapping name to
            ``{"value", "resolved"}``.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def _get() -> dict[str, Any]:
            manager = _sw_type_info.flagged(
                self.currentModel.Extension.CustomPropertyManager(configuration or ""),
                "ICustomPropertyManager",
            )
            props: dict[str, dict[str, str]] = {}
            names = self._attempt(
                lambda: self._get_attr_or_call(manager, "GetNames"), default=None
            )
            for name in _sequence(names):
                value, resolved = _read_custom_property(self, manager, str(name))
                props[str(name)] = {"value": value, "resolved": resolved}
            return {"configuration": configuration or "", "properties": props}

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("get_custom_properties", _get),
        )

    async def set_custom_property(
        self, name: str, value: str, configuration: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Create or overwrite one text custom property on the active document.

        Wraps ``ICustomPropertyManager::Add3(name, swCustomInfoText, value,
        swCustomPropertyReplaceValue)`` and reads the value back.

        Args:
            name: Property name, e.g. ``"PartNo"`` or ``"DrawnBy"``.
            value: Text value; may be a ``$PRP:"..."`` link.
            configuration: Configuration name; file-level when omitted.

        Returns:
            AdapterResult[dict[str, Any]]: The stored and resolved value.
        """
        if not self.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        if not name.strip():
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="name is required"
            )

        def _set() -> dict[str, Any]:
            manager = _sw_type_info.flagged(
                self.currentModel.Extension.CustomPropertyManager(configuration or ""),
                "ICustomPropertyManager",
            )
            code = manager.Add3(
                name,
                _SW_CUSTOM_INFO_TEXT,
                str(value),
                _SW_CUSTOM_PROPERTY_REPLACE_VALUE,
            )
            stored, resolved = _read_custom_property(self, manager, name)
            if stored != str(value):
                raise Exception(
                    f"Custom property {name!r} was not stored (Add3 returned {code!r}, "
                    f"read back {stored!r})."
                )
            return {
                "name": name,
                "value": stored,
                "resolved": resolved,
                "configuration": configuration or "",
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("set_custom_property", _set),
        )

    async def export_flat_pattern(
        self, file_path: str
    ) -> AdapterResult[dict[str, Any]]:
        """Export the active sheet-metal part's flat pattern to DXF or DWG.

        Wraps ``IPartDoc::ExportToDWG2`` with ``swExportToDWG_ExportSheetMetal``.
        SheetMetalOptions ``1`` exports the flat-pattern geometry only (no bend
        lines or sketches).

        Args:
            file_path: Output ``.dxf`` or ``.dwg`` path.

        Returns:
            AdapterResult[dict[str, Any]]: The written path and its size.
        """
        guard = self._require_doc_type({1}, "export_flat_pattern")
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        out = os.path.abspath(file_path)
        if os.path.splitext(out)[1].lower() not in {".dxf", ".dwg"}:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="file_path must end in .dxf or .dwg",
            )

        def _export() -> dict[str, Any]:
            model = self.currentModel
            part = _sw_type_info.flagged(model, "IPartDoc")
            bodies = _sequence(
                self._attempt(
                    lambda: part.GetBodies2(_SW_SOLID_BODY, True), default=None
                )
            )
            if not any(
                self._attempt(
                    lambda b=b: _as_com(self, b, "IBody2").IsSheetMetal(), default=False
                )
                for b in bodies
            ):
                raise Exception("The active part has no sheet-metal body")
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            model_path = str(
                self._attempt(lambda: model.GetPathName(), default="") or ""
            )
            ok = part.ExportToDWG2(
                out,
                model_path,
                _SW_EXPORT_SHEET_METAL,
                True,
                None,
                False,
                False,
                1,
                None,
            )
            if not ok or not os.path.exists(out):
                raise Exception(f"ExportToDWG2 did not write {out} (returned {ok!r})")
            return {"file_path": out, "size_bytes": os.path.getsize(out)}

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("export_flat_pattern", _export),
        )

    # ------------------------------------------------------------------
    # Drawing documentation
    # ------------------------------------------------------------------

    def _view_dimension_count(self, view: Any) -> int:
        count = self._attempt(lambda: view.GetDisplayDimensionCount(), default=0)
        return int(count) if isinstance(count, (int, float)) else 0

    def _pictorial(self, view: Any) -> bool:
        """True for isometric/dimetric/trimetric views, which are not dimensioned."""
        name = str(self._attempt(lambda: view.GetOrientationName(), default="") or "")
        return any(k in name.lower() for k in ("isometric", "dimetric", "trimetric"))

    def _delete_display_dimension(self, model: Any, an: Any) -> bool:
        """Delete one drawing dimension.

        ``IAnnotation::Select3`` selects nothing under late binding (False with
        a null dispatch, type mismatch with ``None``); selecting by
        ``IDisplayDimension::GetNameForSelection`` with type ``DIMENSION`` and
        ``DeleteSelection2`` works - measured live on SW 2025.
        """
        specific = self._attempt(lambda: an.GetSpecificAnnotation(), default=None)
        disp = (
            _as_com(self, specific, "IDisplayDimension")
            if specific is not None
            else None
        )
        sel_name = (
            self._attempt(lambda: disp.GetNameForSelection(), default=None)
            if disp
            else None
        )
        if not sel_name:
            return False
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        selected = self._attempt(
            lambda: model.Extension.SelectByID2(
                sel_name, "DIMENSION", 0.0, 0.0, 0.0, False, 0, _null_callout(), 0
            ),
            default=False,
        )
        deleted = bool(selected) and bool(
            self._attempt(lambda: model.Extension.DeleteSelection2(0), default=False)
        )
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        return deleted

    def _dimension_annotations(self, view: Any) -> list[tuple[Any, str | None]]:
        """(annotation, model dimension name) for each display dimension in a view."""
        found: list[tuple[Any, str | None]] = []
        ann = self._attempt(lambda: view.GetFirstAnnotation3(), default=None)
        guard = 0
        while ann is not None and guard < 2000:
            guard += 1
            an = _sw_type_info.flagged(ann, "IAnnotation")
            if self._attempt(lambda a=an: a.GetType(), default=None) == (
                _SW_ANNOTATION_DISPLAY_DIMENSION
            ):
                specific = self._attempt(
                    lambda a=an: a.GetSpecificAnnotation(), default=None
                )
                name = None
                if specific is not None:
                    disp = _sw_type_info.flagged(specific, "IDisplayDimension")
                    dim = self._attempt(lambda d=disp: d.GetDimension2(0), default=None)
                    if dim is not None:
                        name = _strip_document_suffix(
                            self._attempt(
                                lambda d=dim: (
                                    _sw_type_info.flagged(d, "IDimension").FullName
                                ),
                                default=None,
                            )
                        )
                found.append((an, name))
            ann = self._attempt(lambda a=an: a.GetNext3(), default=None)
        return found

    def _import_dimensions(
        self,
        view_name: str | None = None,
        include_hole_wizard: bool = True,
        only_views: list[str] | None = None,
    ) -> dict[str, Any]:
        """Synchronous body of insert_model_dimensions (also used by the standard drawing)."""
        model = self.currentModel
        drawing = _sw_type_info.flagged(model, "IDrawingDoc")
        all_names = _view_names(self, drawing)
        if view_name and view_name not in all_names:
            raise Exception(
                f"No view named {view_name!r}. Views: {', '.join(all_names) or 'none'}"
            )
        views = {n: _resolve_drawing_view(self, drawing, n) for n in all_names}
        skipped = (
            [] if view_name else [n for n, v in views.items() if self._pictorial(v)]
        )
        names = [view_name] if view_name else [n for n in all_names if n not in skipped]
        if only_views:
            names = [n for n in only_views if n in all_names]
        before = {n: self._view_dimension_count(views[n]) for n in names}

        types = _SW_INSERT_DIMENSIONS_MARKED_FOR_DRAWING
        if include_hole_wizard:
            types |= _SW_INSERT_HOLE_WIZARD_LOCATION_DIMS
        # Dimensions already on the sheet (any view) count as shown.
        shown: set[str] = set()
        for name in all_names:
            if name in names:
                continue
            shown.update(n for _, n in self._dimension_annotations(views[name]) if n)
        removed: dict[str, int] = {}
        method = "insert_model_annotations"
        for name in names:
            self._attempt(lambda n=name: drawing.ActivateView(n), default=None)
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            self._attempt(
                lambda n=name: model.Extension.SelectByID2(
                    n, "DRAWINGVIEW", 0.0, 0.0, 0.0, False, 0, _null_callout(), 0
                ),
                default=None,
            )
            self._attempt(
                lambda: drawing.InsertModelAnnotations3(
                    _SW_IMPORT_FROM_ENTIRE_MODEL, types, False, False, False, False
                ),
                default=None,
            )
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            removed[name] = 0
            for an, dim_name in self._dimension_annotations(views[name]):
                if dim_name and dim_name in shown:
                    if self._delete_display_dimension(model, an):
                        removed[name] += 1
                elif dim_name:
                    shown.add(dim_name)
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        self._attempt(lambda: model.EditRebuild3(), default=None)

        autodim_status: Any = None
        if not shown and all(self._view_dimension_count(views[n]) == 0 for n in names):
            method = "auto_dimension"
            for name in names:
                self._attempt(lambda: model.ClearSelection2(True), default=None)
                self._attempt(
                    lambda n=name: model.Extension.SelectByID2(
                        n,
                        "DRAWINGVIEW",
                        0.0,
                        0.0,
                        0.0,
                        False,
                        0,
                        _null_callout(),
                        0,
                    ),
                    default=None,
                )
                autodim_status = self._attempt(
                    lambda: drawing.AutoDimension(
                        _SW_AUTODIM_ENTITIES_ALL,
                        _SW_AUTODIM_SCHEME_BASELINE,
                        _SW_AUTODIM_HORIZONTAL_BELOW,
                        _SW_AUTODIM_SCHEME_BASELINE,
                        _SW_AUTODIM_VERTICAL_LEFT,
                    ),
                    default=None,
                )
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            self._attempt(lambda: model.EditRebuild3(), default=None)

        per_view = []
        for name in names:
            after = self._view_dimension_count(views[name])
            per_view.append(
                {
                    "view": name,
                    "dimensions_before": before[name],
                    "dimensions_after": after,
                    "dimensions_added": after - before[name],
                    "duplicates_removed": removed.get(name, 0),
                }
            )
        total = sum(v["dimensions_added"] for v in per_view)
        on_sheet = sum(v["dimensions_after"] for v in per_view)
        if on_sheet == 0:
            raise Exception(
                "No dimensions were added to any view: InsertModelAnnotations3 "
                f"imported nothing and AutoDimension returned {autodim_status!r} "
                "(0 = success). See com-api-pitfalls #18."
            )
        return {
            "views": per_view,
            "dimensions_added": total,
            "unique_dimensions": len(shown),
            "skipped_pictorial_views": skipped,
            "method": method,
            "autodimension_status": autodim_status,
        }

    async def insert_model_dimensions(
        self, view_name: str | None = None, include_hole_wizard: bool = True
    ) -> AdapterResult[dict[str, Any]]:
        """Bring model dimensions into drawing views, each dimension shown once.

        Imports the model's "marked for drawing" dimensions view by view with
        ``IDrawingDoc::InsertModelAnnotations3`` (``UsePlacementInSketch`` off,
        so SolidWorks places them rather than copying sketch positions).
        Drafting rules applied:

        * pictorial views (isometric, dimetric, trimetric) are not dimensioned
          unless named explicitly;
        * a model dimension already shown in an earlier view is deleted from
          later views, so each dimension appears exactly once on the sheet.

        Falls back to ``IDrawingDoc::AutoDimension`` only when nothing at all
        could be imported. Placement is then made overlap-free by
        :meth:`arrange_dimensions`.

        Args:
            view_name: One view to dimension; every orthographic view when omitted.
            include_hole_wizard: Also import Hole Wizard location dimensions.

        Returns:
            AdapterResult[dict[str, Any]]: Per-view counts, duplicates removed,
            skipped pictorial views and the ``method`` used.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)

        def _insert() -> dict[str, Any]:
            return self._import_dimensions(view_name, include_hole_wizard)

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("insert_model_dimensions", _insert),
        )

    async def insert_bom_table(
        self,
        view_name: str,
        template_path: str | None = None,
        bom_type: str = "top_level_only",
        x_mm: float | None = None,
        y_mm: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Insert a bill-of-materials table anchored to an assembly drawing view.

        Wraps ``IView::InsertBomTable4``. With no position the table snaps to
        the sheet format's BOM anchor (``UseAnchorPoint=True``). With no
        template the library default ``bom-standard.sldbomtbt`` from the BOM
        templates folder is used.

        Args:
            view_name: A view of an assembly on the active drawing.
            template_path: ``.sldbomtbt`` table template.
            bom_type: ``top_level_only``, ``parts_only`` or ``indented``.
            x_mm: Optional table position on the sheet.
            y_mm: Optional table position on the sheet.

        Returns:
            AdapterResult[dict[str, Any]]: The view, BOM type and row count.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if bom_type not in _SW_BOM_TYPES or bom_type == "flattened":
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="bom_type must be top_level_only, parts_only or indented",
            )

        def _insert() -> dict[str, Any]:
            drawing = _sw_type_info.flagged(self.currentModel, "IDrawingDoc")
            view = _resolve_drawing_view(self, drawing, view_name)
            if view is None:
                raise Exception(
                    f"No view named {view_name!r}. Views: "
                    f"{', '.join(_view_names(self, drawing)) or 'none'}"
                )
            template = template_path
            if not template:
                folder = str(
                    self._attempt(
                        lambda: self.swApp.GetUserPreferenceStringValue(
                            _SW_PREF_BOM_TEMPLATES
                        ),
                        default="",
                    )
                    or ""
                ).split(";")[0]
                candidate = os.path.join(folder, "bom-standard.sldbomtbt")
                template = candidate if os.path.exists(candidate) else ""
            use_anchor = x_mm is None or y_mm is None
            config = str(
                self._attempt(lambda: view.ReferencedConfiguration, default="") or ""
            )
            numbering = 1 if bom_type == "indented" else _SW_NUMBERING_NONE
            table = view.InsertBomTable4(
                use_anchor,
                (x_mm or 0.0) / 1000.0,
                (y_mm or 0.0) / 1000.0,
                _SW_BOM_ANCHOR_TOP_LEFT,
                _SW_BOM_TYPES[bom_type],
                config,
                template,
                False,
                numbering,
                False,
            )
            if table is None:
                raise Exception(
                    f"InsertBomTable4 returned nothing for view {view_name!r}. "
                    "A BOM needs a view of an assembly"
                    + ("" if template else " and a BOM template (none found)")
                    + "."
                )
            rows = self._attempt(
                lambda: _sw_type_info.flagged(table, "ITableAnnotation").RowCount,
                default=None,
            )
            return {
                "view": view_name,
                "bom_type": bom_type,
                "template": template or None,
                "row_count": rows,
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("insert_bom_table", _insert),
        )

    async def set_sheet_scale(
        self, numerator: float, denominator: float
    ) -> AdapterResult[dict[str, Any]]:
        """Set the active drawing sheet's scale, e.g. 1:2.

        Wraps ``ISheet::SetScale``; views set to "use sheet scale" follow it.

        Args:
            numerator: Scale numerator.
            denominator: Scale denominator.

        Returns:
            AdapterResult[dict[str, Any]]: The sheet name and new scale.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if numerator <= 0 or denominator <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Scale values must be positive"
            )

        def _scale() -> dict[str, Any]:
            drawing = _sw_type_info.flagged(self.currentModel, "IDrawingDoc")
            sheet = _sw_type_info.flagged(drawing.GetCurrentSheet(), "ISheet")
            if not sheet.SetScale(float(numerator), float(denominator), True, False):
                raise Exception("ISheet.SetScale returned False")
            self._attempt(lambda: self.currentModel.EditRebuild3(), default=None)
            name = self._attempt(lambda: sheet.GetName(), default=None)
            return {"sheet": name, "scale": f"{numerator:g}:{denominator:g}"}

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("set_sheet_scale", _scale),
        )

    # ------------------------------------------------------------------
    # Dimension layout: no dimension may overlap another
    # ------------------------------------------------------------------

    def _read_view_dimensions(self, view: Any, view_name: str) -> list[tuple[Any, Any]]:
        """Return ``(annotation, DimensionGeometry)`` for every dimension in a view.

        Geometry comes from ``IAnnotation::GetDisplayData``: text boxes from
        ``GetTextPositionAtIndex`` (lower-left) with the larger of
        ``GetTextInBoxWidthAtIndex`` and a width estimated from the text and
        ``GetTextHeightAtIndex``; lines from ``GetLineAtIndex3``, whose
        endpoints are elements 4-5 and 7-8 of the returned tuple (measured
        live on SW 2025).
        """
        found: list[tuple[Any, Any]] = []
        ann = self._attempt(lambda: view.GetFirstAnnotation3(), default=None)
        index = 0
        while ann is not None and index < 2000:
            an = _sw_type_info.flagged(ann, "IAnnotation")
            kind = self._attempt(lambda a=an: a.GetType(), default=None)
            if kind == _SW_ANNOTATION_DISPLAY_DIMENSION:
                geometry = self._dimension_geometry(
                    an, f"{view_name}#{index}", view_name
                )
                if geometry is not None:
                    found.append((an, geometry))
                index += 1
            ann = self._attempt(lambda a=an: a.GetNext3(), default=None)
        return found

    def _dimension_geometry(self, an: Any, key: str, view_name: str) -> Any:
        position = self._attempt(lambda: an.GetPosition(), default=None)
        data = self._attempt(lambda: an.GetDisplayData(), default=None)
        if not isinstance(position, (list, tuple)) or data is None:
            return None
        dd = _sw_type_info.flagged(data, "IDisplayData")
        boxes: list[tuple[float, float, float, float]] = []
        for i in range(int(self._attempt(lambda: dd.GetTextCount(), default=0) or 0)):
            pos = self._attempt(lambda i=i: dd.GetTextPositionAtIndex(i), default=None)
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                continue
            text = str(
                self._attempt(lambda i=i: dd.GetTextAtIndex(i), default="") or ""
            )
            height = float(
                self._attempt(lambda i=i: dd.GetTextHeightAtIndex(i), default=0.0)
                or 0.0
            )
            box_w = float(
                self._attempt(lambda i=i: dd.GetTextInBoxWidthAtIndex(i), default=0.0)
                or 0.0
            )
            width = max(box_w, len(text.strip()) * height * 0.62)
            boxes.append((pos[0], pos[1], pos[0] + width, pos[1] + max(height, 0.001)))
        if not boxes:
            return None
        text_box = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        lines = []
        for i in range(int(self._attempt(lambda: dd.GetLineCount(), default=0) or 0)):
            raw = self._attempt(lambda i=i: dd.GetLineAtIndex3(i), default=None)
            if isinstance(raw, (list, tuple)) and len(raw) >= 9:
                lines.append(
                    (float(raw[4]), float(raw[5]), float(raw[7]), float(raw[8]))
                )
        return _layout.DimensionGeometry(
            key=key,
            view=view_name,
            text_box=text_box,
            position=(float(position[0]), float(position[1])),
            lines=lines,
        )

    def _sheet_bounds(self, drawing: Any) -> Any:
        """Sheet rectangle from ``ISheet::GetProperties2`` (width/height at 5, 6)."""
        sheet = self._attempt(lambda: drawing.GetCurrentSheet(), default=None)
        if sheet is None:
            return None
        props = self._attempt(
            lambda: _sw_type_info.flagged(sheet, "ISheet").GetProperties2(),
            default=None,
        )
        if isinstance(props, (list, tuple)) and len(props) >= 7:
            width, height = props[5], props[6]
            if (
                isinstance(width, (int, float))
                and isinstance(height, (int, float))
                and width > 0
            ):
                return (0.0, 0.0, float(width), float(height))
        return None

    def _collect_layout(
        self, drawing: Any, names: list[str]
    ) -> tuple[dict, list, dict]:
        outlines: dict[str, tuple[float, float, float, float]] = {}
        annotations: dict[str, Any] = {}
        geometries: list[Any] = []
        for name in names:
            view = _resolve_drawing_view(self, drawing, name)
            if view is None:
                continue
            outline = self._attempt(lambda v=view: v.GetOutline(), default=None)
            if isinstance(outline, (list, tuple)) and len(outline) >= 4:
                outlines[name] = tuple(float(c) for c in outline[:4])
            for an, geometry in self._read_view_dimensions(view, name):
                annotations[geometry.key] = an
                geometries.append(geometry)
        return outlines, geometries, annotations

    def _arrange_layout(
        self,
        view_name: str | None = None,
        obstacles: dict[str, Any] | None = None,
        work_area: Any = None,
        move: bool = True,
        raise_on_overlap: bool = True,
    ) -> dict[str, Any]:
        """Synchronous body of arrange_dimensions (also used by the standard drawing)."""
        model = self.currentModel
        drawing = _sw_type_info.flagged(model, "IDrawingDoc")
        all_views = _view_names(self, drawing)
        if view_name and view_name not in all_views:
            raise Exception(
                f"No view named {view_name!r}. Views: {', '.join(all_views) or 'none'}"
            )
        sheet = work_area or self._sheet_bounds(drawing)
        outlines, geometries, annotations = self._collect_layout(drawing, all_views)
        before = _layout.find_overlaps(geometries, outlines, sheet, obstacles)
        movable = [g for g in geometries if not view_name or g.view == view_name]
        fixed = [g for g in geometries if view_name and g.view != view_name]
        moves, unplaced = (
            _layout.plan_layout(fixed + movable, outlines, sheet, obstacles)
            if move
            else ({}, [])
        )
        moved = 0
        for geometry in movable:
            delta = moves.get(geometry.key)
            if not delta or (abs(delta[0]) < 1e-9 and abs(delta[1]) < 1e-9):
                continue
            an = annotations[geometry.key]
            x, y = geometry.position[0] + delta[0], geometry.position[1] + delta[1]
            current = self._attempt(lambda a=an: a.GetPosition(), default=None)
            z = (
                float(current[2])
                if isinstance(current, (list, tuple)) and len(current) > 2
                else 0.0
            )
            if self._attempt(
                lambda a=an, x=x, y=y, z=z: a.SetPosition(x, y, z), default=False
            ):
                moved += 1
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        self._attempt(lambda: model.EditRebuild3(), default=None)
        self._attempt(lambda: model.GraphicsRedraw2(), default=None)
        outlines, geometries, _ = self._collect_layout(drawing, all_views)
        after = _layout.find_overlaps(geometries, outlines, sheet, obstacles)
        result = {
            "dimensions": len(geometries),
            "moved": moved,
            "unplaced": unplaced,
            "overlaps_before": len(before),
            "overlaps_after": len(after),
            "remaining_overlaps": after[:50],
            "sheet_size_m": [sheet[2], sheet[3]] if sheet else None,
        }
        if after and raise_on_overlap:
            raise _DimensionOverlapError(result)
        return result

    async def arrange_dimensions(
        self, view_name: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Move drawing dimensions so none overlaps another, then verify.

        Reads every dimension's text box and lines, plans positions outside
        the views with :func:`dimension_layout.plan_layout`, applies them with
        ``IAnnotation::SetPosition``, rebuilds, then **re-reads the real
        geometry** and checks the rule with :func:`dimension_layout.find_overlaps`.
        The check covers every view on the sheet, even when only one view is
        rearranged, because neighbouring views' dimensions can collide.

        Args:
            view_name: Only move this view's dimensions; all views when omitted.

        Returns:
            AdapterResult[dict[str, Any]]: ``overlaps_before``, ``overlaps_after``
            (each violation listed), ``moved`` and ``unplaced``. ERROR when any
            overlap remains - the rule is not met.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)

        def _arrange() -> dict[str, Any]:
            return self._arrange_layout(view_name)

        try:
            return cast(
                "AdapterResult[dict[str, Any]]",
                self._handle_com_operation("arrange_dimensions", _arrange),
            )
        except (
            _DimensionOverlapError
        ) as exc:  # pragma: no cover - raised only if not wrapped
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=str(exc), data=exc.result
            )

    def _insert_dimensions_sync(
        self, drawing: Any, model: Any, names: list[str]
    ) -> dict[str, Any]:
        """Import dimensions into the named views (standard-drawing helper)."""
        return self._import_dimensions(None, True, only_views=names)

    def _arrange_sync(
        self,
        drawing: Any,
        model: Any,
        names: list[str],
        obstacles: dict[str, Any],
        work_area: Any,
        move: bool = True,
    ) -> dict[str, Any]:
        """Arrange and check all dimensions against obstacles (standard-drawing helper)."""
        return self._arrange_layout(
            None, obstacles, work_area, move, raise_on_overlap=False
        )
