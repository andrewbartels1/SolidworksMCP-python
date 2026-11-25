"""Calls that differ between SolidWorks releases (#265 and the 2024 reports)."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks import compat


class _ComError(Exception):
    """pywintypes.com_error's shape: (hresult, text, excepinfo, argerr)."""


_NOT_FOUND = _ComError(compat.DISP_E_MEMBERNOTFOUND, "Member not found.", None, None)


class _Dispatch:
    """The ``_oleobj_`` of a dispatch: answers ``Invoke`` with ``value``."""

    def __init__(self, value: Any) -> None:
        self.value = value
        self.invoked: list[tuple] = []

    def GetIDsOfNames(self, name: str) -> int:  # noqa: N802
        return 7

    def Invoke(self, dispid: int, lcid: int, flags: int, result: bool, *args: Any):  # noqa: N802
        self.invoked.append((dispid, flags, args))
        return self.value


class _Manager:
    """An equation manager whose members answer, or say Member not found."""

    def __init__(self, fails: bool, value: Any = 3) -> None:
        self.fails = fails
        self._oleobj_ = _Dispatch(value)

    def GetCount(self) -> int:  # noqa: N802
        if self.fails:
            raise _NOT_FOUND
        return 2

    @property
    def Status(self) -> int:  # noqa: N802
        if self.fails:
            raise _NOT_FOUND
        return 0


@pytest.fixture(autouse=True)
def _fresh() -> None:
    compat.fallbacks.clear()


def test_a_call_that_works_is_made_as_before() -> None:
    manager = _Manager(fails=False)

    assert compat.invoke(manager, "GetCount", interface="IEquationMgr") == 2
    assert compat.read(manager, "Status") == 0
    assert manager._oleobj_.invoked == []
    assert compat.fallbacks == set()


def test_member_not_found_is_retried_as_either_kind() -> None:
    manager = _Manager(fails=True, value=5)

    assert compat.invoke(manager, "GetCount", interface="IEquationMgr") == 5
    assert compat.read(manager, "Status") == 5
    assert manager._oleobj_.invoked == [(7, 3, ()), (7, 3, ())]
    assert compat.fallbacks == {"IEquationMgr.GetCount", "Status"}


def test_arguments_are_passed_to_the_retry() -> None:
    class _Indexed:
        _oleobj_ = _Dispatch('"Height" = 18mm')

        def Equation(self, index: int) -> str:  # noqa: N802
            raise _NOT_FOUND

    obj = _Indexed()

    assert compat.invoke(obj, "Equation", 0) == '"Height" = 18mm'
    assert obj._oleobj_.invoked == [(7, 3, (0,))]


def test_the_text_alone_is_enough() -> None:
    assert compat.member_not_found(RuntimeError("COM error: Member not found."))


@pytest.mark.parametrize("error", [ValueError("bad"), _ComError(-1, "x", None, None)])
def test_any_other_error_is_raised(error: Exception) -> None:
    class _Broken:
        def GetCount(self) -> int:  # noqa: N802
            raise error

        @property
        def Status(self) -> int:  # noqa: N802
            raise error

    with pytest.raises(type(error)):
        compat.invoke(_Broken(), "GetCount")
    with pytest.raises(type(error)):
        compat.read(_Broken(), "Status")


def test_an_error_with_no_arguments_is_raised() -> None:
    class _Bare:
        def GetCount(self) -> int:  # noqa: N802
            raise RuntimeError

    with pytest.raises(RuntimeError):
        compat.invoke(_Bare(), "GetCount")


@pytest.mark.parametrize(
    ("revision", "year"),
    [
        ("32.5.0", 2024),
        ("33.3.0", 2025),
        ("34.4.0", 2026),
        ("", None),
        (None, None),
        ("x.1", None),
        ("5.0", None),
    ],
)
def test_release_year(revision: str | None, year: int | None) -> None:
    assert compat.release_year(revision) == year
