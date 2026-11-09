"""The mock adapter describes a fixed SolidWorks 2026 install."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_connected_mock_reports_fixed_values() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.get_application_info()

    assert result.is_success
    assert result.data["revision"] == "34.0.0"
    assert result.data["language"] == "english"
    assert result.data["templates"]["drawing"] == {
        "file_name": "drawing.drwdot",
        "exists": True,
    }


@pytest.mark.asyncio
async def test_disconnected_mock_says_so() -> None:
    result = await MockSolidWorksAdapter({}).get_application_info()

    assert not result.is_success
    assert result.error == "Not connected to SolidWorks"
