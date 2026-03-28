"""
Tests for SolidWorks MCP Server and configuration.

Comprehensive test suite covering server lifecycle, configuration loading,
security setup, tool registration, and health monitoring.
"""

import os
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
    load_config,
)
from src.solidworks_mcp.exceptions import SolidWorksMCPError
from src.solidworks_mcp.server import (
    MCPServerState,
    SolidWorksMCPServer,
    list_capabilities,
    main,
    server_status,
)


class TestSolidWorksMCPConfig:
    """Test suite for configuration management."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SolidWorksMCPConfig()

        assert config.deployment_mode == DeploymentMode.LOCAL
        assert config.security_level == SecurityLevel.STANDARD
        assert config.adapter_type == AdapterType.PYWIN32
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.log_level == "INFO"
        assert config.mock_solidworks is False
        assert config.max_retries == 3
        assert config.timeout_seconds == 30.0

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config should pass
        config = SolidWorksMCPConfig(
            port=8080,
            max_retries=5,
            timeout_seconds=60.0,
        )
        assert config.port == 8080

        # Invalid port should raise error
        with pytest.raises(ValueError):
            SolidWorksMCPConfig(port=99999)  # Port out of range

        # Invalid timeout should raise error
        with pytest.raises(ValueError):
            SolidWorksMCPConfig(timeout_seconds=-1.0)

    def test_config_from_env(self):
        """Test loading configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                "SOLIDWORKS_MCP_PORT": "9000",
                "SOLIDWORKS_MCP_LOG_LEVEL": "DEBUG",
                "SOLIDWORKS_MCP_MOCK_SOLIDWORKS": "true",
                "SOLIDWORKS_MCP_SECURITY_LEVEL": "strict",
            },
        ):
            config = SolidWorksMCPConfig.from_env()

            assert config.port == 9000
            assert config.log_level == "DEBUG"
            assert config.mock_solidworks is True
            assert config.security_level == SecurityLevel.STRICT

    def test_config_to_dict(self):
        """Test configuration serialization."""
        config = SolidWorksMCPConfig(port=8080)
        config_dict = config.model_dump()

        assert isinstance(config_dict, dict)
        assert config_dict["port"] == 8080
        assert "deployment_mode" in config_dict

    def test_load_config_from_file(self, temp_dir):
        """Test loading configuration from file."""
        config_file = temp_dir / "test_config.json"
        config_data = {
            "deployment_mode": "remote",
            "port": 8080,
            "log_level": "DEBUG",
            "mock_solidworks": True,
        }

        with open(config_file, "w") as f:
            import json

            json.dump(config_data, f)

        config = load_config(str(config_file))

        assert config.deployment_mode == DeploymentMode.REMOTE
        assert config.port == 8080
        assert config.log_level == "DEBUG"
        assert config.mock_solidworks is True

    def test_config_testing_defaults_and_helpers(self):
        """Test testing-mode defaults and helper config getters."""
        config = SolidWorksMCPConfig(
            testing=True,
            debug=True,
            api_key="secret-value",
            enable_cors=True,
            cors_origins=["http://localhost:3000"],
            allowed_hosts=["localhost"],
            rate_limit_per_minute=120,
        )

        # model_post_init should force mock adapter defaults in testing mode.
        assert config.mock_solidworks is True
        assert config.adapter_type == AdapterType.MOCK

        db_config = config.get_database_config()
        assert db_config["url"] == config.database_url
        assert db_config["echo"] is True

        security_config = config.get_security_config()
        assert security_config["api_key"] == "secret-value"
        assert security_config["enable_cors"] is True
        assert security_config["cors_origins"] == ["http://localhost:3000"]
        assert security_config["allowed_hosts"] == ["localhost"]
        assert security_config["rate_limit_per_minute"] == 120

    def test_from_env_with_env_file_overrides(self, temp_dir):
        """Test loading env file values and overriding with process env vars."""
        env_file = temp_dir / "solidworks.env"
        env_file.write_text(
            "\n".join(
                [
                    "SOLIDWORKS_MCP_PORT=9001",
                    "SOLIDWORKS_MCP_LOG_LEVEL=WARNING",
                    "SOLIDWORKS_MCP_ENABLE_CORS=true",
                    'SOLIDWORKS_MCP_CORS_ORIGINS=["http://env-file"]',
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "SOLIDWORKS_MCP_PORT": "9002",
                "SOLIDWORKS_MCP_LOG_LEVEL": "DEBUG",
            },
            clear=False,
        ):
            config = SolidWorksMCPConfig.from_env(str(env_file))

        # Process environment should override values loaded from env_file.
        assert config.port == 9002
        assert config.log_level == "DEBUG"
        assert config.enable_cors is True
        assert config.cors_origins == ["http://env-file"]

    def test_load_config_non_json_uses_from_env(self, temp_dir):
        """Test non-JSON config path delegates to from_env."""
        env_path = temp_dir / "settings.env"

        expected = SolidWorksMCPConfig(port=8123)
        with patch.object(
            SolidWorksMCPConfig, "from_env", return_value=expected
        ) as mock_from_env:
            loaded = load_config(str(env_path))

        assert loaded.port == 8123
        mock_from_env.assert_called_once_with(str(env_path))


class TestMCPServerState:
    """Test suite for server state management."""

    def test_server_state_initialization(self, mock_config):
        """Test server state initialization."""
        state = MCPServerState(config=mock_config)

        assert state.config == mock_config
        assert state.adapter is None
        assert state.agent is None
        assert state.is_connected is False
        assert state.startup_time is None
        assert state.tool_count == 0

    def test_server_state_updates(self, mock_config, mock_adapter):
        """Test server state updates."""
        state = MCPServerState(config=mock_config)

        # Update state
        state.adapter = mock_adapter
        state.is_connected = True
        state.tool_count = 42
        state.startup_time = "2024-01-01T10:00:00Z"

        assert state.adapter == mock_adapter
        assert state.is_connected is True
        assert state.tool_count == 42
        assert state.startup_time == "2024-01-01T10:00:00Z"


class TestSolidWorksMCPServer:
    """Test suite for the main MCP server."""

    def test_server_initialization(self, mock_config):
        """Test server initialization."""
        server = SolidWorksMCPServer(mock_config)

        assert server.config == mock_config
        assert isinstance(server.state, MCPServerState)
        assert server.state.config == mock_config
        assert server.mcp is not None
        assert server.server is None
        assert server._setup_complete is False

    @pytest.mark.asyncio
    async def test_server_setup(self, mock_config):
        """Test server setup process."""
        server = SolidWorksMCPServer(mock_config)

        # Mock dependencies
        with patch("src.solidworks_mcp.utils.validate_environment") as mock_validate:
            with patch("src.solidworks_mcp.security.setup_security") as mock_security:
                with patch(
                    "src.solidworks_mcp.adapters.create_adapter"
                ) as mock_create_adapter:
                    with patch(
                        "src.solidworks_mcp.tools.register_tools"
                    ) as mock_register_tools:
                        mock_validate.return_value = None
                        mock_security.return_value = None
                        mock_create_adapter.return_value = Mock()
                        mock_register_tools.return_value = 42

                        await server.setup()

                        assert server._setup_complete is True
                        assert server.state.tool_count == 42
                        assert server.state.adapter is not None
                        assert server.server is not None

                        # Verify setup calls
                        mock_validate.assert_called_once()
                        mock_security.assert_called_once()
                        mock_create_adapter.assert_called_once()
                        mock_register_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_setup_idempotent(self, mock_config):
        """Test that setup can be called multiple times safely."""
        server = SolidWorksMCPServer(mock_config)

        with patch("src.solidworks_mcp.utils.validate_environment"):
            with patch("src.solidworks_mcp.security.setup_security"):
                with patch(
                    "src.solidworks_mcp.adapters.create_adapter"
                ) as mock_create_adapter:
                    with patch("src.solidworks_mcp.tools.register_tools"):
                        mock_create_adapter.return_value = Mock()

                        # First setup
                        await server.setup()
                        first_call_count = mock_create_adapter.call_count

                        # Second setup should not call dependencies again
                        await server.setup()
                        assert mock_create_adapter.call_count == first_call_count

    @pytest.mark.asyncio
    async def test_server_health_check(self, solidworks_server):
        """Test server health check functionality."""
        health = await solidworks_server.health_check()

        assert isinstance(health, dict)
        assert "status" in health
        assert "config" in health
        assert "state" in health

        # Check config section
        config_section = health["config"]
        assert "deployment_mode" in config_section
        assert "adapter_type" in config_section
        assert "security_level" in config_section
        assert "platform" in config_section

        # Check state section
        state_section = health["state"]
        assert "connected" in state_section
        assert "tool_count" in state_section

    @pytest.mark.asyncio
    async def test_server_stop(self, mock_config):
        """Test server stop functionality."""
        server = SolidWorksMCPServer(mock_config)

        # Setup server
        mock_adapter = Mock()
        mock_adapter.disconnect = AsyncMock()

        with patch("src.solidworks_mcp.utils.validate_environment"):
            with patch("src.solidworks_mcp.security.setup_security"):
                with patch(
                    "src.solidworks_mcp.adapters.create_adapter",
                    return_value=mock_adapter,
                ):
                    with patch(
                        "src.solidworks_mcp.tools.register_tools", return_value=10
                    ):
                        await server.setup()

        # Server should be set up
        assert server._setup_complete is True

        # Stop server
        await server.stop()

        # Verify cleanup
        mock_adapter.disconnect.assert_called_once()
        assert server.state.is_connected is False
        assert server._setup_complete is False

    @pytest.mark.asyncio
    async def test_server_local_mode_start(self, mock_config):
        """Test server starting in local mode."""
        mock_config.deployment_mode = DeploymentMode.LOCAL
        server = SolidWorksMCPServer(mock_config)

        with patch.object(server, "setup") as mock_setup:
            with patch.object(server, "_run_local_stdio") as mock_run_stdio:
                mock_setup.return_value = None
                mock_run_stdio.return_value = None

                # This would normally block, so we patch it
                await server.start()

                mock_setup.assert_called_once()
                mock_run_stdio.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_remote_mode_start(self, strict_config):
        """Test server starting in remote mode."""
        strict_config.deployment_mode = DeploymentMode.REMOTE
        server = SolidWorksMCPServer(strict_config)

        with patch.object(server, "setup") as mock_setup:
            with patch.object(server, "_start_http_server") as mock_start_http:
                mock_setup.return_value = None
                mock_start_http.return_value = None

                await server.start()

                mock_setup.assert_called_once()
                mock_start_http.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_connection_failure_handling(self, mock_config):
        """Test server handling of connection failures."""
        server = SolidWorksMCPServer(mock_config)

        # Mock adapter that fails to connect
        mock_adapter = Mock()
        mock_adapter.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("src.solidworks_mcp.utils.validate_environment"):
            with patch("src.solidworks_mcp.security.setup_security"):
                with patch(
                    "src.solidworks_mcp.adapters.create_adapter",
                    return_value=mock_adapter,
                ):
                    with patch(
                        "src.solidworks_mcp.tools.register_tools", return_value=5
                    ):
                        with patch.object(server, "_start_http_server"):
                            # Server should start despite adapter connection failure
                            await server.start()

                            # Server should be running but not connected
                            assert server.state.adapter is not None
                            assert server.state.is_connected is False

    @pytest.mark.asyncio
    async def test_setup_agent_testing_mode_disables_agent(self):
        """Test that testing/mock mode skips PydanticAI agent setup."""
        config = SolidWorksMCPConfig(testing=True, mock_solidworks=True)
        server = SolidWorksMCPServer(config)

        await server._setup_agent()
        assert server.agent is None

    @pytest.mark.asyncio
    async def test_setup_agent_fallback_without_fastmcp_toolset(self):
        """Test agent fallback path when FastMCP toolset integration is unavailable."""
        config = SolidWorksMCPConfig(testing=False, mock_solidworks=False)
        server = SolidWorksMCPServer(config)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("src.solidworks_mcp.server.FastMCPToolset", None):
                with patch("src.solidworks_mcp.server.Agent") as mock_agent:
                    await server._setup_agent()

        mock_agent.assert_called_once()
        assert server.agent is mock_agent.return_value

    @pytest.mark.asyncio
    async def test_setup_agent_with_fastmcp_toolset(self):
        """Test direct FastMCP toolset binding path for the PydanticAI agent."""
        config = SolidWorksMCPConfig(testing=False, mock_solidworks=False)
        server = SolidWorksMCPServer(config)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("src.solidworks_mcp.server.FastMCPToolset") as mock_toolset:
                with patch("src.solidworks_mcp.server.Agent") as mock_agent:
                    mock_toolset.return_value = "toolset"
                    await server._setup_agent()

        mock_toolset.assert_called_once_with(server.mcp)
        assert mock_agent.call_args.kwargs["toolsets"] == ["toolset"]
        assert server.agent is mock_agent.return_value

    @pytest.mark.asyncio
    async def test_setup_agent_without_openai_key_skips_agent(self):
        """Test that missing OpenAI credentials disables agent setup cleanly."""
        config = SolidWorksMCPConfig(testing=False, mock_solidworks=False)
        server = SolidWorksMCPServer(config)

        with patch.dict(os.environ, {}, clear=True):
            with patch("src.solidworks_mcp.server.Agent") as mock_agent:
                await server._setup_agent()

        mock_agent.assert_not_called()
        assert server.agent is None

    @pytest.mark.asyncio
    async def test_run_local_stdio_with_sync_runner(self):
        """Test stdio startup using synchronous run_stdio method."""
        config = SolidWorksMCPConfig(mock_solidworks=False)
        server = SolidWorksMCPServer(config)

        sync_runner = Mock(return_value=None)
        server.server = SimpleNamespace(run_stdio=sync_runner)

        await server._run_local_stdio()
        sync_runner.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_local_stdio_with_async_runner(self):
        """Test stdio startup using async run_stdio_async fallback."""
        config = SolidWorksMCPConfig(mock_solidworks=False)
        server = SolidWorksMCPServer(config)

        async_runner = AsyncMock()
        server.server = SimpleNamespace(run_stdio_async=async_runner)

        await server._run_local_stdio()
        async_runner.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_local_stdio_mock_mode_without_stdin(self, monkeypatch):
        """Test mock mode early return when stdin is unavailable."""
        config = SolidWorksMCPConfig(mock_solidworks=True)
        server = SolidWorksMCPServer(config)

        sync_runner = Mock(return_value=None)
        server.server = SimpleNamespace(run_stdio=sync_runner)
        monkeypatch.setattr("src.solidworks_mcp.server.sys.stdin", None)

        await server._run_local_stdio()
        sync_runner.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_local_stdio_raises_when_no_runner(self):
        """Test error path when server exposes no stdio transport runner."""
        config = SolidWorksMCPConfig(mock_solidworks=False)
        server = SolidWorksMCPServer(config)
        server.server = SimpleNamespace()

        with pytest.raises(SolidWorksMCPError):
            await server._run_local_stdio()

    @pytest.mark.asyncio
    async def test_patch_mcp_for_tests_compat_runner_data_mapping(self, mock_config):
        """Test compat wrapper adds inferred data payload for legacy test calls."""
        server = SolidWorksMCPServer(mock_config)

        @server.mcp.tool()
        async def sample_with_input(payload):
            """Test helper for sample with input."""
            return {"status": "success", "message": "ok", "result": {"x": 1}}

        @server.mcp.tool()
        async def sample_no_args():
            """Test helper for sample no args."""
            return {"status": "success", "message": "ok", "value": 7}

        by_name = {tool.name: tool.handler for tool in server.mcp._tools}

        with_input = await by_name["sample_with_input"](input_data={"a": 1})
        assert with_input["data"] == {"x": 1}

        no_args = await by_name["sample_no_args"]()
        assert no_args["data"] == 7


@pytest.mark.asyncio
async def test_server_status_and_capabilities_helpers():
    """Test helper endpoints return structured response payloads."""
    status = await server_status()
    assert "status" in status
    assert "message" in status

    capabilities = await list_capabilities()
    assert "modeling" in capabilities
    assert "automation" in capabilities
    assert "create_part" in capabilities["modeling"]


def test_create_server_uses_loader_when_config_missing():
    """Test create_server loads configuration when none is provided."""
    with patch("src.solidworks_mcp.server.load_config") as mock_load:
        mock_load.return_value = SolidWorksMCPConfig(port=9123)
        server = SolidWorksMCPServer(mock_load.return_value)

        with patch(
            "src.solidworks_mcp.server.SolidWorksMCPServer", return_value=server
        ):
            created = __import__(
                "src.solidworks_mcp.server", fromlist=["create_server"]
            ).create_server()

    mock_load.assert_called_once_with()
    assert created.config.port == 9123


def test_run_server_exits_on_unhandled_exception():
    """Test synchronous entrypoint exits with status 1 on fatal errors."""
    with patch(
        "src.solidworks_mcp.server.asyncio.run", side_effect=RuntimeError("boom")
    ):
        with patch("src.solidworks_mcp.server.sys.exit") as mock_exit:
            from src.solidworks_mcp.server import run_server

            run_server()

    mock_exit.assert_called_once_with(1)


class TestServerIntegration:
    """Integration tests for server components."""

    @pytest.mark.asyncio
    async def test_full_server_lifecycle(self, mock_config):
        """Test complete server lifecycle from setup to shutdown."""
        server = SolidWorksMCPServer(mock_config)

        # Setup
        await server.setup()
        assert server._setup_complete is True
        assert server.state.tool_count > 0

        # Health check
        health = await server.health_check()
        assert health["status"] in ["healthy", "warning"]

        # Cleanup
        await server.stop()
        assert server._setup_complete is False

    @pytest.mark.asyncio
    async def test_server_with_all_tools(self, mock_config):
        """Test server with all tool categories registered."""
        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Should have tools from all categories
        expected_min_tools = 30  # Rough estimate based on our tool implementations
        assert server.state.tool_count >= expected_min_tools

        # Health check should show all components
        health = await server.health_check()
        assert health["state"]["tool_count"] >= expected_min_tools

    @pytest.mark.asyncio
    async def test_server_error_recovery(self, mock_config):
        """Test server error recovery capabilities."""
        server = SolidWorksMCPServer(mock_config)

        # Setup with some components failing
        with patch("src.solidworks_mcp.adapters.create_adapter") as mock_create_adapter:
            # First call fails, second succeeds
            mock_create_adapter.side_effect = [
                RuntimeError("First attempt failed"),
                Mock(),
            ]

            with patch("src.solidworks_mcp.utils.validate_environment"):
                with patch("src.solidworks_mcp.security.setup_security"):
                    with patch(
                        "src.solidworks_mcp.tools.register_tools", return_value=10
                    ):
                        # First setup attempt should fail
                        with pytest.raises(RuntimeError):
                            await server.setup()

                        # Server should still be able to retry setup
                        server._setup_complete = False
                        await server.setup()
                        assert server._setup_complete is True

    @pytest.mark.asyncio
    async def test_server_performance(self, mock_config, perf_monitor):
        """Test server performance characteristics."""
        server = SolidWorksMCPServer(mock_config)

        # Setup should complete quickly
        perf_monitor.start()
        await server.setup()
        perf_monitor.stop()

        perf_monitor.assert_max_time(5.0)  # Setup should be fast

        # Health check should be very fast
        perf_monitor.start()
        health = await server.health_check()
        perf_monitor.stop()

        assert health is not None
        perf_monitor.assert_max_time(0.1)  # Health check should be instant


class TestServerCompatRunnerEdgeCases:
    """Branch coverage for server _patch_mcp_for_tests compat runner."""

    @pytest.mark.asyncio
    async def test_compat_runner_multiple_items_one_dict(self, mock_config):
        """result with multiple payload items but only one dict value → data = that dict."""
        server = SolidWorksMCPServer(mock_config)

        @server.mcp.tool()
        async def multi_one_dict(payload):
            # Returns two non-dict items and one dict item
            """Test helper for multi one dict."""
            return {
                "status": "success",
                "message": "ok",
                "count": 3,
                "details": {"key": "value"},
            }

        by_name = {tool.name: tool.handler for tool in server.mcp._tools}
        result = await by_name["multi_one_dict"](input_data={})
        assert result["data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_compat_runner_multiple_items_multiple_dicts(self, mock_config):
        """result with multiple dict payload items → data = full payload_items dict."""
        server = SolidWorksMCPServer(mock_config)

        @server.mcp.tool()
        async def multi_many_dicts(payload):
            """Test helper for multi many dicts."""
            return {
                "status": "success",
                "message": "ok",
                "part_a": {"x": 1},
                "part_b": {"y": 2},
            }

        by_name = {tool.name: tool.handler for tool in server.mcp._tools}
        result = await by_name["multi_many_dicts"](input_data={})
        # data should be the payload_items dict when multiple dicts exist
        assert "part_a" in result["data"]
        assert "part_b" in result["data"]

    @pytest.mark.asyncio
    async def test_compat_runner_result_already_has_data_field(self, mock_config):
        """result that already includes 'data' key is not modified."""
        server = SolidWorksMCPServer(mock_config)

        @server.mcp.tool()
        async def with_data_key(payload):
            """Test helper for with data key."""
            return {"status": "success", "message": "ok", "data": {"existing": True}}

        by_name = {tool.name: tool.handler for tool in server.mcp._tools}
        result = await by_name["with_data_key"](input_data={})
        assert result["data"] == {"existing": True}

    @pytest.mark.asyncio
    async def test_compat_runner_single_param_without_payload(self, mock_config):
        """Covers fallback branch when single-arg tool is called without input_data."""
        server = SolidWorksMCPServer(mock_config)

        @server.mcp.tool()
        async def takes_one(payload):
            """Test helper for takes one."""
            return {
                "status": "success",
                "message": "ok",
                "payload": payload,
            }

        by_name = {tool.name: tool.handler for tool in server.mcp._tools}
        result = await by_name["takes_one"](payload={"x": 1})
        assert result["status"] == "success"
        assert result["data"] == {"x": 1}


def test_run_server_keyboard_interrupt_is_silent():
    """KeyboardInterrupt in run_server should not call sys.exit."""
    with patch(
        "src.solidworks_mcp.server.asyncio.run", side_effect=KeyboardInterrupt()
    ):
        with patch("src.solidworks_mcp.server.sys.exit") as mock_exit:
            from src.solidworks_mcp.server import run_server

            run_server()

    mock_exit.assert_not_called()


class TestServerMainEntrypoint:
    """Coverage for main coroutine argument and exception branches."""

    @pytest.mark.asyncio
    async def test_main_applies_cli_overrides_and_starts(self):
        """Test main applies cli overrides and starts."""
        cfg = SolidWorksMCPConfig()
        server_inst = Mock()
        server_inst.start = AsyncMock()
        server_inst.stop = AsyncMock()

        args = Namespace(
            config="cfg.env",
            mode="remote",
            host="0.0.0.0",
            port=9001,
            debug=True,
            mock=True,
        )

        with patch("argparse.ArgumentParser.parse_args", return_value=args):
            with patch("src.solidworks_mcp.server.load_config", return_value=cfg):
                with patch("src.solidworks_mcp.server.utils.setup_logging"):
                    with patch(
                        "src.solidworks_mcp.server.SolidWorksMCPServer",
                        return_value=server_inst,
                    ):
                        await main()

        assert cfg.deployment_mode == DeploymentMode.REMOTE
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9001
        assert cfg.debug is True
        assert cfg.log_level == "DEBUG"
        assert cfg.mock_solidworks is True
        server_inst.start.assert_called_once()
        server_inst.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_handles_keyboard_interrupt(self):
        """Test main handles keyboard interrupt."""
        cfg = SolidWorksMCPConfig()
        server_inst = Mock()
        server_inst.start = AsyncMock(side_effect=KeyboardInterrupt())
        server_inst.stop = AsyncMock()

        args = Namespace(
            config=None,
            mode=None,
            host="localhost",
            port=8000,
            debug=False,
            mock=False,
        )

        with patch("argparse.ArgumentParser.parse_args", return_value=args):
            with patch("src.solidworks_mcp.server.load_config", return_value=cfg):
                with patch("src.solidworks_mcp.server.utils.setup_logging"):
                    with patch(
                        "src.solidworks_mcp.server.SolidWorksMCPServer",
                        return_value=server_inst,
                    ):
                        await main()

        server_inst.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_reraises_non_keyboard_exception(self):
        """Test main reraises non keyboard exception."""
        cfg = SolidWorksMCPConfig()
        server_inst = Mock()
        server_inst.start = AsyncMock(side_effect=RuntimeError("boom"))
        server_inst.stop = AsyncMock()

        args = Namespace(
            config=None,
            mode=None,
            host="localhost",
            port=8000,
            debug=False,
            mock=False,
        )

        with patch("argparse.ArgumentParser.parse_args", return_value=args):
            with patch("src.solidworks_mcp.server.load_config", return_value=cfg):
                with patch("src.solidworks_mcp.server.utils.setup_logging"):
                    with patch(
                        "src.solidworks_mcp.server.SolidWorksMCPServer",
                        return_value=server_inst,
                    ):
                        with pytest.raises(RuntimeError, match="boom"):
                            await main()

        server_inst.stop.assert_called_once()
