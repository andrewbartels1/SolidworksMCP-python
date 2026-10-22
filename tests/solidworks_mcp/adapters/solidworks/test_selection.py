"""Tests for the SolidWorksSelectionMixin."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

import solidworks_mcp.adapters.pywin32_adapter as pywin32_mod
from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks.selection import SolidWorksSelectionMixin
from solidworks_mcp.exceptions import SolidWorksMCPError


class _SelectionHarness(SolidWorksSelectionMixin):
    """Minimal harness to exercise the mixin methods."""

    def __init__(self, *, has_model: bool, swApp: object | None = None) -> None:
        self.currentModel = object() if has_model else None
        self.swApp = swApp
        self._feature_selector = SimpleNamespace(
            list_features=lambda _include, _depth=2: [{"name": "Feat1"}],
            select_feature=lambda name, _append=False: {"selected": name != "Missing"},
        )

    def _handle_com_operation(self, name, operation, *args):
        try:
            data = operation(*args)
        except Exception as e:  # mirror PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default


@pytest.mark.asyncio
async def test_list_features_requires_active_model() -> None:
    """list_features should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.list_features()
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_select_feature_requires_active_model() -> None:
    """select_feature should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.select_feature("Feat1")
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_list_and_select_feature_success() -> None:
    """list_features/select_feature should call the selector when model exists."""
    # Exercise the success path when currentModel is set.
    harness = _SelectionHarness(has_model=True)
    list_result = await harness.list_features()
    select_result = await harness.select_feature("Feat1")
    assert list_result.is_success
    assert list_result.data == [{"name": "Feat1"}]
    assert select_result.is_success
    assert select_result.data == {"selected": True, "selection_count": None}


@pytest.mark.asyncio
async def test_select_feature_unselected_is_an_error() -> None:
    """A payload with selected=False becomes an ERROR naming the feature (#106)."""
    harness = _SelectionHarness(has_model=True)
    result = await harness.select_feature("Missing")
    assert result.status == AdapterResultStatus.ERROR
    assert result.error == "Feature not found or could not be selected: Missing"


class _FakeFace:
    """Stand-in for IFace2 covering the fields get_selected_entities reads."""

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802 - matches pywin32's API
        pass

    def GetBox(self):
        # (xmin, ymin, zmin, xmax, ymax, zmax) in meters
        return (0.0, 0.0, 0.0, 0.03, 0.03, 0.0)

    def GetArea(self):
        return 0.0009  # m^2 -> 900 mm^2

    @property
    def Normal(self):
        return (0.0, 0.0, 1.0)


class _FakeVertex:
    def __init__(self, point):
        self._point = point

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetPoint(self):
        return self._point


class _FakeEdge:
    """Stand-in for IEdge covering the fields get_selected_entities reads."""

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetStartVertex(self):
        return _FakeVertex((0.0, 0.0, -0.015))

    def GetEndVertex(self):
        return _FakeVertex((0.03, 0.0, -0.015))


class _FakeSelectionManager:
    def __init__(self, objects: list[tuple[int, object]]) -> None:
        self._objects = objects

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetSelectedObjectCount2(self, _mark):
        return len(self._objects)

    def GetSelectedObjectType3(self, index, _mark):
        return self._objects[index - 1][0]

    def GetSelectedObject6(self, index, _mark):
        return self._objects[index - 1][1]


@pytest.mark.asyncio
async def test_get_selected_entities_requires_active_model() -> None:
    """get_selected_entities should error when no model is active and swApp has no ActiveDoc."""
    harness = _SelectionHarness(has_model=False, swApp=None)
    result = await harness.get_selected_entities()
    assert result.status == AdapterResultStatus.ERROR
    assert "No active model" in (result.error or "")


@pytest.mark.asyncio
async def test_get_selected_entities_describes_face_and_edge() -> None:
    """A selected FACE and EDGE should each be described with their own fields."""
    sel_mgr = _FakeSelectionManager(
        [(2, _FakeFace()), (1, _FakeEdge())]  # FACE=2, EDGE=1 (confirmed live)
    )
    model = SimpleNamespace(SelectionManager=sel_mgr)
    harness = _SelectionHarness(has_model=True)
    harness.currentModel = model
    harness.swApp = SimpleNamespace(ActiveDoc=None)

    result = await harness.get_selected_entities()

    assert result.is_success
    entities = result.data
    assert len(entities) == 2

    face = entities[0]
    assert face["type"] == "FACE"
    assert face["center_mm"] == [15.0, 15.0, 0.0]
    assert face["area_mm2"] == pytest.approx(900.0)
    assert face["normal"] == [0.0, 0.0, 1.0]

    edge = entities[1]
    assert edge["type"] == "EDGE"
    assert edge["start_mm"] == [0.0, 0.0, -15.0]
    assert edge["end_mm"] == [30.0, 0.0, -15.0]
    assert edge["length_mm"] == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_get_selected_entities_refreshes_current_model_from_active_doc() -> None:
    """The live UI selection lives on swApp.ActiveDoc, which may differ from
    whatever this adapter instance last tracked as currentModel -- the
    method must prefer ActiveDoc, mirroring list_features's behavior."""
    sel_mgr = _FakeSelectionManager([])
    active_doc = SimpleNamespace(SelectionManager=sel_mgr)
    harness = _SelectionHarness(has_model=True)
    harness.swApp = SimpleNamespace(ActiveDoc=active_doc)

    result = await harness.get_selected_entities()

    assert result.is_success
    assert result.data == []
    assert harness.currentModel is active_doc


@pytest.mark.asyncio
async def test_get_selected_entities_describes_vertices_and_skips_unreadable() -> None:
    """A selected VERTEX reports its point in mm; an unreadable entry is skipped."""
    sel_mgr = _FakeSelectionManager(
        [(2, None), (3, _FakeVertex((0.01, 0.02, 0.03))), (3, _FakeVertex(None))]
    )
    harness = _SelectionHarness(has_model=True)
    harness.currentModel = SimpleNamespace(SelectionManager=sel_mgr)
    harness.swApp = SimpleNamespace(ActiveDoc=None)

    result = await harness.get_selected_entities()

    assert result.is_success
    first, second = result.data
    assert first == {"index": 2, "type": "VERTEX", "point_mm": [10.0, 20.0, 30.0]}
    assert second == {"index": 3, "type": "VERTEX"}  # no point -> no point_mm


def test_pywin32_adapter_guard_and_helpers(monkeypatch):
    """Test pywin32 adapter guard and helpers."""

    class _ConcretePyWin32Adapter(PyWin32Adapter):
        """Test suite for ConcretePyWin32Adapter."""

        async def exit_sketch(self):
            """Test helper for exit sketch."""
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", False)
    with pytest.raises(SolidWorksMCPError):
        _ConcretePyWin32Adapter({})

    monkeypatch.setattr(pywin32_mod, "PYWIN32_AVAILABLE", True)
    monkeypatch.setattr(pywin32_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        pywin32_mod,
        "pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )

    adapter = _ConcretePyWin32Adapter({})
    # Synchronous mock ComExecutor so _handle_com_operation doesn't short-circuit.
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    mock_com = MagicMock()
    mock_com._thread = mock_thread
    mock_com.run = lambda fn, timeout=None: fn()
    adapter._com = mock_com

    adapter.currentModel = SimpleNamespace(GetType=lambda: 3)
    assert adapter._get_document_type() == "Drawing"

    ok = adapter._handle_com_operation("simple", lambda: "done")
    assert ok.is_success
    assert ok.data == "done"

    err = adapter._handle_com_operation(
        "simple", lambda: (_ for _ in ()).throw(ValueError("x"))
    )
    assert err.is_error
    assert "Error in simple" in (err.error or "")


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
    async def test_list_features_prefers_tree_traversal(self, monkeypatch):
        """List features should traverse FirstFeature/GetNextFeature when available."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, feature_type, suppressed=False):
                """Test helper for init."""
                self.Name = name
                self._feature_type = feature_type
                self._suppressed = suppressed
                self._next = None

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return self._feature_type

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                return self._suppressed

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return self._next

        f1 = _Feature("Front Plane", "RefPlane", False)
        f2 = _Feature("Boss-Extrude1", "Boss", False)
        f3 = _Feature("Cut-Extrude1", "Cut", True)
        f1._next = f2
        f2._next = f3

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: f1,
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        )

        result = await adapter.list_features(include_suppressed=False)

        assert result.is_success
        assert [row["name"] for row in result.data] == ["Front Plane", "Boss-Extrude1"]

    @pytest.mark.asyncio
    async def test_list_features_falls_back_to_reverse_positions(self, monkeypatch):
        """List features should fall back to model FeatureByPositionReverse when needed."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, feature_type):
                """Test helper for init."""
                self.Name = name
                self._feature_type = feature_type

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return self._feature_type

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                return False

        # FeatureByPositionReverse is zero-based: position 0 is the newest
        # feature (Boss-Extrude1), position 1 is the next-oldest (Sketch1).
        by_pos = {
            0: _Feature("Boss-Extrude1", "Boss"),
            1: _Feature("Sketch1", "ProfileFeature"),
        }

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: (_ for _ in ()).throw(RuntimeError("not available")),
            FeatureByPositionReverse=lambda pos: by_pos.get(pos),
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 2),
        )

        result = await adapter.list_features(include_suppressed=False)

        assert result.is_success
        assert [row["name"] for row in result.data] == ["Boss-Extrude1", "Sketch1"]

    @pytest.mark.asyncio
    async def test_list_features_suppressed_fallback_uses_is_suppressed2(
        self, monkeypatch
    ):
        """When IsSuppressed is unavailable, list_features should fallback to IsSuppressed2."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            Name = "SuppressedCut"

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return "Cut"

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("IsSuppressed unavailable")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                return (True,)

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return None

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: _Feature(),
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        )

        hidden = await adapter.list_features(include_suppressed=False)
        shown = await adapter.list_features(include_suppressed=True)

        assert hidden.is_success
        assert hidden.data == []
        assert shown.is_success
        assert len(shown.data) == 1
        assert shown.data[0]["suppressed"] is True

    @pytest.mark.asyncio
    async def test_list_features_additional_fallback_branches(self, monkeypatch):
        """Cover list_features branches for nested suppression failures, dedupe, and reverse traversal errors."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name: str, next_feature=None):
                """Test helper for init."""
                self.Name = name
                self._next = next_feature

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("primary suppression unavailable")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                raise RuntimeError("secondary suppression unavailable")

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return "Boss"

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return self._next

        duplicate_1 = _Feature("Dup")
        duplicate_2 = _Feature("Dup")
        duplicate_1._next = duplicate_2
        duplicate_2._next = None

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: duplicate_1,
            FeatureManager=SimpleNamespace(
                GetFeatureCount=Mock(side_effect=RuntimeError("count unavailable"))
            ),
            FeatureByPositionReverse=Mock(side_effect=RuntimeError("reverse fail")),
        )

        listed = await adapter.list_features(include_suppressed=True)
        assert listed.is_success
        assert len(listed.data) == 1  # dedupe branch
        assert listed.data[0]["suppressed"] is False

        # Cover _append_feature early return when reverse traversal yields None.
        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: None,
            FeatureManager=SimpleNamespace(GetFeatureCount=Mock(return_value=1)),
            FeatureByPositionReverse=Mock(return_value=None),
        )
        none_feature = await adapter.list_features(include_suppressed=True)
        assert none_feature.is_success
        assert none_feature.data == []

    def test_normalize_feature_name_strips_quotes_and_casefolds(
        self, monkeypatch
    ) -> None:
        """_normalize_feature_name strips whitespace, quotes, and casefolds."""
        adapter = self._build_adapter(monkeypatch)
        assert adapter._normalize_feature_name('"Boss-Extrude"') == "boss-extrude"
        assert adapter._normalize_feature_name(None) == ""
        assert adapter._normalize_feature_name("  SKETCH1  ") == "sketch1"

    def test_build_feature_candidate_names_with_extension(self, monkeypatch) -> None:
        """_build_feature_candidate_names returns bare + @stem + @title when GetTitle has extension."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(GetTitle=Mock(return_value="MyPart.SLDPRT"))
        result = adapter._build_feature_candidate_names("Boss", target_doc)
        assert result == ["Boss", "Boss@MyPart", "Boss@MyPart.SLDPRT"]

    def test_build_feature_candidate_names_no_extension(self, monkeypatch) -> None:
        """_build_feature_candidate_names omits duplicate when title == stem."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(GetTitle=Mock(return_value="MyPart"))
        result = adapter._build_feature_candidate_names("Boss", target_doc)
        assert result == ["Boss", "Boss@MyPart"]

    def test_build_feature_candidate_names_get_title_raises(self, monkeypatch) -> None:
        """_build_feature_candidate_names falls back to bare name when GetTitle raises."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(GetTitle=Mock(side_effect=RuntimeError("COM")))
        result = adapter._build_feature_candidate_names("Boss", target_doc)
        assert result == ["Boss"]

    def test_try_select_by_extension_returns_on_first_success(
        self, monkeypatch
    ) -> None:
        """_try_select_by_extension returns result dict when SelectByID2 returns True."""
        adapter = self._build_adapter(monkeypatch)
        select_mock = Mock(return_value=True)
        target_doc = SimpleNamespace(Extension=SimpleNamespace(SelectByID2=select_mock))
        result = adapter._try_select_by_extension(target_doc, ["Boss"], "Boss")
        assert result is not None
        assert result["selected"] is True
        assert result["feature_name"] == "Boss"
        assert result["entity_type"] == "BODYFEATURE"  # first entity type tried

    def test_try_select_by_extension_returns_none_when_all_false(
        self, monkeypatch
    ) -> None:
        """_try_select_by_extension returns None when SelectByID2 always returns False."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False))
        )
        result = adapter._try_select_by_extension(target_doc, ["Boss"], "Boss")
        assert result is None

    def test_try_select_by_extension_skips_exceptions_and_continues(
        self, monkeypatch
    ) -> None:
        """_try_select_by_extension swallows individual exceptions and keeps trying."""
        adapter = self._build_adapter(monkeypatch)
        call_count = 0

        def _flaky_select(name, entity_type, *args):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("COM error")
            return True

        target_doc = SimpleNamespace(
            Extension=SimpleNamespace(SelectByID2=_flaky_select)
        )
        result = adapter._try_select_by_extension(target_doc, ["Boss"], "Boss")
        assert result is not None
        assert result["selected"] is True

    def test_try_select_by_component_select4_success(self, monkeypatch) -> None:
        """_try_select_by_component returns result when Select4 succeeds."""
        adapter = self._build_adapter(monkeypatch)
        component = SimpleNamespace(
            Select4=Mock(return_value=True),
            Select=Mock(return_value=False),
            Select2=Mock(return_value=False),
        )
        target_doc = SimpleNamespace(GetComponentByName=Mock(return_value=component))
        result = adapter._try_select_by_component(target_doc, ["Axle"], "Axle")
        assert result is not None
        assert result["selected"] is True
        assert result["entity_type"] == "component:Select4"

    def test_try_select_by_component_falls_back_to_select2(self, monkeypatch) -> None:
        """_try_select_by_component falls back to Select2 when Select4/Select fail."""
        adapter = self._build_adapter(monkeypatch)
        component = SimpleNamespace(
            Select4=Mock(return_value=False),
            Select=Mock(return_value=False),
            Select2=Mock(return_value=True),
        )
        target_doc = SimpleNamespace(GetComponentByName=Mock(return_value=component))
        result = adapter._try_select_by_component(target_doc, ["Axle"], "Axle")
        assert result is not None
        assert result["entity_type"] == "component:Select2"

    def test_try_select_by_component_no_method_returns_none(self, monkeypatch) -> None:
        """_try_select_by_component returns None when doc has no GetComponentByName."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace()  # no GetComponentByName
        result = adapter._try_select_by_component(target_doc, ["Axle"], "Axle")
        assert result is None

    def test_try_select_by_component_component_is_none_returns_none(
        self, monkeypatch
    ) -> None:
        """_try_select_by_component returns None when GetComponentByName returns None."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(GetComponentByName=Mock(return_value=None))
        result = adapter._try_select_by_component(target_doc, ["Axle"], "Axle")
        assert result is None

    def test_try_select_by_feature_tree_finds_matching_name(self, monkeypatch) -> None:
        """_try_select_by_feature_tree returns result when feature.Name matches."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(
            Name="Boss-Extrude1",
            Select2=Mock(return_value=True),
            GetNextFeature=Mock(return_value=None),
        )
        target_doc = SimpleNamespace(FirstFeature=Mock(return_value=feature))
        result = adapter._try_select_by_feature_tree(
            target_doc, "Boss-Extrude1", ["Boss-Extrude1"]
        )
        assert result is not None
        assert result["selected"] is True
        assert result["entity_type"] == "feature-tree"
        assert result["selected_name"] == "Boss-Extrude1"

    def test_try_select_by_feature_tree_returns_none_when_no_match(
        self, monkeypatch
    ) -> None:
        """_try_select_by_feature_tree returns None when no feature matches."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(
            Name="OtherFeature",
            Select2=Mock(return_value=True),
            GetNextFeature=Mock(return_value=None),
        )
        target_doc = SimpleNamespace(FirstFeature=Mock(return_value=feature))
        result = adapter._try_select_by_feature_tree(target_doc, "Boss", ["Boss"])
        assert result is None

    def test_try_select_by_feature_tree_first_feature_none(self, monkeypatch) -> None:
        """_try_select_by_feature_tree returns None immediately when FirstFeature is None."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(FirstFeature=Mock(return_value=None))
        result = adapter._try_select_by_feature_tree(target_doc, "Boss", ["Boss"])
        assert result is None

    def test_try_select_by_feature_tree_empty_name_returns_none(
        self, monkeypatch
    ) -> None:
        """_try_select_by_feature_tree should skip empty feature names via _matches(False)."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(
            Name="",
            Select2=Mock(return_value=False),
            GetNextFeature=Mock(return_value=None),
        )
        target_doc = SimpleNamespace(FirstFeature=Mock(return_value=feature))

        result = adapter._try_select_by_feature_tree(
            target_doc, "TargetFeature", ["TargetFeature"]
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_select_feature_uses_extension_strategy(self, monkeypatch) -> None:
        """select_feature should return selected result when SelectByID2 succeeds."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="MyPart.SLDPRT"),
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=True)),
            FirstFeature=Mock(return_value=None),
        )

        result = await adapter.select_feature("Boss-Extrude1")

        assert result.is_success
        assert result.data["selected"] is True
        assert result.data["feature_name"] == "Boss-Extrude1"
        assert result.data["entity_type"] == "BODYFEATURE"

    @pytest.mark.asyncio
    async def test_select_feature_errors_when_all_strategies_fail(
        self, monkeypatch
    ) -> None:
        """No strategy selects the name -> ERROR naming it (#106), never SUCCESS+False."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="MyPart.SLDPRT"),
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            GetComponentByName=Mock(return_value=None),
            FirstFeature=Mock(return_value=None),
        )

        result = await adapter.select_feature("MissingFeature")

        assert result.is_error
        assert result.error == (
            "Feature not found or could not be selected: MissingFeature"
        )

    @pytest.mark.asyncio
    async def test_select_feature_tries_feature_by_name_first(
        self, monkeypatch
    ) -> None:
        """FeatureByName + Select2 short-circuits the slower strategies."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(Name="Boss-Extrude1", Select2=Mock(return_value=True))
        select_by_id = Mock(return_value=True)
        sel_mgr = SimpleNamespace(GetSelectedObjectCount2=Mock(return_value=1))
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="Part1.SLDPRT"),
            ClearSelection2=Mock(),
            FeatureByName=Mock(return_value=feature),
            Extension=SimpleNamespace(SelectByID2=select_by_id),
            SelectionManager=sel_mgr,
        )

        # Qualified with the active document's own name -> FeatureByName path.
        result = await adapter.select_feature("Boss-Extrude1@Part1")

        assert result.is_success
        assert result.data["entity_type"] == "feature-name"
        assert result.data["selected_name"] == "Boss-Extrude1"
        assert result.data["selection_count"] == 1
        adapter.currentModel.FeatureByName.assert_called_once_with("Boss-Extrude1")
        adapter.currentModel.ClearSelection2.assert_called_once_with(True)
        feature.Select2.assert_called_once_with(False, 0)
        select_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_feature_component_path_skips_feature_by_name(
        self, monkeypatch
    ) -> None:
        """Review #1: 'Front Plane@Part1-1@Assem1' must not resolve to the
        assembly's own Front Plane via FeatureByName."""
        adapter = self._build_adapter(monkeypatch)
        select_by_id = Mock(return_value=True)
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="Assem1.SLDASM"),
            FeatureByName=Mock(return_value=SimpleNamespace(Name="Front Plane")),
            Extension=SimpleNamespace(SelectByID2=select_by_id),
        )

        result = await adapter.select_feature("Front Plane@Part1-1@Assem1")

        assert result.is_success
        adapter.currentModel.FeatureByName.assert_not_called()
        assert select_by_id.call_args[0][0] == "Front Plane@Part1-1@Assem1"

    @pytest.mark.asyncio
    async def test_select_feature_append_keeps_existing_selection(
        self, monkeypatch
    ) -> None:
        """append=True skips ClearSelection2 and forwards append to Select2."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(Name="Sketch1", Select2=Mock(return_value=True))
        adapter.currentModel = SimpleNamespace(
            ClearSelection2=Mock(),
            FeatureByName=Mock(return_value=feature),
            SelectionManager=SimpleNamespace(
                GetSelectedObjectCount2=Mock(return_value=2)
            ),
        )

        result = await adapter.select_feature("Sketch1", append=True)

        assert result.is_success
        assert result.data["selection_count"] == 2
        adapter.currentModel.ClearSelection2.assert_not_called()
        feature.Select2.assert_called_once_with(True, 0)

    @pytest.mark.asyncio
    async def test_select_feature_extension_strategy_passes_null_callout(
        self, monkeypatch
    ) -> None:
        """SelectByID2 gets a non-None callout (pitfall #11) and the append flag."""
        adapter = self._build_adapter(monkeypatch)
        select_by_id = Mock(return_value=True)
        adapter.currentModel = SimpleNamespace(
            GetTitle=Mock(return_value="MyPart.SLDPRT"),
            FeatureByName=Mock(return_value=None),
            Extension=SimpleNamespace(SelectByID2=select_by_id),
        )

        result = await adapter.select_feature("Front Plane", append=True)

        assert result.is_success
        args = select_by_id.call_args[0]
        assert args[5] is True  # Append
        assert args[7] is not None  # Callout: VT_DISPATCH null, never None

    @pytest.mark.asyncio
    async def test_list_features_syncs_currentmodel_from_active_doc(
        self, monkeypatch
    ) -> None:
        """list_features should resync currentModel to swApp.ActiveDoc before traversal."""
        adapter = self._build_adapter(monkeypatch)

        active_doc = SimpleNamespace(
            FirstFeature=Mock(return_value=None),
            FeatureManager=SimpleNamespace(GetFeatureCount=Mock(return_value=0)),
        )
        adapter.swApp = SimpleNamespace(ActiveDoc=active_doc)
        adapter.currentModel = None

        result = await adapter.list_features()

        assert result.is_success
        assert adapter.currentModel is active_doc

    @pytest.mark.asyncio
    async def test_list_features_handles_none_feature_in_reverse_fallback(
        self, monkeypatch
    ) -> None:
        """list_features should ignore None entries returned by reverse position traversal."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FirstFeature=Mock(return_value=None),
            FeatureManager=SimpleNamespace(GetFeatureCount=Mock(return_value=1)),
            FeatureByPositionReverse=Mock(return_value=None),
        )

        result = await adapter.list_features(include_suppressed=True)

        assert result.is_success
        assert result.data == []

    def test_try_select_by_component_non_callable_and_selector_exception(
        self, monkeypatch
    ) -> None:
        """_try_select_by_component should skip non-callable selectors and swallow selector errors."""
        adapter = self._build_adapter(monkeypatch)
        component = SimpleNamespace(
            Select4="not-callable",
            Select=Mock(side_effect=RuntimeError("COM select fail")),
            Select2=Mock(return_value=False),
        )
        target_doc = SimpleNamespace(GetComponentByName=Mock(return_value=component))

        result = adapter._try_select_by_component(target_doc, ["Axle"], "Axle")

        assert result is None

    def test_try_select_by_feature_tree_empty_name_select2_exception_and_next(
        self, monkeypatch
    ) -> None:
        """_try_select_by_feature_tree should handle empty names, Select2 exceptions, and continue traversal."""
        adapter = self._build_adapter(monkeypatch)

        second = SimpleNamespace(
            Name="TargetFeature",
            Select2=Mock(return_value=True),
            GetNextFeature=Mock(return_value=None),
        )
        first = SimpleNamespace(
            Name="TargetFeature",
            Select2=Mock(side_effect=RuntimeError("select fail")),
            GetNextFeature=Mock(return_value=second),
        )
        target_doc = SimpleNamespace(FirstFeature=Mock(return_value=first))

        result = adapter._try_select_by_feature_tree(
            target_doc, "TargetFeature", ["TargetFeature"]
        )

        assert result is not None
        assert result["selected"] is True
        assert result["selected_name"] == "TargetFeature"

    @pytest.mark.asyncio
    async def test_select_feature_returns_component_strategy_result(
        self, monkeypatch
    ) -> None:
        """select_feature should return when component strategy succeeds."""
        adapter = self._build_adapter(monkeypatch)
        target_doc = SimpleNamespace(
            GetTitle=Mock(return_value="Asm1.SLDASM"),
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            GetComponentByName=Mock(
                return_value=SimpleNamespace(
                    Select4=Mock(return_value=True),
                    Select=Mock(return_value=False),
                    Select2=Mock(return_value=False),
                )
            ),
            FirstFeature=Mock(return_value=None),
        )
        adapter.currentModel = target_doc

        result = await adapter.select_feature("Bracket-1")

        assert result.is_success
        assert result.data["selected"] is True
        assert result.data["entity_type"] == "component:Select4"

    @pytest.mark.asyncio
    async def test_select_feature_returns_feature_tree_strategy_result(
        self, monkeypatch
    ) -> None:
        """select_feature should return when extension/component fail but feature-tree succeeds."""
        adapter = self._build_adapter(monkeypatch)
        feature = SimpleNamespace(
            Name="Boss-Extrude1",
            Select2=Mock(return_value=True),
            GetNextFeature=Mock(return_value=None),
        )
        target_doc = SimpleNamespace(
            GetTitle=Mock(return_value="Part1.SLDPRT"),
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            GetComponentByName=Mock(return_value=None),
            FirstFeature=Mock(return_value=feature),
        )
        adapter.currentModel = target_doc

        result = await adapter.select_feature("Boss-Extrude1")

        assert result.is_success
        assert result.data["selected"] is True
        assert result.data["entity_type"] == "feature-tree"

    @pytest.mark.asyncio
    async def test_select_feature_returns_error_without_active_model(
        self, monkeypatch
    ) -> None:
        """select_feature should guard when there is no active model."""
        adapter = self._build_adapter(monkeypatch)

        result = await adapter.select_feature("Boss-Extrude1")

        assert result.is_error
        assert result.error == "No active model"


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
    async def test_connect_failure_and_com_error_branch(self, monkeypatch):
        """Test connect failure and com error branch."""
        adapter = self._build_adapter(monkeypatch)

        # connect() delegates to _session_coordinator.connect(), which wraps
        # any exception from initialize_com_apartment as SolidWorksMCPError.
        adapter._session_coordinator.initialize_com_apartment = MagicMock(
            side_effect=RuntimeError("boom")
        )
        with pytest.raises(SolidWorksMCPError, match="Failed to connect"):
            await adapter.connect()
        # Restore so the adapter is usable for the COM-error branch test below.
        adapter._session_coordinator.initialize_com_apartment = MagicMock()

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=ValueError),
            raising=False,
        )
        com_result = adapter._handle_com_operation(
            "forced_com_error", lambda: (_ for _ in ()).throw(ValueError("bad com"))
        )
        assert com_result.is_error
        assert "COM error in forced_com_error" in (com_result.error or "")
