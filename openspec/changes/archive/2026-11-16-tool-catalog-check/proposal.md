## Why

Issue #156: the tool catalog pages drift from the tools and nothing checks
them. Today 20 of the 140 registered tools have no catalog entry at all
(16 of them modeling tools), and about 30 entries list inputs the tool no
longer takes, or miss ones it does. The issue proposed regenerating the
pages from `src/utils/generate_tool_catalog.py`. That script overwrites the
hand-written text the pages are made of (it wiped them once, 2026-11-15),
ignores `--help`, and nothing has run it in months.

## What Changes

- **A check instead of a generator.** A test reads every catalog page and
  fails when:
  - a registered tool has no entry, or one on a page other than its
    family's;
  - an entry names a tool that isn't registered;
  - an entry's parameter table doesn't list exactly the tool's inputs;
  - an entry's sample call isn't valid JSON that the tool's input model
    accepts. So a `null` for a required field fails.
- **The gaps filled by hand:**
  - entries for the 20 missing tools;
  - the stale parameter tables corrected;
  - a page for the server-admin family (`reset_circuit_breaker`).
- **The generator is removed**, with the four harness tests that read its
  JSON output. They were always skipped in CI, and the new check covers
  what they asked.

## Capabilities

### New Capabilities
- `docs/tool-catalog`: what every catalog entry must hold, and the check.

### Modified Capabilities
None.

## Impact

`docs/user-guide/tool-catalog/*.md` (and a new `server-admin.md`),
`mkdocs.yml` nav, `src/utils/generate_tool_catalog.py` (deleted),
`tests/integration/test_all_endpoints_harness.py`, a new
`tests/integration/test_tool_catalog.py`.
