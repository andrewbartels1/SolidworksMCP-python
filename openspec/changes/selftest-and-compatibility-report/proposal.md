## Why

The README says the server is tested on SolidWorks 2026 only, and asks
users of earlier releases to open an issue. Few do, and the reports that
come in lack the facts needed to act on them. Users need one command that
checks their setup the way an agent would use it, and a form to send the
result. Addresses #179.

## What Changes

- New command `solidworks-mcp-python selftest`, with `--selftest` as an alias
  for the spelling in #179. With SolidWorks running, it:
  - reports the environment: SolidWorks revision and language, the default
    part, assembly and drawing templates (and whether each file exists),
    the configured `--year`, and the Python, pywin32 and package versions;
  - builds a small part through the MCP tools (sketch, extrude, hole,
    fillet) and checks its volume and bounding box against hand
    calculations after each feature;
  - builds an assembly (two components, two face mates) and checks the
    component count, mate count and that nothing interferes;
  - makes one drawing view and one STEP export, and checks each exists;
  - prints a PASS, FAIL or SKIP line per area, then a Markdown summary to
    paste into an issue, and a link that opens the issue form with it
    filled in when it fits in a URL.
- It never saves over, closes or changes a document that was open before
  it started. Its own files go in a new temporary folder that it deletes.
- Exit code 0 when every area passes, 1 when any fails, 2 when it cannot
  run (SolidWorks not running, not Windows).
- New issue form `compatibility.yml` asking for the selftest output, the
  SolidWorks version and service pack, Windows version and MCP client.
  Linked from the README's "Tested on" line and from the feedback form.
- New docs page listing the releases the selftest has passed on, seeded
  with SolidWorks 2026 SP4.0. Each report that comes in adds a row.
- One new adapter read, `get_application_info`, for the language and the
  default templates (**touches the adapter interface**: base, pywin32 and
  mock adapters).

## Capabilities

### New Capabilities

- `setup/selftest`: the selftest command, what it checks, the report it
  prints, its exit codes, and its promise to leave the user's documents
  alone.
- `docs/compatibility-reports`: the compatibility issue form and the page
  of releases the selftest has passed on.

### Modified Capabilities

None.

## Impact

- New package `src/solidworks_mcp/selftest/`; `server.cli_main` routes the
  `selftest` subcommand to it.
- Adapter interface: `get_application_info` in `adapters/base.py`, the
  pywin32 adapter and the mock adapter. COM risk is small (three
  `ISldWorks` reads on the connect thread through `_handle_com_operation`).
- The assembly step uses the face mates from #209 (PR #216), so this work
  is built on top of that branch once it merges.
- `.github/ISSUE_TEMPLATE/compatibility.yml` (new), `feedback.yml`, README,
  a new docs page and `mkdocs.yml` nav.
- Tests: mock-adapter tests for the checks and the report, mirroring
  `src/`; one live test running the whole selftest on SolidWorks 2026.
