"""Default planes, the origin and standard views found by identity (#262)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks import default_entities as de

ENGLISH = ("Front Plane", "Top Plane", "Right Plane", "Origin")
FRENCH = ("Plan de face", "Plan de dessus", "Plan de droite", "Origine")
GERMAN = ("Ebene vorne", "Ebene oben", "Ebene rechts", "Ursprung")


class _Adapter:
    """Just what the resolver uses: ``_attempt``, ``currentModel``, ``swApp``."""

    def __init__(self, model: Any = None, language: str | None = "german") -> None:
        self.currentModel = model
        if language is not None:
            self.swApp = SimpleNamespace(GetCurrentLanguage=lambda: language)

    def _attempt(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except Exception:
            return default


def _feature(kind: str, name: str, nxt: Any) -> SimpleNamespace:
    """A late-bound feature: methods are callables."""
    return SimpleNamespace(
        GetTypeName2=lambda: kind, Name=name, GetNextFeature=lambda: nxt
    )


def _tree(*features: tuple[str, str]) -> Any:
    first = None
    for kind, name in reversed(features):
        first = _feature(kind, name, first)
    return first


def _part(names: tuple[str, str, str, str], *extra: tuple[str, str]) -> Any:
    """A part's tree: system folders, the three planes, the origin, features."""
    front, top, right, origin = names
    first = _tree(
        ("CommentsFolder", "Comments"),
        ("MaterialFolder", "Material"),
        ("RefPlane", front),
        ("RefPlane", top),
        ("RefPlane", right),
        ("OriginProfileFeature", origin),
        *extra,
    )
    return SimpleNamespace(FirstFeature=lambda: first)


class TestWhichNamesAreDefaults:
    @pytest.mark.parametrize(
        ("name", "index"),
        [
            ("Front", 0),
            ("front plane", 0),
            ("XY", 0),
            ("Top", 1),
            (" TOP PLANE ", 1),
            ("xz", 1),
            ("Right Plane", 2),
            ("YZ", 2),
            ("Origin", 3),
            ("Top Plane@Part1-1@Assem1", 1),
        ],
    )
    def test_default_names_in_any_case(self, name: str, index: int) -> None:
        assert de.default_index(name) == index

    @pytest.mark.parametrize("name", ["Plane1", "Sketch1", "", "Plan de dessus"])
    def test_other_names_are_not_defaults(self, name: str) -> None:
        assert de.default_index(name) is None


class TestPlanesByTheirPlaceInTheTree:
    @pytest.mark.parametrize(
        ("names", "asked", "expected"),
        [
            (ENGLISH, "Top", "Top Plane"),
            (FRENCH, "Top", "Plan de dessus"),
            (GERMAN, "Top Plane", "Ebene oben"),
            (GERMAN, "XY", "Ebene vorne"),
            (GERMAN, "yz", "Ebene rechts"),
            (FRENCH, "Origin", "Origine"),
        ],
    )
    def test_a_translated_part(self, names, asked, expected) -> None:
        adapter = _Adapter(_part(names))
        assert de.entity_name(adapter, asked) == expected

    def test_a_renamed_default_plane(self) -> None:
        adapter = _Adapter(_part(("Front Plane", "Base", "Right Plane", "Origin")))
        assert de.entity_name(adapter, "Top Plane") == "Base"

    def test_a_plane_the_user_made_is_used_as_given(self) -> None:
        adapter = _Adapter(_part(GERMAN, ("RefPlane", "Plane1")))
        assert de.entity_name(adapter, "Plane1") == "Plane1"

    def test_planes_after_the_origin_are_not_defaults(self) -> None:
        adapter = _Adapter(_part(GERMAN, ("RefPlane", "Plane1")))
        found = de.read_defaults(adapter, adapter.currentModel)
        assert found.planes == GERMAN[:3]
        assert found.origin == "Ursprung"

    def test_each_document_is_read_for_itself(self) -> None:
        german, french = _part(GERMAN), _part(FRENCH)
        adapter = _Adapter(german)
        assert de.entity_name(adapter, "Top") == "Ebene oben"
        adapter.currentModel = french
        assert de.entity_name(adapter, "Top") == "Plan de dessus"

    def test_a_given_owner_is_read_instead_of_the_active_document(self) -> None:
        adapter = _Adapter(_part(ENGLISH))
        assert de.entity_name(adapter, "Right", owner=_part(FRENCH)) == "Plan de droite"

    def test_members_read_as_properties_too(self) -> None:
        origin = SimpleNamespace(
            GetTypeName2="OriginProfileFeature", Name="Origine", GetNextFeature=None
        )
        planes = [
            SimpleNamespace(GetTypeName2="RefPlane", Name=n, GetNextFeature=None)
            for n in FRENCH[:3]
        ]
        planes[0].GetNextFeature, planes[1].GetNextFeature = planes[1], planes[2]
        planes[2].GetNextFeature = origin
        adapter = _Adapter(SimpleNamespace(FirstFeature=planes[0]))
        assert de.entity_name(adapter, "Front") == "Plan de face"


