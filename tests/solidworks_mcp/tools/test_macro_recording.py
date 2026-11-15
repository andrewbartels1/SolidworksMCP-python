"""Tests for SolidWorks macro recording tools."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.tools.macro_recording import (
    MacroPlaybackInput,
    register_macro_recording_tools,
)


class TestMacroRecordingTools:
    """Test suite for macro recording tools."""

    @pytest.mark.asyncio
    async def test_register_macro_recording_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that macro recording tools register correctly."""
        tool_count = await register_macro_recording_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 1

    @pytest.mark.asyncio
    async def test_execute_macro_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful macro execution."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "macro_file": "batch_process.swp",
                    "execution_status": "Completed",
                    "execution_time": 12.3,
                    "operations_performed": 25,
                    "errors_encountered": 0,
                    "warnings_encountered": 2,
                    "output_files": [
                        "processed_part1.sldprt",
                        "processed_part2.sldprt",
                    ],
                    "log_file": "macro_execution_log.txt",
                },
                execution_time=12.3,
            )
        )

        input_data = MacroPlaybackInput(macro_file="batch_process.swp")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "execute_macro":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["execution_status"] == "Completed"
        assert result["data"]["operations_performed"] == 25
        assert result["data"]["errors_encountered"] == 0
        assert result["runs_completed"] == 1
        assert result["message"] == "Macro completed 1 run"
        mock_adapter.execute_macro.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_macro_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test execute_macro exception handling branch."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(side_effect=RuntimeError("engine down"))

        execute_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "execute_macro":
                execute_tool = tool.fn
                break

        assert execute_tool is not None
        result = await execute_tool(
            input_data=MacroPlaybackInput(macro_file="boom.swp", repeat_count=1)
        )

        assert result["status"] == "error"
        assert result["error_type"] == "internal"

    @pytest.mark.asyncio
    async def test_execute_macro_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test execute_macro adapter error return path."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(
            return_value=Mock(
                is_success=False, error="macro syntax error", execution_time=0.1
            )
        )

        execute_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "execute_macro":
                execute_tool = tool.fn
                break

        assert execute_tool is not None
        result = await execute_tool(
            input_data=MacroPlaybackInput(macro_file="bad.swp", repeat_count=1)
        )
        assert result["status"] == "error"
        assert "macro syntax error" in result["message"]
        assert "Run 1 of 1 failed after 0 completed" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_macro_fallback_refuses_without_running_anything(
        self, mcp_server, mock_config
    ):
        """execute_macro refuses without an adapter capability, regardless of
        repeat_count/pause_between_runs — it never fabricates run details or
        a "features_created" count for a macro that never ran."""
        await register_macro_recording_tools(mcp_server, object(), mock_config)

        execute_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "execute_macro":
                execute_tool = tool.fn
                break

        assert execute_tool is not None

        result = await execute_tool(
            input_data=MacroPlaybackInput(
                macro_file="fallback.swp",
                repeat_count=3,
                pause_between_runs=0.25,
            )
        )

        assert result["status"] == "error"
        assert "does not support execute_macro" in result["message"]


def _make_mcp():
    """Create a plain FastMCP instance."""
    mcp = FastMCP("test")
    return mcp


def _make_config():
    """Test make config."""

    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        adapter_type=AdapterType.MOCK,
        mock_solidworks=True,
    )


async def _get_tool(mcp, name: str):
    """Test get tool."""

    for tool in await mcp.list_tools():
        if tool.name == name:
            return tool.fn
    raise KeyError(f"Tool {name!r} not registered in list_tools()")


class TestMacroRecordingExceptionPaths:
    """Test macro recording exception paths."""

    @pytest.mark.asyncio
    async def test_execute_macro_exception(self):
        """Line 358 — exception in execute_macro."""
        from solidworks_mcp.tools.macro_recording import (
            MacroPlaybackInput,
            register_macro_recording_tools,
        )

        mcp = _make_mcp()
        adapter = MockSolidWorksAdapter({})
        adapter.execute_macro = AsyncMock(side_effect=RuntimeError("exec boom"))
        await register_macro_recording_tools(mcp, adapter, _make_config())

        fn = await _get_tool(mcp, "execute_macro")
        result = await fn(MacroPlaybackInput(macro_path="/tmp/m.swp"))
        assert result["status"] == "error"


