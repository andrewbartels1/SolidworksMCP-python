"""
SolidWorks MCP Server - Security Configuration Examples

This file provides comprehensive security configurations for different deployment scenarios,
from local development to production cloud environments.
"""

import os
import json
from typing import Any
from pathlib import Path

# =============================================================================
# Security Level Definitions
# =============================================================================

SECURITY_LEVELS = {
    "development": {
        "name": "Development Mode",
        "description": "Maximum functionality for local development",
        "risk_level": "High",
        "use_cases": ["Local development", "Internal testing", "Prototyping"],
    },
    "restricted": {
        "name": "Restricted Mode",
        "description": "Limited functionality for controlled environments",
        "risk_level": "Medium",
        "use_cases": [
            "Internal tools",
            "Supervised automation",
            "Training environments",
        ],
    },
    "secure": {
        "name": "Secure Mode",
        "description": "Read-only and safe operations only",
        "risk_level": "Low",
        "use_cases": ["Production servers", "Cloud deployment", "Public interfaces"],
    },
    "locked": {
        "name": "Locked Mode",
        "description": "Analysis and reporting only, no file system access",
        "risk_level": "Minimal",
        "use_cases": ["External integrations", "Audit environments", "Public demos"],
    },
}

# =============================================================================
# Tool Security Classifications
# =============================================================================

TOOL_SECURITY_LEVELS = {
    # Safe tools - Analysis and read-only operations
    "safe": [
        "calculate_mass_properties",
        "analyze_part_geometry",
        "get_feature_list",
        "get_material_properties",
        "analyze_drawing_comprehensive",
        "check_drawing_compliance",
        "get_assembly_structure",
        "check_interference",
        "measure_distance",
        "measure_angle",
    ],
    # Moderate tools - Viewing and temporary operations
    "moderate": [
        "create_sketch",
        "sketch_circle",
        "sketch_line",
        "sketch_rectangle",
        "add_dimension",
        "add_constraint",
        "create_drawing_view",
        "add_annotation",
        "zoom_to_fit",
        "hide_feature",
        "show_feature",
    ],
    # Elevated tools - File operations and exports
    "elevated": [
        "export_step",
        "export_iges",
        "export_stl",
        "export_pdf",
        "save_document",
        "create_technical_drawing",
        "manage_file_properties",
        "convert_file_format",
    ],
    # High-risk tools - Modeling and system operations
    "high_risk": [
        "create_part",
        "create_assembly",
        "create_extrusion",
        "create_revolve",
        "create_fillet",
        "create_chamfer",
        "delete_feature",
        "modify_feature",
        "batch_process_files",
        "execute_workflow",
    ],
    # System tools - VBA, macros, and file system access
    "system": [
        "generate_vba_code",
        "execute_macro",
        "start_macro_recording",
        "batch_export",
        "run_system_command",
        "access_file_system",
        "modify_system_settings",
    ],
}

# =============================================================================
# Security Configuration Templates
# =============================================================================


def get_development_config() -> dict[str, Any]:
    """Full access configuration for local development."""
    return {
        "security_level": "development",
        "enabled_tools": "all",
        "disabled_tools": [],
        "file_system_access": {
            "enabled": True,
            "allowed_paths": ["*"],  # All paths allowed
            "read_only": False,
        },
        "vba_execution": {
            "enabled": True,
            "allow_external_macros": True,
            "macro_security_level": "low",
        },
        "network_access": {"enabled": True, "allowed_domains": ["*"]},
        "logging": {
            "level": "DEBUG",
            "log_file_operations": True,
            "log_vba_execution": True,
        },
        "rate_limiting": {"enabled": False},
        "authentication": {"required": False},
    }


def get_restricted_config() -> dict[str, Any]:
    """Controlled access for supervised environments."""
    allowed_tools = (
        TOOL_SECURITY_LEVELS["safe"]
        + TOOL_SECURITY_LEVELS["moderate"]
        + TOOL_SECURITY_LEVELS["elevated"]
    )

    return {
        "security_level": "restricted",
        "enabled_tools": allowed_tools,
        "disabled_tools": TOOL_SECURITY_LEVELS["system"],
        "file_system_access": {
            "enabled": True,
            "allowed_paths": [
                "./drawings/*",
                "./exports/*",
                "./reports/*",
                os.path.expanduser("~/Documents/SolidWorks/*"),
            ],
            "read_only": False,
            "forbidden_paths": ["/System*", "/Windows/*", "/Program Files/*", "C:\\*"],
        },
        "vba_execution": {
            "enabled": True,
            "allow_external_macros": False,
            "macro_security_level": "medium",
            "approved_macros_only": True,
        },
        "network_access": {"enabled": False},
        "logging": {
            "level": "INFO",
            "log_file_operations": True,
            "log_vba_execution": True,
        },
        "rate_limiting": {"enabled": True, "requests_per_minute": 60},
        "authentication": {"required": True, "method": "api_key"},
    }


def get_secure_config() -> dict[str, Any]:
    """Secure configuration for production environments."""
    allowed_tools = TOOL_SECURITY_LEVELS["safe"] + TOOL_SECURITY_LEVELS["moderate"]

    return {
        "security_level": "secure",
        "enabled_tools": allowed_tools,
        "disabled_tools": TOOL_SECURITY_LEVELS["high_risk"]
        + TOOL_SECURITY_LEVELS["system"],
        "file_system_access": {
            "enabled": True,
            "allowed_paths": ["./exports/*", "./reports/*"],
            "read_only": True,
            "forbidden_paths": ["*"],  # All write operations forbidden
        },
        "vba_execution": {
            "enabled": False,
            "allow_external_macros": False,
            "macro_security_level": "disabled",
        },
        "network_access": {"enabled": False},
        "logging": {
            "level": "WARNING",
            "log_file_operations": True,
            "log_security_violations": True,
        },
        "rate_limiting": {"enabled": True, "requests_per_minute": 30},
        "authentication": {
            "required": True,
            "method": "oauth2",
            "token_expiry": 3600,  # 1 hour
        },
    }


