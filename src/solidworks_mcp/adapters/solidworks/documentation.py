"""Model-data mixin for PyWin32 SolidWorks operations.

Covers the engineering data a drawing or BOM is built from: model dimensions,
measurements, material, custom properties and sheet-metal flat patterns.

Every method name, argument order and enum value below was read from the
SOLIDWORKS 2025 type libraries (``sldworks.tlb`` via gen_py, ``swconst.tlb``
via ``pythoncom.LoadTypeLib``), not from memory. Live behaviour is covered by
``tests/live/test_live_sw_documentation_tools.py``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

import defusedxml.ElementTree as ET
from defusedxml import DefusedXmlException

from ..base import AdapterResult, AdapterResultStatus
from .features import _null_callout, _parse_edge_spec, _select_edge_by_coord
from .io import _as_com, _byref_bstr, _doc_type, _sw_type_info

if TYPE_CHECKING:
    from collections.abc import Callable

# swUserPreferenceStringValue_e
_SW_PREF_MATERIAL_DATABASES = 28
# swCustomInfoType_e / swCustomPropertyAddOption_e
_SW_CUSTOM_INFO_TEXT = 30
_SW_CUSTOM_PROPERTY_REPLACE_VALUE = 2
# swExportToDWG_e
_SW_EXPORT_SHEET_METAL = 1
# swBodyType_e
_SW_SOLID_BODY = 0


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
    the root element carries a namespace. Parsed with ``defusedxml``: library
    folders can be user-configured, so entity-expansion and external-entity
    payloads are refused rather than expanded.

    Args:
        path: Path to the ``.sldmat`` file.

    Returns:
        list[dict[str, str]]: ``name``, ``classification`` and ``database``
        for each material; empty when the file cannot be parsed or is refused.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError, DefusedXmlException):
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

    Args:
        adapter: The adapter, for its ``_attempt`` helper.
        manager: The document's ``ICustomPropertyManager``.
        name: Property name.

    Returns:
        tuple[str, str]: The stored value and the resolved value; empty
        strings when the property cannot be read.
    """
    value, resolved = _unpack_custom_property(
        adapter._attempt(lambda: manager.Get6(name, False), default=None)
    )
    if value:
        return value, resolved
    plain = adapter._attempt(lambda: manager.Get(name), default=None)
    text = str(plain) if isinstance(plain, str) else ""
    return text, text


def _read_material(part: Any, configuration: str | None) -> tuple[str, str]:
    """Read ``(material, database)`` from ``IPartDoc::GetMaterialPropertyName2``.

    ``Database`` is a ``String`` out-parameter: under late binding on SW 2026
    omitting it raises "Parameter not optional", so it is passed as a byref
    BSTR and read back from ``.value``. Older pywin32 builds may instead return
    ``(name, database)`` as a tuple; both shapes are accepted.

    Args:
        part: The active ``IPartDoc``.
        configuration: Configuration name; the active one when ``None``.

    Returns:
        tuple[str, str]: Material name and library; empty strings when unset.
    """
    database = _byref_bstr()
    raw = part.GetMaterialPropertyName2(configuration or "", database)
    if isinstance(raw, (list, tuple)):
        strings = [str(s) for s in raw if isinstance(s, str)]
        name = strings[0] if strings else ""
        library = strings[1] if len(strings) > 1 else ""
    else:
        name = raw if isinstance(raw, str) else ""
        library = ""
    stored = getattr(database, "value", "")
    return name, library or (stored if isinstance(stored, str) else "")


def _strip_document_suffix(full_name: Any) -> str | None:
    """Turn ``"D1@Sketch1@Part10.Part"`` into ``"D1@Sketch1"``.

    Live SW 2025 appends ``@<document title>`` to ``IDimension::FullName``;
    ``IModelDoc2::Parameter`` (behind ``set_dimension``) takes the short form.

    Args:
        full_name: ``IDimension::FullName`` as read.

    Returns:
        str | None: The name without the document suffix; ``None`` when
        ``full_name`` is not text.
    """
    if not isinstance(full_name, str):
        return None
    parts = full_name.split("@")
    if len(parts) >= 3 and "." in parts[-1]:
        return "@".join(parts[:-1])
    return full_name


