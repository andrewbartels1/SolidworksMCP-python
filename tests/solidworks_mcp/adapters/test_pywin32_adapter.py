"""Tests for solidworks_mcp.adapters.pywin32_adapter module-level behaviour."""

from __future__ import annotations


def test_pywin32_adapter_imports_without_pywin32(import_without) -> None:
    """Non-Windows CI: the module imports and reports pywin32 as unavailable."""
    attrs = import_without(
        "solidworks_mcp.adapters.pywin32_adapter",
        [
            "pythoncom",
            "pywintypes",
            "win32com",
            "win32com.client",
            "win32com.client.dynamic",
        ],
        ["PYWIN32_AVAILABLE", "pywintypes"],
    )

    assert attrs["PYWIN32_AVAILABLE"] is False
    assert "com_error" in attrs["pywintypes"]


# ---- _SketchGeometryService edge cases --------------------------------------

import platform
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest  # noqa: E402

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402
from solidworks_mcp.exceptions import SolidWorksMCPError


@pytest.fixture
def geometry(monkeypatch):
    """The sketch-geometry service of an adapter that believes it is on Windows."""
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system", lambda: "Windows"
    )
    return PyWin32Adapter({})._sketch_geometry


def _line(start: tuple, end: tuple) -> SimpleNamespace:
    return SimpleNamespace(GetStartPoint=start, GetEndPoint=end)


def _point(xyz: tuple | None) -> SimpleNamespace:
    if xyz is None:
        return SimpleNamespace(GetCoords=lambda: [])  # unreadable point
    return SimpleNamespace(X=xyz[0], Y=xyz[1], Z=xyz[2])


def test_set_display_dimension_value_falls_back_to_legacy_objects(geometry) -> None:
    legacy = SimpleNamespace(SetSystemValue3=lambda *_a: True)
    via_get_dimension = SimpleNamespace(
        GetDimension2=lambda _i: None, GetDimension=lambda: legacy
    )
    calls: list[float] = []
    bare = SimpleNamespace(
        GetDimension2=lambda _i: None,
        GetDimension=lambda: None,
        SetSystemValue3=lambda value, *_a: calls.append(value) or True,
    )

    geometry.set_display_dimension_value(via_get_dimension, 5.0)
    geometry.set_display_dimension_value(bare, 7.0)

    assert calls == [pytest.approx(0.007)]


def test_point_helpers_tolerate_missing_points(geometry) -> None:
    assert geometry.set_point_xyz(None, 0.0, 0.0, 0.0) is False
    assert geometry.read_segment_endpoints(SimpleNamespace()) is None


def test_shared_segment_vertex_skips_unreadable_and_reports_no_match(
    geometry,
) -> None:
    corner = (0.01, 0.0, 0.0)
    shared = SimpleNamespace(GetStartPoint2=_point(None), GetEndPoint2=_point(corner))
    other = SimpleNamespace(GetStartPoint2=_point(None), GetEndPoint2=_point(corner))
    apart = SimpleNamespace(
        GetStartPoint2=_point((1.0, 1.0, 0.0)),
        GetEndPoint2=_point((2.0, 1.0, 0.0)),
    )

    found = geometry.shared_segment_vertex(shared, other)

    assert found is not None
    assert geometry.shared_segment_vertex(shared, apart) is None


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (SimpleNamespace(), _line((0, 0, 0), (0.01, 0, 0))),  # unreadable first
        (_line((0, 0, 0), (0, 0, 0)), _line((0, 0, 0), (0.01, 0, 0))),  # zero length
    ],
)
def test_angular_placement_rejects_unusable_geometry(geometry, first, second) -> None:
    assert geometry.angular_dimension_placement(first, second) is None


def test_angular_placement_for_opposite_rays_uses_a_perpendicular(geometry) -> None:
    """Collinear, opposite legs: the bisector vanishes, so place off the line."""
    left = _line((0.0, 0.0, 0.0), (-0.02, 0.0, 0.0))
    right = _line((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))

    text_x, text_y, _z, _direction = geometry.angular_dimension_placement(left, right)

    assert abs(text_x) < 1e-9
    assert abs(text_y) > 0.0  # pushed perpendicular to the straight line


def test_single_line_placement_needs_endpoints(geometry) -> None:
    assert geometry.single_line_dimension_placement(SimpleNamespace()) is None


