"""Configurations: create, activate and delete one, and read the active one.

Configurations give a part or assembly its variants (a long and a short
version, a simplified one) without Excel: design tables don't work through
COM on SolidWorks 2026 (queue item 10's live check), so this is the path.

COM calls (argument lists from the installed type library):

- ``IConfigurationManager.AddConfiguration2(Name, Comment, AlternateName,
  Options, ParentConfigName, Description, Rebuild)``; the new configuration
  becomes active, so the previous one is shown again unless asked otherwise;
- ``IModelDoc2.ShowConfiguration2(Name)`` and ``DeleteConfiguration2(Name)``;
- ``IModelDoc2.GetConfigurationNames()`` and ``GetActiveConfiguration().Name``.
"""

from __future__ import annotations

from typing import Any, cast

from .. import sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import as_list, string_array

#: ``swInConfigurationOpts_e``, shared by ``SetSystemValue3`` and
#: ``SetSuppression2``.
THIS_CONFIGURATION, ALL_CONFIGURATIONS, SPECIFY_CONFIGURATION = 1, 2, 3


def _names(adapter: Any) -> list[str]:
    """The active model's configuration names."""
    raw = adapter._attempt(lambda: adapter.currentModel.GetConfigurationNames(), None)
    return [str(name) for name in as_list(raw)]


def _active(adapter: Any) -> str | None:
    """The active configuration's name (``IConfiguration.Name`` is a property)."""
    config = adapter._attempt(
        lambda: adapter.currentModel.GetActiveConfiguration(), None
    )
    name = getattr(config, "Name", None) if config is not None else None
    return str(name) if name else None


def _require(adapter: Any, name: str) -> list[str]:
    """The names, after checking ``name`` is one of them."""
    names = _names(adapter)
    if name not in names:
        raise LookupError(
            f"No configuration named '{name}'; the model has {', '.join(names) or 'none'}."
        )
    return names


def configuration_scope(
    adapter: Any, configurations: str | list[str]
) -> tuple[int, list[str], Any]:
    """Where a change applies: the COM option, the names, and their array.

    ``"this"`` is the active configuration, ``"all"`` every one, a list those
    named (each checked first).

    Raises:
        LookupError: For a name the model doesn't have, listing the names.
    """
    names = _names(adapter)
    if configurations == "this":
        active = _active(adapter)
        return THIS_CONFIGURATION, [active] if active else [], None
    if configurations == "all":
        return ALL_CONFIGURATIONS, names, string_array(names)
    unknown = [n for n in configurations if n not in names]
    if unknown:
        raise LookupError(
            f"No configuration named {', '.join(repr(n) for n in unknown)}; the "
            f"model has {', '.join(names) or 'none'}."
        )
    chosen = list(configurations)
    return SPECIFY_CONFIGURATION, chosen, string_array(chosen)


class SolidWorksConfigurationsMixin:
    """Create, activate and delete configurations, and read the active one."""

    def _run_on_model(
        self, operation: str, build: Any
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` on the COM thread when a model is open."""
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(operation, build),
        )

    async def create_configuration(
        self,
        name: str,
        parent: str | None = None,
        description: str = "",
        activate: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a configuration, optionally derived from ``parent``.

        Args:
            name: The new configuration's name.
            parent: A configuration to derive it from, or None.
            description: Its description.
            activate: Leave it active; otherwise the previous one is shown again.

        Returns:
            The configuration, its parent, the active one and every name.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            names = _names(adapter)
            if name in names:
                raise ValueError(f"A configuration named '{name}' already exists.")
            if parent is not None and parent not in names:
                raise LookupError(
                    f"No configuration named '{parent}' to derive from; the model "
                    f"has {', '.join(names)}."
                )
            previous = _active(adapter)
            manager = sw_type_info.flagged(
                adapter.currentModel.ConfigurationManager, "IConfigurationManager"
            )
            made = manager.AddConfiguration2(
                name, "", "", 0, parent or "", description, True
            )
            if made is None:
                raise RuntimeError(f"AddConfiguration2 made no configuration '{name}'.")
            if not activate and previous:
                adapter.currentModel.ShowConfiguration2(previous)
            return {
                "name": name,
                "parent": parent,
                "active": _active(adapter),
                "configurations": _names(adapter),
            }

        return self._run_on_model("create_configuration", build)

    async def activate_configuration(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Make ``name`` the active configuration and rebuild.

        Args:
            name: The configuration to show.

        Returns:
            The active configuration and the one before it.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            _require(adapter, name)
            previous = _active(adapter)
            if not adapter.currentModel.ShowConfiguration2(name):
                raise RuntimeError(
                    f"SolidWorks refused to show configuration '{name}'."
                )
            adapter._attempt(lambda: adapter.currentModel.ForceRebuild3(False), None)
            return {"active": _active(adapter), "previous": previous}

        return self._run_on_model("activate_configuration", build)

    async def delete_configuration(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Delete a configuration that isn't active and isn't the only one.

        Args:
            name: The configuration to delete.

        Returns:
            The deleted name and the configurations left.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            names = _require(adapter, name)
            if len(names) == 1:
                raise ValueError(f"'{name}' is the model's only configuration.")
            if _active(adapter) == name:
                raise ValueError(
                    f"'{name}' is the active configuration; activate another first."
                )
            if not adapter.currentModel.DeleteConfiguration2(name):
                raise RuntimeError(
                    f"SolidWorks refused to delete configuration '{name}'."
                )
            return {"deleted": name, "configurations": _names(adapter)}

        return self._run_on_model("delete_configuration", build)

    async def active_configuration(self) -> AdapterResult[str]:
        """The active configuration's name.

        Returns:
            The name, or an error when no model is open or it can't be read.
        """
        adapter: Any = self
        result = self._run_on_model(
            "active_configuration", lambda: {"active": _active(adapter)}
        )
        if not result.is_success:
            return cast(AdapterResult[str], result)
        active = (result.data or {}).get("active")
        if not active:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="The active configuration's name couldn't be read.",
            )
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=active,
            execution_time=result.execution_time,
        )
