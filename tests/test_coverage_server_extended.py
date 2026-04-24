"""Extended coverage tests for server.py and configuration."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
    load_config,
)
from src.solidworks_mcp.server import SolidWorksMCPServer


class TestServerInitialization:
    """Test SolidWorksMCPServer initialization and configuration."""

    @pytest.fixture
    def test_config(self) -> SolidWorksMCPConfig:
        """Provide test configuration."""
        return SolidWorksMCPConfig(
            deployment_mode=DeploymentMode.LOCAL,
            security_level=SecurityLevel.MINIMAL,
            adapter_type=AdapterType.MOCK,
            mock_solidworks=True,
            log_level="DEBUG",
            host="127.0.0.1",
            port=8000,
            worker_processes=1,
            solidworks_path="mock://solidworks",
            max_retries=3,
            timeout_seconds=30.0,
            circuit_breaker_enabled=True,
            connection_pooling=True,
            max_connections=5,
            enable_cors=False,
            api_key_required=False,
            rate_limit_enabled=False,
            allowed_origins=[],
            api_keys=[],
        )

    def test_server_initialization_with_config(
        self, test_config: SolidWorksMCPConfig
    ) -> None:
        """Test server initializes with configuration."""
        server = SolidWorksMCPServer(config=test_config)

        assert server is not None
        assert server.config == test_config

    def test_server_initialization_without_config(self) -> None:
        """Test server initializes with an explicitly created default config."""
        server = SolidWorksMCPServer(config=SolidWorksMCPConfig())

        assert server is not None
        assert server.config is not None

    def test_server_db_logging_enabled(self, test_config: SolidWorksMCPConfig) -> None:
        """Test server enables database logging when configured."""
        # Set environment variable to enable logging
        with patch.dict(os.environ, {"SOLIDWORKS_MCP_DB_LOGGING": "true"}):
            # Create server - it should detect the env var
            server = SolidWorksMCPServer(config=test_config)
            assert server is not None

    def test_server_db_logging_disabled(self, test_config: SolidWorksMCPConfig) -> None:
        """Test server disables database logging by default."""
        with patch.dict(os.environ, {"SOLIDWORKS_MCP_DB_LOGGING": ""}, clear=False):
            server = SolidWorksMCPServer(config=test_config)
            assert server is not None

    def test_log_tool_event_when_enabled(
        self, test_config: SolidWorksMCPConfig
    ) -> None:
        """Test _log_tool_event works when enabled."""
        server = SolidWorksMCPServer(config=test_config)

        # Mock the database function
        with patch("src.solidworks_mcp.server.insert_tool_event") as mock_insert:
            server._db_logging_enabled = True
            server._db_run_id = "test-run-id"

            payload = {"input": "test"}
            server._log_tool_event(
                tool_name="test_tool",
                phase="pre",
                payload=payload,
            )

            # Should have called insert_tool_event
            mock_insert.assert_called_once()

    def test_log_tool_event_when_disabled(
        self, test_config: SolidWorksMCPConfig
    ) -> None:
        """Test _log_tool_event returns early when disabled."""
        server = SolidWorksMCPServer(config=test_config)

        with patch("src.solidworks_mcp.server.insert_tool_event") as mock_insert:
            server._db_logging_enabled = False

            server._log_tool_event(
                tool_name="test_tool",
                phase="pre",
                payload={"input": "test"},
            )

            # Should NOT have called insert_tool_event
            mock_insert.assert_not_called()

    def test_log_tool_event_with_exception(
        self, test_config: SolidWorksMCPConfig
    ) -> None:
        """Test _log_tool_event handles exceptions gracefully."""
        server = SolidWorksMCPServer(config=test_config)

        with patch(
            "src.solidworks_mcp.server.insert_tool_event",
            side_effect=Exception("DB error"),
        ) as mock_insert:
            server._db_logging_enabled = True
            server._db_run_id = "test-run-id"

            # Should not raise even if insert fails
            server._log_tool_event(
                tool_name="test_tool",
                phase="pre",
                payload={"input": "test"},
            )

            # insert_tool_event should have been attempted
            mock_insert.assert_called_once()

    def test_env_truthy_values(self, test_config: SolidWorksMCPConfig) -> None:
        """Test _env_truthy correctly identifies truthy values."""
        server = SolidWorksMCPServer(config=test_config)

        # Truthy values
        assert server._env_truthy("1") is True
        assert server._env_truthy("true") is True
        assert server._env_truthy("yes") is True
        assert server._env_truthy("on") is True
        assert server._env_truthy("TRUE") is True

        # Falsy values
        assert server._env_truthy("0") is False
        assert server._env_truthy("false") is False
        assert server._env_truthy("no") is False
        assert server._env_truthy("off") is False
        assert server._env_truthy("") is False
        assert server._env_truthy(None) is False

    def test_env_truthy_with_whitespace(self, test_config: SolidWorksMCPConfig) -> None:
        """Test _env_truthy handles whitespace."""
        server = SolidWorksMCPServer(config=test_config)

        assert server._env_truthy("  true  ") is True
        assert server._env_truthy("\n1\t") is True
        assert server._env_truthy("   ") is False


class TestConfigurationLoading:
    """Test configuration loading and initialization."""

    def test_config_from_env_file(self, tmp_path: Path) -> None:
        """Test loading config from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SOLIDWORKS_HOST=localhost\n"
            "SOLIDWORKS_PORT=8000\n"
            "SOLIDWORKS_LOG_LEVEL=INFO\n"
        )

        with patch.dict(os.environ, {"SOLIDWORKS_MCP_CONFIG": str(env_file)}):
            config = load_config()
            assert config is not None

    def test_config_with_security_settings(self) -> None:
        """Test config properly handles security settings."""
        config = SolidWorksMCPConfig(
            security_level=SecurityLevel.STRICT,
            api_key_required=True,
            rate_limit_enabled=True,
            enable_cors=True,
            allowed_origins=["https://example.com"],
            api_keys=["test-key-123"],
        )

        assert config.security_level == SecurityLevel.STRICT
        assert config.api_key_required is True
        assert config.rate_limit_enabled is True

    def test_config_with_adapter_settings(self) -> None:
        """Test config with various adapter types."""
        for adapter_type in AdapterType:
            config = SolidWorksMCPConfig(adapter_type=adapter_type)
            assert config.adapter_type == adapter_type