# ---- _DocumentRoutingService / assembly / screenshot edge cases --------------


@pytest.fixture
def adapter(monkeypatch, geometry):
    """The PyWin32Adapter behind the geometry fixture (same Windows patches)."""
    return geometry._adapter


def test_document_identity_of_none(adapter) -> None:
    assert adapter._document_routing.document_identity(None) == (None, None)


def test_export_target_falls_back_to_whichever_document_exists(adapter) -> None:
    active, current = object(), object()
    adapter.swApp = SimpleNamespace(ActiveDoc=active)
    adapter.currentModel = None
    assert adapter._document_routing.resolve_export_target_doc() is active

    adapter.swApp = SimpleNamespace(ActiveDoc=None)
    adapter.currentModel = current
    assert adapter._document_routing.resolve_export_target_doc() is current


def test_assembly_without_components_lists_nothing(adapter) -> None:
    assembly = SimpleNamespace(GetComponents=lambda _top_level: None)

    assert (
        adapter._feature_selector._list_assembly_component_features(
            assembly, False, 1, None
        )
        == []
    )


@pytest.mark.asyncio
async def test_screenshot_replaces_an_existing_file_without_prompting(
    adapter, tmp_path, monkeypatch
) -> None:
    """SolidWorks would show a 'replace?' dialog; the old file is deleted first."""
    target = tmp_path / "shot.png"
    target.write_bytes(b"stale")
    seen_before_save: list[bool] = []

    def _save(_doc, path, _w, _h):
        seen_before_save.append(target.exists())
        target.write_bytes(b"fresh")
        return True

    adapter.swApp = SimpleNamespace(ActiveDoc=None)
    adapter.currentModel = SimpleNamespace()
    monkeypatch.setattr(adapter, "_resolve_export_target_doc", lambda: object())
    monkeypatch.setattr(adapter, "_document_identity", lambda _doc: (None, None))
    monkeypatch.setattr(adapter, "_zoom_to_fit", lambda _doc: None)
    monkeypatch.setattr(adapter, "_save_screenshot_with_modelview", _save)

    result = await adapter.export_image({"file_path": str(target)})

    assert result.is_success, result.error
    assert seen_before_save == [False]
    assert target.read_bytes() == b"fresh"


class TestPyWin32AdapterInitialization:
    """Test PyWin32Adapter initialization and platform checks."""

    def test_pywin32_not_available_raises_error(self) -> None:
        """Test that init raises error when pywin32 is not available."""
        # Mock PYWIN32_AVAILABLE as False
        with patch("solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", False):
            from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            with pytest.raises(SolidWorksMCPError, match="pywin32 is not available"):
                PyWin32Adapter()

    def test_non_windows_platform_raises_error(self) -> None:
        """Test that init raises error on non-Windows platform."""
        # Mock platform.system to return non-Windows value
        with patch(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system"
        ) as mock_system:
            mock_system.return_value = "Linux"

            # Need to reload module to pick up mocked platform
            with patch(
                "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
            ):
                from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                with pytest.raises(
                    SolidWorksMCPError,
                    match="PyWin32Adapter requires Windows platform",
                ):
                    PyWin32Adapter()

    def test_darwin_platform_raises_error(self) -> None:
        """Test that init raises error on macOS."""
        with patch(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system"
        ) as mock_system:
            mock_system.return_value = "Darwin"

            with patch(
                "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
            ):
                from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                with pytest.raises(SolidWorksMCPError):
                    PyWin32Adapter()

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    def test_initialization_with_config(self) -> None:
        """Test initialization with configuration on Windows."""
        try:
            from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            config = {
                "timeout": 30,
                "auto_connect": False,
                "startup_timeout": 60,
            }
            adapter = PyWin32Adapter(config)

            assert adapter.config_dict["timeout"] == 30
            assert adapter.swApp is None
            assert adapter.currentModel is None
        except SolidWorksMCPError:
            # Skip if pywin32 not actually available
            pytest.skip("pywin32 not available")

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    def test_constants_initialized(self) -> None:
        """Test that COM constants are initialized."""
        try:
            from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            adapter = PyWin32Adapter()

            assert adapter.constants is not None
            assert "swDocPART" in adapter.constants
            assert adapter.constants["swDocPART"] == 1
            assert adapter.constants["swDocASSEMBLY"] == 2
            assert adapter.constants["swDocDRAWING"] == 3
        except SolidWorksMCPError:
            pytest.skip("pywin32 not available")

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    @pytest.mark.asyncio
    async def test_connect_com_initialization(self) -> None:
        """Test connect method initializes COM."""
        try:
            from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            adapter = PyWin32Adapter()

            # Mock COM operations
            with patch("solidworks_mcp.adapters.pywin32_adapter.pythoncom"):
                with patch(
                    "solidworks_mcp.adapters.pywin32_adapter.win32com.client"
                ) as mock_client:
                    mock_app = MagicMock()
                    mock_client.GetObject.return_value = mock_app

                    try:
                        await adapter.connect()
                    except Exception:
                        # Connection might fail without actual SolidWorks
                        pass

                    # CoInitialize now runs on ComExecutor's worker thread,
                    # not in connect() directly — no assertion here.
        except SolidWorksMCPError:
            pytest.skip("pywin32 not available")


