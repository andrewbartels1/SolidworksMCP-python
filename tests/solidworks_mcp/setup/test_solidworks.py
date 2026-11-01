"""Tests for reading the installed SolidWorks versions."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.setup.solidworks import installed_versions


def _registry(subkeys: list[str], open_fails: bool = False) -> Any:
    """A fake ``winreg`` whose SolidWorks key holds ``subkeys``."""

    def open_key(root: int, path: str) -> nullcontext[None]:
        if open_fails:
            raise OSError("no key")
        return nullcontext()

    def enum_key(key: object, index: int) -> str:
        if index >= len(subkeys):
            raise OSError("no more")
        return subkeys[index]

    return SimpleNamespace(HKEY_LOCAL_MACHINE=0, OpenKey=open_key, EnumKey=enum_key)


def test_years_newest_first_and_other_keys_ignored() -> None:
    registry = _registry(
        [
            "SOLIDWORKS 2024",
            "Applications",
            "SOLIDWORKS 2026",
            "solidworks 2024",
            "Security",
        ]
    )

    assert installed_versions(registry) == [2026, 2024]


def test_no_solidworks_key() -> None:
    assert installed_versions(_registry([], open_fails=True)) == []


def test_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "winreg", None)

    assert installed_versions() == []


def test_the_real_registry_is_used_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "winreg", _registry(["SOLIDWORKS 2025"]))

    assert installed_versions() == [2025]
