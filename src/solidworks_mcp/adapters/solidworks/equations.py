"""Equations and global variables: list, add or change, and delete them.

One value (``"Width" = 60mm``) can drive several dimensions
(``"D1@Sketch1" = "Width" / 2``), which is how a SolidWorks part becomes
parametric.

COM calls (argument lists from the installed 2026 type library), all on
``IModelDoc2.GetEquationMgr()``. What each returns was measured on
SolidWorks 2026 (the equations live probe, 2026-11-18):

- ``GetCount()``, and the indexed properties ``Equation(i)``, ``Value(i)``
  and ``GlobalVariable(i)``; ``Equation(i)`` reads the active
  configuration's text;
- ``Add2(Index, Equation, Solve)`` returns the new index, or -1 when
  SolidWorks refuses the text. It adds to every configuration;
- writing the ``Equation(i)`` property changes an equation in every
  configuration (its scope goes back to all). A text SolidWorks can't use
  is refused: ``Status`` becomes -1 and the stored text doesn't change;
- ``SetEquationAndConfigurationOption(Index, Equation, 1, None)`` (this
  configuration) returns 0 when it worked. Named configurations are set one
  at a time, each made active in turn, then the active one is shown again.
  Given any array of configuration names it returns -1, and with option 2
  (all) it returns -1 on a part with many equations (19 in the wrench demo),
  which is why "all" writes the property instead. ``Add3`` takes names too
  and fails the same way, so it isn't used;
- ``Delete(Index)``; ``EvaluateAll()``, whose return value isn't used (it
  returned -1 on a part that solved);
- ``Status``, the last operation's result: -1 when it failed, so an added
  equation SolidWorks couldn't solve is deleted again.

``IModelDoc2.Parameter(name)`` checks a dimension name before anything is
written.
"""

from __future__ import annotations

import re
from typing import Any, cast

from .. import sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .configurations import (
    ALL_CONFIGURATIONS,
    THIS_CONFIGURATION,
    _active,
    configuration_scope,
)

#: The left-hand side of an equation: the text between its first quotes.
_NAME = re.compile(r'^\s*"([^"]*)"')


def equation_text(name: str, expression: str) -> str:
    """The equation SolidWorks stores for ``name`` = ``expression``."""
    return f'"{name}" = {expression.strip()}'


def split_equation(text: str) -> tuple[str, str]:
    """An equation's name and expression, from its text.

    Text with no quoted name (not one SolidWorks writes) gives an empty name
    and the whole text as the expression.
    """
    match = _NAME.match(text)
    if not match:
        return "", text.strip()
    rest = text[match.end() :].lstrip()
    return match.group(1), rest[1:].strip() if rest.startswith("=") else rest


def _same(a: str, b: str) -> bool:
    """Whether two equation texts match, ignoring spaces and case."""
    return re.sub(r"\s+", "", a).lower() == re.sub(r"\s+", "", b).lower()


def _failed(manager: Any) -> bool:
    """Whether the last operation failed: ``Status`` is negative then."""
    status = manager.Status
    return isinstance(status, int) and status < 0


def _add(manager: Any, index: int, text: str) -> int:
    """Add ``text`` at ``index`` (-1: at the end); its index, or -1 if refused.

    An equation ``Add2`` accepts but can't solve leaves ``Status`` negative;
    it is deleted again so nothing half-made stays in the model.
    """
    added = int(manager.Add2(index, text, True))
    if added >= 0 and _failed(manager):
        manager.Delete(added)
        return -1
    return added


def _took(manager: Any, index: int, text: str) -> bool:
    """Whether SolidWorks kept ``text`` for equation ``index``.

    ``Status`` isn't negative and the stored text reads back the same
    (SolidWorks may respace it).
    """
    return not _failed(manager) and _same(str(manager.Equation(index)), text)


def _put_everywhere(manager: Any, index: int, text: str) -> bool:
    """Write the ``Equation(index)`` property: the text in every configuration.

    pywin32's late binding reads indexed properties but can't assign one, so
    the property put goes through ``IDispatch.Invoke``.
    """
    import pythoncom

    dispatch = manager._oleobj_
    dispid = dispatch.GetIDsOfNames("Equation")
    dispatch.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYPUT, False, index, text)
    return _took(manager, index, text)


def _set_here(manager: Any, index: int, text: str) -> bool:
    """Set equation ``index`` to ``text`` in the active configuration only."""
    returned = manager.SetEquationAndConfigurationOption(
        index, text, THIS_CONFIGURATION, None
    )
    return returned == 0 and _took(manager, index, text)


def _kind(name: str, is_global: bool) -> str:
    """``global_variable``, ``dimension`` (a name with ``@``) or ``other``."""
    if is_global:
        return "global_variable"
    return "dimension" if "@" in name else "other"


