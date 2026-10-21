"""Tests for SolidWorks IO mixin behaviors."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import io as _io_module
from solidworks_mcp.adapters.solidworks.io import (
    SolidWorksIOMixin,
    _get_sw_comtypes_lib,
)


class _IOHarness(SolidWorksIOMixin):
    """Minimal harness for IO mixin."""

    def __init__(self, current_model) -> None:
        self.currentModel = current_model

    def _attempt(self, callback, default=None):
        try:
            return callback()
        except Exception:
            return default

    def _handle_com_operation(self, _name, callback, *args):
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=callback())
        except Exception as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))


import pytest


@pytest.mark.asyncio
async def test_get_mass_properties_uses_callable_gmp() -> None:
    """Callable GetMassProperties should be used when CreateMassProperty is missing."""
    # Provide a callable GetMassProperties to cover the callable branch.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=lambda: [1.0, 2.0, 3.0, 0.1, 0.2, 0.3],
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.is_success
    assert result.data.mass == 0.3


@pytest.mark.asyncio
async def test_get_mass_properties_missing_gmp_fails() -> None:
    """Missing GetMassProperties should surface a failure."""
    # Use a non-callable/non-list attribute to hit raw=None.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=123,
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to get mass properties" in (result.error or "")


def test_get_sw_comtypes_lib_returns_cached_value() -> None:
    """Second call returns the cached module without re-querying the registry (io.py:46-47)."""
    sentinel = object()
    with patch.object(_io_module, "_sw_comtypes_lib", sentinel):
        result = _get_sw_comtypes_lib()
    assert result is sentinel


def test_get_sw_comtypes_lib_returns_none_when_comtypes_unavailable() -> None:
    """Returns None immediately when comtypes is not installed (io.py:48-49)."""
    with (
        patch.object(_io_module, "_sw_comtypes_lib", None),
        patch.object(_io_module, "_COMTYPES_AVAILABLE", False),
    ):
        result = _get_sw_comtypes_lib()
    assert result is None


def test_io_imports_without_pywin32_or_comtypes(import_without) -> None:
    """Mock mode on Linux/macOS: names stay defined, COM bridges report absent."""
    attrs = import_without(
        "solidworks_mcp.adapters.solidworks.io",
        [
            "pythoncom",
            "win32com",
            "win32com.client",
            "win32com.client.dynamic",
            "comtypes",
            "comtypes.client",
        ],
        ["_COMTYPES_AVAILABLE", "pythoncom"],
    )

    assert attrs["_COMTYPES_AVAILABLE"] is False
    assert attrs["pythoncom"] == "namespace()"


# ---- byref / array fallbacks, documents, units --------------------------------


def test_com_value_helpers_fall_back_without_pywin32(monkeypatch) -> None:
    monkeypatch.setattr(
        _io_module, "win32com", SimpleNamespace(client=SimpleNamespace())
    )

    assert _io_module._byref_variant().value is None
    assert _io_module._byref_bool().value is False
    assert _io_module._variant_array(9, (1, 2)) == [1, 2]


def test_apply_unit_system_needs_an_extension() -> None:
    harness = _IOHarness(SimpleNamespace())

    with pytest.raises(Exception, match="no Extension"):
        _io_module._apply_unit_system(harness, SimpleNamespace(), "mm")


class _Named:
    def __init__(self, name: str) -> None:
        self._name = name

    def GetName2(self) -> str:  # noqa: N802
        return self._name


def test_resolve_drawing_view_edge_cases(monkeypatch) -> None:
    monkeypatch.setattr(_io_module, "_as_com", lambda _a, view, _i: view)
    harness = _IOHarness(SimpleNamespace())
    front = _Named("Front")
    drawing = SimpleNamespace(GetViews=lambda: [["Sheet1", None, front]])

    assert _io_module._resolve_drawing_view(harness, drawing, "  ") is None
    assert (
        _io_module._resolve_drawing_view(
            harness, SimpleNamespace(GetViews=lambda: None), "Front"
        )
        is None
    )
    assert _io_module._resolve_drawing_view(harness, drawing, "front") is front


class _DocsHarness(_IOHarness):
    """IO mixin harness with an application object and connection state."""

    def __init__(self, current_model, app) -> None:
        super().__init__(current_model)
        self.swApp = app

    def is_connected(self) -> bool:
        return self.swApp is not None

    def _get_attr_or_call(self, obj, name):
        value = getattr(obj, name, None)
        return value() if callable(value) else value

    def _sync_current_model_from_active(self) -> None:
        return None

    def _read_model_title(self, model) -> str:
        return "Part1"


@pytest.mark.asyncio
async def test_create_part_units_are_validated_and_failures_recorded(
    monkeypatch,
) -> None:
    model = SimpleNamespace()
    harness = _DocsHarness(None, SimpleNamespace(NewPart=lambda: model))

    def _units_fail(*_a):
        raise RuntimeError("readback mismatch")

    monkeypatch.setattr(_io_module, "_apply_unit_system", _units_fail)

    unknown = await harness.create_part(units="furlong")
    created = await harness.create_part(units="mm")

    assert unknown.is_error and "Unrecognised units 'furlong'" in unknown.error
    assert created.is_success
    assert created.data.properties["units_error"] == "readback mismatch"


@pytest.mark.asyncio
async def test_get_dimension_reports_an_unreadable_value() -> None:
    def _no_value(*_a):
        raise RuntimeError("GetValue3 unavailable")

    dimension = SimpleNamespace(SystemValue=None, GetValue3=_no_value)
    harness = _DocsHarness(SimpleNamespace(Parameter=lambda _n: dimension), object())

    result = await harness.get_dimension("D1@Sketch1")

    assert result.is_error
    assert "Failed to read dimension 'D1@Sketch1'" in (result.error or "")


@pytest.mark.asyncio
async def test_set_units_and_list_documents_preconditions() -> None:
    no_model = await _DocsHarness(None, object()).set_units("mm")
    not_connected = await _DocsHarness(None, None).list_open_documents()

    assert no_model.error == "No active model"
    assert not_connected.error == "Not connected to SolidWorks"


class _Doc:
    def __init__(self, title, path) -> None:
        self._title, self._path = title, path

    def GetTitle(self):  # noqa: N802
        return self._title

    def GetPathName(self):  # noqa: N802
        return self._path

    def GetType(self) -> int:  # noqa: N802
        return 1


@pytest.mark.asyncio
async def test_activate_document_edge_cases() -> None:
    untitled = _Doc(None, "C:/parts/untitled.sldprt")
    bracket = _Doc("Bracket.SLDPRT", "C:/parts/bracket.sldprt")
    other = _Doc("Other.SLDPRT", "C:/parts/other.sldprt")

    def _app(active):
        return SimpleNamespace(
            GetDocuments=lambda: [untitled, bracket],
            ActivateDoc3=lambda *_a: None,
            ActiveDoc=active,
        )

    blank = await _DocsHarness(None, _app(None)).activate_document("  ")
    no_title = await _DocsHarness(None, _app(None)).activate_document("untitled.sldprt")
    unverified = await _DocsHarness(None, _app(None)).activate_document(
        "bracket.sldprt"
    )
    wrong = await _DocsHarness(None, _app(other)).activate_document("Bracket.SLDPRT")

    assert blank.error == "title_or_path is required"
    assert "could not read its title" in (no_title.error or "")
    assert unverified.is_success and unverified.data["verified"] is None
    assert "activation did not take" in (wrong.error or "")


# ---- auto_center_marks -------------------------------------------------------


class _CenterMarkView:
    """A drawing view whose newer insert API is missing (older builds)."""

    def __init__(self, annotations) -> None:
        self._annotations = annotations
        self.legacy_calls = 0

    def GetName2(self) -> str:  # noqa: N802
        return "Front"

    def GetAnnotations(self):  # noqa: N802
        return self._annotations

    def AutoInsertCenterMarks(self, *_args) -> bool:  # noqa: N802
        self.legacy_calls += 1
        return True


@pytest.mark.asyncio
async def test_auto_center_marks_guards_and_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setattr(_io_module, "_as_com", lambda _a, obj, _i: obj)
    part = SimpleNamespace(GetType=lambda: 1)
    view = _CenterMarkView([None, SimpleNamespace(GetType=lambda: 0)])
    drawing = SimpleNamespace(
        GetType=lambda: 3, GetViews=lambda: [["Sheet1", view]], EditRebuild3=lambda: 1
    )

    not_a_drawing = await _DocsHarness(part, object()).auto_center_marks("Front")
    nothing_selected = await _DocsHarness(drawing, object()).auto_center_marks(
        "Front", mark_holes=False, mark_fillets=False, mark_slots=False
    )
    ran = await _DocsHarness(drawing, object()).auto_center_marks("Front")
    no_annotations = await _DocsHarness(
        SimpleNamespace(
            GetType=lambda: 3,
            GetViews=lambda: [["Sheet1", _CenterMarkView(None)]],
            EditRebuild3=lambda: 1,
        ),
        object(),
    ).auto_center_marks("Front")

    assert not_a_drawing.is_error
    assert "Select at least one feature type" in (nothing_selected.error or "")
    assert ran.is_success, ran.error
    assert view.legacy_calls == 1  # newer API missing -> older one used
    assert ran.data["center_marks_added"] == 0
    assert no_annotations.data["center_marks_before"] == 0


# ---- save_body_as_part ---------------------------------------------------------


def _part_with(bodies, *, manager=True, writes=None):
    manager_obj = SimpleNamespace(
        CreateSaveBodyFeature=lambda *_a: (
            (writes.write_bytes(b"body") if writes else None) or object()
        )
    )
    return SimpleNamespace(
        GetType=lambda: 1,
        GetBodies2=lambda *_a: bodies,
        FeatureManager=manager_obj if manager else None,
        EditRebuild3=lambda: 1,
    )


@pytest.mark.asyncio
async def test_save_body_as_part_argument_checks(tmp_path) -> None:
    drawing = SimpleNamespace(GetType=lambda: 3)
    target = str(tmp_path / "b.sldprt")
    part = _part_with([])

    results = [
        await _DocsHarness(None, object()).save_body_as_part("B", target),
        await _DocsHarness(drawing, object()).save_body_as_part("B", target),
        await _DocsHarness(part, object()).save_body_as_part(" ", target),
        await _DocsHarness(part, object()).save_body_as_part("B", " "),
    ]

    assert [r.error for r in results] == [
        "No active model",
        "save_body_as_part requires an active part document",
        "body_name is required",
        "file_path is required",
    ]


@pytest.mark.asyncio
async def test_save_body_as_part_failures_and_overwrite(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        _io_module, "pythoncom", SimpleNamespace(VT_DISPATCH=9, VT_BSTR=8)
    )
    body = SimpleNamespace(Name="Body1")
    target = tmp_path / "body.sldprt"
    target.write_bytes(b"old")

    no_bodies = await _DocsHarness(_part_with(None), object()).save_body_as_part(
        "Body1", str(target)
    )
    no_manager = await _DocsHarness(
        _part_with([body], manager=False), object()
    ).save_body_as_part("Body1", str(target))
    not_written = await _DocsHarness(_part_with([body]), object()).save_body_as_part(
        "Body1", str(target)
    )

    assert "has no solid bodies" in (no_bodies.error or "")
    assert "has no FeatureManager" in (no_manager.error or "")
    assert "did not write a file" in (not_written.error or "")
    assert not target.exists()  # the stale file was removed before saving


# ---- pack and go: comtypes type library, COM bridge, adapter flow ------------


def test_get_sw_comtypes_lib_tries_newest_version_first(monkeypatch) -> None:
    tried: list[int] = []
    lib = object()

    def get_module(spec):
        tried.append(spec[1])
        if spec[1] > 33:
            raise OSError("type library not registered")
        return lib

    monkeypatch.setattr(_io_module, "_sw_comtypes_lib", None)
    monkeypatch.setattr(_io_module, "_COMTYPES_AVAILABLE", True)
    monkeypatch.setattr(_io_module, "comtypes", SimpleNamespace(GUID=str))
    monkeypatch.setattr(
        _io_module, "_comtypes_client", SimpleNamespace(GetModule=get_module)
    )

    assert _get_sw_comtypes_lib() is lib
    assert tried == [35, 34, 33]
    assert _io_module._sw_comtypes_lib is lib


def test_get_sw_comtypes_lib_returns_none_when_no_version_is_registered(
    monkeypatch,
) -> None:
    def get_module(_spec):
        raise OSError("type library not registered")

    monkeypatch.setattr(_io_module, "_sw_comtypes_lib", None)
    monkeypatch.setattr(_io_module, "_COMTYPES_AVAILABLE", True)
    monkeypatch.setattr(_io_module, "comtypes", SimpleNamespace(GUID=str))
    monkeypatch.setattr(
        _io_module, "_comtypes_client", SimpleNamespace(GetModule=get_module)
    )

    assert _get_sw_comtypes_lib() is None


class _Unknown:
    """pywin32 PyIUnknown stand-in; only its repr carries the raw pointer."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __repr__(self) -> str:
        return self._text


