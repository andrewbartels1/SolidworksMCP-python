"""Focused coverage tests for src.solidworks_mcp.config."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.solidworks_mcp import config as config_module
from src.solidworks_mcp.config import SolidWorksMCPConfig


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