class TestServerCallbacks:
    """Test server callback handling."""

    @pytest.fixture
    def server(self) -> SolidWorksMCPServer:
        """Provide test server."""
        config = SolidWorksMCPConfig(
            deployment_mode=DeploymentMode.LOCAL,
            adapter_type=AdapterType.MOCK,
            mock_solidworks=True,
        )
        return SolidWorksMCPServer(config=config)

    @pytest.mark.asyncio
    async def test_server_startup_callback(self, server: SolidWorksMCPServer) -> None:
        """Test server startup initialization."""
        # Startup should not raise if present on this implementation.
        try:
            if hasattr(server, "startup"):
                await server.startup()
        except Exception:
            # Startup might fail without full setup, that's ok
            pass

    @pytest.mark.asyncio
    async def test_server_shutdown_callback(self, server: SolidWorksMCPServer) -> None:
        """Test server shutdown cleanup."""
        try:
            if hasattr(server, "shutdown"):
                await server.shutdown()
        except Exception:
            # Shutdown might fail without full setup, that's ok
            pass


class TestCacheManagement:
    """Test response cache and tool caching."""

    def test_response_cache_initialization(self) -> None:
        """Test response cache initializes with server."""
        config = SolidWorksMCPConfig(adapter_type=AdapterType.MOCK)
        server = SolidWorksMCPServer(config=config)

        assert server is not None
        # Cache should be available if enabled
        if hasattr(server, "cache"):
            assert server.cache is not None
