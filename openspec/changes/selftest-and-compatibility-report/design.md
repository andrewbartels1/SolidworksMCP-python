## Context

- The console script is `server.cli_main`. It already routes the `setup`
  and `skill` subcommands to their own Typer apps, and runs the server for
  anything else.
- `PyWin32Adapter.connect()` binds to a running SolidWorks with
  `GetActiveObject`, and **launches one** with `Dispatch` when none is
  running. The selftest must not start SolidWorks (spec: exit 2), so it
  checks first.
- The checks it needs already exist as adapter reads and tools:
  `get_model_geometry_summary` (volume, bounding box, component and mate
  counts), `verify_model`, `check_interference`, `list_drawing_views`,
  `list_open_documents`, `activate_document`, `close_model(save=False)`,
  and `health_check` (`sw_version`). The language and the default
  templates have no adapter read yet.
- The live tests' `_ScratchSession` (`tests/live/conftest.py`) already
  holds the rule this command needs: close only the documents that are new
  since a baseline, and only if they were never saved or were saved to a
  file the session wrote. It lives in the tests, so the selftest needs its
  own copy in `src/`.
- Face mates by a point on each part (`add_mate` with `face_a`/`face_b`)
  arrive with #209 (PR #216). This work branches from main after it merges.

## Goals / Non-Goals

**Goals:**

- One run takes under three minutes on SolidWorks 2026 with the default
  settle pauses.
- Every number in a check is worked out in `expected.py` with its formula
  written beside it, so a reviewer can redo it by hand.
- A failure says which tool call failed and what it returned.

**Non-Goals:**

- No `--mock` mode for users: the mock has no geometry (its volumes and
  bounding boxes are `None`), so a mock run would prove nothing. The mock
  is used only by the unit tests.