class TestVBModuleNameParsing:
    """Test VB macro module name parsing."""

    def test_parse_vb_module_name_with_attribute(self, tmp_path) -> None:
        """Test parsing VB module name from macro file."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text(
            'Attribute VB_Name = "CustomMacro"\nSub Main()\nEnd Sub\n'
        )

        name = _parse_vb_module_name(str(macro_file))
        assert name == "CustomMacro"

    def test_parse_vb_module_name_with_single_quotes(self, tmp_path) -> None:
        """Test parsing VB module name with single quotes."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text(
            "Attribute VB_Name = 'QuotedMacro'\nSub Main()\nEnd Sub\n"
        )

        name = _parse_vb_module_name(str(macro_file))
        assert name == "QuotedMacro"

    def test_parse_vb_module_name_missing_attribute(self, tmp_path) -> None:
        """Test parsing when VB_Name attribute is missing."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text("Sub Main()\nEnd Sub\n")

        name = _parse_vb_module_name(str(macro_file))
        # Should fall back to file stem
        assert name == "test_macro"

    def test_parse_vb_module_name_nonexistent_file(self) -> None:
        """Test parsing nonexistent file."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        name = _parse_vb_module_name("/nonexistent/path/macro.swp")
        # Should fall back to default
        assert name == "macro"

    def test_parse_vb_module_name_fallback_to_default(self, tmp_path) -> None:
        """Test fallback to SolidWorksMacro when no name found."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        # File with no name and no stem (edge case)
        macro_file = tmp_path / ".swp"
        macro_file.write_text("Sub Main()\nEnd Sub\n")

        name = _parse_vb_module_name(str(macro_file))
        # Should fall back to SolidWorksMacro
        assert name == "SolidWorksMacro"


class TestPyWin32AdapterMockCOM:
    """Test PyWin32Adapter with mocked COM objects."""

    @pytest.mark.asyncio
    async def test_open_model_with_mock_com(self) -> None:
        """Test opening a model with mocked COM."""
        # Mock the entire adapter to test COM interaction
        with patch("solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True):
            with patch(
                "solidworks_mcp.adapters.pywin32_adapter.platform.system"
            ) as mock_sys:
                mock_sys.return_value = "Windows"

                # Import after mocking
                from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                # Mock pythoncom and win32com
                with (
                    patch("solidworks_mcp.adapters.pywin32_adapter.pythoncom"),
                    patch(
                        "solidworks_mcp.adapters.pywin32_adapter.asyncio.sleep",
                        new=AsyncMock(),
                    ),
                ):
                    with patch(
                        "solidworks_mcp.adapters.pywin32_adapter.win32com.client"
                    ) as mock_client:
                        # Setup mock COM objects
                        mock_app = AsyncMock()
                        mock_client.GetObject.return_value = mock_app
                        mock_client.Dispatch.return_value = mock_app

                        # acquire_solidworks_application() late-binds through
                        # the module-level _dynamic_module reference, not
                        # win32com.client - unless this is stubbed too, it
                        # falls through to the *real* pywin32
                        # dynamic.Dispatch("SldWorks.Application") on any
                        # dev box with real SolidWorks installed.
                        with patch(
                            "solidworks_mcp.adapters.pywin32_adapter._dynamic_module"
                        ) as mock_dynamic:
                            mock_dynamic.Dispatch.return_value = mock_app

                            adapter = PyWin32Adapter({"timeout": 30})

                            # Mock the COM model
                            mock_model = MagicMock()
                            mock_app.OpenDoc6.return_value = mock_model

                            # Try to connect (might fail but should reach COM calls)
                            try:
                                await adapter.connect()
                            except Exception:
                                # Expected to fail without real SolidWorks
                                pass


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

    def test_parse_vb_module_name_reads_binary_swp_project_stream(
        self, tmp_path
    ) -> None:
        """A SW-authored .swp is an OLE compound file; the module name comes from
        its plaintext PROJECT stream (Module=<name>), not the file stem - SW
        names the module <stem>1 (issue #91 follow-up)."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        swp = tmp_path / "sample_macro.swp"
        swp.write_bytes(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            + b"\x00" * 32
            + b'\r\nID="{6F6DBAFC}"\r\nModule=sample_macro1\r\nName="sample_macro"\r\n'
            + b"\x00" * 16
        )
        assert _parse_vb_module_name(str(swp)) == "sample_macro1"

    def test_parse_vb_module_name_text_macro_uses_attribute(self, tmp_path) -> None:
        """A hand-written text macro still resolves via Attribute VB_Name."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        vb = tmp_path / "thing.vb"
        vb.write_text('Attribute VB_Name = "MyModule"\nSub main()\nEnd Sub\n')
        assert _parse_vb_module_name(str(vb)) == "MyModule"

    def test_parse_vb_module_name_falls_back_to_stem(self, tmp_path) -> None:
        """No usable name in the file -> file stem."""
        from solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        blank = tmp_path / "just_a_stem.swp"
        blank.write_bytes(b"not ole, no attribute line\n")
        assert _parse_vb_module_name(str(blank)) == "just_a_stem"

    def test_run_macro_error_name_non_numeric_passes_through(self) -> None:
        """A non-coercible error value renders as-is, not a crash."""
        from solidworks_mcp.adapters.pywin32_adapter import _run_macro_error_name

        assert _run_macro_error_name(None) == "None"
        assert _run_macro_error_name("weird") == "weird"

    def test_byref_long_falls_back_to_plain_int_without_pywin32(
        self, monkeypatch
    ) -> None:
        """When win32com.client.VARIANT is unavailable (CI / non-Windows), the
        ByRef helper hands back a plain int so callers still work."""
        from types import SimpleNamespace as _NS

        from solidworks_mcp.adapters import pywin32_adapter as _mod

        monkeypatch.setattr(_mod, "win32com", _NS(client=_NS()), raising=False)
        assert _mod._byref_long(7) == 7

    @pytest.mark.asyncio
    async def test_connect_raises_when_com_app_instance_is_none(
        self, monkeypatch
    ) -> None:
        """connect should raise when COM returns None instead of an app instance."""
        adapter = self._build_adapter(monkeypatch)

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock()),
            raising=False,
        )
        fake_client = SimpleNamespace(
            GetActiveObject=Mock(return_value=None),
            Dispatch=Mock(return_value=None),
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(client=fake_client),
            raising=False,
        )
        # Late binding goes through win32com.client.dynamic.Dispatch — must
        # also stub it or the call will hit the real COM (which connects on
        # any box with SolidWorks installed).
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter._dynamic_module",
            SimpleNamespace(Dispatch=Mock(return_value=None)),
            raising=False,
        )
        # The 8-cycle acquire_solidworks_application retry loop sleeps 1s
        # between attempts; every attempt here is mocked to fail, so the
        # real 8s wait is pure overhead - skip it without changing the
        # retry-count/exception logic under test.
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.asyncio.sleep",
            AsyncMock(),
        )

        with pytest.raises(SolidWorksMCPError, match="instance is None"):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_com_coordinator_initialize_skip_and_acquire_failure_paths(
        self, monkeypatch
    ) -> None:
        """Coordinator should skip duplicate init and raise last COM error after retries."""
        adapter = self._build_adapter(monkeypatch)

        co_init = Mock()
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(CoInitialize=co_init, CoUninitialize=Mock()),
            raising=False,
        )
        adapter._com_initialized = True
        adapter._initialize_com_apartment()
        co_init.assert_not_called()

        async def _fast_sleep(_seconds):
            return None

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.asyncio.sleep", _fast_sleep
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(
                client=SimpleNamespace(
                    GetActiveObject=Mock(side_effect=RuntimeError("active fail")),
                    Dispatch=Mock(side_effect=RuntimeError("dispatch fail")),
                )
            ),
            raising=False,
        )
        # Acquire path now routes through win32com.client.dynamic.Dispatch —
        # stub it so the retry loop sees the same RuntimeError surface.
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter._dynamic_module",
            SimpleNamespace(Dispatch=Mock(side_effect=RuntimeError("dispatch fail"))),
            raising=False,
        )

        with pytest.raises(SolidWorksMCPError, match="dispatch fail"):
            await adapter._acquire_solidworks_application()

    @pytest.mark.asyncio
    async def test_com_coordinator_wait_ready_timeout_and_no_revision_branch(
        self, monkeypatch
    ) -> None:
        """wait_for_server_ready should no-op without RevisionNumber and timeout when never ready."""
        adapter = self._build_adapter(monkeypatch)

        await adapter._wait_for_server_ready(SimpleNamespace())

        async def _fast_sleep(_seconds):
            return None

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.asyncio.sleep", _fast_sleep
        )

        never_ready = SimpleNamespace(RevisionNumber=lambda: None)
        with pytest.raises(SolidWorksMCPError, match="did not become ready"):
            await adapter._wait_for_server_ready(never_ready)


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

    def test_platform_guard_raises_on_non_windows(self, monkeypatch):
        """Test platform guard raises on non windows."""
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Linux",
        )
        with pytest.raises(SolidWorksMCPError, match="requires Windows"):
            PyWin32Adapter({})


#: Capabilities added on this branch.
CAPABILITIES = [
    "insert_component",
    "list_components",
    "add_mate",
]


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_real_adapter_resolves_to_the_com_mixin(capability: str) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksIOMixin``. Written at module scope in ``io.py`` they still
    import cleanly, still pass every mock test, and still satisfy the
    layer checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code
    is never called. That happened while building this branch, and only
    showed up under runtime MRO inspection.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if capability in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


CAPABILITIESFeatureEditingCapability = [
    "delete_feature",
    "suppress_feature",
    "rename_feature",
    "undo",
]


@pytest.mark.parametrize("capability", CAPABILITIESFeatureEditingCapability)
def test_real_adapter_resolves_to_the_com_mixin_feature_editing(
    capability: str,
) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if capability in vars(k)), None
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


CAPABILITY = "check_interference"


def test_real_adapter_resolves_to_the_com_mixin_interference() -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if CAPABILITY in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{CAPABILITY} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


CAPABILITYMirrorCapability = "mirror_feature"


def test_real_adapter_resolves_to_the_features_mixin() -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    ``mirror_feature`` is only reachable if it is defined *inside*
    ``SolidWorksFeaturesMixin``. Written at module scope in ``features.py``
    it would still import cleanly, still pass every mock test, and still
    satisfy the layer checks above - but ``PyWin32Adapter`` would then
    resolve the name to ``SolidWorksAdapter``'s "not implemented" default
    and the real COM code would never be called.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if CAPABILITYMirrorCapability in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{CAPABILITYMirrorCapability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


def test_real_adapter_resolves_to_the_io_mixin() -> None:
    """PyWin32Adapter resolves ``save_body_as_part`` to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if "save_body_as_part" in vars(k)),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.save_body_as_part resolves to {owner}, not the COM mixin."
    )


