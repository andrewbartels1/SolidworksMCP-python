"""English default names resolve on a French SolidWorks (l10n fallback)."""

from __future__ import annotations

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