def _bridge_env(monkeypatch, unk_repr: str) -> tuple[SimpleNamespace, list]:
    calls: list = []

    class _CtUnknown:
        def __init__(self, address: int) -> None:
            self.address = address

        def AddRef(self) -> None:
            calls.append(("AddRef", self.address))

        def QueryInterface(self, iface):
            calls.append(("QueryInterface", iface))
            return f"{iface}@{self.address:#x}"

    def query_interface(iid):
        calls.append(("ole", iid))
        return _Unknown(unk_repr)

    monkeypatch.setattr(
        _io_module, "pythoncom", SimpleNamespace(IID_IUnknown="IID_IUnknown")
    )
    monkeypatch.setattr(_io_module, "comtypes", SimpleNamespace(IUnknown=object))
    monkeypatch.setattr(
        _io_module,
        "ctypes",
        SimpleNamespace(
            POINTER=lambda kind: kind,
            cast=lambda address, _kind: _CtUnknown(address),
        ),
    )
    obj = SimpleNamespace(_oleobj_=SimpleNamespace(QueryInterface=query_interface))
    return obj, calls


def test_bridge_com_to_comtypes_reuses_the_raw_pointer(monkeypatch) -> None:
    obj, calls = _bridge_env(monkeypatch, "<PyIUnknown at 0x01 with obj at 0x2A>")

    bridged = _io_module._bridge_com_to_comtypes(obj, "IModelDocExtension")

    assert bridged == "IModelDocExtension@0x2a"
    assert calls == [
        ("ole", "IID_IUnknown"),
        ("AddRef", 0x2A),
        ("QueryInterface", "IModelDocExtension"),
    ]


