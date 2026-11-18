"""The real adapter's equation methods, against a fake equation manager.

Spec: tools/equations.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import configurations as cfg
from solidworks_mcp.adapters.solidworks import equations as eq
from solidworks_mcp.adapters.solidworks.equations import (
    SolidWorksEquationsMixin,
    equation_text,
    split_equation,
)

pytestmark = pytest.mark.asyncio


class FakeManager:
    """IEquationMgr: equation texts, their values, and the last status."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.values: list[Any] = []
        self.globals: list[bool] = []
        self.Status = 0
        self.refuse_add = False
        self.fail_status = False
        self.store_as: str | None = None
        self.calls: list[tuple[Any, ...]] = []
        self.evaluated = 0

    def GetCount(self) -> int:
        return len(self.texts)

    def Equation(self, index: int) -> str:
        return self.texts[index]

    def Value(self, index: int) -> Any:
        return self.values[index]

    def GlobalVariable(self, index: int) -> bool:
        if self.globals[index] is None:
            raise RuntimeError("no such property")
        return self.globals[index]

    def Add3(self, index: int, text: str, solve: bool, option: int, names: Any) -> int:
        self.calls.append(("Add3", index, text, solve, option, names))
        if self.refuse_add:
            return -1
        self.texts.append(text)
        self.values.append(1.0)
        self.globals.append("@" not in text.split("=")[0])
        self.Status = -1 if self.fail_status else 0
        return len(self.texts) - 1

    def SetEquationAndConfigurationOption(
        self, index: int, text: str, option: int, names: Any
    ) -> int:
        self.calls.append(("Set", index, text, option, names))
        self.texts[index] = self.store_as if self.store_as is not None else text
        self.store_as = None
        self.Status = -1 if self.fail_status else 0
        self.fail_status = False
        return 1

    def Delete(self, index: int) -> int:
        self.calls.append(("Delete", index))
        del self.texts[index], self.values[index], self.globals[index]
        return 0

    def EvaluateAll(self) -> int:
        self.evaluated += 1
        return 0


class FakeModel:
    """A model with an equation manager, dimensions and configurations."""

    def __init__(self, manager: FakeManager, dimensions: set[str]) -> None:
        self.manager = manager
        self.dimensions = dimensions
        self.rebuilt = 0

    def GetEquationMgr(self) -> FakeManager:
        return self.manager

    def Parameter(self, name: str) -> Any:
        return SimpleNamespace(name=name) if name in self.dimensions else None

    def ForceRebuild3(self, top_only: bool) -> None:
        self.rebuilt += 1

    def GetConfigurationNames(self) -> tuple[str, ...]:
        return ("Default", "Long")

    def GetActiveConfiguration(self) -> Any:
        return SimpleNamespace(Name="Default")


class FakeAdapter(SolidWorksEquationsMixin):
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
    monkeypatch.setattr(eq.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(eq, "string_array", lambda names: tuple(names))
    monkeypatch.setattr(cfg, "string_array", lambda names: tuple(names))


def _adapter(*texts: str, dimensions: set[str] | None = None) -> FakeAdapter:
    manager = FakeManager()
    for text in texts:
        manager.texts.append(text)
        manager.values.append(2.0)
        manager.globals.append("@" not in text.split("=")[0])
    return FakeAdapter(FakeModel(manager, dimensions or {"D1@Sketch1"}))


def _manager(adapter: FakeAdapter) -> FakeManager:
    return adapter.currentModel.manager


def test_equation_text_quotes_the_name() -> None:
    assert equation_text("Width", " 60mm ") == '"Width" = 60mm'


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ('"Width" = 60mm', ("Width", "60mm")),
        ('"D1@Sketch1"= "Width" / 2', ("D1@Sketch1", '"Width" / 2')),
        ('"Odd" 5', ("Odd", "5")),
        ("no quotes", ("", "no quotes")),
    ],
)
def test_split_equation(text: str, parts: tuple[str, str]) -> None:
    assert split_equation(text) == parts


async def test_list_gives_each_equation_with_its_kind_and_value() -> None:
    adapter = _adapter(
        '"Width" = 60mm', '"D1@Sketch1" = "Width" / 2', '"Fillet1" = "suppressed"'
    )
    manager = _manager(adapter)
    manager.globals[2] = None  # GlobalVariable unreadable: not a global
    manager.values[2] = None
    rows = (await adapter.list_equations()).data
    assert [(r["name"], r["kind"], r["value"]) for r in rows] == [
        ("Width", "global_variable", 2.0),
        ("D1@Sketch1", "dimension", 2.0),
        ("Fillet1", "other", None),
    ]
    assert rows[1]["expression"] == '"Width" / 2'


