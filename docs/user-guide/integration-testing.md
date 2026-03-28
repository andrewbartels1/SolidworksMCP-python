# Integration Testing (Real SolidWorks)

This project now includes two test modes:

- Default mode: fast tests, mock-friendly, no real SolidWorks dependency.
- Full mode: includes real SolidWorks integration tests.

The real integration suite is intentionally deterministic and low-risk:

- It validates the full registered MCP tool catalog.
- It executes practical smoke workflows for real COM connectivity.
- It cleans generated artifacts automatically.

## Default Test Mode

Run this in everyday development:

```bash
make test
```

Behavior:

- Runs all tests except those marked solidworks_only.
- Safe for Linux and CI.
- No local SolidWorks instance required.

## Full Test Mode

Run this on Windows with SolidWorks installed and available via COM:

```bash
make test-full
```

Behavior:

- Enables real integration tests through SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true.
- Runs entire suite including tests marked windows_only and solidworks_only.
- Performs cleanup of generated integration artifacts at the end.

## Manual Cleanup

If you want cleanup without running tests:

```bash
make test-clean
```

## New Real Integration Smoke Tests

The real SolidWorks smoke tests are in:

- tests/test_real_solidworks_integration.py

They validate:

1. Connection and health check against a real SolidWorks instance.
2. Part creation, save-as, close, reopen, and save.
3. Assembly creation and save-as.
4. Tool catalog snapshot validation (all registered tool names).
5. Cross-category minimal workflow (part + sketch + save lifecycle).

The suite writes a snapshot report to:

- tests/.generated/solidworks_integration/tool_catalog_snapshot.json

This makes tool registration regressions easy to detect during upgrades.

## Generated Compatibility Artifacts

The integration harness writes machine-readable artifacts to:

- tests/.generated/solidworks_integration/

Key files:

1. api_compat_report.json
 - Output from docs-discovery compatibility checks.
 - Compares discovered COM interface coverage against required surface.
2. smoke_test_report.json
 - Per-tool smoke execution status, elapsed time, and payload keys.
 - Useful for spotting unstable tools by category.
3. smoke_response_size_report.json
 - Per-tool response payload sizes and aggregate total bytes.
 - Enforces context-window guardrails for LLM-facing workflows.
4. tool_catalog_snapshot.json
 - Snapshot of registered tool names used for regression detection.

### Example: Response-Size Guardrail

Use one of the following to run only the payload-size budget test:

```bash
make test-context-budget
```

```powershell
.\dev-commands.ps1 dev-test-context-budget
```

This command is suitable as a CI gate to prevent response-size regressions that can overwhelm chat context windows.

## Marker Strategy

Real tests are intentionally gated by markers and environment:

- integration
- windows_only
- solidworks_only
- SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true

This keeps regular test runs deterministic and fast while still supporting full end-to-end validation when requested.

## All-Tools Validation Strategy

For a large MCP tool set, deterministic validation is split into two layers:

1. Catalog validation for all tools.
2. Real execution smoke validation for lifecycle-critical flows.

See detailed matrix and rationale:

- user-guide/real-tool-validation-matrix.md

## Common Setup Checklist

1. Run SolidWorks before starting full tests.
2. Ensure your Python environment includes pywin32.
3. Verify COM access for SldWorks.Application.
4. Run make test-full from a Windows shell.
5. Review generated files under tests/.generated/solidworks_integration during debugging.

## Troubleshooting

If full mode skips tests:

- Check OS is Windows.
- Confirm environment variable is set by using make test-full.
- Ensure SolidWorks is installed and launchable.

If file save/open fails:

- Verify output folder permissions.
- Check that no modal dialog is blocking SolidWorks UI.
- Retry with simple file names and short paths.

If sketch or feature operations fail intermittently:

- Confirm active document is the expected part/assembly.
- Ensure reference planes are visible and selectable.
- Avoid interacting with SolidWorks UI while tools execute.

## Related Guides

- user-guide/solidworks-ui-llm-tutorial.md
- user-guide/prompting-best-practices.md
