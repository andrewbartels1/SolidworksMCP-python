"""Focused coverage tests for solidworks_mcp.config."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from solidworks_mcp import config as config_module
from solidworks_mcp.config import AdapterType, SolidWorksMCPConfig, load_config


def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear SolidWorks MCP env vars so tests remain isolated."""
    for key in list(os.environ):
        if key.startswith("SOLIDWORKS_MCP_"):
            monkeypatch.delenv(key, raising=False)


def test_from_env_parses_json_list_fields(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON-encoded list env values should be coerced before model validation."""
    _clear_config_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"SOLIDWORKS_MCP_DATA_DIR={tmp_path / 'data'}",
                'SOLIDWORKS_MCP_CORS_ORIGINS=["http://localhost:3000","https://example.com"]',
                'SOLIDWORKS_MCP_ALLOWED_HOSTS=["localhost","example.com"]',
                'SOLIDWORKS_MCP_API_KEYS=["alpha","beta"]',
            ]
        ),
        encoding="utf-8",
    )

    config = SolidWorksMCPConfig.from_env(str(env_file))

    assert config.cors_origins == ["http://localhost:3000", "https://example.com"]
    assert config.allowed_hosts == ["localhost", "example.com"]
    assert config.api_keys == ["alpha", "beta"]


def test_from_env_invalid_json_list_bubbles_to_validation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid JSON list syntax should be left untouched for Pydantic to reject."""
    _clear_config_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"SOLIDWORKS_MCP_DATA_DIR={tmp_path / 'data'}",
                'SOLIDWORKS_MCP_CORS_ORIGINS=["http://localhost",invalid]',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        SolidWorksMCPConfig.from_env(str(env_file))


def test_from_env_environment_overrides_env_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Process env values should override env-file values for the same field."""
    _clear_config_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"SOLIDWORKS_MCP_DATA_DIR={tmp_path / 'file-data'}",
                "SOLIDWORKS_MCP_HOST=10.0.0.1",
                'SOLIDWORKS_MCP_ALLOWED_HOSTS=["filehost"]',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SOLIDWORKS_MCP_DATA_DIR", str(tmp_path / "env-data"))
    monkeypatch.setenv("SOLIDWORKS_MCP_HOST", "127.0.0.9")
    monkeypatch.setenv("SOLIDWORKS_MCP_ALLOWED_HOSTS", '["envhost"]')

    config = SolidWorksMCPConfig.from_env(str(env_file))

    assert config.host == "127.0.0.9"
    assert config.allowed_hosts == ["envhost"]
    assert config.data_dir == tmp_path / "env-data"


def test_from_env_json_parse_failure_returns_original_value(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON parse failures inside list coercion should fall back to the raw env string."""
    _clear_config_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"SOLIDWORKS_MCP_DATA_DIR={tmp_path / 'data'}",
                'SOLIDWORKS_MCP_ALLOWED_HOSTS=["localhost"]',
            ]
        ),
        encoding="utf-8",
    )

    original_loads = json.loads

    def boom(value: str):
        if value == '["localhost"]':
            raise ValueError("bad json")
        return original_loads(value)

    monkeypatch.setattr(json, "loads", boom)

    with pytest.raises(ValidationError):
        SolidWorksMCPConfig.from_env(str(env_file))


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("complexity_parameter_threshold", 0),
        ("complexity_score_threshold", 0.0),
        ("response_cache_ttl_seconds", 0),
        ("response_cache_max_entries", 0),
    ],
)
def test_config_numeric_lower_bounds(field_name: str, field_value: float | int) -> None:
    """Lower-bound validators should reject invalid configuration values."""
    with pytest.raises(ValidationError):
        SolidWorksMCPConfig(**{field_name: field_value})


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("complexity_parameter_threshold", 1),
        ("complexity_score_threshold", 1.0),
        ("response_cache_max_entries", 1),
    ],
)
def test_config_numeric_lower_bounds_accept_valid_values(
    field_name: str, field_value: float | int
) -> None:
    """Lower-bound validators should return valid values unchanged."""
    config = SolidWorksMCPConfig(**{field_name: field_value})
    assert getattr(config, field_name) == field_value