@pytest.mark.parametrize("field", ["macro_path", "macro_file"])
@pytest.mark.parametrize(
    "path", ["C:/macros/build.vb", "build.bas", "macro.txt", "Sub main()"]
)
def test_playback_input_rejects_vba_source(field, path) -> None:
    with pytest.raises(ValueError, match=r"\.swp or \.swb"):
        MacroPlaybackInput(**{field: path})


@pytest.mark.parametrize("path", ["C:/macros/build.SWP", "legacy.swb"])
def test_playback_input_accepts_binary_macros(path) -> None:
    assert MacroPlaybackInput(macro_path=path).macro_path == path


@pytest.mark.asyncio
async def test_execute_macro_rejects_vb_before_reaching_the_adapter(
    mcp_server, mock_adapter, mock_config
) -> None:
    await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)
    mock_adapter.execute_macro = AsyncMock()
    tools = {t.name: t.fn for t in await mcp_server.list_tools()}

    result = await tools["execute_macro"]({"macro_path": "C:/macros/build.vb"})

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert ".swp" in result["message"]
    mock_adapter.execute_macro.assert_not_called()


@pytest.mark.asyncio
async def test_execute_macro_repeats_and_pauses(mcp_server, mock_adapter, monkeypatch):
    """repeat_count runs the macro that many times, pausing between runs."""
    await register_macro_recording_tools(mcp_server, mock_adapter, {})
    mock_adapter.execute_macro = AsyncMock(
        return_value=Mock(is_success=True, data={"errors": 0}, execution_time=0.5)
    )
    pauses: list[float] = []

    async def _sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr("solidworks_mcp.tools.macro_recording.asyncio.sleep", _sleep)
    tool = next(
        t.fn for t in await mcp_server.list_tools() if t.name == "execute_macro"
    )

    result = await tool(
        input_data={"macro_path": "m.swp", "repeat_count": 3, "pause_between_runs": 2}
    )

    assert result["runs_completed"] == 3
    assert result["message"] == "Macro completed 3 runs"
    assert result["execution_time"] == 1.5
    assert mock_adapter.execute_macro.await_count == 3
    assert pauses == [2, 2]


@pytest.mark.asyncio
async def test_execute_macro_stops_at_the_first_failed_run(mcp_server, mock_adapter):
    """The second of three runs fails: no third run, and the count is reported."""
    await register_macro_recording_tools(mcp_server, mock_adapter, {})
    ok = Mock(is_success=True, data={}, execution_time=0.5)
    bad = Mock(is_success=False, error="boom", data=None, execution_time=0.25)
    mock_adapter.execute_macro = AsyncMock(side_effect=[ok, bad, ok])
    tool = next(
        t.fn for t in await mcp_server.list_tools() if t.name == "execute_macro"
    )

    result = await tool(input_data={"macro_path": "m.swp", "repeat_count": 3})

    assert result["status"] == "error"
    assert "Run 2 of 3 failed after 1 completed: boom" in result["message"]
    assert result["execution_time"] == 0.75
    assert mock_adapter.execute_macro.await_count == 2


@pytest.mark.asyncio
async def test_execute_macro_refuses_removed_inputs_and_bad_counts(
    mcp_server, mock_adapter
):
    await register_macro_recording_tools(mcp_server, mock_adapter, {})
    mock_adapter.execute_macro = AsyncMock()
    tool = next(
        t.fn for t in await mcp_server.list_tools() if t.name == "execute_macro"
    )

    removed = await tool(input_data={"macro_path": "m.swp", "target_file": "a.sldprt"})
    too_many = await tool(input_data={"macro_path": "m.swp", "repeat_count": 101})

    assert removed["error_type"] == "invalid_input"
    assert "open_model" in removed["message"]
    assert too_many["error_type"] == "invalid_input"
    mock_adapter.execute_macro.assert_not_awaited()
