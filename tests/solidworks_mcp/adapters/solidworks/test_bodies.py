"""Multi-body operations on fake COM objects shaped like SolidWorks 2026's (queue item 35).

Spec: tools/body-listing and tools/body-operations. The calls, arrays and
selection marks are the ones the probes of 2026-11-26 settled (design.md,
Decision 1).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SplitBodyParameters,
)
from solidworks_mcp.adapters.solidworks import bodies


class _Body:
    """IBody2: a box, its volume in mm³, and its selections."""

    def __init__(
        self,
        name: str,
        volume: float,
        lo: tuple[float, float, float] = (0, 0, 0),
        hi: tuple[float, float, float] = (10, 10, 10),
        readable: bool = True,
    ) -> None:
        self.Name, self.volume, self.lo, self.hi = name, volume, lo, hi
        self.readable = readable
        self.selected: list[tuple[bool, int]] = []
        self.selectable = True

    def GetMassProperties(self, density: float) -> tuple[float, ...]:
        if not self.readable:
            raise RuntimeError("no mass")
        return (0.0, 0.0, 0.0, self.volume / 1e9, 0.0, 0.0)

    def GetBodyBox(self) -> tuple[float, ...]:
        return tuple(v / 1000 for v in (*self.lo, *self.hi))

    def Select2(self, append: bool, data: Any) -> bool:
        self.selected.append((append, data.Mark))
        return self.selectable


class _Manager:
    """IFeatureManager: records each call; ``effect`` changes the part."""

    def __init__(self, part: _Part) -> None:
        self.part = part
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.effect: Callable[[], Any] = lambda: None
        self.pieces: list[Any] = []

    def _call(self, name: str, args: tuple[Any, ...]) -> Any:
        self.calls.append((name, args))
        return self.effect()

    def InsertCombineFeature(self, *args: Any) -> Any:
        return self._call("combine", args)

    def PreSplitBody2(self) -> Any:
        self.calls.append(("presplit", ()))
        return tuple(self.pieces)

    def PostSplitBody2(self, *args: Any) -> Any:
        return self._call("split", args)

    def InsertMoveCopyBody2(self, *args: Any) -> Any:
        return self._call("move", args)

    def InsertDeleteBody2(self, *args: Any) -> Any:
        return self._call("delete", args)

    def InsertScale(self, *args: Any) -> Any:
        return self._call("scale", args)


class _Part:
    """IModelDoc2 / IPartDoc with solid bodies and a few named features."""

    def __init__(self, *solids: _Body, kind: int = 1) -> None:
        self.solids = list(solids)
        self.kind = kind
        self.features: dict[str, Any] = {
            "Right Plane": SimpleNamespace(Select2=lambda a, m: True)
        }
        self.FeatureManager = _Manager(self)
        self.SelectionManager = SimpleNamespace(
            CreateSelectData=lambda: SimpleNamespace(Mark=-1)
        )

    def GetType(self) -> int:
        return self.kind

    def GetBodies2(self, kind: int, visible_only: bool) -> Any:
        return tuple(self.solids) if self.solids else None

    def FeatureByName(self, name: str) -> Any:
        return self.features.get(name)

    def ClearSelection2(self, everything: bool) -> None:
        return None


class _Harness(bodies.SolidWorksBodiesMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any) -> None:
        self.currentModel = model

    def _attempt(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception:
            return default

    def _handle_com_operation(self, name: str, operation: Any) -> AdapterResult[Any]:
        try:
            data = operation()
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


@pytest.fixture
def deleted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Plain COM (no flagging, lists for arrays); deleted features recorded."""
    names: list[str] = []
    monkeypatch.setattr(bodies.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(bodies, "dispatch_array", list)
    monkeypatch.setattr(bodies, "string_array", list)
    monkeypatch.setattr(
        bodies, "_delete_feature_impl", lambda adapter, name: names.append(name)
    )
    return names


def _feature(name: str) -> Any:
    return SimpleNamespace(Name=name)


def _block() -> _Body:
    return _Body("Block", 16000.0, (-20, 0, -20), (20, 10, 20))


def _pin() -> _Body:
    return _Body("Pin", 1570.8, (-5, 0, -5), (5, 20, 5))


@pytest.mark.asyncio
async def test_list_bodies(deleted: list[str]) -> None:
    result = await _Harness(_Part(_pin(), _block())).list_bodies()

    assert result.data["count"] == 2
    assert result.data["bodies"][0]["name"] == "Pin"
    assert result.data["bodies"][1]["bounding_box_mm"]["size"] == [40.0, 10.0, 40.0]


@pytest.mark.asyncio
async def test_a_part_without_bodies_lists_none(deleted: list[str]) -> None:
    result = await _Harness(_Part()).list_bodies()

    assert result.data == {"bodies": [], "count": 0, "total_volume_mm3": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "message"),
    [
        (None, "No active model"),
        (_Part(kind=2), "The body tools read a part's solid bodies"),
        (
            _Part(_Body("Odd", 1.0, readable=False)),
            "Could not read the volume and size of body 'Odd'",
        ),
    ],
)
async def test_list_bodies_refused(
    deleted: list[str], model: Any, message: str
) -> None:
    result = await _Harness(model).list_bodies()

    assert message in (result.error or "")