def test_from_env_non_string_value_passthrough(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-string values from dotenv parsing should bypass JSON coercion."""
    _clear_config_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("SOLIDWORKS_MCP_HOST=ignored\n", encoding="utf-8")

    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _: {
            "SOLIDWORKS_MCP_DATA_DIR": str(tmp_path / "data"),
            "SOLIDWORKS_MCP_STATE_FILE": Path(tmp_path / "state.json"),
        },
    )

    with pytest.raises(ValidationError):
        SolidWorksMCPConfig.from_env(str(env_file))


def test_config_cache_and_log_path_passthrough(tmp_path) -> None:
    """Explicit cache_dir/log_file should be preserved."""
    # Provide explicit paths to cover the passthrough branch.
    cache_dir = tmp_path / "cache"
    log_file = tmp_path / "logs" / "server.log"
    config = SolidWorksMCPConfig(cache_dir=cache_dir, log_file=log_file)
    assert config.cache_dir == cache_dir
    assert config.log_file == log_file


def test_soc_and_docs_index_defaults() -> None:
    """New knobs default to safe values: SoC logging off, index auto-refresh on."""
    config = SolidWorksMCPConfig()
    assert config.soc_logging_enabled is False
    assert config.soc_session_id is None
    assert config.soc_db_path is None
    assert config.docs_index_auto_refresh is True
    assert config.docs_index_max_age_days == 21


def test_soc_logging_env_toggle_and_generated_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SOLIDWORKS_MCP_SOC_LOGGING_ENABLED=true flips it on; an id is generated."""
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("SOLIDWORKS_MCP_SOC_LOGGING_ENABLED", "true")
    config = SolidWorksMCPConfig.from_env()
    assert config.soc_logging_enabled is True
    assert config.soc_session_id and config.soc_session_id.startswith("soc-")


def test_soc_logging_env_explicit_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("SOLIDWORKS_MCP_SOC_LOGGING_ENABLED", "1")
    monkeypatch.setenv("SOLIDWORKS_MCP_SOC_SESSION_ID", "my-bracket")
    config = SolidWorksMCPConfig.from_env()
    assert config.soc_session_id == "my-bracket"


class TestConfigValidatorCoverage:
    """Test config validator coverage."""

    def test_cache_dir_defaults_when_none(self):
        """Lines 246-252 — cache_dir=None triggers set_cache_dir to derive path."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, cache_dir=None)
        assert cfg.cache_dir is not None
        assert cfg.cache_dir.name == "cache"

    def test_log_file_defaults_when_none(self):
        """Lines 258-264 — log_file=None triggers set_log_file to derive path."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, log_file=None)
        assert cfg.log_file is not None
        assert cfg.log_file.name == "server.log"

    def test_validate_port_too_low_raises(self):
        """Lines 336-338 — port < 1 raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SolidWorksMCPConfig(mock_solidworks=True, port=0)

    def test_validate_port_too_high_raises(self):
        """Lines 336-338 — port > 65535 raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SolidWorksMCPConfig(mock_solidworks=True, port=70000)

    def test_validate_port_boundary_valid(self):
        """Test validate port boundary valid."""

        cfg = SolidWorksMCPConfig(mock_solidworks=True, port=1)
        assert cfg.port == 1
        cfg2 = SolidWorksMCPConfig(mock_solidworks=True, port=65535)
        assert cfg2.port == 65535

    def test_load_config_no_args_calls_from_env(self, monkeypatch):
        """Line 417 — load_config() with no path falls back to from_env()."""
        monkeypatch.delenv("SOLIDWORKS_MCP_CONFIG", raising=False)
        cfg = load_config(None)
        assert isinstance(cfg, SolidWorksMCPConfig)

    def test_load_config_json_file(self, tmp_path):
        """Line 414 — load_config from JSON file."""
        import json

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"mock_solidworks": True, "port": 9000}))
        cfg = load_config(str(cfg_file))
        assert cfg.port == 9000

    def test_validate_adapter_type_passthrough(self):
        """Line 328 — validate_adapter_type just returns the value."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, adapter_type=AdapterType.MOCK)
        assert cfg.adapter_type == AdapterType.MOCK