def _sequence(raw: Any) -> list[Any]:
    """Normalise a COM array return (``None``, scalar or tuple) into a list.

    Args:
        raw: What the COM call returned.

    Returns:
        list[Any]: The non-``None`` items.
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [item for item in raw if item is not None]
    return [raw]


class SolidWorksDocumentationMixin:
    """Expose model-data and drawing-documentation methods through a mixin."""

    if TYPE_CHECKING:
        currentModel: Any
        swApp: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], default: Any = None
        ) -> Any: ...

        def _get_attr_or_call(self, obj: Any, name: str) -> Any: ...

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
                raise LookupError(
                    f"No dimensions found on feature {feature_name!r}; list "
                    "the feature tree with list_features for exact names"
                )
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
            metres and radians, plus ``selected``; ``is_parallel`` only for
            two entities.
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
                    raise LookupError(
                        f"No entity found for {spec!r}; check the name or the "
                        "coordinates (metres)"
                    )

            # CreateMeasure is a zero-arg method; unflagged, late binding asks
            # for it as a property and SW 2026 answers "Member not found".
            # Not wrapped in _attempt: a COM error surfaces with its message.
            extension = _sw_type_info.flagged(model.Extension, "IModelDocExtension")
            measure = extension.CreateMeasure()
            if measure is None:
                raise Exception("CreateMeasure returned nothing")
            measure = _sw_type_info.flagged(measure, "IMeasure")
            if not measure.Calculate(None):
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
            if len(entities) == 2:
                # Parallelism only means something between two entities.
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

        Wraps ``IPartDoc::GetMaterialPropertyName2``; see
        :func:`_read_material` for its ``Database`` out-parameter.

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
            name, database = _read_material(part, configuration)
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
        A name the library does not hold leaves the part unchanged and is
        reported as not found.

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
            applied, _library = _read_material(part, configuration)
            if applied.lower() != material_name.lower():
                # SolidWorks ignores a name its library does not hold.
                raise LookupError(
                    f"Material {material_name!r} not found in {library!r}; the "
                    f"part still reports {applied or 'no material'}. Use "
                    "list_available_materials for the exact name and library."
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

        Reads the custom library folders from
        ``swFileLocationsMaterialDatabases`` (a ``;``-separated list) plus the
        install's built-in ``sldmaterials`` folder, and parses every
        ``.sldmat`` file in them.

        Args:
            search: Case-insensitive substring filter on name or classification.

        Returns:
            AdapterResult[list[dict[str, str]]]: ``name``, ``classification``
            and ``database`` per material. ``metadata`` gives the ``folders``
            read and the ``total`` before filtering, so an empty search can be
            told apart from an unexpected library location.
        """
        app = getattr(self, "swApp", None)
        if app is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Not connected to SolidWorks"
            )
        needle = (search or "").strip().lower()
        searched: dict[str, Any] = {}

        def _list() -> list[dict[str, str]]:
            configured = str(
                self._attempt(
                    lambda: app.GetUserPreferenceStringValue(
                        _SW_PREF_MATERIAL_DATABASES
                    ),
                    default="",
                )
                or ""
            )
            # swFileLocationsMaterialDatabases lists only the folders the user
            # added: "" on a fresh SW 2025 install, just "Custom Materials" on
            # SW 2026 (both measured live). SolidWorks always shows its
            # built-in <install>\lang\<language>\sldmaterials library as
            # well, so read that too.
            exe_dir = str(
                self._attempt(lambda: app.GetExecutablePath(), default="") or ""
            )
            language = str(
                self._attempt(lambda: app.GetCurrentLanguage(), default="") or "english"
            )
            if exe_dir.lower().endswith(".exe"):
                exe_dir = os.path.dirname(exe_dir)
            built_in = os.path.join(exe_dir, "lang", language, "sldmaterials")
            folder_list = [f.strip() for f in configured.split(";") if f.strip()]
            if os.path.normcase(built_in) not in map(os.path.normcase, folder_list):
                folder_list.append(built_in)
            folders = ";".join(folder_list)
            materials: list[dict[str, str]] = []
            for folder in folder_list:
                if not os.path.isdir(folder):
                    continue
                for entry in sorted(os.listdir(folder)):
                    if entry.lower().endswith(".sldmat"):
                        materials.extend(
                            _parse_material_library(os.path.join(folder, entry))
                        )
            searched["folders"] = folder_list
            searched["total"] = len(materials)
            if not materials:
                raise LookupError(f"No .sldmat libraries found in: {folders}")
            if needle:
                materials = [
                    m
                    for m in materials
                    if needle in m["name"].lower()
                    or needle in m["classification"].lower()
                ]
            return materials

        result = cast(
            "AdapterResult[list[dict[str, str]]]",
            self._handle_com_operation("list_available_materials", _list),
        )
        if result.is_success:
            result.metadata = dict(searched)
        return result

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
                raise LookupError(
                    "The active part has no sheet-metal body, so it has no flat "
                    "pattern to export"
                )
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
