## Why

A part set up once (units, material, custom properties) can't be reused as
the start of the next one: nothing saves a template, though `create_part`,
`create_assembly` and `create_drawing` all take one. Queue item 21, found
by item 10's ledger: `create_template` and `save_to_template_library` were
removed and nothing replaced them.

## What Changes

- A new tool, `save_as_template`, saves the active part, assembly or drawing
  as a template (`.prtdot`, `.asmdot`, `.drwdot`, from the document's type).
  It takes either a full `file_path` or a `name`, saved in SolidWorks'
  first template folder so it appears in File > New. Afterwards SolidWorks
  has the template open in place of the document, as its own File > Save
  As does; the reply says so.
- A file already there is refused unless `overwrite` is on; a path whose
  extension doesn't match the document is refused before SolidWorks is
  asked.
- The reply gives the template's path, whether it is in one of SolidWorks'
  template folders, and how to use it (`create_part` with `template`).

## Capabilities

### New Capabilities
- `tools/document-templates`: saving the active document as a template.

### Modified Capabilities
None. `create_part`'s `template` already takes a `.prtdot` path.

## Impact

- New adapter method `save_as_template` on the base adapter interface, the
  circuit breaker, the connection pool, the real adapter
  (`adapters/solidworks/templates.py`: `IModelDocExtension.SaveAs`,
  run in `_handle_com_operation`) and the mock adapter.
- `tools/file_management.py`: the tool; support level beta until its live
  check; hints, catalog, verb list (`save_` is listed).
- No issue filed; queue item 21.
