"""The real adapter's equation methods, against a fake equation manager.

Spec: tools/equations.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

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
    """IEquationMgr as SolidWorks 2026 behaves from Python (the live probe).

    ``Add2`` adds; writing ``Equation(i)`` (through ``_oleobj_.Invoke``)
    changes it everywhere, or leaves it and sets ``Status`` -1 when told to
    refuse; the set call returns 0, or -1 when given any array of
    configuration names (as the real one does) or told to refuse.
    """

    def __init__(self, model: FakeModel) -> None:
        self.model = model
        self.texts: list[str] = []
        self.values: list[Any] = []
        self.globals: list[Any] = []
        self.Status = 0
        self.refuse_add = False
        self.refuse_set = False
        self.raise_on_set = False
        self.fail_status = False
        self.store_as: str | None = None
        self.calls: list[tuple[Any, ...]] = []
        self.evaluated = 0
        self._oleobj_ = self  # IDispatch: GetIDsOfNames and Invoke below

    def GetIDsOfNames(self, name: str) -> int:
        assert name == "Equation"
        return 7

    def Invoke(
        self, dispid: int, lcid: int, flags: int, wanted: bool, index: int, text: str
    ) -> None:
        assert (dispid, lcid, flags, wanted) == (7, 0, 4, False)  # a property put
        self.calls.append(("Put", index, text, self.model.active))
        self._store(index, text)

    def _store(self, index: int, text: str) -> bool:
        """Keep ``text`` unless told to refuse; whether it was kept."""
        if self.refuse_set:
            self.refuse_set = False
            self.Status = -1
            return False
        self.texts[index] = self.store_as if self.store_as is not None else text
        self.store_as = None
        self.Status = -1 if self.fail_status else 1
        self.fail_status = False
        return True

    def GetCount(self) -> int:
        return len(self.texts)

    def Equation(self, index: int) -> str:
        return self.texts[index]

    def Value(self, index: int) -> Any:
        return self.values[index]

    def GlobalVariable(self, index: int) -> bool:
        if self.globals[index] is None:
            raise RuntimeError("no such property")
        return bool(self.globals[index])

    def Add2(self, index: int, text: str, solve: bool) -> int:
        self.calls.append(("Add2", index, text, solve))
        if self.refuse_add:
            return -1
        self.texts.append(text)
        self.values.append(1.0)
        self.globals.append("@" not in text.split("=")[0])
        self.Status = -1 if self.fail_status else 1
        return len(self.texts) - 1

    def SetEquationAndConfigurationOption(
        self, index: int, text: str, option: int, names: Any
    ) -> int:
        self.calls.append(("Set", index, text, option, names, self.model.active))
        if self.raise_on_set:
            raise RuntimeError("COM error")
        if names is not None:
            self.Status = -1
            return -1
        return 0 if self._store(index, text) else -1

    def Delete(self, index: int) -> int:
        self.calls.append(("Delete", index))
        del self.texts[index], self.values[index], self.globals[index]
        return 0

    def EvaluateAll(self) -> int:
        self.evaluated += 1
        return 0


class FakeModel:
    """A model with an equation manager, dimensions and configurations."""

    def __init__(self, dimensions: set[str]) -> None:
        self.manager = FakeManager(self)
        self.dimensions = dimensions
        self.rebuilt = 0
        self.active: str | None = "Default"
        self.shown: list[str] = []

    def GetEquationMgr(self) -> FakeManager:
        return self.manager

    def Parameter(self, name: str) -> Any:
        return SimpleNamespace(name=name) if name in self.dimensions else None

    def ForceRebuild3(self, top_only: bool) -> None:
        self.rebuilt += 1

    def GetConfigurationNames(self) -> tuple[str, ...]:
        return ("Default", "Long", "Short")

    def GetActiveConfiguration(self) -> Any:
        return SimpleNamespace(Name=self.active) if self.active else None

    def ShowConfiguration2(self, name: str) -> bool:
        self.shown.append(name)
        self.active = name
        return True


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
    monkeypatch.setattr(cfg, "string_array", lambda names: tuple(names))


def _adapter(*texts: str, dimensions: set[str] | None = None) -> FakeAdapter:
    model = FakeModel(dimensions or {"D1@Sketch1"})
    for text in texts:
        model.manager.texts.append(text)
        model.manager.values.append(2.0)
        model.manager.globals.append("@" not in text.split("=")[0])
    return FakeAdapter(model)


def _manager(adapter: FakeAdapter) -> FakeManager:
    return cast(FakeManager, adapter.currentModel.manager)


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
    assert manager.calls == [("Add2", -1, '"Width" = 60mm', True)]
    assert result.data["action"] == "added"
    assert result.data["kind"] == "global_variable"
    assert result.data["configurations"] == ["Default", "Long", "Short"]
    assert manager.evaluated == 1 and adapter.currentModel.rebuilt == 1


async def test_a_new_equation_for_this_configuration_is_scoped_after_adding() -> None:
    adapter = _adapter()
    result = await adapter.set_equation("Width", "60mm", "this")
    assert _manager(adapter).calls[1] == (
        "Set",
        0,
        '"Width" = 60mm',
        1,
        None,
        "Default",
    )
    assert result.data["configurations"] == ["Default"]


async def test_named_configurations_are_set_one_at_a_time_then_shown_back() -> None:
    adapter = _adapter('"Width" = 60mm')
    result = await adapter.set_equation("width", "80mm", ["Long", "Short"])
    model = adapter.currentModel
    assert _manager(adapter).calls == [
        ("Set", 0, '"width" = 80mm', 1, None, "Long"),
        ("Set", 0, '"width" = 80mm', 1, None, "Short"),
    ]
    assert model.shown == ["Long", "Short", "Default"]
    assert result.data["action"] == "changed"
    # Read back in Default, so the reply says what was set and each value.
    assert result.data["expression"] == "80mm"
    assert result.data["values"] == {"Long": 2.0, "Short": 2.0}
    assert result.data["value"] == 2.0


async def test_an_unreadable_value_in_a_configuration_is_none() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).values[0] = None
    result = await adapter.set_equation("Width", "80mm", ["Long"])
    assert result.data["values"] == {"Long": None}


async def test_a_change_in_all_configurations_writes_the_property() -> None:
    adapter = _adapter('"Width" = 60mm')
    await adapter.set_equation("Width", "80mm")
    assert _manager(adapter).calls == [("Put", 0, '"Width" = 80mm', "Default")]


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


async def test_an_add_its_configuration_refuses_is_deleted_again() -> None:
    adapter = _adapter()
    _manager(adapter).refuse_set = True
    result = await adapter.set_equation("Width", "5mm", ["Long"])
    assert result.error == (
        'SolidWorks refused the equation "Width" = 5mm in Long; nothing was added.'
    )
    assert _manager(adapter).texts == []
    assert adapter.currentModel.active == "Default"


async def test_a_change_solidworks_refuses_restores_the_old_text() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).refuse_set = True
    result = await adapter.set_equation("Width", '"Nope" * 2')
    assert 'was left as "Width" = 60mm' in result.error
    assert _manager(adapter).texts == ['"Width" = 60mm']


async def test_a_change_in_one_configuration_it_refuses_is_restored() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).refuse_set = True
    result = await adapter.set_equation("Width", '"Nope" * 2', "this")
    assert 'was left as "Width" = 60mm' in result.error
    assert [c[0] for c in _manager(adapter).calls] == ["Set", "Set"]


async def test_a_change_that_fails_to_solve_restores_the_old_text() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).fail_status = True
    result = await adapter.set_equation("Width", '"Nope" * 2')
    assert "refused" in result.error
    assert _manager(adapter).texts == ['"Width" = 60mm']


async def test_a_change_stored_differently_is_restored() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).store_as = '"Width" = 1'
    result = await adapter.set_equation("Width", "80mm")
    assert "refused" in result.error
    assert _manager(adapter).texts == ['"Width" = 60mm']


async def test_the_active_configuration_is_shown_again_after_an_error() -> None:
    adapter = _adapter('"Width" = 60mm')
    _manager(adapter).raise_on_set = True
    result = await adapter.set_equation("Width", "80mm", ["Long"])
    assert result.error == "COM error"
    assert adapter.currentModel.active == "Default"


async def test_with_no_active_configuration_nothing_is_shown_back() -> None:
    adapter = _adapter('"Width" = 60mm')
    adapter.currentModel.active = None
    result = await adapter.set_equation("Width", "80mm", ["Long"])
    assert result.is_success, result.error
    assert adapter.currentModel.shown == ["Long"]


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
    result = await _adapter().set_equation("Width", "1mm", ["Tall"])
    assert result.error.startswith("No configuration named 'Tall'")


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