class TestWhenThePlanesCantBeFound:
    def test_too_few_planes_before_the_origin_lists_them_and_the_language(
        self,
    ) -> None:
        model = SimpleNamespace(
            FirstFeature=lambda: _tree(
                ("RefPlane", "Ebene vorne"),
                ("RefPlane", "Ebene oben"),
                ("OriginProfileFeature", "Ursprung"),
            )
        )
        with pytest.raises(LookupError) as raised:
            de.entity_name(_Adapter(model), "Right")
        message = str(raised.value)
        assert "'Right' not found" in message
        assert "2 reference plane(s)" in message
        assert "Ebene vorne, Ebene oben" in message
        assert "SolidWorks language: german" in message

    def test_no_planes_and_no_language(self) -> None:
        model = SimpleNamespace(
            FirstFeature=lambda: _tree(("OriginProfileFeature", "Origin"))
        )
        with pytest.raises(LookupError, match=r"\(none\).*language: unknown"):
            de.entity_name(_Adapter(model, language=None), "Top")

    def test_the_origin_is_still_found_without_planes(self) -> None:
        model = SimpleNamespace(
            FirstFeature=lambda: _tree(("OriginProfileFeature", "Ursprung"))
        )
        assert de.entity_name(_Adapter(model), "Origin") == "Ursprung"

    @pytest.mark.parametrize(
        "model",
        [
            SimpleNamespace(),  # no tree at all
            SimpleNamespace(FirstFeature=lambda: None),
            SimpleNamespace(FirstFeature=lambda: _tree(("ProfileFeature", "S1"))),
        ],
    )
    def test_an_unreadable_tree_keeps_the_english_name(self, model) -> None:
        assert de.entity_name(_Adapter(model), "Top") == "Top Plane"
        assert de.entity_name(_Adapter(model), "origin") == "Origin"

    def test_a_looping_tree_stops(self) -> None:
        looping = SimpleNamespace(GetTypeName2=lambda: "Other", Name="x")
        looping.GetNextFeature = lambda: looping
        model = SimpleNamespace(FirstFeature=lambda: looping)
        assert de.entity_name(_Adapter(model), "Front") == "Front Plane"


class TestComponentSuffix:
    def _assembly(self, components: dict[str, Any]) -> SimpleNamespace:
        model = _part(ENGLISH)
        model.GetComponentByName = lambda name: components.get(name)
        return model

    def test_the_named_components_tree_is_read_and_the_suffix_kept(self) -> None:
        adapter = _Adapter(self._assembly({"Part1-1": _part(GERMAN)}))
        assert (
            de.entity_name(adapter, "Front Plane@Part1-1@Assem1")
            == "Ebene vorne@Part1-1@Assem1"
        )

    def test_an_unknown_component_reads_the_active_document(self) -> None:
        adapter = _Adapter(self._assembly({}))
        assert de.entity_name(adapter, "Top Plane@Part9-1") == "Top Plane@Part9-1"

    def test_an_empty_suffix_reads_the_active_document(self) -> None:
        adapter = _Adapter(self._assembly({}))
        assert de.entity_name(adapter, "Top@") == "Top Plane@"


class TestStandardViews:
    FRENCH_VIEWS = (
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
        "*Ma vue",
    )

    def _model(self, names: Any) -> SimpleNamespace:
        return SimpleNamespace(GetModelViewNames=lambda: names)

    @pytest.mark.parametrize(
        ("english", "local"),
        [
            ("*Isometric", "*Isométrique"),
            ("*Front", "*Face"),
            ("*Normal To", "*Normal à"),
        ],
    )
    def test_the_model_names_each_view_by_its_place(self, english, local) -> None:
        model = self._model(self.FRENCH_VIEWS)
        assert de.standard_view_name(_Adapter(), model, english) == local

    @pytest.mark.parametrize(
        "names",
        [
            FRENCH_VIEWS[:9],  # too short
            ("Mine", *FRENCH_VIEWS[1:]),  # not a standard list
            None,
        ],
    )
    def test_an_unusable_list_keeps_the_english_name(self, names) -> None:
        model = self._model(names)
        assert de.standard_view_name(_Adapter(), model, "*Top") == "*Top"

    def test_no_model_keeps_the_english_name(self) -> None:
        assert de.standard_view_name(_Adapter(), None, "*Top") == "*Top"

    def test_a_view_that_isnt_standard_is_used_as_given(self) -> None:
        model = self._model(self.FRENCH_VIEWS)
        assert de.standard_view_name(_Adapter(), model, "*Current") == "*Current"
