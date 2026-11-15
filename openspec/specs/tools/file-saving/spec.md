# tools/file-saving Specification

## Purpose
How `save_as` treats a file that already exists at the target path.
## Requirements
### Requirement: save_as keeps an existing file unless told to overwrite

`save_as` SHALL refuse to write when a file already exists at `file_path` and
`overwrite` is off, and SHALL leave that file untouched. With `overwrite` on, it
SHALL replace the file.

#### Scenario: The file exists and overwrite is off
- **WHEN** an agent saves the active part as a path that already holds a file
- **THEN** the reply is an `invalid_input` error naming the path and `overwrite`, and the file's contents and modified time are unchanged

#### Scenario: Overwrite is on
- **WHEN** the same call has `overwrite: true`
- **THEN** the file is replaced and the call succeeds

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

