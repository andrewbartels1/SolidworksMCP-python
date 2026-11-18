"""Equations and global variables: list, add or change, and delete them.

One value (``"Width" = 60mm``) can drive several dimensions
(``"D1@Sketch1" = "Width" / 2``), which is how a SolidWorks part becomes
parametric.

COM calls (argument lists from the installed 2026 type library), all on
``IModelDoc2.GetEquationMgr()``:

- ``GetCount()``, and the indexed properties ``Equation(i)``, ``Value(i)``
  and ``GlobalVariable(i)``;
- ``Add3(Index, Equation, Solve, WhichConfigurations, ConfigNames)``, which
  returns the new index, or -1 when SolidWorks refuses the text;
- ``SetEquationAndConfigurationOption(Index, Equation, WhichConfigurations,
  ConfigNames)``; its return value isn't documented, so the stored text is
  read back instead;
- ``Delete(Index)`` and ``EvaluateAll()``;
- ``Status``, the last operation's result: negative when it failed (an
  added equation SolidWorks couldn't solve is deleted again).

``IModelDoc2.Parameter(name)`` checks a dimension name before anything is
written.
"""

from __future__ import annotations

import re
from typing import Any, cast

from .. import sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import string_array
from .configurations import configuration_scope

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
            ``changed``) and the configurations it applies in.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            option, names, array = configuration_scope(adapter, configurations)
            if "@" in name and not adapter.currentModel.Parameter(name):
                raise LookupError(
                    f"No dimension named '{name}' in the active document; read "
                    "the names with list_model_dimensions."
                )
            manager = self._equation_manager()
            text = equation_text(name, expression)
            scope = array if array is not None else string_array(names)
            existing = next(
                (
                    row
                    for row in self._equations(manager)
                    if row["name"].lower() == name.lower()
                ),
                None,
            )
            if existing is None:
                index = int(manager.Add3(-1, text, True, option, scope))
                if index >= 0 and _failed(manager):
                    manager.Delete(index)
                    index = -1
                if index < 0:
                    raise ValueError(
                        f"SolidWorks refused the equation {text}; nothing was added."
                    )
                action = "added"
            else:
                index = existing["index"]
                previous = str(manager.Equation(index))
                manager.SetEquationAndConfigurationOption(index, text, option, scope)
                if _failed(manager) or not _same(str(manager.Equation(index)), text):
                    manager.SetEquationAndConfigurationOption(
                        index, previous, option, scope
                    )
                    raise ValueError(
                        f"SolidWorks refused the equation {text}; the equation "
                        f"was left as {previous}."
                    )
                action = "changed"
            self._solve(manager)
            row = self._equations(manager)[index]
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