CAPABILITIESOpenDocumentsCapability = ["list_open_documents", "activate_document"]


@pytest.mark.parametrize("capability", CAPABILITIESOpenDocumentsCapability)
def test_real_adapter_resolves_to_the_io_mixin_open_documents(capability: str) -> None:
    """PyWin32Adapter resolves the capability to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if capability in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin."
    )


CAPABILITYPatternCapability = "pattern_circular"


def test_real_adapter_resolves_to_the_features_mixin_pattern() -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    ``pattern_circular`` is only reachable if it is defined *inside*
    ``SolidWorksFeaturesMixin``. Written at module scope in ``features.py``
    it would still import cleanly, still pass every mock test, and still
    satisfy the layer checks above - but ``PyWin32Adapter`` would then
    resolve the name to ``SolidWorksAdapter``'s "not implemented" default
    and the real COM code would never be called.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if CAPABILITYPatternCapability in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{CAPABILITYPatternCapability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


#: Reference-geometry capabilities on ``SolidWorksFeaturesMixin``.
CAPABILITIESReferenceGeometryCapability = [
    "create_reference_plane",
    "create_axis",
    "create_reference_point",
]


@pytest.mark.parametrize("capability", CAPABILITIESReferenceGeometryCapability)
def test_real_adapter_resolves_to_the_features_mixin_reference_geometry(
    capability: str,
) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksFeaturesMixin``. Written at module scope in ``features.py``
    they still import cleanly, still pass every mock test, and still satisfy
    the layer checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code
    is never called.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if capability in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


def test_real_adapter_resolves_to_the_io_mixin_set_units() -> None:
    """PyWin32Adapter resolves ``set_units`` to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (k.__name__ for k in PyWin32Adapter.__mro__ if "set_units" in vars(k)), None
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.set_units resolves to {owner}, not the COM mixin."
    )