class SolidWorksEquationsMixin:
    """List, add or change, and delete equations and global variables."""

    def _equation_manager(self) -> Any:
        """The active model's equation manager, its methods flagged."""
        adapter: Any = self
        return sw_type_info.flagged(
            adapter.currentModel.GetEquationMgr(), "IEquationMgr"
        )

    def _equations(self, manager: Any) -> list[dict[str, Any]]:
        """Every equation, in order, with its solved value."""
        adapter: Any = self
        rows = []
        for index in range(int(manager.GetCount() or 0)):
            text = str(manager.Equation(index))
            name, expression = split_equation(text)
            is_global = bool(
                adapter._attempt(lambda i=index: manager.GlobalVariable(i), False)
            )
            value = adapter._attempt(lambda i=index: manager.Value(i), None)
            rows.append(
                {
                    "index": index,
                    "name": name,
                    "expression": expression,
                    "kind": _kind(name, is_global),
                    "value": float(value) if value is not None else None,
                }
            )
        return rows

    def _set(
        self,
        index: int,
        text: str,
        option: int,
        names: list[str],
        values: dict[str, Any] | None = None,
    ) -> bool:
        """Set equation ``index`` to ``text`` where ``option`` says.

        All configurations and the active one are one call each. Named
        configurations are set one at a time with "this configuration", each
        made active in turn, and the configuration that was active is shown
        again afterwards, whatever happens.

        Args:
            index: The equation's index.
            text: The whole equation, e.g. ``'"Size" = 8mm'``.
            option: ``ALL_CONFIGURATIONS``, ``THIS_CONFIGURATION`` or
                ``SPECIFY_CONFIGURATION``.
            names: The configurations, for ``SPECIFY_CONFIGURATION``.
            values: Filled with each named configuration's solved value,
                read while it is active.

        Returns:
            Whether SolidWorks took the text everywhere it was asked to.
        """
        adapter: Any = self
        if option == ALL_CONFIGURATIONS:
            return _put_everywhere(self._equation_manager(), index, text)
        if option == THIS_CONFIGURATION:
            return _set_here(self._equation_manager(), index, text)
        previous = _active(adapter)
        took = True
        try:
            for name in names:
                adapter.currentModel.ShowConfiguration2(name)
                manager = self._equation_manager()
                took = _set_here(manager, index, text) and took
                if values is not None:
                    self._solve(manager)
                    value = adapter._attempt(lambda m=manager: m.Value(index), None)
                    values[name] = float(value) if value is not None else None
        finally:
            if previous:
                adapter.currentModel.ShowConfiguration2(previous)
        return took

    def _solve(self, manager: Any) -> None:
        """Solve every equation, then rebuild."""
        adapter: Any = self
        adapter._attempt(lambda: manager.EvaluateAll(), None)
        adapter._attempt(lambda: adapter.currentModel.ForceRebuild3(False), None)

    def _on_model(self, operation: str, build: Any) -> AdapterResult[Any]:
        """Run ``build`` on the COM thread when a model is open."""
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return cast(AdapterResult[Any], adapter._handle_com_operation(operation, build))

    async def list_equations(self) -> AdapterResult[list[dict[str, Any]]]:
        """Every equation and global variable of the active model.

        Returns:
            Each with ``index``, ``name``, ``expression``, ``kind`` and
            ``value`` (in the document's units, or None).
        """

        def build() -> list[dict[str, Any]]:
            return self._equations(self._equation_manager())

        return self._on_model("list_equations", build)

    async def set_equation(
        self,
        name: str,
        expression: str,
        configurations: str | list[str] = "all",
    ) -> AdapterResult[dict[str, Any]]:
        """Add an equation for ``name``, or change the one there is.

        Args:
            name: A global variable, or a dimension such as ``D1@Sketch1``.
            expression: The right-hand side, e.g. ``60mm`` or ``"Width" / 2``.
            configurations: ``"all"``, ``"this"`` or configuration names.

        Returns:
            The stored equation, its value, ``action`` (``added`` or
            ``changed``) and the configurations it applies in; for named
            configurations, the expression set and ``values``, its solved
            value in each of them.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            option, names, _array = configuration_scope(adapter, configurations)
            if "@" in name and not adapter.currentModel.Parameter(name):
                raise LookupError(
                    f"No dimension named '{name}' in the active document; read "
                    "the names with list_model_dimensions."
                )
            manager = self._equation_manager()
            text = equation_text(name, expression)
            values: dict[str, Any] = {}
            existing = next(
                (
                    row
                    for row in self._equations(manager)
                    if row["name"].lower() == name.lower()
                ),
                None,
            )
            if existing is None:
                index = _add(manager, -1, text)
                if index < 0:
                    raise ValueError(
                        f"SolidWorks refused the equation {text}; nothing was added."
                    )
                if option != ALL_CONFIGURATIONS and not self._set(
                    index, text, option, names, values
                ):
                    self._equation_manager().Delete(index)
                    raise ValueError(
                        f"SolidWorks refused the equation {text} in "
                        f"{', '.join(names)}; nothing was added."
                    )
                action = "added"
            else:
                index = existing["index"]
                previous = str(manager.Equation(index))
                if not self._set(index, text, option, names, values):
                    self._set(index, previous, option, names)
                    raise ValueError(
                        f"SolidWorks refused the equation {text}; the equation "
                        f"was left as {previous}."
                    )
                action = "changed"
            manager = self._equation_manager()
            self._solve(manager)
            row = self._equations(manager)[index]
            if values:
                # The row is read in the active configuration; say what was
                # set instead: the expression, its value in the first named
                # configuration, and in each one it was set in.
                row = {
                    **row,
                    "expression": expression.strip(),
                    "value": values[names[0]],
                    "values": values,
                }
            return {**row, "action": action, "configurations": names}

        return self._on_model("set_equation", build)

    async def delete_equation(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Delete the equation for ``name``.

        Args:
            name: The equation's name (its left-hand side).

        Returns:
            The deleted name and the names left.
        """

        def build() -> dict[str, Any]:
            manager = self._equation_manager()
            rows = self._equations(manager)
            match = next((r for r in rows if r["name"].lower() == name.lower()), None)
            if match is None:
                known = ", ".join(r["name"] for r in rows) or "none"
                raise LookupError(f"No equation named '{name}'; the model has {known}.")
            manager.Delete(match["index"])
            self._solve(manager)
            return {
                "deleted": match["name"],
                "equations": [r["name"] for r in self._equations(manager)],
            }

        return self._on_model("delete_equation", build)
