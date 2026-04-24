"""Configuration management for SolidWorks MCP Server.

Supports both local and remote deployment with comprehensive security options.
"""

from __future__ import annotations

import os
import platform
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_core.core_schema import ValidationInfo


class DeploymentMode(StrEnum):
    """Deployment mode options.
    
    Attributes:
        HYBRID (Any): The hybrid value.
        LOCAL (Any): The local value.
        REMOTE (Any): The remote value.
    """

    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"


class SecurityLevel(StrEnum):
    """Security level options.
    
    Attributes:
        MINIMAL (Any): The minimal value.
        STANDARD (Any): The standard value.
        STRICT (Any): The strict value.
    """

    MINIMAL = "minimal"  # Local only, no authentication
    STANDARD = "standard"  # API keys, basic validation
    STRICT = "strict"  # Full authentication, encryption, audit logs


class AdapterType(StrEnum):
    """SolidWorks adapter implementation options.
    
    Attributes:
        EDGE_DOTNET (Any): The edge dotnet value.
        MOCK (Any): The mock value.
        POWERSHELL (Any): The powershell value.
        PYWIN32 (Any): The pywin32 value.
        VBA (Any): The vba value.
    """

    PYWIN32 = "pywin32"  # Direct COM via pywin32
    VBA = "vba"  # VBA-oriented adapter wrapper
    MOCK = "mock"  # Mock for testing
    EDGE_DOTNET = "edge_dotnet"  # Edge.js bridge to .NET (future)
    POWERSHELL = "powershell"  # PowerShell bridge (future)


