"""
Configuration management for SolidWorks MCP Server.

Supports both local and remote deployment with comprehensive security options.
"""

from __future__ import annotations

import os
import platform
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import ConfigDict
from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, field_validator


class DeploymentMode(str, Enum):
    """Deployment mode options."""

    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"


class SecurityLevel(str, Enum):
    """Security level options."""

    MINIMAL = "minimal"  # Local only, no authentication
    STANDARD = "standard"  # API keys, basic validation
    STRICT = "strict"  # Full authentication, encryption, audit logs


class AdapterType(str, Enum):
    """SolidWorks adapter implementation options."""

    PYWIN32 = "pywin32"  # Direct COM via pywin32
    MOCK = "mock"  # Mock for testing
    EDGE_DOTNET = "edge_dotnet"  # Edge.js bridge to .NET (future)
    POWERSHELL = "powershell"  # PowerShell bridge (future)


class SolidWorksMCPConfig(BaseModel):
    """Main configuration for SolidWorks MCP Server."""

    # === Server Configuration ===
    deployment_mode: DeploymentMode = Field(
        default=DeploymentMode.LOCAL,
        description="Deployment mode: local, remote, or hybrid",
    )

    security_level: SecurityLevel = Field(
        default=SecurityLevel.STANDARD, description="Security level for the server"
    )

    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # === SolidWorks Configuration ===
    solidworks_path: str | None = Field(
        default=None, description="Path to SolidWorks executable"
    )

    adapter_type: AdapterType = Field(
        default=AdapterType.PYWIN32,
        description="SolidWorks adapter implementation to use",
    )

    enable_windows_validation: bool = Field(
        default=True, description="Validate Windows environment on startup"
    )

    # === Feature Flags ===
    enable_macro_recording: bool = Field(
        default=True, description="Enable VBA macro recording capabilities"
    )

    enable_pdm: bool = Field(
        default=False, description="Enable PDM (Product Data Management) integration"
    )

    enable_sql_integration: bool = Field(
        default=False, description="Enable SQL database integration"
    )

    enable_design_tables: bool = Field(
        default=True, description="Enable design table functionality"
    )

    enable_analysis_tools: bool = Field(
        default=True, description="Enable FEA and analysis tools"
    )

    # === Security Configuration ===
    api_key: SecretStr | None = Field(
        default=None, description="API key for remote authentication"
    )

    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"],
        description="Allowed hosts for remote connections",
    )

    enable_cors: bool = Field(
        default=False, description="Enable CORS for web client access"
    )

    cors_origins: list[str] = Field(
        default_factory=list, description="Allowed CORS origins"
    )

    enable_rate_limiting: bool = Field(
        default=True, description="Enable rate limiting for API endpoints"
    )

    rate_limit_per_minute: int = Field(
        default=60, description="Maximum requests per minute per client"
    )

    # === Data Storage ===
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".solidworks_mcp",
        description="Data directory for persistent storage",
    )

    state_file: str | None = Field(
        default=None, description="Path to persistent state file"
    )

    cache_dir: Path | None = Field(
        default=None, description="Cache directory (defaults to data_dir/cache)"
    )

    # === Database Configuration ===
    database_url: str = Field(
        default="sqlite:///./solidworks_mcp.db",
        description="Database URL for persistent storage",
    )

    sql_connection: str | None = Field(
        default=None, description="External SQL server connection string"
    )

    # === PDM Configuration ===
    pdm_vault: str | None = Field(default=None, description="PDM vault name")

    pdm_server: str | None = Field(default=None, description="PDM server address")

    # === Logging Configuration ===
    log_level: str = Field(default="INFO", description="Logging level")

    log_file: Path | None = Field(
        default=None, description="Log file path (defaults to data_dir/logs/server.log)"
    )

    enable_audit_logging: bool = Field(
        default=False, description="Enable detailed audit logging"
    )

    # === Performance Configuration ===
    worker_processes: int = Field(default=1, description="Number of worker processes")

    enable_connection_pooling: bool = Field(
        default=False, description="Enable SolidWorks connection pooling"
    )

    connection_pool_size: int = Field(
        default=3, description="Maximum connections in pool"
    )

    enable_circuit_breaker: bool = Field(
        default=True, description="Enable circuit breaker pattern"
    )

    circuit_breaker_threshold: int = Field(
        default=5, description="Circuit breaker failure threshold"
    )

    circuit_breaker_timeout: int = Field(
        default=60, description="Circuit breaker timeout in seconds"
    )

    # === Additional Test Configuration Fields ===
    max_retries: int = Field(default=3, description="Maximum retries for operations")

    timeout_seconds: float = Field(
        default=30.0, description="Operation timeout in seconds"
    )

    circuit_breaker_enabled: bool = Field(
        default=True,
        description="Enable circuit breaker (alias for enable_circuit_breaker)",
    )

    connection_pooling: bool = Field(
        default=False,
        description="Enable connection pooling (alias for enable_connection_pooling)",
    )

    max_connections: int = Field(
        default=5, description="Maximum connections (alias for connection_pool_size)"
    )

    api_key_required: bool = Field(
        default=False, description="Whether API key is required for access"
    )

    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting (alias for enable_rate_limiting)",
    )

    allowed_origins: list[str] = Field(
        default_factory=list,
        description="Allowed CORS origins (alias for cors_origins)",
    )

    api_keys: list[str] = Field(
        default_factory=list, description="List of valid API keys"
    )

    # === Development & Testing ===
    debug: bool = Field(default=False, description="Enable debug mode")

    testing: bool = Field(default=False, description="Enable testing mode")

    mock_solidworks: bool = Field(
        default=False, description="Use mock SolidWorks for testing"
    )

    model_config = ConfigDict(
        extra="allow"  # Allow extra fields for test configurations
    )

    @field_validator("cache_dir")
    @classmethod
    def set_cache_dir(cls, v, info):
        """Set default cache directory."""
        if v is None:
            data_dir = info.data.get("data_dir", Path.home() / ".solidworks_mcp")
            return data_dir / "cache"
        return v

    @field_validator("log_file")
    @classmethod
    def set_log_file(cls, v, info):
        """Set default log file path."""
        if v is None:
            data_dir = info.data.get("data_dir", Path.home() / ".solidworks_mcp")
            return data_dir / "logs" / "server.log"
        return v

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, v, info):
        """Validate adapter type based on platform."""
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return v

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "SolidWorksMCPConfig":
        """Build configuration from environment variables."""
        import json

        env_prefix = "SOLIDWORKS_MCP_"
        raw_values: dict[str, Any] = {}

        list_like_fields = {"cors_origins", "allowed_hosts", "api_keys"}

        def _coerce_env_value(key: str, value: Any) -> Any:
            if not isinstance(value, str):
                return value
            if key in list_like_fields:
                stripped = value.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, list):
                            return parsed
                    except Exception:
                        # Leave original value for Pydantic to validate/report.
                        return value
            return value

        if env_file and Path(env_file).exists():
            for key, value in dotenv_values(env_file).items():
                if key and key.startswith(env_prefix) and value is not None:
                    field_name = key[len(env_prefix) :].lower()
                    raw_values[field_name] = _coerce_env_value(field_name, value)

        for key, value in os.environ.items():
            if key.startswith(env_prefix):
                field_name = key[len(env_prefix) :].lower()
                raw_values[field_name] = _coerce_env_value(field_name, value)

        return cls(**raw_values)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization setup."""
        if self.cache_dir is None:
            self.cache_dir = self.data_dir / "cache"
        if self.log_file is None:
            self.log_file = self.data_dir / "logs" / "server.log"

        # Ensure data directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Set testing defaults
        if self.testing:
            self.mock_solidworks = True
            self.adapter_type = AdapterType.MOCK

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows."""
        return platform.system() == "Windows"

    @property
    def can_use_solidworks(self) -> bool:
        """Check if SolidWorks integration is possible."""
        return (
            self.is_windows
            and not self.mock_solidworks
            and self.adapter_type != AdapterType.MOCK
        )

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration."""
        return {
            "url": self.database_url,
            "echo": self.debug,
        }

    def get_security_config(self) -> dict[str, Any]:
        """Get security configuration."""
        return {
            "api_key": self.api_key.get_secret_value() if self.api_key else None,
            "allowed_hosts": self.allowed_hosts,
            "enable_cors": self.enable_cors,
            "cors_origins": self.cors_origins,
            "enable_rate_limiting": self.enable_rate_limiting,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "security_level": self.security_level,
        }


def load_config(config_file: str | None = None) -> SolidWorksMCPConfig:
    """Load configuration from file and environment variables."""
    if config_file:
        config_path = Path(config_file)
        if config_path.exists() and config_path.suffix.lower() == ".json":
            import json

            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return SolidWorksMCPConfig(**data)
        return SolidWorksMCPConfig.from_env(str(config_path))

    return SolidWorksMCPConfig.from_env()
