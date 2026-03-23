# Real SolidWorks Tool Validation Matrix

This page documents how the project validates the full MCP tool set with deterministic test behavior.

## Validation Model

The project uses two layers:

1. Catalog validation for all registered tools.
2. Real execution smoke workflows for core CAD lifecycle paths.

This split keeps tests deterministic and maintainable while still validating real COM connectivity.

## Layer 1: All-Tools Catalog Validation

Implemented in real integration tests by checking:

- The server registers the full tool catalog.
- Tool names are unique.
- Core tool names across all major categories exist.
- A local snapshot JSON is written under tests/.generated/solidworks_integration.

What this guarantees:

- No silent tool-registration regressions.
- No accidental tool-name collisions.

## Layer 2: Real Execution Smoke Workflows

Executed against a live SolidWorks session:

- Part create/save/open/save/close flow.
- Assembly create/save flow.
- Cross-category smoke flow (part + sketch + save lifecycle).

What this guarantees:

- End-to-end COM connectivity on real SolidWorks.
- Deterministic basic lifecycle behavior for users and tutorials.

## Why Not Execute Every Tool in One Real Test Run

Not all tools are equally deterministic in unattended runs:

- Some require rich model preconditions (existing sketches, references, or drawing views).
- Some are macro/file-system heavy and intentionally scenario-specific.
- Some are best validated with targeted unit tests plus focused integration scenarios.

The repo already includes broad unit coverage by tool category under tests/test_tools_*.py.

## Run Commands

Default fast run:

```bash
make test
```

Full run including real SolidWorks integration:

```bash
make test-full
```

Manual cleanup:

```bash
make test-clean
```

## Environment Requirements

- Windows 10/11.
- Local SolidWorks installation.
- SolidWorks launchable and COM-accessible.
- SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true (handled by make test-full).

## Expected Generated Artifacts

During full runs:

- tests/.generated/solidworks_integration/*.sldprt
- tests/.generated/solidworks_integration/*.sldasm
- tests/.generated/solidworks_integration/tool_catalog_snapshot.json

Cleanup is performed by tests/scripts/cleanup_generated_integration_artifacts.py.
