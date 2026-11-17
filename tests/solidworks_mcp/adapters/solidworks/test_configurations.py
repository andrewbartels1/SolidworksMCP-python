"""The real adapter's configuration methods, against a fake COM model.

Spec: tools/configurations.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import configurations as cfg
from solidworks_mcp.adapters.solidworks.configurations import (
    SolidWorksConfigurationsMixin,
)


class FakeModel:
    """A model with configurations, an active one, and the COM calls."""

    def __init__(self, names: list[str], active: str | None = "Default") -> None:
        self.names = list(names)
        self.active = active
        self.show_ok = True
        self.delete_ok = True
        self.ConfigurationManager = MagicMock()
        self.ConfigurationManager.AddConfiguration2.side_effect = self._add
        self.rebuilt = 0

    def _add(self, name: str, *_args: Any) -> Any:
        self.names.append(name)
        self.active = name
        return SimpleNamespace(Name=name)

    def GetConfigurationNames(self) -> tuple[str, ...]:
        return tuple(self.names)

    def GetActiveConfiguration(self) -> Any:
        return SimpleNamespace(Name=self.active) if self.active else None

    def ShowConfiguration2(self, name: str) -> bool:
        if self.show_ok:
            self.active = name
        return self.show_ok

    def DeleteConfiguration2(self, name: str) -> bool:
        if self.delete_ok:
            self.names.remove(name)
        return self.delete_ok

    def ForceRebuild3(self, top_only: bool) -> None:
        self.rebuilt += 1


class FakeAdapter(SolidWorksConfigurationsMixin):
    def __init__(self, model: Any) -> None:
        self.currentModel = model

    def _attempt(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except Exception:
            return default

    def _handle_com_operation(self, name: str, fn: Any) -> AdapterResult[Any]:
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=fn())
        except Exception as error:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(error))


@pytest.fixture(autouse=True)
def _no_flagging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg.sw_type_info, "flagged", lambda obj, *_: obj)


@pytest.mark.asyncio
async def test_create_restores_the_previous_configuration() -> None:
    model = FakeModel(["Default"])

    result = await FakeAdapter(model).create_configuration("Long", "Default", "a")

    model.ConfigurationManager.AddConfiguration2.assert_called_once_with(
        "Long", "", "", 0, "Default", "a", True
    )
    assert result.data == {
        "name": "Long",
        "parent": "Default",
        "active": "Default",
        "configurations": ["Default", "Long"],
    }


@pytest.mark.asyncio
async def test_create_and_activate() -> None:
    model = FakeModel(["Default"])

    result = await FakeAdapter(model).create_configuration("Long", activate=True)

    assert result.data["active"] == "Long"


@pytest.mark.parametrize(
    ("name", "parent", "message"),
    [
        ("Default", None, "A configuration named 'Default' already exists."),
        ("Long", "Ghost", "No configuration named 'Ghost' to derive from"),
    ],
)
@pytest.mark.asyncio
async def test_create_refusals(name: str, parent: str | None, message: str) -> None:
    result = await FakeAdapter(FakeModel(["Default"])).create_configuration(
        name, parent
    )

    assert (result.error or "").startswith(message)


@pytest.mark.asyncio
async def test_create_when_nothing_is_made() -> None:
    model = FakeModel(["Default"])
    model.ConfigurationManager.AddConfiguration2.side_effect = None
    model.ConfigurationManager.AddConfiguration2.return_value = None

    result = await FakeAdapter(model).create_configuration("Long")

    assert result.error == "AddConfiguration2 made no configuration 'Long'."


@pytest.mark.asyncio
async def test_no_model_is_refused() -> None:
    result = await FakeAdapter(None).activate_configuration("Default")

    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_activate() -> None:
    model = FakeModel(["Default", "Long"])

    result = await FakeAdapter(model).activate_configuration("Long")
    unknown = await FakeAdapter(model).activate_configuration("Ghost")
    model.show_ok = False
    refused = await FakeAdapter(model).activate_configuration("Default")

    assert result.data == {"active": "Long", "previous": "Default"}
    assert model.rebuilt == 1
    assert (
        unknown.error == "No configuration named 'Ghost'; the model has Default, Long."
    )
    assert refused.error == "SolidWorks refused to show configuration 'Default'."


@pytest.mark.asyncio
async def test_delete() -> None:
    model = FakeModel(["Default", "Long"])
    adapter = FakeAdapter(model)

    active = await adapter.delete_configuration("Default")
    model.delete_ok = False
    refused = await adapter.delete_configuration("Long")
    model.delete_ok = True
    deleted = await adapter.delete_configuration("Long")
    only = await adapter.delete_configuration("Default")

    assert (
        active.error == "'Default' is the active configuration; activate another first."
    )
    assert refused.error == "SolidWorks refused to delete configuration 'Long'."
    assert deleted.data == {"deleted": "Long", "configurations": ["Default"]}
    assert only.error == "'Default' is the model's only configuration."


@pytest.mark.asyncio
async def test_unknown_with_no_names() -> None:
    model = FakeModel([])

    result = await FakeAdapter(model).delete_configuration("Default")

    assert result.error == "No configuration named 'Default'; the model has none."


@pytest.mark.asyncio
async def test_active_configuration() -> None:
    named = await FakeAdapter(FakeModel(["Default"])).active_configuration()
    unread = await FakeAdapter(
        FakeModel(["Default"], active=None)
    ).active_configuration()
    no_model = await FakeAdapter(None).active_configuration()

    assert named.data == "Default"
    assert unread.error == "The active configuration's name couldn't be read."
    assert no_model.error == "No active model"


# ---- where a change applies (section 3) ------------------------------------------


def _scoped(model: FakeModel, configurations: Any) -> Any:
    adapter = FakeAdapter(model)
    return cfg.configuration_scope(adapter, configurations)


def test_scope_this_all_and_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "string_array", lambda names: ("ARRAY", *names))
    model = FakeModel(["Default", "Long", "Short"], active="Long")

    assert _scoped(model, "this") == (1, ["Long"], None)
    assert _scoped(model, "all") == (
        2,
        ["Default", "Long", "Short"],
        ("ARRAY", "Default", "Long", "Short"),
    )
    assert _scoped(model, ["Short"]) == (3, ["Short"], ("ARRAY", "Short"))
    assert _scoped(FakeModel(["Default"], active=None), "this") == (1, [], None)


def test_scope_refuses_unknown_names() -> None:
    with pytest.raises(
        LookupError,
        match="No configuration named 'Tall', 'Wide'; the model has Default.",
    ):
        _scoped(FakeModel(["Default"]), ["Default", "Tall", "Wide"])
    with pytest.raises(LookupError, match="the model has none"):
        _scoped(FakeModel([]), ["Tall"])