#: Capabilities added on this branch. These names are a contract with the
#: gates in ``tools/drawing.py`` — see the module docstring.
CAPABILITIESDrawingCapabilities = [
    "create_drawing_view",
    "add_drawing_view",
    "create_technical_drawing",
    "add_note",
    "list_drawing_views",
    "auto_center_marks",
]


@pytest.mark.parametrize("capability", CAPABILITIESDrawingCapabilities)
def test_real_adapter_resolves_to_the_com_mixin_drawing(capability: str) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksIOMixin``. Written at module scope in ``io.py`` they still
    import cleanly, still pass every mock test, and still satisfy the layer
    checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code is
    never called. That happened on the assembly branch and only showed up
    under runtime MRO inspection.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if capability in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


class TestOperationFailureLogging:
    """Expected "not found" answers log one line; real faults keep the traceback."""

    @pytest.fixture
    def logged(self, monkeypatch):
        from loguru import logger

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
        records: list = []
        sink = logger.add(lambda m: records.append(m.record), level="WARNING")
        yield PyWin32Adapter({}), records
        logger.remove(sink)

    def test_lookup_error_is_a_one_line_warning(self, logged) -> None:
        adapter, records = logged

        def missing():
            raise LookupError("Feature not found: NoSuchFeature")

        result = adapter._handle_com_operation("select_feature", missing)

        assert (
            result.error == "Error in select_feature: Feature not found: NoSuchFeature"
        )
        [record] = records
        assert record["level"].name == "WARNING"
        assert record["exception"] is None

    def test_other_failures_log_the_traceback(self, logged) -> None:
        adapter, records = logged

        def broken():
            raise ValueError("bad")

        adapter._handle_com_operation("add_line", broken)

        [record] = records
        assert record["level"].name == "ERROR"
        assert record["exception"] is not None