def test_bridge_com_to_comtypes_rejects_an_unparseable_pointer(monkeypatch) -> None:
    obj, _calls = _bridge_env(monkeypatch, "<PyIUnknown with no address>")

    with pytest.raises(RuntimeError, match="Could not extract COM pointer"):
        _io_module._bridge_com_to_comtypes(obj, "IModelDocExtension")


class _PackAndGo:
    """IPackAndGo stand-in that records its configuration."""

    def __init__(self, names) -> None:
        self.names = names
        self.FlattenToSingleFolder = False
        self.save_to = None

    def SetSaveToName(self, flag, folder) -> None:
        self.save_to = (flag, folder)

    def GetDocumentNames(self):
        return (self.names,)


class _PackApp:
    """swApp stand-in: OpenDoc6 answers from a scripted list of (model, err)."""

    def __init__(self, opens) -> None:
        self.opens = list(opens)
        self.closed_all = False

    def OpenDoc6(self, _path, _type, _opts, _cfg, err, _warn):
        model, code = self.opens.pop(0)
        err.value = code
        return model

    def CloseAllDocuments(self, _include_unsaved) -> None:
        self.closed_all = True


class _PackHarness(_IOHarness):
    def __init__(self, app) -> None:
        super().__init__(None)
        self.swApp = app

    def _adapter(self, _owner):
        return self


