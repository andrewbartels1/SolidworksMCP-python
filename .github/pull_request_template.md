## What and why

<!-- One or two sentences. Link the issue: "Closes #123". -->

## How it was tested

- [ ] `pytest tests -m "not solidworks_only"` passes
- [ ] Live SolidWorks run, if this touches COM behaviour (say which SolidWorks version)
- [ ] `mkdocs build --strict` passes, if docs changed

## Checklist

- [ ] Tests sit beside the module they exercise (`tests/solidworks_mcp/<path>/test_<module>.py`)
- [ ] Tools use the error boundary helpers (`require_success`, `ToolOperationError`, ...) rather than `try/except`
- [ ] No new claims in README or docs that a test or live run doesn't back up
