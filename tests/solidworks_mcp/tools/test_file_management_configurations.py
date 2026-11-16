"""The configuration tools (spec: tools/configurations)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from solidworks_mcp.tools.file_management import (
    ConfigurationNameInput,
    CreateConfigurationInput,
    register_file_management_tools,
)


async def _tools(mcp_server: Any, adapter: Any, config: Any) -> dict[str, Any]:
    await register_file_management_tools(mcp_server, adapter, config)
    return {t.name: t.fn for t in await mcp_server.list_tools()}


@pytest.mark.asyncio
async def test_create_activate_list_delete(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    await mock_adapter.create_part()
    tools = await _tools(mcp_server, mock_adapter, mock_config)

    made = await tools["create_configuration"](CreateConfigurationInput(name="Long"))
    shown = await tools["activate_configuration"](ConfigurationNameInput(name="Long"))
    listed = await tools["list_configurations"]()
    back = await tools["activate_configuration"](ConfigurationNameInput(name="Default"))
    deleted = await tools["delete_configuration"](ConfigurationNameInput(name="Long"))

    assert made["message"] == "Added configuration Long"
    assert (shown["active"], shown["previous"]) == ("Long", "Default")
    assert (listed["configurations"], listed["active"]) == (["Default", "Long"], "Long")
    assert back["active"] == "Default"
    assert (deleted["deleted"], deleted["configurations"]) == ("Long", ["Default"])


@pytest.mark.asyncio
async def test_list_without_an_active_reader(mcp_server: Any, mock_config: Any) -> None:
    class _ListsOnly:
        async def list_configurations(self) -> Any:
            from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=["Default"])

    tools = await _tools(mcp_server, _ListsOnly(), mock_config)

    listed = await tools["list_configurations"]()

    assert (listed["configurations"], listed["active"]) == (["Default"], None)


@pytest.mark.asyncio
async def test_list_when_the_active_read_fails(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    await mock_adapter.create_part()
    tools = await _tools(mcp_server, mock_adapter, mock_config)
    mock_adapter._current_model, model = None, mock_adapter._current_model

    async def _listed() -> Any:
        from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=["Default"])

    mock_adapter.list_configurations = _listed

    listed = await tools["list_configurations"]()

    assert listed["active"] is None
    mock_adapter._current_model = model


@pytest.mark.asyncio
async def test_errors(mcp_server: Any, mock_adapter: Any, mock_config: Any) -> None:
    await mock_adapter.create_part()
    tools = await _tools(mcp_server, mock_adapter, mock_config)

    deleted = await tools["delete_configuration"](
        ConfigurationNameInput(name="Default")
    )
    unknown = await tools["activate_configuration"](
        ConfigurationNameInput(name="Ghost")
    )
    duplicate = await tools["create_configuration"](
        CreateConfigurationInput(name="Default")
    )

    assert [r["status"] for r in (deleted, unknown, duplicate)] == ["error"] * 3


@pytest.mark.parametrize("model", [CreateConfigurationInput, ConfigurationNameInput])
def test_a_blank_name_is_refused(model: Any) -> None:
    with pytest.raises((ValueError, ValidationError), match="name is required"):
        model(name="  ")
