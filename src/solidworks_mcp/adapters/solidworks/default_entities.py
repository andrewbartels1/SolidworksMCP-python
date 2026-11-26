"""Find the default planes, the origin and the standard views by identity.

Added in 2.2.0 for #262 (German SolidWorks 2025) and #261 (French): it
replaces the name tables and the process-wide pywin32 hook.

The tools name these in English (``"Top"``, ``"Front Plane"``,
``"*Isometric"``), but their names in a document depend on the template and
the install's language: ``"Plan de dessus"`` on French, ``"Ebene oben"`` on
German, and anything at all once a user renames them. Their identity does
not change:

- the first three ``RefPlane`` features before the ``OriginProfileFeature``
  are Front, Top and Right, in that order, in every part, assembly and
  component, in every language;
- ``IModelDoc2.GetModelViewNames`` lists the ten standard views first, in a
  fixed order (normal to, front, back, left, right, top, bottom, isometric,
  trimetric, dimetric).

Every call reads the document it works on, so two open documents with
differently named planes each get their own names and nothing is cached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .com_utils import as_list, attempt, flag

#: The default planes in tree order, then the origin.
DEFAULT_PLANES = ("Front Plane", "Top Plane", "Right Plane")
ORIGIN = "Origin"
_ORIGIN_INDEX = 3

#: Names that mean a default entity, folded to lower case -> its index in
#: (Front, Top, Right, Origin). SolidWorks' default orientation is Y up, so
#: the Front plane is XY, the Top plane XZ and the Right plane YZ.
_ALIASES: dict[str, int] = {
    "front": 0,
    "front plane": 0,
    "xy": 0,
    "top": 1,
    "top plane": 1,
    "xz": 1,
    "right": 2,
    "right plane": 2,
    "yz": 2,
    "origin": _ORIGIN_INDEX,
}

#: The standard views in ``GetModelViewNames`` order, by their English names.
STANDARD_VIEWS = (
    "*Normal To",
    "*Front",
    "*Back",
    "*Left",
    "*Right",
    "*Top",
    "*Bottom",
    "*Isometric",
    "*Trimetric",
    "*Dimetric",
)

#: Upper bound on the walk to the origin, which sits near the top of the tree.
_WALK_LIMIT = 200


@dataclass(frozen=True)
class DefaultEntities:
    """What the start of one feature tree says about its default entities.

    Attributes:
        planes: Every ``RefPlane`` before the origin, in tree order; the
            first three are Front, Top and Right.
        origin: The origin feature's name, ``None`` when the walk never
            reached it (the tree couldn't be read).
    """

    planes: tuple[str, ...]
    origin: str | None

    @property
    def readable(self) -> bool:
        """Whether the walk reached the origin, so the planes are known."""
        return self.origin is not None

    def name_of(self, index: int) -> str | None:
        """The document's name for entity ``index`` (0 Front ... 3 Origin)."""
        if index == _ORIGIN_INDEX:
            return self.origin
        return self.planes[index] if len(self.planes) >= 3 else None


def _read(obj: Any, name: str) -> Any:
    """Read a member late binding may expose as a property or a method."""
    member = getattr(obj, name)
    return member() if callable(member) else member


def default_index(name: str) -> int | None:
    """Which default entity ``name`` means (0 Front, 1 Top, 2 Right, 3 Origin).

    Any ``@component@assembly`` suffix is ignored; ``None`` for any other name.
    """
    base = str(name or "").partition("@")[0]
    return _ALIASES.get(base.strip().casefold())


def read_defaults(adapter: Any, owner: Any) -> DefaultEntities:
    """Walk ``owner``'s tree (a ModelDoc2 or Component2) up to its origin.

    Args:
        adapter: The adapter, for ``_attempt``.
        owner: The document or component whose tree to read.

    Returns:
        DefaultEntities: The planes before the origin, and the origin.
    """
    flag(adapter, owner, "FirstFeature")
    feature = attempt(adapter, lambda: _read(owner, "FirstFeature"))
    planes: list[str] = []
    for _ in range(_WALK_LIMIT):
        if feature is None:
            break
        flag(adapter, feature, "GetTypeName2", "GetNextFeature")
        type_name = attempt(adapter, lambda f=feature: _read(f, "GetTypeName2"), "")
        name = str(attempt(adapter, lambda f=feature: f.Name, "") or "")
        if type_name == "OriginProfileFeature":
            return DefaultEntities(tuple(planes), name)
        if type_name == "RefPlane":
            planes.append(name)
        feature = attempt(adapter, lambda f=feature: _read(f, "GetNextFeature"))
    return DefaultEntities(tuple(planes), None)


def install_language(adapter: Any) -> str:
    """The SolidWorks install's language (``GetCurrentLanguage``), or ``unknown``."""
    language = attempt(adapter, lambda: adapter.swApp.GetCurrentLanguage(), None)
    return str(language) if language else "unknown"


def _owner_for(adapter: Any, suffix: str) -> Any:
    """The tree a name with ``@suffix`` lives in: the named component when the
    active document is an assembly that has it, else the active document."""
    model = adapter.currentModel
    component_name = suffix.partition("@")[0]
    if component_name:
        component = attempt(
            adapter, lambda: model.GetComponentByName(component_name), None
        )
        if component is not None:
            return component
    return model


def entity_name(adapter: Any, name: str, owner: Any = None) -> str:
    """The document's own name for a default plane or the origin.

    ``Front``, ``Top``, ``Right``, ``XY``, ``XZ``, ``YZ``, ``Front Plane``...
    and ``Origin``, in any case, are found by their place in the tree; a
    ``@component@assembly`` suffix reads that component's tree and is kept.
    Any other name is returned unchanged.

    Args:
        adapter: A connected adapter with a document open.
        name: The name a tool was given.
        owner: The document or component to read; by default the active
            document, or the component the suffix names.

    Returns:
        str: The name to pass to SolidWorks. When the tree can't be read, the
        English name (``"Top Plane"``), as before this lookup existed.

    Raises:
        LookupError: The tree reached its origin with fewer than three
            reference planes before it; the message lists them and the
            install's language.
    """
    index = default_index(name)
    if index is None:
        return name
    base, sep, suffix = str(name).partition("@")
    target = owner if owner is not None else _owner_for(adapter, suffix)
    defaults = read_defaults(adapter, target)
    english = ORIGIN if index == _ORIGIN_INDEX else DEFAULT_PLANES[index]
    if not defaults.readable:
        return english + sep + suffix
    local = defaults.name_of(index)
    if local is None:
        planes = ", ".join(defaults.planes) or "none"
        raise LookupError(
            f"Default plane {base.strip()!r} not found: the document has "
            f"{len(defaults.planes)} reference plane(s) before its origin "
            f"({planes}), not the three default ones. SolidWorks language: "
            f"{install_language(adapter)}."
        )
    return local + sep + suffix


def standard_view_name(adapter: Any, model: Any, english: str) -> str:
    """The model's own name for a standard view (``"*Isometric"`` ...).

    Read from ``model.GetModelViewNames`` by the view's position; the
    English name when ``english`` isn't a standard view, or when the list is
    too short or its first ten aren't all ``*``-named views.
    """
    if english not in STANDARD_VIEWS:
        return english
    position = STANDARD_VIEWS.index(english)
    flag(adapter, model, "GetModelViewNames")
    names = [
        str(n)
        for n in as_list(attempt(adapter, lambda: _read(model, "GetModelViewNames")))
    ]
    count = len(STANDARD_VIEWS)
    if len(names) < count or not all(n.startswith("*") for n in names[:count]):
        return english
    return names[position]