def _pack_env(monkeypatch, out_dir, *, names, statuses):
    """Fake the comtypes layer; SavePackAndGo writes the packed files."""
    pg = _PackAndGo(names)

    class _Ext:
        def GetPackAndGo(self):
            return pg

        def SavePackAndGo(self, _pg):
            for name in ("asm.SLDASM", "part.sldprt", "notes.txt"):
                (out_dir / name).write_text("x")
            return statuses

    monkeypatch.setattr(
        _io_module, "win32com", SimpleNamespace(client=SimpleNamespace())
    )
    monkeypatch.setattr(
        _io_module,
        "_get_sw_comtypes_lib",
        lambda: SimpleNamespace(IModelDocExtension="IModelDocExtension"),
    )
    monkeypatch.setattr(
        _io_module, "_bridge_com_to_comtypes", lambda _obj, _iface: _Ext()
    )
    monkeypatch.setattr(_io_module._sw_type_info, "flag_doc", lambda _m, _t: None)
    return pg


@pytest.mark.asyncio
async def test_pack_and_go_assembly_packs_into_a_fresh_folder(
    tmp_path, monkeypatch
) -> None:
    out_dir = tmp_path / "pkg"
    pg = _pack_env(
        monkeypatch, out_dir, names=["a.sldasm", "b.sldprt"], statuses=(0, 0)
    )
    model = SimpleNamespace(Extension=object())
    harness = _PackHarness(_PackApp([(model, 0)]))

    result = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    assert result.is_success
    assert harness.currentModel is model
    assert pg.FlattenToSingleFolder is True
    assert pg.save_to == (True, str(out_dir) + "\\")
    assert result.data["source_files"] == ["a.sldasm", "b.sldprt"]
    assert result.data["copied_files"] == sorted(
        [str(out_dir / "asm.SLDASM"), str(out_dir / "part.sldprt")]
    )
    assert result.data["save_statuses"] == [0, 0]
    assert result.data["all_files_saved"] is True