@pytest.mark.asyncio
async def test_no_active_model_for_an_operation(deleted: list[str]) -> None:
    result = await _Harness(None).delete_bodies(DeleteBodiesParameters(bodies=["Pin"]))

    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_a_subtract_passes_the_tools_alone(deleted: list[str]) -> None:
    block, pin = _block(), _pin()
    part = _Part(pin, block)

    def cut() -> Any:
        part.solids = [_Body("Combine1", 16000.0 - 785.4, block.lo, block.hi)]
        return _feature("Combine1")

    part.FeatureManager.effect = cut

    result = await _Harness(part).combine_bodies(
        CombineBodiesParameters(
            operation="subtract", main_body="block", tool_bodies=["PIN"]
        )
    )

    assert result.is_success, result.error
    assert part.FeatureManager.calls == [("combine", (15902, block, [pin]))]
    assert result.data["bodies_after"] == ["Combine1"]
    assert result.data["operation"] == "subtract"


@pytest.mark.asyncio
async def test_an_add_passes_every_body_the_main_one_too(deleted: list[str]) -> None:
    block, pin = _block(), _pin()
    part = _Part(pin, block)

    def join() -> Any:
        part.solids = [_Body("Combine1", 16000.0 + 785.4, block.lo, pin.hi)]
        return _feature("Combine1")

    part.FeatureManager.effect = join

    result = await _Harness(part).combine_bodies(
        CombineBodiesParameters(operation="add", main_body="Block", tool_bodies=["Pin"])
    )

    assert result.is_success, result.error
    assert part.FeatureManager.calls == [("combine", (15903, block, [block, pin]))]


@pytest.mark.asyncio
async def test_a_combine_that_makes_nothing_fails(deleted: list[str]) -> None:
    part = _Part(_pin(), _block())

    result = await _Harness(part).combine_bodies(
        CombineBodiesParameters(
            operation="common", main_body="Block", tool_bodies=["Pin"]
        )
    )

    assert result.error == (
        "Error in combine_bodies: SolidWorks combined (common) nothing; the "
        "bodies are unchanged."
    )
    assert deleted == []


@pytest.mark.asyncio
async def test_a_combine_that_breaks_its_rule_is_deleted(deleted: list[str]) -> None:
    far = _Body("Far", 500.0, (60, 0, 60), (70, 5, 70))
    part = _Part(far, _block())

    def consume() -> Any:
        part.solids = [_block()]
        return _feature("Combine1")

    part.FeatureManager.effect = consume

    result = await _Harness(part).combine_bodies(
        CombineBodiesParameters(
            operation="subtract", main_body="Block", tool_bodies=["Far"]
        )
    )

    assert "combine_bodies should leave the main body smaller" in (result.error or "")
    assert deleted == ["Combine1"]


@pytest.mark.asyncio
async def test_a_failed_rule_on_a_nameless_feature_deletes_nothing(
    deleted: list[str],
) -> None:
    part = _Part(_block())
    part.FeatureManager.effect = lambda: SimpleNamespace()

    result = await _Harness(part).scale_body(ScaleBodyParameters(scale=2))

    assert "scale_body should multiply the scaled volume by 8" in (result.error or "")
    assert deleted == []


@pytest.mark.asyncio
async def test_a_split_passes_equal_length_arrays(deleted: list[str]) -> None:
    block = _block()
    part = _Part(block)
    halves = [_Body("Split1[1]", 8000.0), _Body("Split1[2]", 8000.0, (1, 0, 0))]
    part.FeatureManager.pieces = ["piece-1", "piece-2"]

    def split() -> Any:
        part.solids = halves
        return _feature("Split1")

    part.FeatureManager.effect = split

    result = await _Harness(part).split_body(SplitBodyParameters(tool="Right Plane"))

    assert result.is_success, result.error
    assert part.FeatureManager.calls[-1] == (
        "split",
        (["piece-1", "piece-2"], False, [None, None], ["", ""], ""),
    )
    assert result.data["made"] == ["Split1[1]", "Split1[2]"]
    assert result.data["tool"] == "Right Plane"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "pieces", "message"),
    [
        ("Plane9", [], "No plane or sketch named 'Plane9' to split with."),
        ("Right Plane", ["one"], "SolidWorks split nothing at 'Right Plane'"),
    ],
)
async def test_a_split_refused(
    deleted: list[str], tool: str, pieces: list[Any], message: str
) -> None:
    part = _Part(_block())
    part.FeatureManager.pieces = pieces

    result = await _Harness(part).split_body(SplitBodyParameters(tool=tool))

    assert message in (result.error or "")


