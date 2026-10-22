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


import inspect
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

import solidworks_mcp.adapters.pywin32_adapter as pywin32_mod
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks.io import (
    SolidWorksIOMixin,
    _apply_unit_system,
    _byref_int,
    _ByrefFallback,
    _coerce_dispatch_sequence,
    _component_pairs,
    _component_transforms,
    _describe_open_document,
    _interference_details,
    _normalise_unit_system,
    _payload,
    _payload_dict,
    _view_names,
)
from solidworks_mcp.exceptions import SolidWorksMCPError


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
    monkeypatch.setattr(
        _io_module, "comtypes", SimpleNamespace(GUID=str), raising=False
    )
    monkeypatch.setattr(
        _io_module,
        "_comtypes_client",
        SimpleNamespace(GetModule=get_module),
        raising=False,
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
    monkeypatch.setattr(
        _io_module, "comtypes", SimpleNamespace(GUID=str), raising=False
    )
    monkeypatch.setattr(
        _io_module,
        "_comtypes_client",
        SimpleNamespace(GetModule=get_module),
        raising=False,
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
    monkeypatch.setattr(
        _io_module, "comtypes", SimpleNamespace(IUnknown=object), raising=False
    )
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


@pytest.mark.asyncio
async def test_activate_document_needs_a_connection() -> None:
    result = await _DocsHarness(None, None).activate_document("bracket.SLDPRT")

    assert result.error == "Not connected to SolidWorks"


@pytest.mark.asyncio
async def test_save_body_as_part_needs_an_existing_parent_folder(tmp_path) -> None:
    missing = tmp_path / "missing"

    result = await _DocsHarness(_part_with([]), object()).save_body_as_part(
        "B", str(missing / "b.sldprt")
    )

    assert result.error == f"Parent directory does not exist: {missing}"


def _build_adapter(monkeypatch) -> PyWin32Adapter:
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter._ComSessionCoordinator",
        lambda _adapter: SimpleNamespace(),
        raising=False,
    )
    return PyWin32Adapter({})


class TestSolidWorksIOMixinNotConnected:
    """Cover the not-connected early-return paths in SolidWorksIOMixin."""

    # --- _adapter staticmethod (line 16 in io.py) ---

    def test_adapter_staticmethod_returns_obj(self) -> None:
        """SolidWorksIOMixin._adapter is a transparent identity cast."""
        sentinel = object()
        result = SolidWorksIOMixin._adapter(sentinel)
        assert result is sentinel

    # --- open_model with is_connected() == False (line 21) ---

    @pytest.mark.asyncio
    async def test_open_model_not_connected_returns_error(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.open_model("test.sldprt")
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_part with is_connected() == False (line 71) ---

    @pytest.mark.asyncio
    async def test_create_part_not_connected_returns_error(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_part()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_assembly with is_connected() == False (line 86) ---

    @pytest.mark.asyncio
    async def test_create_assembly_not_connected_returns_error(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_assembly()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_drawing with is_connected() == False (line 101) ---

    @pytest.mark.asyncio
    async def test_create_drawing_not_connected_returns_error(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_drawing()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_open_model_uses_int_errors_when_variant_ctor_missing(
        self, monkeypatch
    ) -> None:
        """open_model should pass integer error/warning refs when VARIANT is unavailable."""
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: True)

        class _Cfg:
            @staticmethod
            def GetName() -> str:
                return "Default"

        model = MagicMock()
        model.GetActiveConfiguration.return_value = _Cfg()
        app = MagicMock()
        app.OpenDoc6.return_value = model

        adapter.swApp = app
        adapter.constants = {
            "swDocPART": 1,
            "swDocASSEMBLY": 2,
            "swDocDRAWING": 3,
        }
        adapter._attempt = lambda operation, default=None: operation()
        adapter._read_model_title = lambda _m: "Part1"

        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=None)),
            raising=False,
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.pythoncom",
            SimpleNamespace(VT_BYREF=0x4000, VT_I4=3),
            raising=False,
        )

        result = await adapter.open_model("model.sldprt")

        assert result.is_success
        args = app.OpenDoc6.call_args.args
        assert args[4] == 0
        assert args[5] == 0


class TestPayloadCoercionFallbacks:
    """Cover the ``vars(data)`` fallback in ``_payload`` / ``_payload_dict``."""

    def test_payload_coerces_plain_object_via_vars(self) -> None:
        class _Obj:
            def __init__(self) -> None:
                self.text = "hello"
                self._private = "hidden"

        result = _payload(_Obj())
        assert result == {"text": "hello"}

    def test_payload_dict_coerces_plain_object_via_vars(self) -> None:
        class _Obj:
            def __init__(self) -> None:
                self.coincident = True
                self._private = "hidden"

        result = _payload_dict(_Obj())
        assert result == {"coincident": True}

    def test_payload_dict_passes_through_a_plain_dict(self) -> None:
        given = {"coincident": True}
        assert _payload_dict(given) is given

    def test_payload_dict_uses_model_dump_for_pydantic_style_objects(self) -> None:
        model = SimpleNamespace(model_dump=lambda: {"coincident": False})
        assert _payload_dict(model) == {"coincident": False}


class TestRequireDrawingGuard:
    """Cover ``SolidWorksIOMixin._require_drawing``'s two error branches."""

    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None

        result = await adapter.add_note({"text": "hi"})

        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_active_document_is_not_a_drawing(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1  # Part, not a drawing (3)

        result = await adapter.add_note({"text": "hi"})

        assert result.is_error
        assert "requires a drawing document" in (result.error or "")


class TestPlaceViewErrors:
    """Cover ``_place_view``'s input-validation error branches."""

    @staticmethod
    def _drawing_adapter(monkeypatch) -> PyWin32Adapter:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        return adapter

    @pytest.mark.asyncio
    async def test_errors_when_model_path_missing(self, monkeypatch) -> None:
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view({"orientation": "front"})

        assert result.is_error
        assert "A model path is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_file_not_found(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view(
            {"model_path": str(tmp_path / "does-not-exist.sldprt")}
        )

        assert result.is_error
        assert "Model file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_orientation_unknown(self, monkeypatch) -> None:
        adapter = self._drawing_adapter(monkeypatch)
        # __file__ definitely exists on disk, so the file-not-found check
        # passes and the orientation check is what actually gets exercised.
        result = await adapter.create_drawing_view(
            {"model_path": __file__, "orientation": "not_a_real_view"}
        )

        assert result.is_error
        assert "Unknown orientation" in (result.error or "")

    @pytest.mark.asyncio
    async def test_accepts_an_explicit_position_list_and_a_raw_star_view_name(
        self, monkeypatch
    ) -> None:
        """An explicit [x, y] position and a raw '*Name' orientation both parse.

        Doesn't assert success - reaching the raw-name branch means the call
        proceeds to a real (mocked) OpenDoc6, which this bare MagicMock
        currentModel can't satisfy. What matters here is that both parsing
        branches (position-as-list, and the '*'-prefixed raw view name) run
        without raising, rather than falling into their "not given" defaults.
        """
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view(
            {
                "model_path": __file__,
                "position": [200.0, 75.0],
                "orientation": "*CustomView1",
            }
        )

        # However it resolves, it must have gotten past both the
        # "model path required" and "Unknown orientation" checks.
        assert "Unknown orientation" not in (result.error or "")
        assert "A model path is required" not in (result.error or "")


class TestCreateTechnicalDrawingNoViewsCreated:
    """Cover ``create_technical_drawing``'s "no views were created" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_no_new_views_appear(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        # GetViews() defaults to a MagicMock, which _view_names treats as
        # "not a list/tuple" and reduces to [] both before and after, so
        # nothing appears to have been added.

        result = await adapter.create_technical_drawing({"model_path": __file__})

        assert result.is_error
        assert "No views were created" in (result.error or "")


class TestAddNoteInsertNoteReturnsNothing:
    """Cover ``add_note``'s "InsertNote returned nothing" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_insert_note_returns_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        adapter.currentModel.InsertNote.return_value = None

        result = await adapter.add_note({"text": "MATERIAL: AISI 1018"})

        assert result.is_error
        assert "InsertNote returned nothing" in (result.error or "")


class TestCheckInterferenceManagerUnavailable:
    """Cover ``check_interference``'s "manager is unavailable" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_interference_detection_manager_unavailable(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2  # Assembly
        adapter.currentModel.InterferenceDetectionManager = None

        result = await adapter.check_interference()

        assert result.is_error
        assert "InterferenceDetectionManager is unavailable" in (result.error or "")


class TestCreateDrawingTemplateFallback:
    """Without a usable template, create_drawing makes a blank drawing."""

    def _adapter(self, monkeypatch, template, *, new_document, new_drawing):
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: True)
        adapter.swApp = MagicMock()
        adapter.swApp.NewDocument.return_value = new_document
        adapter.swApp.NewDrawing2.return_value = new_drawing
        adapter._resolve_template_path = lambda *a, **kw: template
        return adapter

    @pytest.mark.asyncio
    async def test_uses_the_configured_template(self, monkeypatch) -> None:
        drawing = MagicMock()
        adapter = self._adapter(
            monkeypatch, "C:/t/Drawing.drwdot", new_document=drawing, new_drawing=None
        )

        result = await adapter.create_drawing()

        assert result.is_success
        adapter.swApp.NewDocument.assert_called_once_with(
            "C:/t/Drawing.drwdot", 12, 0.2794, 0.2159
        )
        adapter.swApp.NewDrawing2.assert_not_called()

    @pytest.mark.parametrize("template", [None, "C:/deleted/Drawing.drwdot"])
    @pytest.mark.asyncio
    async def test_falls_back_to_a_blank_a_size_drawing(
        self, monkeypatch, template
    ) -> None:
        adapter = self._adapter(
            monkeypatch, template, new_document=None, new_drawing=MagicMock()
        )

        result = await adapter.create_drawing()

        assert result.is_success
        assert result.data.type == "Drawing"
        # swDwgTemplateNone, no template file, swDwgPaperAsize, 11 x 8.5 in
        adapter.swApp.NewDrawing2.assert_called_once_with(13, "", 0, 0.2794, 0.2159)

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            (None, "no drawing template is configured"),
            ("C:/deleted/Drawing.drwdot", "template 'C:/deleted/Drawing.drwdot'"),
        ],
    )
    @pytest.mark.asyncio
    async def test_reports_both_attempts_when_everything_fails(
        self, monkeypatch, template, expected
    ) -> None:
        adapter = self._adapter(
            monkeypatch, template, new_document=None, new_drawing=None
        )

        result = await adapter.create_drawing()

        assert result.is_error
        assert expected in result.error
        assert "without a template (NewDrawing2) also failed" in result.error


class TestByrefFallback:
    """Cover ``_ByrefFallback``'s dunder methods directly.

    Earlier assessment (mine, inherited from an automated survey) called
    this "dead code on Windows+pywin32". That was wrong: it's a plain
    Python class, reachable any time ``win32com.client.VARIANT`` is
    unavailable - the exact same monkeypatch already used a few classes up
    in this file (``test_open_model_uses_int_errors_when_variant_ctor_missing``).
    No mocking is even needed to cover the dunders themselves.
    """

    def test_equality_against_seeded_value_and_another_instance(self) -> None:
        holder = _ByrefFallback(1)
        assert holder == 1
        assert holder == _ByrefFallback(1)
        assert holder != 2
        assert holder != _ByrefFallback(2)

    def test_hash_and_bool_follow_the_seeded_value(self) -> None:
        assert hash(_ByrefFallback(5)) == hash(5)
        assert bool(_ByrefFallback(0)) is False
        assert bool(_ByrefFallback(1)) is True

    def test_repr_shows_the_seeded_value(self) -> None:
        assert repr(_ByrefFallback(3)) == "_ByrefFallback(3)"

    def test_byref_int_falls_back_when_variant_ctor_unavailable(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=None)),
            raising=False,
        )
        result = _byref_int()
        assert isinstance(result, _ByrefFallback)
        assert result.value == 0


class TestAddMateErrorBranches:
    """Cover ``add_mate``'s remaining error branches - pre-existing PR #56
    code, not one of the 7 new-capability PRs this coverage sprint targeted,
    but closed anyway since the technique generalizes directly.

    ``_as_com`` wraps every component/feature through the real
    ``win32com.client.dynamic.Dispatch`` before flagging it, which raises on
    a plain test double (it expects a real COM PyIDispatch). Monkeypatching
    io.py's module-level ``_dynamic`` alias to an identity passthrough
    (mirroring its own non-Windows fallback shape, ``SimpleNamespace(Dispatch=...)``)
    lets ``SimpleNamespace`` components flow through unchanged, the same way
    the real object would after wrapping.
    """

    @staticmethod
    def _identity_dynamic(monkeypatch) -> None:
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )

    @staticmethod
    def _assembly_adapter(monkeypatch) -> PyWin32Adapter:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2  # Assembly
        return adapter

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly_document(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1  # Part, not an assembly

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_on_unknown_mate_type(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)

        result = await adapter.add_mate("part-1", "part-2", mate_type="not_a_type")

        assert result.is_error
        assert "Unknown mate type" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_on_unknown_alignment(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)

        result = await adapter.add_mate(
            "part-1", "part-2", alignment="not_an_alignment"
        )

        assert result.is_error
        assert "Unknown alignment" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_components_unreadable(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        adapter.currentModel.GetComponents.return_value = None

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Could not read the assembly's components" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_every_component_fails_to_wrap(self, monkeypatch) -> None:
        """Exercises both the per-component 'continue' and the resulting
        'not found' raise: nothing wraps, so nothing can ever match."""
        adapter = self._assembly_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        adapter.currentModel.GetComponents.return_value = [object(), object()]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Component(s) not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_named_components_are_not_in_the_assembly(
        self, monkeypatch
    ) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="other-part-1"),
            SimpleNamespace(Name2="other-part-2"),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Component(s) not found: part-1, part-2" in (result.error or "")
        assert "other-part-1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_entity_not_found_on_component(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: None),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: None),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "not found on part-1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_entity_selection_fails(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: False)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Failed to select" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_selected_count_is_not_two(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: True)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]
        adapter.currentModel.SelectionManager.GetSelectedObjectCount2.return_value = 1

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Expected 2 selected entities" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_solidworks_rejects_the_mate(self, monkeypatch) -> None:
        """error_status=2 mirrors the documented real measurement: this build
        reports 1 for success, so anything else (including a successful-looking
        object with an unhelpful status) is treated as a rejection."""
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: True)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]
        adapter.currentModel.SelectionManager.GetSelectedObjectCount2.return_value = 2
        adapter.currentModel.AddMate5.return_value = SimpleNamespace()

        def fake_byref_int():
            return SimpleNamespace(value=2)  # not 1 == success per the docstring

        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._byref_int", fake_byref_int
        )

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "SolidWorks rejected the coincident mate" in (result.error or "")


class TestSaveFileLegacyFallback:
    """Cover ``save_file``'s legacy ``Save()`` fallback and unwritten-file raise."""

    @pytest.mark.asyncio
    async def test_falls_back_to_save_and_errors_when_file_not_written(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        # A path that does not exist, so the final os.path.exists check fails
        # regardless of what the mocked Save3/Save calls "do".
        target = str(tmp_path / "does_not_exist.sldprt")

        model = MagicMock()
        model.GetPathName.return_value = target
        model.Save3.return_value = None  # forces the legacy Save() fallback
        adapter.currentModel = model

        result = await adapter.save_file(target)

        assert result.is_error
        assert "File not written after save" in (result.error or "")
        model.Save.assert_called_once()


class TestViewNamesHelper:
    def test_skips_unwrappable_views(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        drawing = SimpleNamespace(GetViews=lambda: [["sheet_obj", "view_obj1"]])

        result = _view_names(adapter, drawing)

        assert result == []


class TestComponentTransformsHelper:
    def test_skips_component_that_is_none(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [object()]

        result = _component_transforms(adapter, assembly)

        assert result == {}

    def test_skips_non_list_transform_data(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(
            Name2="part-1", Transform2=SimpleNamespace(ArrayData="not-a-list")
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_transforms(adapter, assembly)

        assert result == {}

    def test_skips_transform_with_unconvertible_values(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(
            Name2="part-1",
            Transform2=SimpleNamespace(ArrayData=["not-a-number"] * 16),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_transforms(adapter, assembly)

        assert result == {}


class TestInterferenceDetailsHelper:
    def test_skips_unwrappable_interference(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )

        result = _interference_details(adapter, [object()])

        assert result == []

    def test_volume_conversion_failure_reports_none(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        item = SimpleNamespace(
            Volume="not-a-number", GetComponentCount=lambda: 2, Components=[]
        )

        result = _interference_details(adapter, [item])

        assert result[0]["volume_mm3"] is None

    def test_skips_unwrappable_nested_component(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None if isinstance(obj, str) else obj),
        )
        item = SimpleNamespace(
            Volume=1e-6, GetComponentCount=lambda: 1, Components=["raw-string"]
        )

        result = _interference_details(adapter, [item])

        assert result[0]["components"] == []


class TestComponentPairsHelper:
    def test_unwrappable_component_reported_as_unnamed(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [object()]

        result = _component_pairs(adapter, assembly)

        assert result == [("<unnamed>", None)]

    def test_falls_back_to_get_path_name_when_name2_empty(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(Name2="", GetPathName=lambda: "C:/parts/a.sldprt")
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_pairs(adapter, assembly)

        assert result == [("C:/parts/a.sldprt", component)]


class TestInsertComponentMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.insert_component("C:/parts/a.sldprt", 0, 0, 0)
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_file_not_found(self, monkeypatch, tmp_path) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = await adapter.insert_component(
            str(tmp_path / "does-not-exist.sldprt"), 0, 0, 0
        )
        assert result.is_error
        assert "Component file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_opendoc6_returns_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = None

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        assert "OpenDoc6 returned nothing" in (result.error or "")

    @pytest.mark.asyncio
    async def test_falls_back_to_add_component5_and_still_fails(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        adapter.currentModel.GetComponents.return_value = []
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        adapter.currentModel.AddComponent4.return_value = None
        adapter.currentModel.AddComponent5.return_value = None

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        adapter.currentModel.AddComponent5.assert_called_once()
        assert "Component was not inserted" in (result.error or "")


class TestListComponentsMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.list_components()
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1

        result = await adapter.list_components()

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")


class TestPlaceViewMoreErrors:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.create_drawing_view({"model_path": __file__})
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_scale_parse_failure_is_absorbed_not_raised(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.GetViews.return_value = None

        # "1:1" cannot convert via float() - if the except branch (1794-1798)
        # did not absorb it, this would raise ValueError instead of
        # returning a normal AdapterResult.
        result = await adapter.create_drawing_view(
            {"model_path": __file__, "scale": "1:1"}
        )

        assert result.is_error  # a normal error result, not an exception

    @pytest.mark.asyncio
    async def test_errors_when_view_count_unchanged(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        adapter.currentModel.GetViews.return_value = None

        result = await adapter.create_drawing_view({"model_path": __file__})

        assert result.is_error
        assert "View was not created" in (result.error or "")

    @pytest.mark.asyncio
    async def test_applies_scale_when_view_is_created(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        view_names_calls = iter([[], ["Drawing View1"]])
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._view_names",
            lambda adapter, drawing: next(view_names_calls),
        )
        adapter.currentModel.CreateDrawViewFromModelView3.return_value = (
            SimpleNamespace()
        )

        result = await adapter.create_drawing_view(
            {"model_path": __file__, "scale": "2.0"}
        )

        assert result.is_success
        assert result.data["name"] == "Drawing View1"


class TestAddDrawingViewDelegates:
    @pytest.mark.asyncio
    async def test_add_drawing_view_reaches_place_view(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None

        result = await adapter.add_drawing_view({"model_path": __file__})

        assert result.is_error
        assert "No active model" in (result.error or "")


class TestCreateTechnicalDrawingMoreErrors:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.create_technical_drawing({"model_path": __file__})
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_path_missing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.create_technical_drawing({})

        assert result.is_error
        assert "A model path is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_file_not_found(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.create_technical_drawing(
            {"model_path": str(tmp_path / "does-not-exist.sldprt")}
        )

        assert result.is_error
        assert "Model file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_first_angle_projection_calls_the_first_angle_overload(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.GetViews.return_value = None

        result = await adapter.create_technical_drawing(
            {"model_path": __file__, "projection": "first_angle"}
        )

        assert result.is_error  # no views appear either way; that's fine here
        adapter.currentModel.Create1stAngleViews2.assert_called_once()
        adapter.currentModel.Create3rdAngleViews2.assert_not_called()


class TestAddNoteMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_text_missing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.add_note({})

        assert result.is_error
        assert "add_note requires text" in (result.error or "")

    @pytest.mark.asyncio
    async def test_accepts_an_explicit_position_list(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.InsertNote.return_value = None

        result = await adapter.add_note({"text": "hi", "position": [10.0, 20.0]})

        assert result.is_error
        assert "InsertNote returned nothing" in (result.error or "")


class TestListDrawingViewsGuard:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.list_drawing_views()
        assert result.is_error
        assert "No active model" in (result.error or "")


class TestCheckInterferenceMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.check_interference()
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_filters_by_wanted_component_names(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        manager = MagicMock()
        manager.GetInterferenceCount.return_value = 1
        item = SimpleNamespace(
            Volume=1e-6,
            GetComponentCount=lambda: 2,
            Components=[
                SimpleNamespace(Name2="part-1"),
                SimpleNamespace(Name2="part-2"),
            ],
        )
        manager.GetInterferences.return_value = [item]
        adapter.currentModel.InterferenceDetectionManager = manager

        result = await adapter.check_interference({"components": ["part-1"]})

        assert result.is_success
        assert result.data["interference_found"] is True
        assert result.data["scope"] == ["part-1"]


@pytest.mark.asyncio
async def test_pywin32_adapter_many_guard_paths(monkeypatch):
    """Test pywin32 adapter many guard paths."""

    class _ConcretePyWin32Adapter(PyWin32Adapter):
        """Test suite for ConcretePyWin32Adapter."""

        async def exit_sketch(self):
            """Test helper for exit sketch."""
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", True)
    monkeypatch.setattr(pywin32_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        pywin32_mod,
        "pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )

    adapter = _ConcretePyWin32Adapter({})

    # Disconnected guards
    assert adapter.is_connected() is False
    assert (await adapter.open_model("x.sldprt")).is_error
    assert (await adapter.create_part()).is_error
    assert (await adapter.create_assembly()).is_error
    assert (await adapter.create_drawing()).is_error

    # No active model guards
    assert (
        await adapter.create_extrusion(
            SimpleNamespace(
                depth=1,
                draft_angle=0,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_error
    assert (
        await adapter.create_revolve(
            SimpleNamespace(
                angle=90,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
    ).is_error
    assert (
        await adapter.create_sweep(
            SimpleNamespace(path="P", twist_along_path=False, twist_angle=0)
        )
    ).is_error
    assert (
        await adapter.create_loft(
            SimpleNamespace(
                profiles=["S1"],
                guide_curves=[],
                start_tangent=False,
                end_tangent=False,
            )
        )
    ).is_error


class TestPyWin32AdapterBranches:
    """Additional PyWin32Adapter branch coverage with pure mocks."""

    @staticmethod
    def _build_adapter(monkeypatch) -> PyWin32Adapter:
        """Test helper for build adapter."""
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Windows",
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=RuntimeError),
            raising=False,
        )
        adapter = PyWin32Adapter({})
        # Synchronous mock ComExecutor: avoids "ComExecutor is not running"
        # guard in _handle_com_operation for tests that set swApp/currentModel
        # directly without going through connect().
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_com = MagicMock()
        mock_com._thread = mock_thread
        mock_com.run = lambda fn, timeout=None: fn()
        adapter._com = mock_com
        return adapter

    @staticmethod
    def _sketch_tree(*names):
        """Build a FirstFeature→GetNextFeature chain of ProfileFeature mocks.

        Each node mimics the COM ``IFeature`` attributes the feature-tree
        walk in ``features.py`` reads: ``GetTypeName2`` and ``Name`` as
        properties and ``GetNextFeature`` as the link to the next node.
        """
        nxt = None
        for name in reversed(names):
            nxt = SimpleNamespace(
                GetTypeName2="ProfileFeature", Name=name, GetNextFeature=nxt
            )
        return nxt

    @staticmethod
    def _feature_by_name(selected, *, fail=()):
        """Return a FeatureByName mock that records ``Select2(append, mark)``.

        ``features.py`` selects sketches/curves via
        ``currentModel.FeatureByName(name).Select2(append, mark)``.  This
        helper returns a callable that appends ``(name, append, mark)`` to
        ``selected`` and reports success, except for names in ``fail`` (which
        return ``None`` from ``FeatureByName`` to simulate a missing feature).
        """

        def factory(name):
            if name in fail:
                return None
            feature = SimpleNamespace()
            feature.Select2 = lambda append, mark, _n=name: bool(
                selected.append((_n, append, mark)) or True
            )
            return feature

        return factory

    @pytest.mark.asyncio
    async def test_health_check_and_model_info_branches(self, monkeypatch):
        """Test healthy/disconnected checks and model-info default branches."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = SimpleNamespace(RevisionNumber=lambda: "33.2")
        healthy = await adapter.health_check()
        assert healthy.healthy is True
        assert healthy.connection_status == "connected"
        assert healthy.metrics["sw_version"] == "33.2"

        adapter.swApp = SimpleNamespace(RevisionNumber=lambda: None)
        unhealthy = await adapter.health_check()
        assert unhealthy.healthy is False
        assert unhealthy.connection_status == "disconnected"

        adapter.currentModel = SimpleNamespace(
            GetTitle=lambda: "Model1",
            GetPathName=lambda: "C:/tmp/model1.sldprt",
            GetType=lambda: 99,
            GetActiveConfiguration=lambda: None,
            GetSaveFlag=lambda: True,
            GetRebuildStatus=lambda: 0,
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda include_hidden: 7),
        )
        info = await adapter.get_model_info()
        assert info.is_success
        assert info.data["type"] == "Unknown"
        assert info.data["configuration"] == "Default"

    @pytest.mark.asyncio
    async def test_save_export_close_and_dimension_error_paths(self, monkeypatch):
        """Test save/export/close operation branches and dimension failure paths."""
        adapter = self._build_adapter(monkeypatch)
        # Avoid real filesystem calls: makedirs is a no-op and existence check
        # always returns True so SaveAs3 returning True is treated as success.
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.makedirs",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: True,
        )

        no_model = await adapter.close_model()
        assert no_model.status.name == "WARNING"

        model = SimpleNamespace(
            Save=Mock(),
            Save3=Mock(return_value=False),
            SaveAs3=Mock(return_value=False),
            Parameter=Mock(return_value=None),
            ForceRebuild3=Mock(return_value=False),
            GetTitle=Mock(return_value="Model1"),
        )
        adapter.currentModel = model
        adapter.swApp = SimpleNamespace(CloseDoc=Mock())

        assert (await adapter.save_file()).is_error
        assert (await adapter.save_file("C:/tmp/new.sldprt")).is_error
        assert (await adapter.export_file("C:/tmp/out.bad", "badfmt")).is_error

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: False,
        )
        assert (await adapter.export_file("C:/tmp/out.step", "step")).is_error
        assert (await adapter.get_dimension("D1@Sketch1")).is_error
        assert (await adapter.set_dimension("D1@Sketch1", 20.0)).is_error
        assert (await adapter.rebuild_model()).is_error

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: True,
        )
        model.Save3 = Mock(return_value=True)
        model.SaveAs3 = Mock(return_value=True)
        model.ForceRebuild3 = Mock(return_value=True)
        model.Parameter = Mock(
            return_value=SimpleNamespace(
                GetValue3=Mock(return_value=0.015), SetValue3=Mock(return_value=True)
            )
        )

        assert (await adapter.save_file()).is_success
        assert (await adapter.save_file("C:/tmp/new.sldprt")).is_success
        assert (await adapter.export_file("C:/tmp/out.step", "step")).is_success
        assert (await adapter.get_dimension("D1@Sketch1")).data == pytest.approx(15.0)
        assert (await adapter.set_dimension("D1@Sketch1", 20.0)).is_success
        assert (await adapter.rebuild_model()).is_success

        closed = await adapter.close_model(save=True)
        assert closed.is_success
        assert adapter.currentModel is None
        adapter.swApp.CloseDoc.assert_any_call("Model1")

    @pytest.mark.asyncio
    async def test_list_configurations_supports_tuple_property(self, monkeypatch):
        """list_configurations should handle COM variants exposing names as tuple properties."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = SimpleNamespace(GetConfigurationNames=("Default", "Alt"))
        result = await adapter.list_configurations()

        assert result.is_success
        assert result.data == ["Default", "Alt"]

    @pytest.mark.asyncio
    async def test_list_configurations_falls_back_to_active_configuration(
        self, monkeypatch
    ):
        """list_configurations should fall back to the active configuration name."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = SimpleNamespace(
            GetConfigurationNames=Mock(return_value=None),
            GetActiveConfiguration=Mock(
                return_value=SimpleNamespace(GetName=Mock(return_value="Default"))
            ),
        )

        result = await adapter.list_configurations()

        assert result.is_success
        assert result.data == ["Default"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        __import__("platform").system() != "Windows",
        reason="win32com only available on Windows",
    )
    async def test_connect_disconnect_and_document_creation_paths(self, monkeypatch):
        """Test COM connect lifecycle plus model creation/open branches with mocks."""
        adapter = self._build_adapter(monkeypatch)

        co_initialize = Mock()
        co_uninitialize = Mock()
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(
                CoInitialize=co_initialize,
                CoUninitialize=co_uninitialize,
                VT_BYREF=0x4000,
                VT_I4=3,
            ),
            raising=False,
        )

        fake_app = SimpleNamespace(
            Visible=False,
            SetUserPreferenceToggle=Mock(),
            OpenDoc6=Mock(),
            NewDocument=Mock(),
            CloseDoc=Mock(),
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(
                client=SimpleNamespace(
                    GetActiveObject=Mock(side_effect=RuntimeError("no running app")),
                    Dispatch=Mock(return_value=fake_app),
                    VARIANT=lambda _kind, val: val,
                )
            ),
            raising=False,
        )

        import win32com.client.dynamic as _win32_dynamic

        monkeypatch.setattr(_win32_dynamic, "Dispatch", Mock(return_value=fake_app))

        await adapter.connect()
        assert adapter.swApp is fake_app
        assert fake_app.Visible is True
        fake_app.SetUserPreferenceToggle.assert_any_call(150, False)
        fake_app.SetUserPreferenceToggle.assert_any_call(149, False)
        # CoInitialize now runs on the ComExecutor thread, not in connect() directly.

        fake_open_model = SimpleNamespace(
            GetTitle=lambda: "OpenedAsm",
            GetActiveConfiguration=lambda: None,
            GetSaveTime=lambda: "now",
        )
        fake_app.OpenDoc6.return_value = fake_open_model
        fake_app.GetUserPreferenceStringValue = Mock(
            side_effect=lambda idx: {
                0: "C:/Templates/Part.prtdot",
                1: "",
                2: "",
            }[idx]
        )

        fake_app.NewDocument.side_effect = lambda template, *_args: SimpleNamespace(
            GetTitle=lambda: (
                template.split("/")[-1]
                .replace(".prtdot", "")
                .replace(".asmdot", "")
                .replace(".drwdot", "")
            )
        )

        opened = await adapter.open_model("C:/Models/sample.sldasm")
        assert opened.is_success
        assert opened.data.type == "Assembly"
        assert opened.data.configuration == "Default"

        unsupported = await adapter.open_model("C:/Models/sample.txt")
        assert unsupported.is_error
        assert "Unsupported file type" in (unsupported.error or "")

        part = await adapter.create_part()
        assembly = await adapter.create_assembly()
        drawing = await adapter.create_drawing()
        assert part.is_success and part.data.type == "Part"
        assert assembly.is_success and assembly.data.type == "Assembly"
        assert drawing.is_success and drawing.data.type == "Drawing"

        adapter.currentModel = SimpleNamespace(GetTitle=lambda: "ActiveModel")
        adapter.currentSketch = object()
        adapter.currentSketchManager = object()
        toggle_call_count = fake_app.SetUserPreferenceToggle.call_count
        await adapter.disconnect()
        assert fake_app.SetUserPreferenceToggle.call_count == toggle_call_count
        assert adapter.swApp is None
        assert adapter.currentSketchManager is None

    @pytest.mark.asyncio
    async def test_save_file_fallback_and_noop_paths(self, monkeypatch, tmp_path):
        """Cover save_file fallback branches: SaveAs fallback, Save3 fallback, and clean-file no-op."""
        adapter = self._build_adapter(monkeypatch)

        target = tmp_path / "out.sldprt"

        # SaveAs3 fails, SaveAs fallback also fails -> explicit error branch.
        adapter.swApp = SimpleNamespace(
            CloseDoc=Mock(side_effect=RuntimeError("locked"))
        )
        adapter.currentModel = SimpleNamespace(
            SaveAs3=Mock(return_value=1),
            SaveAs=Mock(return_value=1),
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.remove",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
        )
        failed_save_as = await adapter.save_file(str(target))
        assert failed_save_as.is_error
        assert "Failed to save as" in (failed_save_as.error or "")

        # SaveAs3 reports numeric success but file is still missing -> file-not-written error.
        adapter.currentModel = SimpleNamespace(SaveAs3=Mock(return_value=0))
        missing_output = await adapter.save_file(str(target))
        assert missing_output.is_error
        assert "File not written after save" in (missing_output.error or "")

        # Save3 raises; fallback Save returns non-success, but existing path means no-op success.
        existing = tmp_path / "existing.sldprt"
        existing.write_text("x", encoding="utf-8")
        adapter.currentModel = SimpleNamespace(
            Save3=Mock(side_effect=RuntimeError("Save3 unavailable")),
            Save=Mock(return_value=1),
            GetPathName=Mock(return_value=str(existing)),
        )
        no_op = await adapter.save_file()
        assert no_op.is_success

    @pytest.mark.asyncio
    async def test_feature_and_configuration_edge_paths(self, monkeypatch):
        """Cover list_features/list_configurations edge cases and guarded feature ops."""
        adapter = self._build_adapter(monkeypatch)

        # Guard branches on no active model.
        assert (await adapter.list_configurations()).is_error
        assert (
            await adapter.create_cut_extrude(
                SimpleNamespace(depth=1.0, draft_angle=0.0, reverse_direction=False)
            )
        ).is_error
        assert (await adapter.add_fillet(1.0, ["E1"])).is_error
        assert (await adapter.add_chamfer(1.0, ["E1"])).is_error
        assert (await adapter.rebuild_model()).is_error

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, next_feature=None):
                """Test helper for init."""
                self.Name = name
                self._next = next_feature

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("fallback")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                return 1

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                raise RuntimeError("unknown type")

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                raise RuntimeError("walk break")

        dup = _Feature("Dup")
        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: dup,
            FeatureManager=SimpleNamespace(
                GetFeatureCount=Mock(side_effect=RuntimeError("count fail"))
            ),
            FeatureByPositionReverse=Mock(side_effect=RuntimeError("reverse fail")),
        )
        listed = await adapter.list_features(include_suppressed=True)
        assert listed.is_success
        assert listed.data and listed.data[0]["type"] == "Unknown"

        # list_configurations callable/None/string/list branches.
        adapter.currentModel = SimpleNamespace(
            GetConfigurationNames=Mock(return_value=None)
        )
        assert (await adapter.list_configurations()).data == []
        adapter.currentModel = SimpleNamespace(GetConfigurationNames="Default")
        assert (await adapter.list_configurations()).data == ["Default"]
        adapter.currentModel = SimpleNamespace(GetConfigurationNames=["Default", "Alt"])
        assert (await adapter.list_configurations()).data == ["Default", "Alt"]

    @pytest.mark.asyncio
    async def test_title_template_and_document_type_fallbacks(self, monkeypatch):
        """Cover _read_model_title, _resolve_template_path, and _get_document_type fallback branches."""
        adapter = self._build_adapter(monkeypatch)

        class _ModelWithTitleProperty:
            """Test suite for ModelWithTitleProperty."""

            GetTitle = 123
            Title = "FromTitleProperty"

        class _ModelUntitled:
            """Test suite for ModelUntitled."""

            def GetTitle(self):
                """Test helper for GetTitle."""
                raise RuntimeError("title fail")

            Title = None

        assert (
            adapter._read_model_title(_ModelWithTitleProperty()) == "FromTitleProperty"
        )
        assert adapter._read_model_title(_ModelUntitled()) == "Untitled"

        adapter.swApp = SimpleNamespace(
            GetUserPreferenceStringValue=Mock(
                side_effect=lambda idx: {
                    8: "C:/Templates/Part.prtdot",
                    0: "C:/Templates/Backup.prtdot",
                }.get(idx, "")
            )
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: str(p).endswith("Part.prtdot"),
        )
        resolved = adapter._resolve_template_path([8, 0], ".prtdot")
        assert resolved and resolved.endswith("Part.prtdot")

        adapter.currentModel = None
        assert adapter._get_document_type() == "Unknown"

    @pytest.mark.asyncio
    async def test_create_part_and_assembly_no_template_paths(self, monkeypatch):
        """Cover create_part/create_assembly branches where native creators fail and no template exists."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = SimpleNamespace(
            NewPart=Mock(side_effect=RuntimeError("native part failed")),
            NewAssembly=Mock(side_effect=RuntimeError("native asm failed")),
            GetUserPreferenceStringValue=Mock(return_value=""),
            NewDocument=Mock(return_value=None),
        )

        part_result = await adapter.create_part()
        asm_result = await adapter.create_assembly()
        assert part_result.is_error
        assert "No part template configured" in (part_result.error or "")
        assert asm_result.is_error
        assert "No assembly template configured" in (asm_result.error or "")

    @pytest.mark.asyncio
    async def test_save_guard_non_numeric_success_and_rebuild_failure(
        self, monkeypatch
    ):
        """Cover save guard path, non-numeric Save3 success, and rebuild operation failure branch."""
        adapter = self._build_adapter(monkeypatch)

        no_model_save = await adapter.save_file()
        assert no_model_save.is_error

        adapter.currentModel = SimpleNamespace(
            Save3=Mock(return_value=object()),
            ForceRebuild3=Mock(return_value=False),
        )
        # non-numeric truthy value follows bool(value) branch in _is_success
        save_success = await adapter.save_file()
        assert save_success.is_success

        rebuild_fail = await adapter.rebuild_model()
        assert rebuild_fail.is_error
        assert "listed no failing feature" in (rebuild_fail.error or "")

    @pytest.mark.asyncio
    async def test_set_view_orientation_calls_show_named_view2(
        self, monkeypatch
    ) -> None:
        """_set_view_orientation should call ShowNamedView2 with correct constant."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(ShowNamedView2=Mock())
        adapter._set_view_orientation(target_doc, "front", 1)
        target_doc.ShowNamedView2.assert_called_once_with("", 1)

    @pytest.mark.asyncio
    async def test_set_view_orientation_logs_on_failure(
        self, monkeypatch, caplog
    ) -> None:
        """_set_view_orientation should log warning but not raise on exception."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(
            ShowNamedView2=Mock(side_effect=RuntimeError("COM error"))
        )
        adapter._set_view_orientation(target_doc, "front", 1)
        assert target_doc.ShowNamedView2.called

    @pytest.mark.asyncio
    async def test_zoom_to_fit_calls_view_zoom_to_fit2_success(
        self, monkeypatch
    ) -> None:
        """_zoom_to_fit should call ViewZoomToFit2 and succeed."""
        adapter = self._build_adapter(monkeypatch)
        active_view = SimpleNamespace(ZoomToFit=Mock())
        target_doc = SimpleNamespace(ViewZoomToFit2=Mock(), ActiveView=active_view)
        adapter._zoom_to_fit(target_doc)
        target_doc.ViewZoomToFit2.assert_called_once()
        active_view.ZoomToFit.assert_not_called()

    @pytest.mark.asyncio
    async def test_zoom_to_fit_falls_back_to_active_view_zoom_to_fit(
        self, monkeypatch
    ) -> None:
        """_zoom_to_fit should fall back to ActiveView.ZoomToFit on failure."""
        adapter = self._build_adapter(monkeypatch)
        active_view = SimpleNamespace(ZoomToFit=Mock())
        target_doc = SimpleNamespace(
            ViewZoomToFit2=Mock(side_effect=RuntimeError("COM error")),
            ActiveView=active_view,
        )
        adapter._zoom_to_fit(target_doc)
        assert target_doc.ViewZoomToFit2.called
        assert active_view.ZoomToFit.called

    @pytest.mark.asyncio
    async def test_zoom_to_fit_both_fail_logs_warning(
        self, monkeypatch, caplog
    ) -> None:
        """_zoom_to_fit should log warning if both zoom methods fail."""
        adapter = self._build_adapter(monkeypatch)
        active_view = SimpleNamespace(
            ZoomToFit=Mock(side_effect=RuntimeError("COM error"))
        )
        target_doc = SimpleNamespace(
            ViewZoomToFit2=Mock(side_effect=RuntimeError("COM error")),
            ActiveView=active_view,
        )
        adapter._zoom_to_fit(target_doc)
        assert target_doc.ViewZoomToFit2.called
        assert active_view.ZoomToFit.called

    @pytest.mark.asyncio
    async def test_save_screenshot_with_modelview_success(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_screenshot_with_modelview should return True when file created."""
        adapter = self._build_adapter(monkeypatch)
        test_file = tmp_path / "test.png"
        test_file.touch()
        model_view = SimpleNamespace(SaveBitmapWithVariableSize=Mock(return_value=True))
        result = adapter._save_screenshot_with_modelview(
            model_view, str(test_file), 1280, 720
        )
        assert result is True
        model_view.SaveBitmapWithVariableSize.assert_called_once_with(
            str(test_file), 1280, 720
        )

    @pytest.mark.asyncio
    async def test_save_screenshot_with_modelview_file_not_exists(
        self, monkeypatch
    ) -> None:
        """_save_screenshot_with_modelview should return False if file doesn't exist."""
        adapter = self._build_adapter(monkeypatch)
        model_view = SimpleNamespace(SaveBitmapWithVariableSize=Mock(return_value=True))
        result = adapter._save_screenshot_with_modelview(
            model_view, "/nonexistent/file.png", 1280, 720
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_screenshot_with_modelview_exception(self, monkeypatch) -> None:
        """_save_screenshot_with_modelview should return False on exception."""
        adapter = self._build_adapter(monkeypatch)
        model_view = SimpleNamespace(
            SaveBitmapWithVariableSize=Mock(side_effect=RuntimeError("COM error"))
        )
        result = adapter._save_screenshot_with_modelview(
            model_view, "/path/file.png", 1280, 720
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_screenshot_with_targetdoc_success(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_screenshot_with_targetdoc should return True when file created."""
        adapter = self._build_adapter(monkeypatch)
        test_file = tmp_path / "test.png"
        test_file.touch()
        target_doc = SimpleNamespace(SaveBitmapWithVariableSize=Mock(return_value=True))
        result = adapter._save_screenshot_with_targetdoc(
            target_doc, str(test_file), 1280, 720
        )
        assert result is True
        target_doc.SaveBitmapWithVariableSize.assert_called_once_with(
            str(test_file), 1280, 720
        )

    @pytest.mark.asyncio
    async def test_save_screenshot_with_targetdoc_file_not_exists(
        self, monkeypatch
    ) -> None:
        """_save_screenshot_with_targetdoc should return False if file doesn't exist."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(SaveBitmapWithVariableSize=Mock(return_value=True))
        result = adapter._save_screenshot_with_targetdoc(
            target_doc, "/nonexistent/file.png", 1280, 720
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_screenshot_with_targetdoc_exception(self, monkeypatch) -> None:
        """_save_screenshot_with_targetdoc should return False on exception."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(
            SaveBitmapWithVariableSize=Mock(side_effect=RuntimeError("COM error"))
        )
        result = adapter._save_screenshot_with_targetdoc(
            target_doc, "/path/file.png", 1280, 720
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_screenshot_with_saveas3_success(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_screenshot_with_saveas3 should return silently when file created."""
        adapter = self._build_adapter(monkeypatch)
        test_file = tmp_path / "test.png"
        test_file.touch()
        target_doc = SimpleNamespace(SaveAs3=Mock())
        adapter._save_screenshot_with_saveas3(target_doc, str(test_file))
        target_doc.SaveAs3.assert_called_once_with(str(test_file), 0, 2)

    @pytest.mark.asyncio
    async def test_save_screenshot_with_saveas3_file_not_created(
        self, monkeypatch
    ) -> None:
        """_save_screenshot_with_saveas3 should raise if SaveAs3 doesn't create file."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(SaveAs3=Mock())
        with pytest.raises(RuntimeError) as exc_info:
            adapter._save_screenshot_with_saveas3(target_doc, "/nonexistent/file.png")
        assert "All screenshot methods failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_screenshot_with_saveas3_raises(self, monkeypatch) -> None:
        """_save_screenshot_with_saveas3 should raise if SaveAs3 raises."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(
            SaveAs3=Mock(side_effect=RuntimeError("COM SaveAs3 error"))
        )
        with pytest.raises(RuntimeError) as exc_info:
            adapter._save_screenshot_with_saveas3(target_doc, "/path/file.png")
        assert "All screenshot methods failed" in str(exc_info.value)

    def test_invoke_run_macro2_tuple_success(self, monkeypatch) -> None:
        """_invoke_run_macro2 returns dict when RunMacro2 returns (True, 0) tuple."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=(True, 0)))
        result = adapter._invoke_run_macro2("/macros/test.swp", "TestModule", "main")
        assert result["macro_path"] == "/macros/test.swp"
        assert result["module_name"] == "TestModule"
        assert result["errors"] == 0

    def test_invoke_run_macro2_bool_success(self, monkeypatch) -> None:
        """_invoke_run_macro2 handles scalar True return (non-tuple)."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=True))
        result = adapter._invoke_run_macro2("/macros/test.swp", "TestModule", "main")
        assert result["errors"] == 0

    def test_invoke_run_macro2_tuple_failure_raises(self, monkeypatch) -> None:
        """_invoke_run_macro2 raises SolidWorksMCPError when RunMacro2 returns (False, 5)."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=(False, 5)))
        with pytest.raises(SolidWorksMCPError):
            adapter._invoke_run_macro2("/macros/test.swp", "TestModule", "main")

    def test_invoke_run_macro2_bool_failure_raises(self, monkeypatch) -> None:
        """_invoke_run_macro2 raises SolidWorksMCPError when RunMacro2 returns False."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=False))
        with pytest.raises(SolidWorksMCPError):
            adapter._invoke_run_macro2("/macros/test.swp", "TestModule", "main")

    def test_invoke_run_macro2_passes_byref_retval(self, monkeypatch) -> None:
        """Regression (issue #91): RunMacro2's nRetval is a ByRef Long. Passing
        a plain int raises DISP_E_TYPEMISMATCH at arg index 5, so a 5th arg
        must always be supplied (VARIANT on Windows, int on the mocked path)."""
        adapter = self._build_adapter(monkeypatch)
        run = Mock(return_value=True)
        adapter.swApp = SimpleNamespace(RunMacro2=run)

        adapter._invoke_run_macro2("/macros/test.swp", "TestModule", "main")

        call = run.call_args
        assert call.args[:4] == ("/macros/test.swp", "TestModule", "main", 0)
        assert len(call.args) == 5

    def test_invoke_run_macro2_names_the_error_code(self, monkeypatch) -> None:
        """A RunMacro2 failure reports the swRunMacroError_e name, not a bare int
        (issue #91 follow-up: errors=22 -> 'Invalidindex')."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=(False, 22)))
        with pytest.raises(SolidWorksMCPError) as excinfo:
            adapter._invoke_run_macro2("/macros/x.swp", "wrongmod", "main")
        msg = str(excinfo.value)
        assert "22 (Invalidindex)" in msg
        assert "proc='main'" in msg

    @pytest.mark.asyncio
    async def test_close_model_reads_get_title_property_style(
        self, monkeypatch
    ) -> None:
        """Regression (issue #91): currentModel can be an unflagged dispatch
        where GetTitle resolves property-style to a str. close_model must read
        it through _get_attr_or_call, not call the returned string."""
        adapter = self._build_adapter(monkeypatch)
        close_doc = Mock()
        adapter.swApp = SimpleNamespace(CloseDoc=close_doc)
        adapter.currentModel = SimpleNamespace(GetTitle="wifi_box_snapfit")

        result = await adapter.close_model(save=False)

        assert result.is_success
        close_doc.assert_called_once_with("wifi_box_snapfit")
        assert adapter.currentModel is None

    @pytest.mark.asyncio
    async def test_close_model_save_reads_save_property_style(
        self, monkeypatch
    ) -> None:
        """save=True path also reaches Save through _get_attr_or_call (issue #91)."""
        adapter = self._build_adapter(monkeypatch)
        saved = Mock()
        adapter.swApp = SimpleNamespace(CloseDoc=Mock())
        adapter.currentModel = SimpleNamespace(GetTitle="Part1", Save=saved)

        result = await adapter.close_model(save=True)

        assert result.is_success
        saved.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_model_activates_opened_document(self, monkeypatch) -> None:
        """Regression (issue #91): open_model must ActivateDoc3 the freshly
        opened document. OpenDoc6 with swOpenDocOptions_Silent opens the file
        but leaves the previously focused document active, so without this
        every later tool call targets the wrong document."""
        adapter = self._build_adapter(monkeypatch)

        opened_doc = SimpleNamespace(
            GetTitle=Mock(return_value="snapfit.SLDPRT"),
            GetActiveConfiguration=Mock(return_value=None),
            GetSaveTime=Mock(return_value="now"),
        )
        activated_doc = SimpleNamespace(
            GetTitle=Mock(return_value="snapfit.SLDPRT"),
            GetActiveConfiguration=Mock(return_value=None),
            GetSaveTime=Mock(return_value="now"),
        )
        activate = Mock(return_value=activated_doc)
        adapter.swApp = SimpleNamespace(
            OpenDoc6=Mock(return_value=opened_doc),
            ActivateDoc3=activate,
        )

        result = await adapter.open_model("C:/parts/snapfit.SLDPRT")

        assert result.is_success
        # ActivateDoc3 takes the titlebar name, not the path.
        assert activate.call_args.args[0] == "snapfit.SLDPRT"
        assert adapter.currentModel is activated_doc

    @pytest.mark.asyncio
    async def test_export_image_returns_error_without_connection(
        self, monkeypatch
    ) -> None:
        """export_image should validate currentModel and swApp preconditions."""
        adapter = self._build_adapter(monkeypatch)

        no_model = await adapter.export_image({"file_path": "C:/tmp/out.png"})
        assert no_model.is_error
        assert no_model.error == "No active model"

        adapter.currentModel = SimpleNamespace()
        adapter.swApp = None
        no_sw = await adapter.export_image({"file_path": "C:/tmp/out.png"})
        assert no_sw.is_error
        assert no_sw.error == "SolidWorks not connected"

    @pytest.mark.asyncio
    async def test_export_image_success_with_orientation(
        self, monkeypatch, tmp_path
    ) -> None:
        """export_image should set orientation and persist an image on success."""
        adapter = self._build_adapter(monkeypatch)
        output_file = tmp_path / "shot.png"

        def _save_bitmap(path, *_args):
            output_file.write_text("image", encoding="utf-8")
            return True

        target_doc = SimpleNamespace(
            SaveBitmapWithVariableSize=Mock(side_effect=_save_bitmap),
            ShowNamedView2=Mock(),
            ViewZoomToFit2=Mock(),
            GetTitle=Mock(return_value="shot.SLDPRT"),
            GetPathName=Mock(return_value=""),
        )
        adapter.currentModel = target_doc
        adapter.swApp = SimpleNamespace(
            ActiveDoc=target_doc,
            Frame=SimpleNamespace(SetFocus=Mock()),
            ActivateDoc3=Mock(return_value=target_doc),
        )

        result = await adapter.export_image(
            {
                "file_path": str(output_file),
                "view_orientation": "front",
                "width": 640,
                "height": 480,
            }
        )

        assert result.is_success
        assert result.data["file_path"] == str(output_file)
        assert result.data["format"] == "PNG"
        assert result.data["dimensions"] == "640x480"
        assert result.data["view"] == "front"
        target_doc.ShowNamedView2.assert_called_once_with("", 1)
        target_doc.ViewZoomToFit2.assert_called_once()
        adapter.swApp.ActivateDoc3.assert_called_once()
        assert adapter.swApp.ActivateDoc3.call_args[0][0] == "shot.SLDPRT"

    def test_prepare_stl_export_data_paths(self, monkeypatch) -> None:
        """_prepare_stl_export_data should handle missing app, missing data, and success."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = None
        assert adapter._prepare_stl_export_data() is None

        adapter.swApp = SimpleNamespace(GetExportFileData=Mock(return_value=None))
        assert adapter._prepare_stl_export_data() is None

        stl_data = SimpleNamespace(Merge=False, ExportBodiesAs=1)
        adapter.swApp = SimpleNamespace(GetExportFileData=Mock(return_value=stl_data))
        result = adapter._prepare_stl_export_data()
        assert result is stl_data
        assert stl_data.Merge is True
        assert stl_data.ExportBodiesAs == 0

    def test_save_stl_with_extension_fallback_to_no_export_data(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_stl_with_extension should retry SaveAs2 with None export data."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "out.stl"

        call_counter = {"count": 0}

        def _saveas2(path, *_args):
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                raise RuntimeError("type mismatch")
            out_file.write_text("solid", encoding="utf-8")

        extension = SimpleNamespace(SaveAs2=Mock(side_effect=_saveas2))
        saved = adapter._save_stl_with_extension(extension, object(), str(out_file))

        assert saved is True
        assert extension.SaveAs2.call_count == 2

    def test_save_stl_with_extension_returns_false_on_failure(
        self, monkeypatch
    ) -> None:
        """_save_stl_with_extension should return False when SaveAs2 keeps failing."""
        adapter = self._build_adapter(monkeypatch)
        extension = SimpleNamespace(SaveAs2=Mock(side_effect=RuntimeError("fail")))

        saved = adapter._save_stl_with_extension(
            extension, object(), "C:/tmp/missing.stl"
        )

        assert saved is False

    def test_save_stl_with_fallback_raises_when_file_not_created(
        self, monkeypatch
    ) -> None:
        """_save_stl_with_fallback should raise when SaveAs3 does not create output."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(SaveAs3=Mock(return_value=False))

        with pytest.raises(Exception, match="STL export failed"):
            adapter._save_stl_with_fallback(target_doc, "C:/tmp/missing.stl")

    @pytest.mark.asyncio
    async def test_execute_macro_returns_error_without_macro_path(
        self, monkeypatch
    ) -> None:
        """execute_macro should error when neither macro_path nor macro_file is provided."""
        adapter = self._build_adapter(monkeypatch)
        result = await adapter.execute_macro({})
        assert result.is_error
        assert result.error == "No macro_path provided"

    @pytest.mark.asyncio
    async def test_execute_macro_returns_error_when_file_missing(
        self, monkeypatch
    ) -> None:
        """execute_macro should error when macro file path does not exist."""
        adapter = self._build_adapter(monkeypatch)
        result = await adapter.execute_macro({"macro_path": "C:/missing/not_found.swp"})
        assert result.is_error
        assert "Macro file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_macro_success_with_macro_file_alias(
        self, monkeypatch, tmp_path
    ) -> None:
        """execute_macro should accept macro_file alias and parse module name from file."""
        adapter = self._build_adapter(monkeypatch)
        adapter.swApp = SimpleNamespace(RunMacro2=Mock(return_value=(True, 0)))

        macro_file = tmp_path / "my_macro.swp"
        macro_file.write_text('Attribute VB_Name = "MyMacroModule"\n', encoding="utf-8")

        result = await adapter.execute_macro(
            {
                "macro_file": str(macro_file),
                "proc_name": "main",
            }
        )

        assert result.is_success
        assert result.data["macro_path"] == str(macro_file)
        assert result.data["module_name"] == "MyMacroModule"
        assert result.data["errors"] == 0
        call = adapter.swApp.RunMacro2.call_args
        assert call.args[:4] == (str(macro_file), "MyMacroModule", "main", 0)
        # 5th arg is the ByRef Long retval out-param (VARIANT on Windows,
        # plain int on the mocked CI path).
        assert len(call.args) == 5

    @pytest.mark.asyncio
    async def test_export_file_stl_errors_when_extension_missing(
        self, monkeypatch, tmp_path
    ) -> None:
        """export_file should fail STL export when target document has no Extension."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "missing_ext.stl"

        target_doc = SimpleNamespace(
            ResolveAllLightweightComponents=Mock(),
            Extension=None,
        )
        adapter.currentModel = target_doc
        adapter.swApp = SimpleNamespace(ActiveDoc=target_doc)

        result = await adapter.export_file(str(out_file), "stl")
        assert result.is_error
        assert "No Extension object available for STL export" in (result.error or "")

    @pytest.mark.asyncio
    async def test_export_file_stl_success_via_extension_path(
        self, monkeypatch, tmp_path
    ) -> None:
        """export_file should complete STL export when SaveAs2 path succeeds."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "ok_ext.stl"

        extension = SimpleNamespace(SaveAs2=Mock())
        target_doc = SimpleNamespace(
            ResolveAllLightweightComponents=Mock(),
            Extension=extension,
            SaveAs3=Mock(),
        )
        adapter.currentModel = target_doc
        adapter.swApp = SimpleNamespace(ActiveDoc=target_doc)

        monkeypatch.setattr(
            adapter,
            "_prepare_stl_export_data",
            Mock(return_value=SimpleNamespace(Merge=True, ExportBodiesAs=0)),
        )
        monkeypatch.setattr(
            adapter, "_save_stl_with_extension", Mock(return_value=True)
        )
        monkeypatch.setattr(adapter, "_save_stl_with_fallback", Mock())

        result = await adapter.export_file(str(out_file), "stl")

        assert result.is_success
        target_doc.ResolveAllLightweightComponents.assert_called_once_with(True)
        adapter._save_stl_with_extension.assert_called_once()
        adapter._save_stl_with_fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_file_stl_falls_back_to_saveas3(
        self, monkeypatch, tmp_path
    ) -> None:
        """export_file should use _save_stl_with_fallback when SaveAs2 path fails."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "fallback_ok.stl"

        extension = SimpleNamespace(SaveAs2=Mock())
        target_doc = SimpleNamespace(
            ResolveAllLightweightComponents=Mock(),
            Extension=extension,
            SaveAs3=Mock(),
        )
        adapter.currentModel = target_doc
        adapter.swApp = SimpleNamespace(ActiveDoc=target_doc)

        monkeypatch.setattr(
            adapter,
            "_prepare_stl_export_data",
            Mock(return_value=SimpleNamespace(Merge=True, ExportBodiesAs=0)),
        )
        monkeypatch.setattr(
            adapter, "_save_stl_with_extension", Mock(return_value=False)
        )
        monkeypatch.setattr(adapter, "_save_stl_with_fallback", Mock(return_value=None))

        result = await adapter.export_file(str(out_file), "stl")

        assert result.is_success
        adapter._save_stl_with_extension.assert_called_once()
        adapter._save_stl_with_fallback.assert_called_once_with(
            target_doc, str(out_file)
        )

    @pytest.mark.asyncio
    async def test_export_file_non_stl_accepts_false_when_file_written(
        self, monkeypatch, tmp_path
    ) -> None:
        """export_file should succeed if SaveAs3 is False but output file exists."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "out.step"

        def _saveas3(path, *_args):
            out_file.write_text("ok", encoding="utf-8")
            return False

        target_doc = SimpleNamespace(SaveAs3=Mock(side_effect=_saveas3))
        adapter.currentModel = target_doc
        adapter.swApp = SimpleNamespace(ActiveDoc=target_doc)

        result = await adapter.export_file(str(out_file), "step")

        assert result.is_success
        target_doc.SaveAs3.assert_called_once()

    def test_save_stl_with_fallback_succeeds_when_file_exists(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_stl_with_fallback should return cleanly when output exists after SaveAs3."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "fallback_success.stl"

        def _saveas3(path, *_args):
            out_file.write_text("solid", encoding="utf-8")
            return True

        target_doc = SimpleNamespace(SaveAs3=Mock(side_effect=_saveas3))

        adapter._save_stl_with_fallback(target_doc, str(out_file))
        target_doc.SaveAs3.assert_called_once_with(str(out_file), 0, 2)

    def test_save_stl_with_fallback_swallows_saveas3_error_if_file_exists(
        self, monkeypatch, tmp_path
    ) -> None:
        """_save_stl_with_fallback should not raise when SaveAs3 errors but file is present."""
        adapter = self._build_adapter(monkeypatch)
        out_file = tmp_path / "already_exists.stl"
        out_file.write_text("solid", encoding="utf-8")
        target_doc = SimpleNamespace(SaveAs3=Mock(side_effect=RuntimeError("COM fail")))

        adapter._save_stl_with_fallback(target_doc, str(out_file))
        target_doc.SaveAs3.assert_called_once_with(str(out_file), 0, 2)

    @pytest.mark.asyncio
    async def test_export_file_returns_error_without_active_model(
        self, monkeypatch
    ) -> None:
        """export_file should return a guard error when currentModel is missing."""
        adapter = self._build_adapter(monkeypatch)

        result = await adapter.export_file("C:/tmp/out.step", "step")

        assert result.is_error
        assert result.error == "No active model"

    @pytest.mark.asyncio
    async def test_dimension_methods_return_error_without_active_model(
        self, monkeypatch
    ) -> None:
        """get_dimension/set_dimension should guard when there is no current model."""
        adapter = self._build_adapter(monkeypatch)

        get_result = await adapter.get_dimension("D1@Sketch1")
        set_result = await adapter.set_dimension("D1@Sketch1", 12.5)

        assert get_result.is_error
        assert get_result.error == "No active model"
        assert set_result.is_error
        assert set_result.error == "No active model"

    @pytest.mark.asyncio
    async def test_save_file_raises_when_save3_none_and_save_missing(
        self, monkeypatch
    ) -> None:
        """save_file should error when Save3 returns None and no Save fallback exists."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            Save3=Mock(return_value=None),
            GetPathName=Mock(return_value=""),
        )

        result = await adapter.save_file()

        assert result.is_error
        assert "Failed to save file" in (result.error or "")

    @pytest.mark.asyncio
    async def test_model_info_and_list_features_return_error_without_model(
        self, monkeypatch
    ) -> None:
        """get_model_info/list_features should return guard errors when model is absent."""
        adapter = self._build_adapter(monkeypatch)

        info_result = await adapter.get_model_info()
        list_result = await adapter.list_features()

        assert info_result.is_error
        assert info_result.error == "No active model"
        assert list_result.is_error
        assert list_result.error == "No active model"

    @pytest.mark.asyncio
    async def test_get_model_info_syncs_currentmodel_from_active_doc(
        self, monkeypatch
    ) -> None:
        """get_model_info should resync currentModel to swApp.ActiveDoc.

        Regression coverage for the live-readback fix: a stale currentModel
        pointer (e.g. from a prior document) must not shadow whatever
        document is actually active in SolidWorks right now.
        """
        adapter = self._build_adapter(monkeypatch)

        active_doc = SimpleNamespace(
            GetTitle=Mock(return_value="LiveActive.sldprt"),
            GetPathName=Mock(return_value="C:/parts/LiveActive.sldprt"),
            GetType=Mock(return_value=1),
            GetSaveFlag=Mock(return_value=False),
            GetRebuildStatus=Mock(return_value=0),
            GetActiveConfiguration=None,
            FeatureManager=SimpleNamespace(GetFeatureCount=Mock(return_value=3)),
        )
        adapter.swApp = SimpleNamespace(ActiveDoc=active_doc)
        # A stale reference from a previously-open document.
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="Stale.sldprt")
        )

        result = await adapter.get_model_info()

        assert result.is_success
        assert result.data["title"] == "LiveActive.sldprt"
        assert result.data["path"] == "C:/parts/LiveActive.sldprt"
        assert adapter.currentModel is active_doc

    @pytest.mark.asyncio
    async def test_connect_and_document_creation_not_connected_paths(
        self, monkeypatch
    ) -> None:
        """Cover connection/document creation branches when COM app is missing."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = None
        assert adapter._resolve_template_path([8, 0], ".prtdot") is None

        adapter.currentModel = SimpleNamespace(GetTitle=Mock(return_value="Part1"))
        close_result = await adapter.close_model()
        assert close_result.is_error
        assert "not connected" in (close_result.error or "").lower()

        monkeypatch.setattr(adapter, "is_connected", lambda: True)
        adapter.swApp = None
        part_result = await adapter.create_part()
        assembly_result = await adapter.create_assembly()
        drawing_result = await adapter.create_drawing()
        assert part_result.is_error
        assert assembly_result.is_error
        assert drawing_result.is_error
        assert "not connected" in (part_result.error or "").lower()
        assert "not connected" in (assembly_result.error or "").lower()
        assert "not connected" in (drawing_result.error or "").lower()

    @pytest.mark.asyncio
    async def test_export_image_and_stl_prep_failure_paths(
        self, monkeypatch, tmp_path
    ) -> None:
        """Cover export_image all-methods-failed and STL export-data exception branch."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace()
        adapter.swApp = SimpleNamespace(
            ActiveDoc=None,
            Frame=SimpleNamespace(SetFocus=Mock()),
        )

        monkeypatch.setattr(
            adapter,
            "_save_screenshot_with_modelview",
            lambda *_args, **_kwargs: False,
        )
        monkeypatch.setattr(
            adapter,
            "_save_screenshot_with_targetdoc",
            lambda *_args, **_kwargs: False,
        )
        monkeypatch.setattr(
            adapter,
            "_save_screenshot_with_saveas3",
            lambda *_args, **_kwargs: None,
        )

        failed = await adapter.export_image(
            {
                "file_path": str(tmp_path / "never-created.png"),
                "orientation": "current",
                "width": 800,
                "height": 600,
            }
        )
        assert failed.is_error
        assert "All screenshot methods produced no output" in (failed.error or "")

        adapter.swApp = SimpleNamespace(
            GetExportFileData=Mock(side_effect=RuntimeError("COM failure"))
        )
        assert adapter._prepare_stl_export_data() is None

    @pytest.mark.asyncio
    async def test_set_dimension_setvalue_failure_branch(self, monkeypatch) -> None:
        """set_dimension should report error when SetValue3 returns False."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            Parameter=Mock(
                return_value=SimpleNamespace(SetValue3=Mock(return_value=False))
            )
        )

        result = await adapter.set_dimension("D1@Sketch1", 10.0)
        assert result.is_error
        assert "Failed to set dimension" in (result.error or "")

    @pytest.mark.parametrize(
        "select4_result,select2_result,select_result,expected",
        [
            (True, False, False, True),
            (False, True, False, True),
            (False, False, True, True),
            (False, False, False, False),
        ],
    )
    def test_sketch_geometry_select_entity_variants(
        self, monkeypatch, select4_result, select2_result, select_result, expected
    ) -> None:
        """select_entity should follow Select4 -> Select2 -> Select fallback order."""
        adapter = self._build_adapter(monkeypatch)
        entity = SimpleNamespace(
            Select4=Mock(return_value=select4_result),
            Select2=Mock(return_value=select2_result),
            Select=Mock(return_value=select_result),
        )
        assert adapter._select_sketch_entity(entity, append=False) is expected

    def test_sketch_geometry_set_display_dimension_value_fallbacks(
        self, monkeypatch
    ) -> None:
        """set_display_dimension_value should use SetSystemValue3, then SetSystemValue2, then SystemValue."""
        adapter = self._build_adapter(monkeypatch)

        dim3 = SimpleNamespace(
            SetSystemValue3=Mock(return_value=True),
            SetSystemValue2=Mock(return_value=True),
        )
        display3 = SimpleNamespace(
            GetDimension2=Mock(return_value=dim3), GetDimension=Mock(return_value=None)
        )
        adapter._set_display_dimension_value(display3, 12.0)
        dim3.SetSystemValue3.assert_called_once()

        dim2 = SimpleNamespace(
            SetSystemValue3=Mock(side_effect=RuntimeError("no v3")),
            SetSystemValue2=Mock(return_value=True),
        )
        display2 = SimpleNamespace(
            GetDimension2=Mock(return_value=dim2), GetDimension=Mock(return_value=None)
        )
        adapter._set_display_dimension_value(display2, 13.0)
        dim2.SetSystemValue2.assert_called_once()

        dim1 = SimpleNamespace(
            SetSystemValue3=Mock(side_effect=RuntimeError("no v3")),
            SetSystemValue2=Mock(side_effect=RuntimeError("no v2")),
            SystemValue=None,
        )
        display1 = SimpleNamespace(
            GetDimension2=Mock(return_value=dim1), GetDimension=Mock(return_value=None)
        )
        adapter._set_display_dimension_value(display1, 14.0)
        assert dim1.SystemValue == pytest.approx(0.014)

    @pytest.mark.parametrize(
        "point_obj,expected",
        [
            (None, None),
            (SimpleNamespace(X=1.0, Y=2.0, Z=3.0), (1.0, 2.0, 3.0)),
            (SimpleNamespace(GetCoords=lambda: [4.0, 5.0, 6.0]), (4.0, 5.0, 6.0)),
            (SimpleNamespace(GetCoords=lambda: [1.0, 2.0]), None),
        ],
    )
    def test_sketch_geometry_point_xyz_variants(
        self, monkeypatch, point_obj, expected
    ) -> None:
        """point_xyz should support direct XYZ, GetCoords fallback, and invalid payloads."""
        adapter = self._build_adapter(monkeypatch)
        assert adapter._sketch_geometry.point_xyz(point_obj) == expected

    @pytest.mark.parametrize(
        "mode,expected", [("setcoords", True), ("setcoords2", True), ("none", False)]
    )
    def test_sketch_geometry_set_point_xyz_variants(
        self, monkeypatch, mode, expected
    ) -> None:
        """set_point_xyz should try SetCoords then SetCoords2 and return False on full failure."""
        adapter = self._build_adapter(monkeypatch)

        if mode == "setcoords":
            point = SimpleNamespace(
                SetCoords=Mock(return_value=True), SetCoords2=Mock(return_value=True)
            )
        elif mode == "setcoords2":
            point = SimpleNamespace(
                SetCoords=Mock(side_effect=RuntimeError("no setcoords")),
                SetCoords2=Mock(return_value=True),
            )
        else:
            point = SimpleNamespace(
                SetCoords=Mock(side_effect=RuntimeError("no setcoords")),
                SetCoords2=Mock(side_effect=RuntimeError("no setcoords2")),
            )

        assert adapter._sketch_geometry.set_point_xyz(point, 1.0, 2.0, 3.0) is expected

    def test_sketch_geometry_segment_vertex_and_placement_paths(
        self, monkeypatch
    ) -> None:
        """Sketch geometry helpers should cover endpoint parsing, shared vertices, and placement edge cases."""
        adapter = self._build_adapter(monkeypatch)
        service = adapter._sketch_geometry

        segment = SimpleNamespace(
            GetStartPoint=(0.0, 0.0, 0.0), GetEndPoint=(10.0, 0.0, 0.0)
        )
        assert service.read_segment_endpoints(segment) == (
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
        )
        assert service.segment_point_objects(
            SimpleNamespace(GetStartPoint2="p1", GetEndPoint2="p2")
        ) == ("p1", "p2")

        shared_p = SimpleNamespace(X=0.0, Y=0.0, Z=0.0)
        other_p = SimpleNamespace(X=1.0, Y=0.0, Z=0.0)
        e1 = SimpleNamespace(GetStartPoint2=shared_p, GetEndPoint2=other_p)
        e2 = SimpleNamespace(
            GetStartPoint2=shared_p, GetEndPoint2=SimpleNamespace(X=0.0, Y=1.0, Z=0.0)
        )
        shared = service.shared_segment_vertex(e1, e2)
        assert shared is not None

        assert (
            service.smart_dimension_direction(1.0, 0.1)
            == adapter.constants["swSmartDimensionDirectionRight"]
        )
        assert (
            service.smart_dimension_direction(-1.0, 0.0)
            == adapter.constants["swSmartDimensionDirectionLeft"]
        )
        assert (
            service.smart_dimension_direction(0.0, 1.0)
            == adapter.constants["swSmartDimensionDirectionUp"]
        )

        assert (
            service.single_line_dimension_placement(
                SimpleNamespace(
                    GetStartPoint=(0.0, 0.0, 0.0), GetEndPoint=(0.0, 0.0, 0.0)
                )
            )
            is None
        )
        placement = service.single_line_dimension_placement(segment)
        assert placement is not None

        assert (
            service.angular_dimension_placement(
                segment,
                SimpleNamespace(
                    GetStartPoint=(20.0, 0.0, 0.0), GetEndPoint=(30.0, 0.0, 0.0)
                ),
            )
            is None
        )
        angle_ok = service.angular_dimension_placement(
            SimpleNamespace(
                GetStartPoint=(0.0, 0.0, 0.0), GetEndPoint=(10.0, 0.0, 0.0)
            ),
            SimpleNamespace(
                GetStartPoint=(0.0, 0.0, 0.0), GetEndPoint=(0.0, 10.0, 0.0)
            ),
        )
        assert angle_ok is not None

    @pytest.mark.parametrize(
        "current_path,current_title,active_path,active_title,expect_active",
        [
            (None, None, "C:/a.sldprt", "A", False),
            ("C:/a.sldprt", "A", "C:/a.sldprt", "B", True),
            (None, "A", None, "A", True),
            ("C:/a.sldprt", "A", "C:/b.sldprt", "A", False),
        ],
    )
    def test_document_routing_identity_and_resolution_variants(
        self,
        monkeypatch,
        current_path,
        current_title,
        active_path,
        active_title,
        expect_active,
    ) -> None:
        """Document routing should pick active or current model based on identity/path/title policy."""
        adapter = self._build_adapter(monkeypatch)

        def _doc(path, title):
            return SimpleNamespace(
                GetPathName=(lambda: path) if path is not None else (lambda: ""),
                GetTitle=(lambda: title) if title is not None else (lambda: ""),
            )

        current_doc = _doc(current_path, current_title)
        active_doc = _doc(active_path, active_title)
        adapter.currentModel = current_doc
        adapter.swApp = SimpleNamespace(ActiveDoc=active_doc)

        resolved = adapter._resolve_export_target_doc()
        assert (resolved is active_doc) is expect_active

        path_value, title_value = adapter._document_identity(current_doc)
        if current_path:
            assert path_value is not None
        if current_title:
            assert title_value == current_title

    def test_pywin32_wrapper_delegations(self, monkeypatch) -> None:
        """Thin pywin32 wrappers should delegate to coordinator/geometry/routing services."""
        adapter = self._build_adapter(monkeypatch)

        adapter._session_coordinator = SimpleNamespace(
            initialize_com_apartment=Mock(),
            uninitialize_com_apartment=Mock(),
            acquire_solidworks_application=AsyncMock(return_value="app"),
            wait_for_server_ready=AsyncMock(return_value=None),
            set_automation_preferences=Mock(),
        )
        adapter._sketch_geometry = SimpleNamespace(
            select_entity=Mock(return_value=True),
            set_display_dimension_value=Mock(),
        )
        adapter._document_routing = SimpleNamespace(
            document_identity=Mock(return_value=("C:/x.sldprt", "X")),
        )

        adapter._initialize_com_apartment()
        adapter._uninitialize_com_apartment()
        assert adapter._select_sketch_entity(SimpleNamespace(), append=False) is True
        adapter._set_display_dimension_value(SimpleNamespace(), 10.0)
        assert adapter._document_identity(SimpleNamespace()) == ("C:/x.sldprt", "X")


class TestPyWin32AdapterAdditionalCoverage:
    """Target additional edge paths for pywin32 adapter coverage."""

    @staticmethod
    def _build_adapter(monkeypatch) -> PyWin32Adapter:
        """Test helper for build adapter."""
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Windows",
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=RuntimeError),
            raising=False,
        )
        adapter = PyWin32Adapter({})
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_com = MagicMock()
        mock_com._thread = mock_thread
        mock_com.run = lambda fn, timeout=None: fn()
        adapter._com = mock_com
        return adapter

    @pytest.mark.asyncio
    async def test_open_create_and_feature_failure_paths(self, monkeypatch):
        """Test open create and feature failure paths."""
        adapter = self._build_adapter(monkeypatch)

        fake_app = SimpleNamespace(
            OpenDoc6=Mock(return_value=None),
            NewDocument=Mock(return_value=None),
            GetUserPreferenceStringValue=Mock(
                side_effect=lambda idx: {
                    0: "C:/Templates/Part.prtdot",
                    1: "",
                    2: "",
                }.get(idx, "")
            ),
        )
        adapter.swApp = fake_app

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(VT_BYREF=0x4000, VT_I4=3),
            raising=False,
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=lambda _kind, val: val)),
            raising=False,
        )

        failed_part_open = await adapter.open_model("C:/tmp/model.sldprt")
        failed_drawing_open = await adapter.open_model("C:/tmp/model.slddrw")
        assert failed_part_open.is_error
        assert failed_drawing_open.is_error

        failed_part_create = await adapter.create_part()
        failed_assembly_create = await adapter.create_assembly()
        failed_drawing_create = await adapter.create_drawing()
        assert failed_part_create.is_error
        assert failed_assembly_create.is_error
        assert failed_drawing_create.is_error

        adapter.swApp = SimpleNamespace(
            RevisionNumber=Mock(side_effect=[RuntimeError("x"), "Unknown"])
        )
        health = await adapter.health_check()
        assert health.healthy is False

        adapter.currentModel = SimpleNamespace(
            FeatureManager=SimpleNamespace(
                FeatureExtrusion2=Mock(return_value=None),
                FeatureExtruThin2=Mock(return_value=None),
                FeatureRevolve2=Mock(return_value=None),
            )
        )
        extrusion_failed = await adapter.create_extrusion(
            SimpleNamespace(
                depth=10.0,
                draft_angle=0.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
        revolve_failed = await adapter.create_revolve(
            SimpleNamespace(
                angle=90.0,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
        assert extrusion_failed.is_error
        assert revolve_failed.is_error


def test_mock_mate_types_match_the_com_layer() -> None:
    """The mock's accepted mate types must match the COM implementation.

    The two lists are maintained separately, so a mate type added to the COM
    layer alone would be rejected in mock mode and accepted live -- and the
    whole test suite runs against the mock.
    """
    from solidworks_mcp.adapters.solidworks.io import _MATE_TYPES

    source = inspect.getsource(MockSolidWorksAdapter.add_mate)
    for mate_type in _MATE_TYPES:
        assert f'"{mate_type}"' in source, (
            f"the COM layer supports the {mate_type!r} mate but the mock "
            "rejects it, so no test can cover it"
        )


def test_the_obsolete_com_call_is_not_used() -> None:
    """``ToolsCheckInterference2`` must not come back.

    It is declared ``Sub`` with two ``ByRef`` out-parameters and on SW 2025
    could not be made to report anything through pywin32 late binding:
    ``pythoncom.Missing`` raises, a plain ``None`` or a typed array VARIANT
    raises ``Type mismatch``, a component array throws server-side, and a
    byref ``VT_VARIANT`` pair is accepted but leaves both out-parameters
    ``None`` on an assembly that demonstrably interferes.

    A reference implementation read its non-existent return value as a count
    (``int(raw[0])``), which would report "no interference" on an assembly
    that has some.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.io as io_module

    source = Path(io_module.__file__).read_text(encoding="utf-8")
    # Match the call syntax rather than the name, so the docstring explaining
    # why it is avoided does not trip its own guard.
    call_sites = [
        line.strip()
        for line in source.splitlines()
        if ".ToolsCheckInterference" in line and "(" in line
    ]
    assert not call_sites, (
        "ToolsCheckInterference2 is being called again; it cannot report a "
        f"result on SW 2025. Offending lines: {call_sites}"
    )


def test_tolerance_is_reported_as_unapplied() -> None:
    """The tool schema accepts a tolerance SolidWorks has no setting for.

    Dropping it silently would let a caller believe a tolerance was honoured,
    so the payload carries ``tolerance_applied`` explicitly.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.io as io_module

    source = Path(io_module.__file__).read_text(encoding="utf-8")
    assert '"tolerance_applied": None' in source


class _FakeDoc:
    """Stand-in for ``IModelDoc2`` exposing the three accessors used."""

    def __init__(self, title: str, path: str, doc_type: int) -> None:
        """Store the values the fake's accessors return.

        Args:
            title: Value for ``GetTitle``.
            path: Value for ``GetPathName``.
            doc_type: Value for ``GetType`` (``swDocumentTypes_e``).
        """
        self._title = title
        self._path = path
        self._type = doc_type

    def GetTitle(self) -> str:
        """Return the document's window title."""
        return self._title

    def GetPathName(self) -> str:
        """Return the document's full path (empty when unsaved)."""
        return self._path

    def GetType(self) -> int:
        """Return the ``swDocumentTypes_e`` code for the document."""
        return self._type


class _FakeAdapter:
    """Minimal adapter surface: ``_attempt`` and ``_get_attr_or_call``."""

    @staticmethod
    def _attempt(fn, default=None):  # noqa: ANN001
        """Run ``fn`` and return ``default`` if it raises.

        Args:
            fn: Zero-argument callable to invoke.
            default: Value returned on any exception.

        Returns:
            The callable's result, or ``default``.
        """
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _get_attr_or_call(obj, name):  # noqa: ANN001
        """Return ``obj.name``, calling it when it resolves to a method.

        Args:
            obj: Object to read the attribute from.
            name: Attribute name.

        Returns:
            The attribute value, or its call result when callable.
        """
        attr = getattr(obj, name)
        return attr() if callable(attr) else attr


@pytest.mark.parametrize(
    ("raw", "expected_len"),
    [
        (None, 0),
        ("single", 1),
        (["a", "b"], 2),
        (("a", None, "b"), 2),
        ([], 0),
    ],
)
def test_coerce_dispatch_sequence(raw: object, expected_len: int) -> None:
    """None, a bare dispatch and a tuple/list all normalise to a clean list."""
    assert len(_coerce_dispatch_sequence(raw)) == expected_len


def test_describe_open_document_marks_active_by_title() -> None:
    """A title that matches the active title yields the full active summary."""
    doc = _FakeDoc("bracket.SLDPRT", r"C:\p\bracket.SLDPRT", 1)
    out = _describe_open_document(_FakeAdapter(), doc, "bracket.SLDPRT", None)
    assert out == {
        "title": "bracket.SLDPRT",
        "path": r"C:\p\bracket.SLDPRT",
        "type": "Part",
        "is_active": True,
    }


def test_describe_open_document_inactive_and_unknown_type() -> None:
    """A non-matching title is inactive; an unmapped type code is 'Unknown'."""
    doc = _FakeDoc("thing.SLDXXX", "", 99)
    out = _describe_open_document(_FakeAdapter(), doc, "other.SLDASM", None)
    assert out["is_active"] is False
    assert out["type"] == "Unknown"


def test_describe_open_document_falls_back_to_path_for_active_match() -> None:
    """With no active title, a case-insensitive path match marks the doc active."""
    doc = _FakeDoc("asm.SLDASM", r"C:\P\Asm.SLDASM", 2)
    out = _describe_open_document(_FakeAdapter(), doc, None, r"c:\p\asm.sldasm")
    assert out["is_active"] is True
    assert out["type"] == "Assembly"


class _FakeExt:
    """Minimal ``IModelDocExtension`` stand-in recording preference writes."""

    def __init__(self, readback: dict[int, int] | None = None) -> None:
        """Seed the readback map used by ``GetUserPreferenceInteger``.

        Args:
            readback: Optional starting ``{pref: value}`` map; writes update it.
        """
        self.writes: list[tuple[int, int, int]] = []
        self._readback = readback or {}

    def SetUserPreferenceInteger(self, pref: int, option: int, value: int) -> bool:
        """Record the write, update the readback map, and report success.

        Args:
            pref: ``swUserPreferenceIntegerValue_e`` slot.
            option: ``swUserPreferenceOption_e`` value.
            value: The integer to store.

        Returns:
            bool: Always ``True`` (tests override this to simulate rejection).
        """
        self.writes.append((pref, option, value))
        self._readback[pref] = value
        return True

    def GetUserPreferenceInteger(self, pref: int, option: int) -> int:
        """Return the stored value for ``pref``, or ``-1`` when unset.

        Args:
            pref: ``swUserPreferenceIntegerValue_e`` slot.
            option: ``swUserPreferenceOption_e`` value (ignored).

        Returns:
            int: The recorded value or ``-1``.
        """
        return self._readback.get(pref, -1)


class _FakeModel:
    """Stand-in for ``IModelDoc2`` with a fake ``Extension`` and rebuild count."""

    def __init__(self, ext: _FakeExt) -> None:
        """Attach the fake extension and zero the rebuild counter.

        Args:
            ext: The ``_FakeExt`` to expose as ``.Extension``.
        """
        self.Extension = ext
        self.rebuilt = 0

    def EditRebuild3(self) -> bool:
        """Count a rebuild request and report success."""
        self.rebuilt += 1
        return True

    def GraphicsRedraw2(self) -> None:
        """No-op stand-in for the graphics refresh call."""
        return None

    def SetSaveFlag(self) -> None:
        """No-op stand-in for marking the document dirty."""
        return None


class _FakeAdapter_set_units:
    """Just enough of the adapter surface for ``_apply_unit_system``."""

    @staticmethod
    def _attempt(fn, default=None):  # noqa: ANN001
        """Run ``fn`` and return ``default`` if it raises.

        Args:
            fn: Zero-argument callable to invoke.
            default: Value returned on any exception.

        Returns:
            The callable's result, or ``default``.
        """
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("mm", "mm"),
        ("MM", "mm"),
        ("millimeters", "mm"),
        (" Inch ", "in"),
        ("inches", "in"),
        ("feet", "ft"),
        ("m", "m"),
        ("centimeter", "cm"),
    ],
)
def test_normalise_unit_system_accepts_aliases(token: str, expected: str) -> None:
    """Case, whitespace and long-form aliases all map to a canonical token."""
    assert _normalise_unit_system(token) == expected


@pytest.mark.parametrize("token", ["", "furlong", "mmgs", None])
def test_normalise_unit_system_rejects_unknown(token: str) -> None:
    """Empty, unknown and preset-name tokens return ``None``."""
    assert _normalise_unit_system(token) is None


def test_apply_unit_system_preset_sets_only_the_system_slot_and_verifies() -> None:
    """A preset writes only swUnitSystem and verifies against slot 263."""
    ext = _FakeExt()
    model = _FakeModel(ext)

    out = _apply_unit_system(_FakeAdapter_set_units(), model, "in")

    # A preset (IPS = 3) sets swUnitSystem (263) only; the preset drives the
    # linear unit, so the swUnitsLinear slot (47) is left alone.
    assert (263, 0, 3) in ext.writes
    assert not any(pref == 47 for pref, _opt, _val in ext.writes)
    assert model.rebuilt == 1
    assert out["verified"] is True
    assert out["observed_unit_system"] == 3
    assert out["set_call_ok"] is True


def test_apply_unit_system_custom_sets_both_slots_for_feet() -> None:
    """``ft`` has no preset, so it writes swUnitSystem=Custom plus swUnitsLinear."""
    ext = _FakeExt()
    out = _apply_unit_system(_FakeAdapter_set_units(), _FakeModel(ext), "ft")

    # ft has no preset: swUnitSystem (263) -> Custom (4),
    # swUnitsLinear (47) -> swFEET (4)
    assert (263, 0, 4) in ext.writes
    assert (47, 0, 4) in ext.writes
    assert out["verified"] is True
    assert out["observed_length_unit"] == 4


def test_apply_unit_system_raises_when_document_keeps_its_unit_system() -> None:
    """When the readback shows the doc did not move, the helper raises."""
    # The document reports swUnitSystem 5 (MMGS) no matter what is written.
    ext = _FakeExt(readback={263: 5, 47: 0})

    def _no_op_write(pref, option, value):  # noqa: ANN001
        """Record the write but leave the readback map unchanged (SW ignored it).

        Args:
            pref: Preference slot.
            option: Option value.
            value: Value that would have been written.

        Returns:
            bool: ``False`` - SW "accepted" the call but changed nothing.
        """
        ext.writes.append((pref, option, value))
        return False

    ext.SetUserPreferenceInteger = _no_op_write  # type: ignore[method-assign]

    with pytest.raises(Exception, match="was not adopted"):
        _apply_unit_system(_FakeAdapter_set_units(), _FakeModel(ext), "in")


def test_apply_unit_system_verified_none_when_readback_unavailable() -> None:
    """When the readback itself fails, ``verified`` is ``None`` (not ``False``)."""
    ext = _FakeExt()

    def _raise(pref, option):  # noqa: ANN001
        """Raise to simulate ``GetUserPreferenceInteger`` being unavailable.

        Args:
            pref: Preference slot (unused).
            option: Option value (unused).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("no readback")

    ext.GetUserPreferenceInteger = _raise  # type: ignore[method-assign]

    out = _apply_unit_system(_FakeAdapter_set_units(), _FakeModel(ext), "cm")
    assert out["verified"] is None


def test_payload_helper_accepts_dicts_models_and_none() -> None:
    """Tools hand the adapter dicts; direct callers may hand it a model."""
    from solidworks_mcp.adapters.solidworks.io import _first, _payload

    class _Model:
        def __init__(self) -> None:
            self.model_path = "C:/parts/a.sldprt"

        def model_dump(self) -> dict[str, str]:
            return {"model_path": self.model_path}

    assert _payload(None) == {}
    assert _payload({"a": 1}) == {"a": 1}
    assert _payload(_Model())["model_path"] == "C:/parts/a.sldprt"

    # model_file and model_path are the same thing on different schemas.
    assert _first({"model_file": "x"}, "model_path", "model_file") == "x"
    assert _first({}, "model_path", default="fallback") == "fallback"