@pytest.mark.asyncio
async def test_pack_and_go_assembly_retries_after_closing_documents(
    tmp_path, monkeypatch
) -> None:
    """err 65536 (file already open elsewhere) closes everything and retries once."""
    out_dir = tmp_path / "pkg"
    _pack_env(monkeypatch, out_dir, names=None, statuses=(0, 2))
    app = _PackApp([(None, 65536), (SimpleNamespace(Extension=object()), 0)])
    harness = _PackHarness(app)

    result = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    assert app.closed_all is True
    assert result.data["source_files"] == []
    assert result.data["all_files_saved"] is False


@pytest.mark.asyncio
async def test_pack_and_go_assembly_moves_an_existing_folder_aside(
    tmp_path, monkeypatch
) -> None:
    out_dir = tmp_path / "pkg"
    out_dir.mkdir()
    (out_dir / "stale.sldprt").write_text("old")
    _pack_env(monkeypatch, out_dir, names=[], statuses=None)
    harness = _PackHarness(_PackApp([(SimpleNamespace(Extension=object()), 0)]))

    result = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    assert result.is_success
    assert result.data["save_statuses"] == []
    assert str(out_dir / "stale.sldprt") not in result.data["copied_files"]
    assert [p.name for p in tmp_path.iterdir()] == ["pkg"]


@pytest.mark.asyncio
async def test_pack_and_go_assembly_keeps_going_when_the_old_folder_is_locked(
    tmp_path, monkeypatch
) -> None:
    """SolidWorks file locks: a failed rename or delete must not stop the pack."""
    out_dir = tmp_path / "pkg"
    out_dir.mkdir()
    _pack_env(monkeypatch, out_dir, names=[], statuses=(0,))
    harness = _PackHarness(_PackApp([(SimpleNamespace(Extension=object()), 0)] * 2))

    def locked(*_args, **_kwargs):
        raise OSError("[WinError 32] file in use")

    monkeypatch.setattr(_io_module.shutil, "rmtree", locked)
    first = await harness.pack_and_go_assembly(str(tmp_path / "a.sldasm"), str(out_dir))
    backups = [p for p in tmp_path.iterdir() if p.name.startswith("pkg_bak_")]

    monkeypatch.setattr(_io_module.os, "rename", locked)
    second = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    assert first.is_success and second.is_success
    assert len(backups) == 1


@pytest.mark.asyncio
async def test_pack_and_go_assembly_reports_why_it_failed(
    tmp_path, monkeypatch
) -> None:
    out_dir = tmp_path / "pkg"
    _pack_env(monkeypatch, out_dir, names=[], statuses=())
    harness = _PackHarness(_PackApp([(None, 1024)]))

    opened = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    monkeypatch.setattr(_io_module, "_get_sw_comtypes_lib", lambda: None)
    no_lib = await harness.pack_and_go_assembly(
        str(tmp_path / "a.sldasm"), str(out_dir)
    )

    assert opened.status == AdapterResultStatus.ERROR
    assert opened.error == "Pack and Go failed: OpenDoc6 failed err=1024 warn=0"
    assert no_lib.error.startswith(
        "Pack and Go failed: comtypes SolidWorks type library not available"
    )
