## Context

`save_file` (real adapter, `adapters/solidworks/io.py`) saves with
`IModelDoc2.SaveAs3(path, version, options)`, which then makes the saved
file the open document. `create_part`, `create_assembly` and
`create_drawing` already take a template path (`_explicit_template_path`
checks its extension and existence; `NewDocument` uses it).

From `swconst.tlb` (SolidWorks 2026):

| Need | Value |
| --- | --- |
| Template folders | `swUserPreferenceStringValue_e.swFileLocationsDocumentTemplates` = 6 (`;`-separated) |
| Save a copy, silently | `swSaveAsOptions_Copy` = 2, `swSaveAsOptions_Silent` = 1 |
| Current version | `swSaveAsCurrentVersion` = 0 |

## Goals / Non-Goals

**Goals:** a template from the active document, usable at once by
`create_part`, `create_assembly` and `create_drawing`; visible in File > New
when saved by name.

**Non-Goals:** editing template contents (units, properties) through this
tool, which the existing tools do on the document first; changing
SolidWorks' default templates or template folders; sheet-format files
(`.slddrt`).

## Decisions

### 1. The template opens in place of the document, and the reply says so

The plan was `SaveAs3(path, 0, Copy | Silent)`, leaving the open document
on its own path. Live on SolidWorks 2026 (2026-11-16) the copy option made
no difference, through `IModelDoc2.SaveAs3` or `IModelDocExtension.SaveAs`,
for a part never saved or a saved one: SolidWorks has the template open in
place of the document afterwards, as its own File > Save As does, and a
saved document's file is left as last saved. So the adapter calls
`IModelDocExtension.SaveAs(path, 0, Silent, null, errors, warnings)`,
checks the file exists, and compares the document's path and title before
and after (the path of a document never saved reads empty both times, so
the title is needed); the reply's `document_became_template` and the tool's
`warning` tell the agent the template is now open and `save_file` would
change it.

*Alternative:* close the template and reopen the original. Rejected: a
document never saved has no original, and a saved one would lose changes
made since its last save.

### 2. Type from the document, checked first

The extension comes from the active document's type (1 part `.prtdot`, 2
assembly `.asmdot`, 3 drawing `.drwdot`). The tool checks a given
`file_path`'s extension, folder and existing file before the adapter is
called, like `save_file` does (`_checked_new_path`); a `name` is joined
with the first template folder and the extension, and the same checks run.
A `name` containing a path separator or a reserved character is refused.

### 3. The template folder

The adapter reads `swFileLocationsDocumentTemplates`; the first folder
receives a template saved by name. The reply's `in_template_folder` compares
the written path's folder with every listed folder, so a template saved
elsewhere by path is reported as working (through `create_part`) but not
shown in File > New.

### 4. One adapter method

`save_as_template(file_path)` takes the final path. A small read-only
adapter method, `get_template_folders`, returns the folders and the active
document's template extension (`None` with no document), so the tool can
resolve a `name` and check the path before SolidWorks is asked. The mock
adapter records each template's units, material and custom properties in
memory and starts a part made from it with them; its template folders are
empty unless a test sets them.

*Alternative:* resolve the folder inside `save_as_template` from `name`.
Rejected: the tool's path checks would then run after SolidWorks is asked.

## Risks / Trade-offs

- [The template is the open document after the save] → the reply warns, and
  the skill's workflow starts the next part from the template.
- [A template keeps geometry] → templates are usually empty; the
  description says to save from a part with no features when only settings
  are wanted. A part with geometry is allowed (SolidWorks allows it).
