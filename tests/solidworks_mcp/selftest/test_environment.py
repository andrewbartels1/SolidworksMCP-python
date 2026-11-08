"""read_environment reports what it can read and None for the rest."""

from __future__ import annotations

from importlib import metadata

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.selftest import environment
from solidworks_mcp.version import __version__


@pytest.mark.asyncio
async def test_reads_solidworks_and_versions() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    env = await environment.read_environment(adapter, 2026)

    assert env["solidworks"]["revision"] == "34.0.0"
    assert env["solidworks"]["year"] == 2026
    assert env["solidworks"]["templates"]["part"]["file_name"] == "part.prtdot"
    assert env["solidworks_mcp"] == __version__
    assert env["python"]


@pytest.mark.asyncio
async def test_an_unreadable_solidworks_is_none_and_pywin32_may_be_missing(
    monkeypatch,
) -> None:
    class _Adapter:
        async def get_application_info(self):
            return AdapterResult(status=AdapterResultStatus.ERROR, error="busy")

    def _missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(environment.metadata, "version", _missing)

    env = await environment.read_environment(_Adapter(), None)

    assert env["solidworks"] == {
        "revision": None,
        "language": None,
        "year": None,
        "templates": {},
    }
    assert env["pywin32"] is None
