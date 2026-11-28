"""Modelled threads on fake COM objects shaped like SolidWorks 2026's (queue item 43).

Spec: tools/threads. The calls are the ones the probe of 2026-11-28 measured
(design.md of the modelled-threads change).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters import sw_type_info
from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ThreadParameters,
)
from solidworks_mcp.adapters.solidworks import threads

METRIC = ["M6x1.0", "M8x1.25", "M8x1.0"]


class _Curve:
    def __init__(self, radius_m: float | None) -> None:
        self.radius = radius_m

    def IsCircle(self) -> bool:
        return self.radius is not None

    @property
    def CircleParams(self) -> Any:
        return (0, 0, 0, 0, 1, 0, self.radius) if self.radius else None


class _Model:
    def __init__(self, radius_m: float | None = 0.003, made: bool = True) -> None:
        self.edge = SimpleNamespace(GetCurve=lambda: _Curve(radius_m))
        self.selected: Any = None
        self.data = SimpleNamespace(InitializeThreadData=lambda: None)
        self.made = made
        self.Extension = SimpleNamespace(SelectByID2=self._select)
        self.SelectionManager = SimpleNamespace(
            GetSelectedObject6=lambda index, mark: self.selected
        )
        self.FeatureManager = SimpleNamespace(
            CreateDefinition=lambda kind: self.data,
            CreateFeature=lambda data: (
                SimpleNamespace(Name="Thread1") if self.made else None
            ),
        )

    def _select(
        self, name: str, kind: str, x: float, y: float, z: float, *rest: Any
    ) -> bool:
        self.selected = (
            self.edge if (round(x, 6), round(y, 6)) == (0.003, 0.025) else None
        )
        return self.selected is not None

    def ForceRebuild3(self, top_only: bool) -> bool:
        return True

    def ClearSelection2(self, everything: bool) -> None:
        return None


class _Harness(threads.SolidWorksThreadsMixin):
    def __init__(self, model: Any, folder: str, names: Any = METRIC) -> None:
        self.currentModel = model
        self.swApp = SimpleNamespace(
            GetUserPreferenceStringValue=lambda pref: folder,
            GetConfigurationNames=lambda path: names,
        )

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

    async def _measured(self, operation: str, build: Any, direction: int = 0) -> Any:
        assert direction == -1
        return self._handle_com_operation(operation, build)


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A profile folder holding the four profiles; no flagging; an ISO library."""
    for name in ("Metric Die", "Metric Tap", "Inch Die", "Inch Tap"):
        (tmp_path / f"{name}.SLDLFP").write_text("")
    monkeypatch.setattr(sw_type_info, "flagged", lambda obj, *_: obj)
    library = SimpleNamespace(
        size_rows=lambda standard, table: [
            {"size": "M6", "dimensions": {"pitch": 1.0}},
            {"size": "M8", "dimensions": {"pitch": 1.25}},
        ]
    )
    monkeypatch.setattr(threads.hole_library, "find_library", lambda: library)
    return f";{tmp_path}"


def _params(**change: Any) -> ThreadParameters:
    values: dict[str, Any] = {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 12}
    values.update(change)
    return ThreadParameters(**values)


@pytest.mark.asyncio
async def test_metric_sizes_take_the_library_coarse_pitches(folder: str) -> None:
    result = await _Harness(_Model(), folder).list_thread_sizes("metric")

    assert result.data["profile"] == "Metric Die"
    assert [e["pitch_class"] for e in result.data["sizes"]] == [
        "coarse",
        "coarse",
        "fine",
    ]


@pytest.mark.asyncio
async def test_inch_sizes_go_by_the_list(folder: str) -> None:
    result = await _Harness(_Model(), folder, ["0.2500-20"]).list_thread_sizes("inch")

    assert result.data["sizes"][0]["pitch_class"] == "only"
    assert "25.4/TPI" in result.data["runout_basis"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("standard", "setting", "names", "words"),
    [
        ("din", None, METRIC, "standard must be"),
        ("metric", "", METRIC, "names no thread profile 'Metric Die'"),
        ("metric", None, None, "read no sizes"),
    ],
)
async def test_size_failures(
    folder: str, standard: str, setting: str | None, names: Any, words: str
) -> None:
    harness = _Harness(_Model(), folder if setting is None else setting, names)

    result = await harness.list_thread_sizes(standard)

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_an_external_thread(folder: str) -> None:
    model = _Model()

    result = await _Harness(model, folder).create_thread(_params(hand="left"))

    assert result.data["name"] == "Thread1"
    assert result.data["edge_diameter_mm"] == 6.0
    assert result.data["turns"] == 12
    data = model.data
    assert (data.Type, data.Size, data.ThreadMethod, data.EndCondition) == (
        "Metric Die",
        "M6x1.0",
        0,
        0,
    )
    assert data.BlindDepth == pytest.approx(0.012)
    assert data.RightHanded is False
    assert data.Edge is model.edge


@pytest.mark.asyncio
async def test_an_internal_thread_uses_the_tap(folder: str) -> None:
    model = _Model(radius_m=0.0025)
    model.Extension = SimpleNamespace(
        SelectByID2=lambda *args: setattr(model, "selected", model.edge) or True
    )

    result = await _Harness(model, folder).create_thread(_params(kind="internal"))

    assert result.data["profile"] == "Metric Tap"
    assert model.data.Type == "Metric Tap"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "params", "words"),
    [
        (_Model(), {"size": "M7x1.0"}, "No thread size"),
        (_Model(), {"edge_point": [9, 9, 9]}, "No edge at"),
        (_Model(radius_m=None), {}, "is not a circle"),
        (_Model(radius_m=0.005), {}, "wants a rod of about 6 mm"),
        (_Model(made=False), {}, "SolidWorks made no thread"),
        (_Model(), {"length": -1}, "length must be greater than 0"),
    ],
)
async def test_thread_failures(
    folder: str, model: Any, params: dict[str, Any], words: str
) -> None:
    result = await _Harness(model, folder).create_thread(_params(**params))

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_no_document(folder: str) -> None:
    result = await _Harness(None, folder).create_thread(_params())

    assert result.error == "No active model"