def get_locked_config() -> dict[str, Any]:
    """Minimum access for public or external use."""
    return {
        "security_level": "locked",
        "enabled_tools": TOOL_SECURITY_LEVELS["safe"],
        "disabled_tools": (
            TOOL_SECURITY_LEVELS["moderate"]
            + TOOL_SECURITY_LEVELS["elevated"]
            + TOOL_SECURITY_LEVELS["high_risk"]
            + TOOL_SECURITY_LEVELS["system"]
        ),
        "file_system_access": {"enabled": False},
        "vba_execution": {"enabled": False},
        "network_access": {"enabled": False},
        "logging": {"level": "ERROR", "log_security_violations": True},
        "rate_limiting": {"enabled": True, "requests_per_minute": 10},
        "authentication": {
            "required": True,
            "method": "jwt",
            "token_expiry": 300,  # 5 minutes
        },
    }


# =============================================================================
# Configuration Utilities
# =============================================================================


def get_config_by_level(level: str) -> dict[str, Any]:
    """Get security configuration by level name."""
    configs = {
        "development": get_development_config,
        "restricted": get_restricted_config,
        "secure": get_secure_config,
        "locked": get_locked_config,
    }

    if level not in configs:
        raise ValueError(f"Unknown security level: {level}")

    return configs[level]()


def save_config(config: dict[str, Any], filepath: str):
    """Save configuration to JSON file."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Configuration saved to: {filepath}")


def load_config(filepath: str) -> dict[str, Any]:
    """Load configuration from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate configuration and return list of issues."""
    issues = []

    # Check required fields
    required_fields = [
        "security_level",
        "enabled_tools",
        "file_system_access",
        "vba_execution",
        "logging",
    ]

    for field in required_fields:
        if field not in config:
            issues.append(f"Missing required field: {field}")

    # Validate security level
    if config.get("security_level") not in SECURITY_LEVELS:
        issues.append(f"Invalid security level: {config.get('security_level')}")

    # Check for conflicting settings
    if config.get("vba_execution", {}).get("enabled") and config.get(
        "security_level"
    ) in ["secure", "locked"]:
        issues.append("VBA execution should be disabled in secure/locked modes")

    # Validate file system access
    fs_config = config.get("file_system_access", {})
    if fs_config.get("enabled") and not fs_config.get("allowed_paths"):
        issues.append("File system access enabled but no allowed paths specified")

    return issues


def create_example_configs():
    """Create example configuration files for all security levels."""
    configs_dir = Path("./examples/configurations")
    configs_dir.mkdir(parents=True, exist_ok=True)

    for level in SECURITY_LEVELS.keys():
        config = get_config_by_level(level)
        filepath = configs_dir / f"{level}_config.json"
        save_config(config, str(filepath))

    # Create a comprehensive example with comments
    readme_content = f"""
# SolidWorks MCP Security Configuration

This directory contains security configuration examples for different deployment scenarios.

## Security Levels

{
        chr(10).join(
            [
                f"### {level.title()}: {info['name']}"
                + chr(10)
                + f"- **Risk Level**: {info['risk_level']}"
                + chr(10)
                + f"- **Description**: {info['description']}"
                + chr(10)
                + f"- **Use Cases**: {', '.join(info['use_cases'])}"
                + chr(10)
                for level, info in SECURITY_LEVELS.items()
            ]
        )
    }

## Configuration Files

- `development_config.json` - Full access for local development
- `restricted_config.json` - Controlled access for supervised environments  
- `secure_config.json` - Production-ready secure configuration
- `locked_config.json` - Minimal access for public deployment

## Tool Security Classifications

**Safe Tools** (Analysis & Read-only):
{chr(10).join([f"- {tool}" for tool in TOOL_SECURITY_LEVELS["safe"]])}

**Moderate Tools** (Viewing & Temporary):
{chr(10).join([f"- {tool}" for tool in TOOL_SECURITY_LEVELS["moderate"]])}

**Elevated Tools** (File Operations):
{chr(10).join([f"- {tool}" for tool in TOOL_SECURITY_LEVELS["elevated"]])}

**High-Risk Tools** (Modeling Operations):
{chr(10).join([f"- {tool}" for tool in TOOL_SECURITY_LEVELS["high_risk"]])}

**System Tools** (VBA & System Access):
{chr(10).join([f"- {tool}" for tool in TOOL_SECURITY_LEVELS["system"]])}

## Usage Example

```python
from examples.configurations.security_config import get_config_by_level

# Load secure configuration
config = get_config_by_level("secure")

# Initialize MCP server with security config
server = SolidWorksMCPServer(security_config=config)
```

## Environment Variables

You can also configure security via environment variables:

```bash
export SOLIDWORKS_MCP_SECURITY_LEVEL=secure
export SOLIDWORKS_MCP_API_KEY=your_api_key_here
export SOLIDWORKS_MCP_LOG_LEVEL=INFO
```
"""

    with open(configs_dir / "README.md", "w") as f:
        f.write(readme_content)

    print(f"✅ Created {len(SECURITY_LEVELS)} example configurations")
    print(f"📁 Configuration files saved to: {configs_dir}")


if __name__ == "__main__":
    create_example_configs()