@pytest.mark.asyncio
async def test_a_move_selects_with_mark_1_in_metres_and_radians(
    deleted: list[str],
) -> None:
    block = _block()
    part = _Part(block)

    def move() -> Any:
        part.solids = [_Body("Body-Move/Copy1", 16000.0, (-20, 0, 0), (20, 10, 40))]
        return _feature("Body-Move/Copy1")

    part.FeatureManager.effect = move

    result = await _Harness(part).move_copy_body(
        MoveCopyBodyParameters(
            bodies=["Block"], rotate=[0, 90, 0], rotation_point=[10, 0, 0]
        )
    )

    assert result.is_success, result.error
    assert block.selected == [(False, 1)]
    args = part.FeatureManager.calls[0][1]
    assert args[:7] == (0.0, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0)
    assert args[8] == pytest.approx(math.pi / 2)
    assert args[10:] == (False, 1)
    assert (result.data["as_copy"], result.data["copies"]) == (False, 0)


@pytest.mark.asyncio
async def test_copies(deleted: list[str]) -> None:
    block = _block()
    part = _Part(block)

    def copy() -> Any:
        part.solids = [
            *part.solids,
            *(_Body(f"Body-Move/Copy1[{n}]", 16000.0) for n in (1, 2)),
        ]
        return _feature("Body-Move/Copy1")

    part.FeatureManager.effect = copy

    result = await _Harness(part).move_copy_body(
        MoveCopyBodyParameters(
            bodies=["Block"], translate=[50, 0, 0], as_copy=True, copies=2
        )
    )

    assert result.is_success, result.error
    assert part.FeatureManager.calls[0][1][0] == 0.05
    assert part.FeatureManager.calls[0][1][10:] == (True, 2)
    assert result.data["copies"] == 2


@pytest.mark.asyncio
async def test_a_body_solidworks_wont_select_fails(deleted: list[str]) -> None:
    block = _block()
    block.selectable = False

    result = await _Harness(_Part(block)).move_copy_body(
        MoveCopyBodyParameters(bodies=["Block"], translate=[1, 0, 0])
    )

    assert (
        result.error == "Error in move_copy_body: SolidWorks would not select a body."
    )


@pytest.mark.asyncio
async def test_keep_selects_with_mark_0(deleted: list[str]) -> None:
    block, pin, far = _block(), _pin(), _Body("Far", 500.0, (60, 0, 60), (70, 5, 70))
    part = _Part(far, pin, block)

    def keep() -> Any:
        part.solids = [pin, block]
        return _feature("Body-Delete/Keep1")

    part.FeatureManager.effect = keep

    result = await _Harness(part).delete_bodies(
        DeleteBodiesParameters(bodies=["Pin", "Block"], keep=True)
    )

    assert result.is_success, result.error
    assert (pin.selected, block.selected) == ([(False, 0)], [(True, 0)])
    assert part.FeatureManager.calls == [("delete", (True,))]
    assert result.data["removed"] == ["Far"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "args", "selected"),
    [
        (ScaleBodyParameters(scale=2), (0, True, 2.0, 2.0, 2.0), ("Pin", "Block")),
        (
            ScaleBodyParameters(scale_xyz=[1, 2, 4], about="origin", bodies=["block"]),
            (1, False, 1.0, 2.0, 4.0),
            ("Block",),
        ),
    ],
)
async def test_a_scale(
    deleted: list[str],
    params: ScaleBodyParameters,
    args: tuple[Any, ...],
    selected: tuple[str, ...],
) -> None:
    block, pin = _block(), _pin()
    part = _Part(pin, block)

    def scale() -> Any:
        part.solids = [
            _Body(b.Name, b.volume * 8 if b.Name in selected else b.volume, b.lo, b.hi)
            for b in (pin, block)
        ]
        return _feature("Scale1")

    part.FeatureManager.effect = scale

    result = await _Harness(part).scale_body(params)

    assert result.is_success, result.error
    assert part.FeatureManager.calls == [("scale", args)]
    assert [b.Name for b in (pin, block) if b.selected] == list(selected)
    assert all(mark == 1 for b in (pin, block) for _, mark in b.selected)
    assert result.data["about"] == params.about
