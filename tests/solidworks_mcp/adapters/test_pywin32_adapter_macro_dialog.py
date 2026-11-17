"""``execute_macro`` runs RunMacro2 inside the dialog watch (#97)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import solidworks_mcp.adapters.pywin32_adapter as module
from solidworks_mcp.adapters.solidworks.dialog_watch import DialogSeen
from solidworks_mcp.exceptions import SolidWorksMCPError
from tests.solidworks_mcp.adapters.solidworks.test_io import _build_adapter


class FakeWatch:
    """Stands in for DialogWatch: records how it was made and what it 'saw'."""

    made: list[tuple[int, float]] = []
    seen_next: list[DialogSeen] = []

    def __init__(self, pid: int, timeout: float) -> None:
        FakeWatch.made.append((pid, timeout))
        self.seen = list(FakeWatch.seen_next)

    def __enter__(self) -> FakeWatch:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> Any:
    FakeWatch.made, FakeWatch.seen_next = [], []
    monkeypatch.setattr(module, "DialogWatch", FakeWatch)
    built = _build_adapter(monkeypatch)
    built.swApp = SimpleNamespace(
        GetProcessID=lambda: 4242, RunMacro2=lambda *_a: (True, 0)
    )
    return built


def test_the_macro_runs_inside_a_watch_on_the_solidworks_process(adapter) -> None:
    result = adapter._invoke_run_macro2("m.swp", "Module1", "main", 12)

    assert FakeWatch.made == [(4242, 12)]
    assert result["errors"] == 0


def test_a_dialog_the_watch_answered_makes_the_run_an_error(adapter) -> None:
    FakeWatch.seen_next = [DialogSeen("SOLIDWORKS", "Done", ("OK",), "OK")]

    with pytest.raises(SolidWorksMCPError) as raised:
        adapter._invoke_run_macro2("m.swp", "Module1", "main", 5)

    assert str(raised.value).startswith(
        "The macro waited for the user: after 5 s a dialog was still open, "
        "'SOLIDWORKS': 'Done' (answered 'OK')."
    )


def test_without_a_process_id_the_macro_runs_unwatched(adapter) -> None:
    adapter.swApp = SimpleNamespace(RunMacro2=lambda *_a: (True, 0))

    assert adapter._invoke_run_macro2("m.swp", "Module1", "main")["errors"] == 0
    assert FakeWatch.made == []


@pytest.mark.asyncio
async def test_execute_macro_passes_its_dialog_timeout(adapter, tmp_path) -> None:
    macro = tmp_path / "m.swp"
    macro.write_bytes(b"")
    adapter._handle_com_operation = lambda _name, operation: operation()

    await adapter.execute_macro({"macro_path": str(macro), "dialog_timeout": 7})
    await adapter.execute_macro({"macro_path": str(macro)})

    assert [timeout for _pid, timeout in FakeWatch.made] == [7.0, 30.0]
