## ADDED Requirements

### Requirement: save_file checks a new path before writing
When `save_file` is given `file_path`, it SHALL check, before calling
SolidWorks, that the folder exists and is writable, that the extension
matches the active document's type (`.sldprt`, `.sldasm`, `.slddrw`), and
that no file is there unless `overwrite` is on. A failed check SHALL be an
`invalid_input` error that leaves the disk unchanged.

#### Scenario: A part saved to a missing folder
- **WHEN** the active document is a part and `save_file` is called with
  `C:/no/such/folder/bracket.sldprt`
- **THEN** the call fails with `invalid_input` naming the folder, and
  SolidWorks is not asked to save

#### Scenario: The wrong extension
- **WHEN** the active document is an assembly and `file_path` ends `.sldprt`
- **THEN** the call fails with `invalid_input` naming `.sldasm`

#### Scenario: Saving in place
- **WHEN** `save_file` is called with no `file_path`
- **THEN** the document is saved to its own path, as before
