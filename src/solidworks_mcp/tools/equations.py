"""Equations and global variables: what makes a part parametric.

``list_equations``, ``set_equation`` and ``delete_equation`` read and change
the active part's or assembly's equations, so one value
(``"Width" = 60mm``) can drive several dimensions
(``"D1@Sketch1" = "Width" / 2``) and the model stays consistent when it
changes.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .modeling import _check_configurations
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

#: Characters a name can't hold: SolidWorks writes it between quotes.
_NAME_FORBIDDEN = ('"', "=", "\n", "\r")


class SetEquationInput(CompatInput):
    """Input schema for adding or changing an equation.

    Attributes:
        name (str): A global variable, or a dimension such as ``D1@Sketch1``.
        expression (str): The right-hand side.
        configurations (str | list[str]): Where it applies.
    """

    name: str = Field(
        description=(
            "A global variable (e.g. 'Width'), or a dimension of the active "
            "document as list_model_dimensions names it (e.g. 'D1@Sketch1'); "
            "no quotes"
        )
    )
    expression: str = Field(
        description=(
            "The right-hand side, e.g. '60mm' or '\"Width\" / 2'; names in "
            "double quotes. A number with no unit is in the document's units"
        )
    )
    configurations: Literal["all", "this"] | list[str] = Field(
        default="all",
        description="Where it applies: 'all' (the default, as in SolidWorks' "
        "Equations dialog), 'this' (the active configuration), or a list of "
        "configuration names from `list_configurations`",
    )

    def model_post_init(self, __context: Any) -> None:
        """Check the name and expression before anything is written.

        Args:
            __context (Any): The context value.

        Raises:
            ValueError: A blank name or expression, a name with a quote, ``=``
                or line break, an expression with a line break, or an empty
                list of configurations.
        """
        if not self.name.strip():
            raise ValueError("name is required")
        if any(c in self.name for c in _NAME_FORBIDDEN):
            raise ValueError(
                f"name {self.name!r} can't hold a double quote, '=' or a line "
                "break; give it without quotes, e.g. Width or D1@Sketch1"
            )
        if not self.expression.strip():
            raise ValueError("expression is required, e.g. 60mm")
        if "\n" in self.expression or "\r" in self.expression:
            raise ValueError("expression must be one line")
        self.name = self.name.strip()
        _check_configurations(self.configurations)


class EquationNameInput(CompatInput):
    """Input schema naming one equation.

    Attributes:
        name (str): The equation's name (its left-hand side).
    """

    name: str = Field(
        description="The equation's name as list_equations gives it, e.g. 'Width'"
    )

    def model_post_init(self, __context: Any) -> None:
        """Refuse a blank name.

        Args:
            __context (Any): The context value.

        Raises:
            ValueError: The name is blank.
        """
        if not self.name.strip():
            raise ValueError("name is required")
        self.name = self.name.strip()


async def register_equation_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the equation tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def list_equations() -> dict[str, Any]:
        """List the active part's or assembly's equations and global variables, with their values.

        Use it before `set_equation` or `delete_equation`, to see which values
        drive which dimensions. Needs: an open part or assembly. Read-only.
        Returns: `equations`, each with `index`, `name`, `expression`, `kind`
        (`global_variable`, `dimension` or `other`) and `value` (solved, in the
        document's units; null when SolidWorks has none), and `count`.
        """
        require_capability(
            adapter, "list_equations", "Active adapter can't read equations"
        )
        result = await adapter.list_equations()
        require_success(result, "Failed to list equations")
        rows = result.data or []
        return {
            "status": "success",
            "equations": rows,
            "count": len(rows),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_equation(input_data: SetEquationInput) -> dict[str, Any]:
        """Add or change an equation or global variable, so one value drives others (a parametric part).

        E.g. `Width` = `60mm`, then `D1@Sketch1` = `"Width" / 2`: changing `Width`
        later resizes the sketch. A `name` with `@` is a dimension of the active
        document (`list_model_dimensions`); any other is a global variable. An
        existing equation for `name` is changed, else one is added; the model
        is solved and rebuilt. Applies in all configurations unless
        `configurations` says otherwise. An expression SolidWorks can't use
        fails as `equation_refused`, changing nothing. Needs: an open part or
        assembly. Changes: the equation and what it drives. Returns:
        `equation` with `name`, `expression`, `kind`, `value` (document units),
        `action` (`added` or `changed`) and `configurations`.

        Args:
            input_data: `name` and `expression` are required; `configurations`
                defaults to `all`.

        Returns:
            dict[str, Any]: The equation as SolidWorks stored it.
        """
        input_data = normalize_input(input_data, SetEquationInput)
        require_capability(
            adapter, "set_equation", "Active adapter can't change equations"
        )
        result = await adapter.set_equation(
            input_data.name, input_data.expression, input_data.configurations
        )
        require_success(result, "Failed to set equation")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{str(data.get('action', 'set')).capitalize()} "
            f"{input_data.name} = {input_data.expression.strip()}",
            "equation": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def delete_equation(input_data: EquationNameInput) -> dict[str, Any]:
        """Delete an equation or global variable of the active part or assembly, by name.

        A dimension the equation drove keeps its last value; an equation that
        used a deleted global variable stops solving, so check
        `list_equations` afterwards. Needs: an open part or assembly with that
        equation. Changes: removes the equation. Returns: `deleted` and the
        `equations` left (names).

        Args:
            input_data: `name`, as `list_equations` gives it.

        Returns:
            dict[str, Any]: The deleted name and those left.
        """
        input_data = normalize_input(input_data, EquationNameInput)
        require_capability(
            adapter, "delete_equation", "Active adapter can't delete equations"
        )
        result = await adapter.delete_equation(input_data.name)
        require_success(result, "Failed to delete equation")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Deleted equation {data.get('deleted', input_data.name)}",
            "deleted": data.get("deleted"),
            "equations": data.get("equations", []),
            "execution_time": result.execution_time,
        }

    return 3
