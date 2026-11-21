## Why

A user on SolidWorks 2024 SP5, installed with `uvx` and run from Claude
Desktop, reported three faults on 2026-11-20 (#255, #256, #257). Each is
ours, and each has gone unseen because every live run so far has been on
SolidWorks 2026 from a developer's checkout:

- **#255** `add_fillet` always fails before 2025: below major version 33 it
  calls `IFeatureManager.FeatureFillet3` with 15 arguments, radius first; the
  type library's signature has 14, options first. That branch has never run.
- **#256** `create_drawing_view` never changes a view's scale: the view keeps
  using the sheet scale (`UseSheetScale` is never turned off), and the reply's
  `scale_applied` is always false because it tests `setattr`'s return value.
  Also, `view_type` alone never sets the view, because the tool always sends
  `orientation` (default `front`).
- **#257** every API lookup fails with `PermissionError` when the server's
  working folder isn't writable (Claude Desktop through `uvx`): the index is
  saved to a folder relative to it, `.generated/docs-index`.

## What Changes

- `add_fillet` uses `IModelDoc2.FeatureFillet3` (9 arguments) on every
  SolidWorks version, the call checked live on 2026; the version check and
  the broken branch go.
- `create_drawing_view` turns the view's `UseSheetScale` off, sets
  `ScaleDecimal`, and reads it back for `scale_applied`. With no
  `orientation`, a `view_type` that names a view (`top`, `isometric`, ...)
  sets it.
- The API index is saved in the user's own folder (`~/.solidworks_mcp/
  docs-index`, beside the server's other data); the old relative folders are
  still read, so an index built there keeps working.

## Capabilities

### New Capabilities

- `tools/drawing-view-scale`: a view's own scale, applied and read back;
  `view_type` as the orientation when none is given.

### Modified Capabilities

- `tools/edge-treatment`: a fillet works on every supported SolidWorks
  version (an added requirement).
- `tools/api-help-lookup`: the index is saved in a user-writable folder (an
  added requirement).

## Impact

- `adapters/solidworks/features.py` (`_add_fillet_impl`),
  `adapters/solidworks/io.py` (`_place_view`), `tools/drawing.py`
  (`CreateDrawingViewInput`), `tools/docs_discovery.py` (`_INDEX_DIRS`);
  tests beside each; the catalog pages; CHANGELOG.
- No public reply on the issues until the user decides (the user's
  instruction, 2026-11-20). Each fix is checked live on 2026; 2024 can only
  be confirmed by the reporter.
