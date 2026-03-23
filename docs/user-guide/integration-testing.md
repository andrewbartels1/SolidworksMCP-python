# Integration Testing (Real SolidWorks)

This project now includes two test modes:

- Default mode: fast tests, mock-friendly, no real SolidWorks dependency.
- Full mode: includes real SolidWorks integration tests.

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

## Marker Strategy

Real tests are intentionally gated by markers and environment:

- integration
- windows_only
- solidworks_only
- SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true

This keeps regular test runs deterministic and fast while still supporting full end-to-end validation when requested.

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
