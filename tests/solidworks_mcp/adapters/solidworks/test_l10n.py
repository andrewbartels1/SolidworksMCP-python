"""English default names resolve on a French SolidWorks (l10n fallback)."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks import l10n


class _Feat:
    def __init__(self, name: str, type_name: str, nxt: _Feat | None = None) -> None:
        self.Name = name
        self.GetTypeName2 = type_name
        self.GetNextFeature = nxt


def _french_tree() -> _Feat:
    chain = [
        ("Annotations", "DetailCabinet"),
        ("Plan de face", "RefPlane"),
        ("Plan de dessus", "RefPlane"),
        ("Plan de droite", "RefPlane"),
        ("Origine", "OriginProfileFeature"),
        ("Plan1", "RefPlane"),
    ]
    nxt = None
    for name, type_name in reversed(chain):
        nxt = _Feat(name, type_name, nxt)
    assert nxt is not None
    return nxt


class _Model:
    def __init__(self, names: dict[str, str]) -> None:
        self._names = names
        self.FirstFeature = _french_tree()
        self.GetModelViewNames = [
            "*Normal à",
            "*Face",
            "*Arrière",
            "*Gauche",
            "*Droite",
            "*Dessus",
            "*Dessous",
            "*Isométrique",
            "*Trimétrique",
            "*Dimétrique",
            "Ma vue",
        ]
        self.calls: list[str] = []

    def FeatureByName(self, name: str) -> Any:
        self.calls.append(name)
        return self._names.get(name)


@pytest.fixture(autouse=True)
def _clean() -> None:
    l10n.reset_for_tests()


def test_planes_learned_by_type_and_order() -> None:
    l10n.learn_from_tree(_Model({}))
    assert l10n._learned == {
        "Front Plane": "Plan de face",
        "Top Plane": "Plan de dessus",
        "Right Plane": "Plan de droite",
        "Origin": "Origine",
    }


def test_views_learned_from_model_view_names() -> None:
    l10n.learn_views(_Model({}))
    assert l10n._learned["*Isometric"] == "*Isométrique"
    assert l10n._learned["*Front"] == "*Face"


def test_candidates_keep_component_suffix_and_ignore_other_names() -> None:
    l10n.reset_for_tests([("Front Plane", "Plan de face")])
    assert l10n.local_candidates("front plane@Part1-1@Assem1") == [
        "Plan de face@Part1-1@Assem1"
    ]
    assert l10n.local_candidates("Plane1") == []
    assert l10n.local_candidates("Sketch1") == []


def test_retry_only_after_the_english_name_fails() -> None:
    model = _Model({"Plan de dessus": "FR-TOP"})
    call = l10n._retrying(model.FeatureByName, model, "FeatureByName")
    assert call("Top Plane") == "FR-TOP"
    assert model.calls == ["Top Plane", "Plan de dessus"]


def test_english_document_untouched() -> None:
    model = _Model({"Top Plane": "EN-TOP"})
    call = l10n._retrying(model.FeatureByName, model, "FeatureByName")
    assert call("Top Plane") == "EN-TOP"
    assert model.calls == ["Top Plane"]


def test_select_by_id2_retries_with_static_table() -> None:
    seen: list[str] = []

    def select(name: str, kind: str, *_rest: Any) -> bool:
        seen.append(name)
        return name == "Plan de droite"

    call = l10n._retrying(select, object(), "SelectByID2")
    assert call("Right Plane", "PLANE", 0, 0, 0, False, 0, None, 0) is True
    assert seen == ["Right Plane", "Plan de droite"]


def test_original_error_reraised_when_nothing_matches() -> None:
    def boom(_path: str, _view: str, *_rest: Any) -> Any:
        raise RuntimeError("COM failure")

    call = l10n._retrying(boom, object(), "CreateDrawViewFromModelView3")
    with pytest.raises(RuntimeError, match="COM failure"):
        call("part.sldprt", "*Isometric", 0.1, 0.1, 0.0)


def test_a_member_exposed_as_a_method_is_called() -> None:
    class _Doc:
        def GetModelViewNames(self) -> list[str]:  # noqa: N802 - COM name
            return ["*Front"]

    assert l10n._value(_Doc().GetModelViewNames) == ["*Front"]


class _Raises:
    """A COM object whose every member read fails."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"COM: {name}")