class SolidWorksMCPConfig(BaseModel):
    """Main configuration for SolidWorks MCP Server.
    
    Attributes:
        adapter_type (AdapterType): The adapter type value.
        allowed_hosts (list[str]): The allowed hosts value.
        allowed_origins (list[str]): The allowed origins value.
        api_key (SecretStr | None): The api key value.
        api_key_required (bool): The api key required value.
        api_keys (list[str]): The api keys value.
        cache_dir (Path | None): The cache dir value.
        circuit_breaker_enabled (bool): The circuit breaker enabled value.
        circuit_breaker_threshold (int): The circuit breaker threshold value.
        circuit_breaker_timeout (int): The circuit breaker timeout value.
        complexity_parameter_threshold (int): The complexity parameter threshold value.
        complexity_score_threshold (float): The complexity score threshold value.
        connection_pool_size (int): The connection pool size value.
        connection_pooling (bool): The connection pooling value.
        cors_origins (list[str]): The cors origins value.
        data_dir (Path): The data dir value.
        database_url (str): The database url value.
        debug (bool): The debug value.
        deployment_mode (DeploymentMode): The deployment mode value.
        enable_analysis_tools (bool): The enable analysis tools value.
        enable_audit_logging (bool): The enable audit logging value.
        enable_circuit_breaker (bool): The enable circuit breaker value.
        enable_connection_pooling (bool): The enable connection pooling value.
        enable_cors (bool): The enable cors value.
        enable_design_tables (bool): The enable design tables value.
        enable_intelligent_routing (bool): The enable intelligent routing value.
        enable_macro_recording (bool): The enable macro recording value.
        enable_pdm (bool): The enable pdm value.
        enable_rate_limiting (bool): The enable rate limiting value.
        enable_response_cache (bool): The enable response cache value.
        enable_sql_integration (bool): The enable sql integration value.
        enable_windows_validation (bool): The enable windows validation value.
        host (str): The host value.
        log_file (Path | None): The log file value.
        log_level (str): The log level value.
        max_connections (int): The max connections value.
        max_retries (int): The max retries value.
        mock_solidworks (bool): The mock solidworks value.
        model_config (Any): The model config value.
        pdm_server (str | None): The pdm server value.
        pdm_vault (str | None): The pdm vault value.
        port (int): The port value.
        rate_limit_enabled (bool): The rate limit enabled value.
        rate_limit_per_minute (int): The rate limit per minute value.
        response_cache_max_entries (int): The response cache max entries value.
        response_cache_ttl_seconds (int): The response cache ttl seconds value.
        security_level (SecurityLevel): The security level value.
        solidworks_path (str | None): The solidworks path value.
        solidworks_year (int | None): The solidworks year value.
        sql_connection (str | None): The sql connection value.
        state_file (str | None): The state file value.
        testing (bool): The testing value.
        timeout_seconds (float): The timeout seconds value.
        worker_processes (int): The worker processes value.
    """

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

    solidworks_year: int | None = Field(
        default=None,
        description="SolidWorks release year hint (e.g., 2025, 2026)",
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

    enable_intelligent_routing: bool = Field(
        default=True,
        description="Enable complexity-based COM/VBA routing for eligible operations",
    )

    complexity_parameter_threshold: int = Field(
        default=12,
        description="Parameter-count threshold used by the complexity analyzer",
    )

    complexity_score_threshold: float = Field(
        default=0.6,
        description="Complexity score threshold used to prefer VBA routing",
    )

    enable_response_cache: bool = Field(
        default=True,
        description="Enable in-memory caching for read-heavy adapter operations",
    )

    response_cache_ttl_seconds: int = Field(
        default=60,
        description="Default TTL for cached responses in seconds",
    )

    response_cache_max_entries: int = Field(
        default=512,
        description="Maximum number of entries retained in response cache",
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

    @model_validator(mode="after")
    def sync_legacy_alias_fields(self) -> SolidWorksMCPConfig:
        """Sync test/developer alias fields into canonical runtime fields.
        
        Several fixtures and scripts still populate compatibility fields such as
        ``rate_limit_enabled`` and ``connection_pooling``. Runtime code reads the canonical
        fields, so normalize them here after validation.
        
        Returns:
            SolidWorksMCPConfig: The result produced by the operation.
        """
        self.enable_circuit_breaker = self.circuit_breaker_enabled
        self.enable_connection_pooling = self.connection_pooling
        self.connection_pool_size = self.max_connections
        self.enable_rate_limiting = self.rate_limit_enabled
        if self.allowed_origins and not self.cors_origins:
            self.cors_origins = list(self.allowed_origins)
        return self

    @field_validator("cache_dir")
    @classmethod
    def set_cache_dir(cls, v: Path | None, info: ValidationInfo) -> Path:
        """Set default cache directory.
        
        Args:
            v (Path | None): The v value.
            info (ValidationInfo): The info value.
        
        Returns:
            Path: The result produced by the operation.
        """
        if v is None:
            data_dir = cast(
                Path,
                info.data.get("data_dir", Path.home() / ".solidworks_mcp"),
            )
            return data_dir / "cache"
        return v

    @field_validator("log_file")
    @classmethod
    def set_log_file(cls, v: Path | None, info: ValidationInfo) -> Path:
        """Set default log file path.
        
        Args:
            v (Path | None): The v value.
            info (ValidationInfo): The info value.
        
        Returns:
            Path: The result produced by the operation.
        """
        if v is None:
            data_dir = cast(
                Path,
                info.data.get("data_dir", Path.home() / ".solidworks_mcp"),
            )
            return data_dir / "logs" / "server.log"
        return v

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, v: AdapterType, info: ValidationInfo) -> AdapterType:
        """Validate adapter type based on platform.
        
        Args:
            v (AdapterType): The v value.
            info (ValidationInfo): The info value.
        
        Returns:
            AdapterType: The result produced by the operation.
        """
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate the port.
        
        Args:
            v (int): The v value.
        
        Returns:
            int: The computed numeric result.
        
        Raises:
            ValueError: Port must be between 1 and 65535.
        """
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Validate the timeout.
        
        Args:
            v (float): The v value.
        
        Returns:
            float: The computed numeric result.
        
        Raises:
            ValueError: Timeout_seconds must be > 0.
        """
        if v <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return v

    @field_validator("complexity_parameter_threshold")
    @classmethod
    def validate_complexity_parameter_threshold(cls, v: int) -> int:
        """Validate the complexity parameter threshold.
        
        Args:
            v (int): The v value.
        
        Returns:
            int: The computed numeric result.
        
        Raises:
            ValueError: Complexity_parameter_threshold must be >= 1.
        """
        if v < 1:
            raise ValueError("complexity_parameter_threshold must be >= 1")
        return v

    @field_validator("complexity_score_threshold")
    @classmethod
    def validate_complexity_score_threshold(cls, v: float) -> float:
        """Validate the complexity score threshold.
        
        Args:
            v (float): The v value.
        
        Returns:
            float: The computed numeric result.
        
        Raises:
            ValueError: Complexity_score_threshold must be in (0, 1].
        """
        if v <= 0 or v > 1:
            raise ValueError("complexity_score_threshold must be in (0, 1]")
        return v

    @field_validator("response_cache_ttl_seconds")
    @classmethod
    def validate_response_cache_ttl_seconds(cls, v: int) -> int:
        """Validate default response cache TTL.
        
        Args:
            v (int): The v value.
        
        Returns:
            int: The computed numeric result.
        
        Raises:
            ValueError: Response_cache_ttl_seconds must be >= 1.
        """
        if v < 1:
            raise ValueError("response_cache_ttl_seconds must be >= 1")
        return v

    @field_validator("response_cache_max_entries")
    @classmethod
    def validate_response_cache_max_entries(cls, v: int) -> int:
        """Validate response cache size.
        
        Args:
            v (int): The v value.
        
        Returns:
            int: The computed numeric result.
        
        Raises:
            ValueError: Response_cache_max_entries must be >= 1.
        """
        if v < 1:
            raise ValueError("response_cache_max_entries must be >= 1")
        return v

    @classmethod
    def from_env(cls, env_file: str | None = None) -> SolidWorksMCPConfig:
        """Build configuration from environment variables.
        
        Args:
            env_file (str | None): The env file value. Defaults to None.
        
        Returns:
            SolidWorksMCPConfig: The result produced by the operation.
        """
        import json

        env_prefix = "SOLIDWORKS_MCP_"
        raw_values: dict[str, Any] = {}

        list_like_fields = {"cors_origins", "allowed_hosts", "api_keys"}

        def _coerce_env_value(key: str, value: Any) -> Any:
            """Build internal coerce env value.
            
            Args:
                key (str): The key value.
                value (Any): The value value.
            
            Returns:
                Any: The result produced by the operation.
            """
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
        """Post-initialization setup.
        
        Args:
            __context (Any): The context value.
        
        Returns:
            None: None.
        """
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
        """Check if running on Windows.
        
        Returns:
            bool: True if windows, otherwise False.
        """
        return platform.system() == "Windows"

    @property
    def can_use_solidworks(self) -> bool:
        """Check if SolidWorks integration is possible.
        
        Returns:
            bool: True if use solidworks, otherwise False.
        """
        return (
            self.is_windows
            and not self.mock_solidworks
            and self.adapter_type != AdapterType.MOCK
        )

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration.
        
        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        return {
            "url": self.database_url,
            "echo": self.debug,
        }

    def get_security_config(self) -> dict[str, Any]:
        """Get security configuration.
        
        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
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
    """Load configuration from file and environment variables.
    
    Args:
        config_file (str | None): The config file value. Defaults to None.
    
    Returns:
        SolidWorksMCPConfig: The result produced by the operation.
    """
    if config_file:
        config_path = Path(config_file)
        if config_path.exists() and config_path.suffix.lower() == ".json":
            import json

            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return SolidWorksMCPConfig(**data)
        return SolidWorksMCPConfig.from_env(str(config_path))

    return SolidWorksMCPConfig.from_env()
