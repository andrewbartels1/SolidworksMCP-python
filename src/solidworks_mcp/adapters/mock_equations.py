"""The mock adapter's equations and global variables, kept in memory.

Values are worked out for simple expressions: numbers (with an optional
``mm``, ``in`` or ``deg``, kept as written), quoted names of equations that
have a value, ``+ - * /`` and brackets. Anything else has no value, as an
equation SolidWorks can't solve. A quoted name with no equation is refused,
as SolidWorks refuses it, so the ``equation_refused`` path runs without
SolidWorks.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from .base import AdapterResult, AdapterResultStatus
from .solidworks.equations import equation_text

_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_QUOTED = re.compile(r'"([^"]*)"')
_UNITS = re.compile(r"(\d)\s*(mm|in|deg)\b")


def _arithmetic(node: ast.AST) -> float:
    """The value of a tree of numbers, ``+ - * /`` and signs.

    Raises:
        ValueError: For anything else.
    """
    if isinstance(node, ast.Expression):
        return _arithmetic(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return float(
            _OPERATORS[type(node.op)](_arithmetic(node.left), _arithmetic(node.right))
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _arithmetic(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    raise ValueError("not arithmetic")


def mock_value(expression: str, values: dict[str, float | None]) -> float | None:
    """The value of ``expression``, with quoted names looked up in ``values``.

    Args:
        expression: The right-hand side of an equation.
        values: Each equation's value by lower-case name.

    Returns:
        The value, or None when it can't be worked out.

    Raises:
        LookupError: A quoted name has no equation.
    """
    missing = [n for n in _QUOTED.findall(expression) if n.lower() not in values]
    if missing:
        raise LookupError(missing[0])
    names = {n.lower(): values[n.lower()] for n in _QUOTED.findall(expression)}
    if any(v is None for v in names.values()):
        return None
    text = _QUOTED.sub(lambda m: repr(names[m.group(1).lower()]), expression)
    try:
        return _arithmetic(ast.parse(_UNITS.sub(r"\1", text), mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None


class MockEquationsMixin:
    """``list_equations``, ``set_equation`` and ``delete_equation`` for the mock."""

    _current_model: Any
    _dimensions: dict[str, float]

    def _mock_equations(self) -> list[dict[str, Any]]:
        """The active model's equations, in order."""
        if "_equations" not in self.__dict__:
            self._equations: dict[str, list[dict[str, Any]]] = {}
        return self._equations.setdefault(self._current_model.name, [])

    def _mock_solve(self) -> list[dict[str, Any]]:
        """Every equation with its value; dimensions take theirs."""
        values: dict[str, float | None] = {}
        rows = []
        for index, row in enumerate(self._mock_equations()):
            value = mock_value(row["expression"], values)
            values[row["name"].lower()] = value
            if row["kind"] == "dimension" and value is not None:
                self._dimensions[row["name"]] = value
            rows.append({"index": index, **row, "value": value})
        return rows

    def _no_model(self) -> AdapterResult[Any] | None:
        """An error when no model is open."""
        if self._current_model:
            return None
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    async def list_equations(self) -> AdapterResult[list[dict[str, Any]]]:
        """The active model's equations, as the real adapter lists them.

        Returns:
            AdapterResult[list[dict[str, Any]]]: Each with its value.
        """
        refused = self._no_model()
        if refused:
            return refused
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=self._mock_solve()
        )

    async def set_equation(
        self,
        name: str,
        expression: str,
        configurations: str | list[str] = "all",
    ) -> AdapterResult[dict[str, Any]]:
        """Add or change an equation, as the real adapter does.

        Args:
            name: A global variable, or a dimension such as ``D1@Sketch1``.
            expression: The right-hand side.
            configurations: ``"all"``, ``"this"`` or configuration names.

        Returns:
            AdapterResult[dict[str, Any]]: The equation, its value and action.
        """
        refused = self._no_model()
        if refused:
            return refused
        scope = self._mock_scope(configurations)  # type: ignore[attr-defined]
        if isinstance(scope, AdapterResult):
            return scope
        if "@" in name and name not in self._dimensions:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"No dimension named '{name}' in the active document; read "
                "the names with list_model_dimensions.",
            )
        rows = self._mock_equations()
        index = next(
            (i for i, r in enumerate(rows) if r["name"].lower() == name.lower()),
            None,
        )
        values = {r["name"].lower(): r["value"] for r in self._mock_solve()}
        try:
            mock_value(expression, values)
        except LookupError:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"SolidWorks refused the equation {equation_text(name, expression)}; "
                "nothing was changed.",
            )
        kind = "dimension" if "@" in name else "global_variable"
        row = {"name": name, "expression": expression.strip(), "kind": kind}
        if index is None:
            rows.append(row)
            index, action = len(rows) - 1, "added"
        else:
            rows[index] = row
            action = "changed"
        solved = self._mock_solve()[index]
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={**solved, "action": action, "configurations": scope},
        )

    async def delete_equation(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Delete an equation, as the real adapter does.

        Args:
            name: The equation's name.

        Returns:
            AdapterResult[dict[str, Any]]: The deleted name and those left.
        """
        refused = self._no_model()
        if refused:
            return refused
        rows = self._mock_equations()
        index = next(
            (i for i, r in enumerate(rows) if r["name"].lower() == name.lower()),
            None,
        )
        if index is None:
            known = ", ".join(r["name"] for r in rows) or "none"
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"No equation named '{name}'; the model has {known}.",
            )
        deleted = rows.pop(index)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"deleted": deleted["name"], "equations": [r["name"] for r in rows]},
        )