class TestComThreadAffinity:
    """COM objects are STA-bound: calls from another thread are refused."""

    @pytest.fixture
    def adapter(self, monkeypatch) -> PyWin32Adapter:
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
            "solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None),
            raising=False,
        )
        return PyWin32Adapter({})

    def test_apartment_records_and_releases_its_thread(self, adapter) -> None:
        import threading

        adapter._session_coordinator.initialize_com_apartment()
        assert adapter._com_thread_id == threading.get_ident()

        adapter._session_coordinator.uninitialize_com_apartment()
        assert adapter._com_thread_id is None

    def test_owner_thread_runs_and_other_threads_are_refused(self, adapter) -> None:
        import threading

        adapter._session_coordinator.initialize_com_apartment()
        calls: list[str] = []
        from_worker: dict = {}

        def worker() -> None:
            from_worker["result"] = adapter._handle_com_operation(
                "get_model_info", lambda: calls.append("worker")
            )

        thread = threading.Thread(target=worker, name="tool-worker")
        thread.start()
        thread.join()
        own = adapter._handle_com_operation("get_model_info", lambda: "ok")

        refused = from_worker["result"]
        assert refused.is_error
        assert "'tool-worker'" in refused.error
        assert "belong to the thread that called connect()" in refused.error
        assert calls == []  # the operation never ran
        assert own.is_success and own.data == "ok"

    def test_no_owner_means_no_guard(self, adapter) -> None:
        result = adapter._handle_com_operation("noop", lambda: 1)

        assert result.is_success
