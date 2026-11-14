"""Tests for the shared feature-tree walk."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from solidworks_mcp.adapters.solidworks.feature_walk import (
    WALK_MEMBERS,
    TreeFeature,
    walk_feature_tree,
)


class _Adapter:
    """The two adapter members the walk uses."""

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, name):
        value = getattr(obj, name)
        return value() if callable(value) else value


class _Feature:
    """A fake ``IFeature`` with a forward link."""

    def __init__(self, name: str, kind: str = "Extrusion") -> None:
        self.Name = name
        self._kind = kind
        self.next: Any = None

    def GetTypeName2(self):  # noqa: N802 - COM name
        return self._kind

    def GetNextFeature(self):  # noqa: N802 - COM name
        return self.next


def _chain(*features: _Feature) -> None:
    for current, following in zip(features, features[1:], strict=False):
        current.next = following


def _document(features: list[_Feature], first: Any) -> Any:
    total = len(features)
    return SimpleNamespace(
        FirstFeature=lambda: first,
        FeatureByPositionReverse=lambda pos: features[total - pos - 1],
        FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: total),
    )


def test_a_full_forward_walk_gives_each_feature_once_in_order() -> None:
    features = [
        _Feature("Front Plane", "RefPlane"),
        _Feature("Sketch1"),
        _Feature("Boss"),
    ]
    _chain(*features)

    walked = walk_feature_tree(_Adapter(), _document(features, features[0]))

    assert [(f.position, f.name) for f in walked] == [
        (0, "Front Plane"),
        (1, "Sketch1"),
        (2, "Boss"),
    ]
    assert walked[0].type_name == "RefPlane"
    assert walked[2].feature is features[2]


def test_a_walk_that_stops_early_is_completed_and_sorted() -> None:
    features = [_Feature(name) for name in ("A", "B", "C", "D")]
    _chain(features[0], features[1])  # the forward walk stops after B

    walked = walk_feature_tree(_Adapter(), _document(features, features[0]))

    assert [f.name for f in walked] == ["A", "B", "C", "D"]
    assert [f.position for f in walked] == [0, 1, 2, 3]


def test_no_forward_walk_and_gaps_in_the_reverse_pass() -> None:
    # The count says three; the newest (reverse position 0) can't be read.
    by_reverse = {1: _Feature("B"), 2: _Feature("A")}
    document = SimpleNamespace(
        FirstFeature=lambda: None,
        FeatureByPositionReverse=lambda pos: by_reverse.get(pos),
        FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 3),
    )

    walked = walk_feature_tree(_Adapter(), document)

    assert [(f.position, f.name) for f in walked] == [(0, "A"), (1, "B")]


def test_an_unreadable_type_and_a_missing_feature_manager() -> None:
    class _Bare:
        Name = "Odd"

        def GetNextFeature(self):  # noqa: N802 - COM name
            return None

    document = SimpleNamespace(FirstFeature=lambda: _Bare())

    walked = walk_feature_tree(_Adapter(), document)

    assert walked == [TreeFeature(0, "Odd", "Unknown", walked[0].feature)]


def test_walk_members_cover_what_callers_read() -> None:
    assert {"GetNextFeature", "GetTypeName2", "IsSuppressed"} <= set(WALK_MEMBERS)