async def test_no_model_is_an_error() -> None:
    result = await FakeAdapter(None).list_equations()
    assert result.error == "No active model"


async def test_a_new_global_variable_is_added_in_all_configurations() -> None:
    adapter = _adapter()
    result = await adapter.set_equation("Width", "60mm")
    manager = _manager(adapter)
    assert manager.calls[0] == (
        "Add3",
        -1,
        '"Width" = 60mm',
        True,
        2,
        ("Default", "Long"),
    )
    assert result.data["action"] == "added"
    assert result.data["kind"] == "global_variable"
    assert result.data["configurations"] == ["Default", "Long"]
    assert manager.evaluated == 1 and adapter.currentModel.rebuilt == 1


async def test_this_configuration_passes_the_active_name() -> None:
    adapter = _adapter()
    await adapter.set_equation("Width", "60mm", "this")
    assert _manager(adapter).calls[0][4:] == (1, ("Default",))


async def test_an_existing_equation_is_changed_whatever_its_case() -> None:
    adapter = _adapter('"Width" = 60mm')
    result = await adapter.set_equation("width", "80mm", ["Long"])
    manager = _manager(adapter)
    assert manager.calls == [("Set", 0, '"width" = 80mm', 3, ("Long",))]
    assert result.data["action"] == "changed"


async def test_solidworks_reformatting_the_text_is_not_a_refusal() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).store_as = '"Width"=  80MM'
    result = await adapter.set_equation("Width", "80mm")
    assert result.is_success, result.error


async def test_an_add_solidworks_refuses_changes_nothing() -> None:
    adapter = _adapter()
    _manager(adapter).refuse_add = True
    result = await adapter.set_equation("Width", '"Nope" * 2')
    assert result.error.startswith('SolidWorks refused the equation "Width"')
    assert _manager(adapter).texts == []


async def test_an_add_that_fails_to_solve_is_deleted_again() -> None:
    adapter = _adapter()
    _manager(adapter).fail_status = True
    result = await adapter.set_equation("Width", '"Nope" * 2')
    assert "refused" in result.error
    assert _manager(adapter).texts == []
    assert ("Delete", 0) in _manager(adapter).calls


async def test_a_change_solidworks_refuses_restores_the_old_text() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).fail_status = True
    result = await adapter.set_equation("Width", '"Nope" * 2')
    assert 'was left as "Width" = 60mm' in result.error
    assert _manager(adapter).texts == ['"Width" = 60mm']


async def test_a_change_stored_differently_is_restored() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).store_as = '"Width" = 1'
    result = await adapter.set_equation("Width", "80mm")
    assert "refused" in result.error
    assert _manager(adapter).texts == ['"Width" = 60mm']


async def test_a_dimension_the_model_lacks_is_refused_first() -> None:
    adapter = _adapter()
    result = await adapter.set_equation("D9@Nowhere", "5mm")
    assert result.error.startswith("No dimension named 'D9@Nowhere'")
    assert _manager(adapter).calls == []


async def test_a_known_dimension_is_driven() -> None:
    adapter = _adapter('"Width" = 60mm')
    result = await adapter.set_equation("D1@Sketch1", '"Width" / 2')
    assert result.data["kind"] == "dimension"


async def test_an_unknown_configuration_is_refused() -> None:
    result = await _adapter().set_equation("Width", "1mm", ["Short"])
    assert result.error.startswith("No configuration named 'Short'")


async def test_delete_removes_the_equation_and_solves() -> None:
    adapter = _adapter('"Width" = 60mm', '"D1@Sketch1" = "Width"')
    result = await adapter.delete_equation("d1@sketch1")
    assert result.data == {"deleted": "D1@Sketch1", "equations": ["Width"]}
    assert _manager(adapter).evaluated == 1


@pytest.mark.parametrize(
    ("texts", "known"), [(('"Width" = 1',), "Width"), ((), "none")]
)
async def test_delete_an_unknown_name_lists_the_names(
    texts: tuple[str, ...], known: str
) -> None:
    result = await _adapter(*texts).delete_equation("Ghost")
    assert result.error == f"No equation named 'Ghost'; the model has {known}."