- No automatic upload: the user reads the report and chooses to send it.
- No change to the per-tool support levels (#214). A report is evidence a
  maintainer reads before moving a tool up a level.

## Decisions

### 1. A subcommand, with `--selftest` as an alias

`selftest` matches `setup` and `skill`. `cli_main` also maps a leading
`--selftest` to it, because #179 and any early docs use that spelling. The
alternative, a `--selftest` option on the server's Typer command, would
mix the selftest's own options (`--report`) into the server's `--help`.

### 2. Through the MCP tools, in process

The selftest builds the same FastMCP server the CLI runs
(`SolidWorksMCPServer` with the loaded config) and calls tools through an
in-memory `fastmcp.Client`, as `tests/live/test_live_sw_ujoint_demo.py`
does. That covers the tool boundary, input validation, the circuit
breaker and the adapter: everything a client's call goes through. Calling
the adapter directly would be quicker to write but would miss the
problems users actually hit at the tool layer.

### 3. Areas behind one small interface

```
selftest/
  __init__.py
  cli.py        # Typer app: options, precheck, exit codes
  runner.py     # runs areas in order, skips dependents, always cleans up
  areas.py      # PartArea, AssemblyArea, DrawingArea, ExportArea
  expected.py   # hand calculations, one named constant per check
  documents.py  # DocumentGuard: baseline, temp folder, close-only-ours
  report.py     # area lines, Markdown summary, prefilled issue link
  environment.py# environment section from get_application_info etc.
```

Each area has a `name`, the names of the areas it `needs`, and
`async run(context) -> AreaResult`. An `AreaResult` holds `Check`s
(`name`, `expected`, `measured`, `tolerance`, `passed`) and the tool calls
made. The runner does not know what an area does, and the report does not
know how a check was measured, so adding an area touches only `areas.py`
and `expected.py`.

### 4. The part, the assembly and the hand calculations

- **Block:** a 40 × 20 mm rectangle on the Top Plane, centred on the
  origin, extruded 10 mm. Volume 8,000 mm³; bounding box 40 × 10 × 20 mm.
- **Hole:** a Ø10 circle at the origin, cut through all. Volume
  8,000 − π·5²·10 = 7,214.60 mm³; the bounding box is unchanged.
- **Fillet:** r = 2 mm on one 40 mm top edge, picked by its midpoint
  (0, 10, 10) mm. It removes (1 − π/4)·2²·40 = 34.34 mm³, leaving
  7,180.26 mm³.
- **Pin:** a Ø9.5 circle extruded 20 mm. Volume π·4.75²·20 = 1,417.64 mm³.
- **Assembly:** the block and the pin, saved in the temporary folder. A
  concentric face mate (the hole's wall at (5, 5, 0), the pin's side at
  (4.75, 10, 0)), then a coincident aligned mate of the two bottom faces
  ((−15, 0, 0) and (0, 0, 0)). Expected: 2 components, 2 mates, 0
  interferences (0.25 mm radial clearance).
- **Drawing:** a new drawing from the default template, one isometric
  view of the block. Expected: 1 view.
- **Export:** the block as STEP into the temporary folder. Expected: the
  file exists and its size is above zero.

Tolerances: volume within 0.01 % (relative), lengths within 0.01 mm.

### 5. Leaving the user's documents alone

`DocumentGuard` is an async context manager:

1. On entry it reads `list_open_documents` as the baseline and makes a
   folder with `tempfile.mkdtemp(prefix="solidworks-mcp-selftest-")`.
2. Every path the areas save to is inside that folder.
3. On exit, also after an exception or Ctrl+C, it lists the open documents
   again. It closes each one that is not in the baseline and either has no
   path or a path inside its folder, using `activate_document` and then
   `close_model(save=False)`. Then it deletes the folder.

A document in the baseline is never activated, so the user's active
document only changes while the selftest's own documents are open in
front of it.

### 6. Not starting SolidWorks

Before connecting, `cli.py` checks that `SLDWORKS.exe` is running. It uses
`tasklist /FI "IMAGENAME eq SLDWORKS.exe" /NH`, so it needs no new
dependency and makes no COM call. No process means exit 2 with the
message from the spec. A non-Windows platform, or no SolidWorks install
(`setup.solidworks.installed_versions()` returns empty), is also exit 2.

### 7. `get_application_info`, the one new adapter read

`get_application_info() -> AdapterResult[dict]` returns `revision`,
`language`, and `templates` (`part`, `assembly` and `drawing`, each with
`file_name` and `exists`). In the pywin32 adapter it is three
`ISldWorks` reads (`RevisionNumber`, `GetCurrentLanguage`, and
`GetUserPreferenceStringValue` with swDefaultTemplatePart = 8,
swDefaultTemplateAssembly = 9 and swDefaultTemplateDrawing = 10, read from
`swconst.tlb`), run inside `_handle_com_operation`. Each read is wrapped
in `_attempt` so one unreadable value is `None`, not an error. The mock
returns fixed values. Only file names leave the adapter, never full paths
(the spec's privacy rule).

Python, pywin32 and package versions come from `platform`,
`importlib.metadata` and `solidworks_mcp.version`, not the adapter.

### 8. The report and the issue link

- Area lines: `PASS  part       6/6 checks`, `SKIP  drawing    needs part`.
- The Markdown summary is a fenced environment table, then one table per
  area (check, expected, measured, tolerance, result), then the tools
  called.
- GitHub issue forms take field values from the query string. The link is
  `…/issues/new?template=compatibility.yml&labels=compatibility&summary=<url-encoded summary>`.
  It is printed only while the whole URL is under 8,000 characters. Past
  that, the plain form link is printed with "paste the summary above". A
  full report is about 2,500 characters, so the fallback is for failures
  with long error messages.

### 9. The compatibility page

`docs/compatibility.md` is a table maintained by hand: release and
service pack, date, the four area results, and a report link. A maintainer
adds the row when a report arrives. The README's "Tested on" line links
to it. A generated page was considered, but reports arrive as issues, so
there's no structured source to generate it from yet.

## Risks / Trade-offs

- [The user's active document changes while the selftest runs] → The
  guard never activates or closes a baseline document. The README and the
  command's opening line say the selftest opens and closes a few documents
  of its own.
- [Default templates missing or in another language] → `create_part`
  already falls back to the installed templates. The environment section
  shows what was found, which is often the answer to a failing report.
- [Face-mate behaviour differs on older releases] → That is the point of
  the selftest. The assembly area fails with the tool's message, and the
  other areas still run.
- [A crash in SolidWorks during the run] → The guard's cleanup is
  best-effort. Its failures are printed, never raised over the area
  results, and the temporary folder is still removed.
- [`tasklist` output is localised] → It is matched only for the image
  name, which is not translated.

## Migration Plan

Additive. Nothing to migrate or roll back beyond reverting the PR.