def test_an_unreadable_tree_or_view_list_learns_nothing() -> None:
    l10n.learn_from_tree(_Raises())
    l10n.learn_views(_Raises())

    assert l10n._learned == {}


class _NoNext:
    """A plane whose next feature can't be read."""

    Name = "Plan de face"
    GetTypeName2 = "RefPlane"

    @property
    def GetNextFeature(self) -> Any:  # noqa: N802 - COM name
        raise OSError("COM")


def test_a_tree_walk_stops_at_its_end_or_an_unreadable_feature() -> None:
    planes = _Feat("Plan de face", "RefPlane", _Feat("Plan de dessus", "RefPlane"))

    for first in (planes, _Raises(), _NoNext()):
        l10n.learn_from_tree(SimpleNamespace(FirstFeature=first))

    assert l10n._learned == {}


def test_the_active_document_is_read_when_nothing_is_learned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(l10n, "_app", SimpleNamespace(ActiveDoc=_Model({})))

    assert l10n.local_candidates("*Isometric") == ["*Isométrique"]
    assert l10n._learned["Top Plane"] == "Plan de dessus"


@pytest.mark.parametrize(
    "app",
    [None, _Raises(), SimpleNamespace(ActiveDoc=None)],
    ids=["no-app", "unreadable", "no-document"],
)
def test_no_active_document_falls_back_to_the_table(
    monkeypatch: pytest.MonkeyPatch, app: Any
) -> None:
    monkeypatch.setattr(l10n, "_app", app)

    assert l10n.local_candidates("Top Plane") == ["Plan de dessus"]


def test_a_failure_without_a_name_is_passed_on_unchanged() -> None:
    def fails(*_args: Any) -> Any:
        raise RuntimeError("no name")

    returns_none = l10n._retrying(lambda *_a: None, object(), "FeatureByName")
    raises = l10n._retrying(fails, object(), "FeatureByName")

    assert returns_none(7) is None
    with pytest.raises(RuntimeError, match="no name"):
        raises()


def test_a_failed_retry_tries_the_next_name_then_returns_the_first_result() -> None:
    seen: list[str] = []

    def select(name: str, *_rest: Any) -> bool:
        seen.append(name)
        if name == "Plan de face":
            raise RuntimeError("COM")
        return False

    l10n.reset_for_tests([("Front Plane", "Plan de face")])
    call = l10n._retrying(select, object(), "SelectByID2")

    assert call("Front Plane", "PLANE") is False
    assert seen == ["Front Plane", "Plan de face"]


class _CDispatch:
    """Stands in for ``win32com.client.dynamic.CDispatch``."""

    def __getattr__(self, attr: str) -> Any:
        if attr == "FeatureByName":
            return lambda name: "FR-TOP" if name == "Plan de dessus" else None
        return f"value of {attr}"


def _fake_win32com(monkeypatch: pytest.MonkeyPatch, cdispatch: type) -> None:
    client = types.ModuleType("win32com.client")
    client.dynamic = SimpleNamespace(CDispatch=cdispatch)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setattr(l10n, "_installed", False)
    monkeypatch.setattr(l10n, "_app", None)


def test_install_hooks_the_named_calls_once(monkeypatch: pytest.MonkeyPatch) -> None:
    cdispatch = type("CDispatch", (_CDispatch,), {})
    monkeypatch.setattr(cdispatch, "__getattr__", _CDispatch.__getattr__)
    _fake_win32com(monkeypatch, cdispatch)
    app = object()

    l10n.install(app)
    hooked = cdispatch.__getattr__
    l10n.install()
    obj = cdispatch()

    assert l10n._app is app
    assert cdispatch.__getattr__ is hooked
    assert obj.FeatureByName("Top Plane") == "FR-TOP"
    assert obj.Visible == "value of Visible"


def test_install_without_pywin32_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "win32com.client", None)
    monkeypatch.setattr(l10n, "_installed", False)

    l10n.install()

    assert l10n._installed is False
