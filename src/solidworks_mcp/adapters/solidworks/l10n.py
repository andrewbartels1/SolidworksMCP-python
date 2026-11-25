"""Make English default names work on non-English SolidWorks installs.

The tools name the default planes, the origin and the standard views in
English (``"Front Plane"``, ``"Origin"``, ``"*Isometric"``). A French
SolidWorks calls them ``"Plan de face"``, ``"Origine"``, ``"*Isométrique"``,
so ``FeatureByName``, ``SelectByID2`` and ``CreateDrawViewFromModelView3``
fail with the English name.

:func:`install` hooks late-bound COM dispatch once. The original call always
runs first with the name it was given, so English documents behave exactly as
before. Only when that call fails, and the name is one of the English
defaults, it is retried with the document's own name:

- planes and origin: found by feature type and tree order (the first three
  ``RefPlane`` features before ``OriginProfileFeature`` are Front, Top and
  Right in every language), learned from the document when it is at hand;
- standard views: ``GetModelViewNames`` lists the ten standard views first,
  in a fixed order, in every language;
- a built-in French table as a last resort.
"""

from __future__ import annotations

import types
from collections.abc import Callable, Iterable
from typing import Any

from loguru import logger

DEFAULT_PLANES = ("Front Plane", "Top Plane", "Right Plane")
ORIGIN = "Origin"
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

#: Fallback names seen on SOLIDWORKS 2026 French.
_STATIC: dict[str, tuple[str, ...]] = {
    "Front Plane": ("Plan de face",),
    "Top Plane": ("Plan de dessus",),
    "Right Plane": ("Plan de droite",),
    "Origin": ("Origine",),
    "*Normal To": ("*Normal à",),
    "*Front": ("*Face",),
    "*Back": ("*Arrière",),
    "*Left": ("*Gauche",),
    "*Right": ("*Droite",),
    "*Top": ("*Dessus",),
    "*Bottom": ("*Dessous",),
    "*Isometric": ("*Isométrique",),
    "*Trimetric": ("*Trimétrique",),
    "*Dimetric": ("*Dimétrique",),
}

_CANONICAL = {
    name.casefold(): name for name in (*DEFAULT_PLANES, ORIGIN, *STANDARD_VIEWS)
}

#: English name -> local name, learned from documents this session.
_learned: dict[str, str] = {}
_app: Any = None
_installed = False


def _value(member: Any) -> Any:
    """Read a no-argument COM member that late binding may expose either as
    a property or as a method."""
    if isinstance(member, (types.MethodType, types.FunctionType)):
        return member()
    return member


def learn_from_tree(owner: Any, limit: int = 300) -> None:
    """Learn the local names of the default planes and origin from ``owner``
    (a ModelDoc2 or Component2)."""
    try:
        feat = _value(owner.FirstFeature)
    except Exception:
        return
    planes: list[str] = []
    for _ in range(limit):
        if feat is None:
            break
        try:
            type_name = _value(feat.GetTypeName2)
            name = feat.Name
        except Exception:
            break
        if type_name == "RefPlane" and len(planes) < 3:
            planes.append(name)
        elif type_name == "OriginProfileFeature":
            if len(planes) == 3:
                _learned.update(zip(DEFAULT_PLANES, planes, strict=True))
            _learned[ORIGIN] = name
            break
        try:
            feat = _value(feat.GetNextFeature)
        except Exception:
            break


def learn_views(model: Any) -> None:
    """Learn the local standard view names from ``model.GetModelViewNames``."""
    try:
        names = list(_value(model.GetModelViewNames) or ())
    except Exception:
        return
    count = len(STANDARD_VIEWS)
    if len(names) >= count and all(str(n).startswith("*") for n in names[:count]):
        _learned.update(
            zip(STANDARD_VIEWS, (str(n) for n in names[:count]), strict=True)
        )


def _learn_from_active_doc() -> None:
    if _app is None:
        return
    try:
        doc = _value(_app.ActiveDoc)
    except Exception:
        return
    if doc is not None:
        learn_from_tree(doc)
        learn_views(doc)


def local_candidates(name: str, owner: Any = None) -> list[str]:
    """Names to retry ``name`` with, best first; empty when ``name`` is not
    an English default. A ``@component@assembly`` suffix is kept."""
    base, sep, rest = name.partition("@")
    english = _CANONICAL.get(base.strip().casefold())
    if english is None:
        return []
    if owner is not None:
        learn_from_tree(owner)
        learn_views(owner)
    if english not in _learned:
        _learn_from_active_doc()
    locals_: list[str] = []
    for local in (_learned.get(english), *_STATIC.get(english, ())):
        if local and local != base and local not in locals_:
            locals_.append(local)
    return [local + sep + rest for local in locals_]


def _failed_if_none(result: Any) -> bool:
    return result is None


def _failed_if_false(result: Any) -> bool:
    return not result


#: COM method -> (index of the name argument, test for a failed result,
#: whether the owner object carries a feature tree to learn from).
_TARGETS: dict[str, tuple[int, Callable[[Any], bool], bool]] = {
    "FeatureByName": (0, _failed_if_none, True),
    "SelectByID2": (0, _failed_if_false, False),
    "CreateDrawViewFromModelView3": (1, _failed_if_none, False),
}


def _retrying(method: Callable[..., Any], owner: Any, attr: str) -> Callable[..., Any]:
    index, failed, owner_has_tree = _TARGETS[attr]

    def call(*args: Any, **kwargs: Any) -> Any:
        error: Exception | None = None
        try:
            result = method(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised below
            result, error = None, exc
        if error is None and not failed(result):
            return result
        name = args[index] if len(args) > index else None
        if not isinstance(name, str):
            if error is not None:
                raise error
            return result
        for candidate in local_candidates(name, owner if owner_has_tree else None):
            retry_args = list(args)
            retry_args[index] = candidate
            try:
                retried = method(*retry_args, **kwargs)
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
            if not failed(retried):
                logger.debug("[l10n] {}({!r}) matched as {!r}", attr, name, candidate)
                return retried
        if error is not None:
            raise error
        return result

    return call


def install(app: Any = None) -> None:
    """Hook late-bound COM dispatch (idempotent). ``app`` is the
    SldWorks.Application, used to learn names from the active document."""
    global _app, _installed
    if app is not None:
        _app = app
    if _installed:
        return
    try:
        from win32com.client import dynamic
    except ImportError:
        return
    original = dynamic.CDispatch.__getattr__

    def __getattr__(self: Any, attr: str) -> Any:
        value = original(self, attr)
        if attr in _TARGETS and callable(value):
            return _retrying(value, self, attr)
        return value

    dynamic.CDispatch.__getattr__ = __getattr__
    _installed = True
    logger.info("[l10n] localized default-name fallback installed")


def reset_for_tests(names: Iterable[tuple[str, str]] = ()) -> None:
    """Clear learned names (tests only)."""
    _learned.clear()
    _learned.update(names)
