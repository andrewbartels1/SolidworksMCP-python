"""The one walk of a document's top-level feature tree.

``list_features`` and ``list_model_dimensions`` both read the tree through
:func:`walk_feature_tree`, so they always see the same features in the same
order.

SolidWorks can stop ``IFeature.GetNextFeature`` at the system folders even
though later sketches and features exist, so the walk always makes a second
pass with ``IModelDoc2.FeatureByPositionReverse``. Both passes number a
feature by its place in the tree (the forward pass counts from 0, the
reverse pass uses ``count - reverse_position - 1``), so a feature found by
both gets one number, and sorting by it gives tree order, oldest first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .com_utils import attempt, flag

#: The ``IFeature`` members the walk and its callers read. Flagging only these
#: keeps each fresh dispatch cheap (a whole interface costs ~27 ms).
WALK_MEMBERS = ("GetNextFeature", "GetTypeName2", "IsSuppressed", "IsSuppressed2")

#: Upper bound on the forward walk, against a feature chain that loops.
_MAX_FORWARD_STEPS = 10000


@dataclass(frozen=True)
class TreeFeature:
    """One top-level feature found by the walk.

    Attributes:
        position: Its place in the tree, 0 for the first.
        name: The feature's name.
        type_name: Its ``GetTypeName2`` type, ``"Unknown"`` when unreadable.
        feature: The ``IFeature`` dispatch, for reading more from it.
    """

    position: int
    name: str
    type_name: str
    feature: Any


def _describe(adapter: Any, feature: Any, position: int) -> TreeFeature:
    """Read one feature's name and type into a :class:`TreeFeature`.

    Args:
        adapter: The adapter, for ``_attempt`` and ``_get_attr_or_call``.
        feature: The ``IFeature`` dispatch.
        position: Its place in the tree.

    Returns:
        TreeFeature: The feature with its name and type.
    """
    type_name = attempt(
        adapter,
        lambda: adapter._get_attr_or_call(feature, "GetTypeName2"),
        "Unknown",
    )
    return TreeFeature(
        position=position,
        name=str(getattr(feature, "Name", "")),
        type_name=str(type_name),
        feature=feature,
    )


def walk_feature_tree(adapter: Any, document: Any) -> list[TreeFeature]:
    """Every top-level feature of ``document``, once each, in tree order.

    Args:
        adapter: The adapter, for ``_attempt`` and ``_get_attr_or_call``.
        document: The ``IModelDoc2`` dispatch to walk.

    Returns:
        list[TreeFeature]: The features, sorted by tree position. A feature
        found by both passes (same name and type) is kept once.
    """
    found: list[TreeFeature] = []
    seen: set[tuple[str, str]] = set()

    def _keep(feature: Any, position: int) -> None:
        item = _describe(adapter, feature, position)
        key = (item.name, item.type_name)
        if key not in seen:
            seen.add(key)
            found.append(item)

    feature = attempt(adapter, lambda: document.FirstFeature())
    position = 0
    while feature is not None and position < _MAX_FORWARD_STEPS:
        flag(adapter, feature, *WALK_MEMBERS)
        _keep(feature, position)
        position += 1
        feature = attempt(adapter, lambda f=feature: f.GetNextFeature())

    feature_manager = getattr(document, "FeatureManager", None)
    count = attempt(
        adapter,
        lambda: int(feature_manager.GetFeatureCount(True) or 0),  # type: ignore[union-attr]
        0,
    )
    # FeatureByPositionReverse is zero-based: 0 is the newest feature.
    for reverse_position in range(count):
        feature = attempt(
            adapter, lambda p=reverse_position: document.FeatureByPositionReverse(p)
        )
        if feature is not None:
            _keep(feature, count - reverse_position - 1)

    found.sort(key=lambda item: item.position)
    return found
