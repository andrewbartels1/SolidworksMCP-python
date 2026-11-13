# tools/pack-and-go Specification

## Purpose
`pack_and_go_assembly` copies an assembly and every file it uses into one folder that opens on its own, without closing or changing the user's documents, and says when the copy leaves out unsaved changes.

## Requirements
### Requirement: Pack and Go never closes the user's documents

`pack_and_go_assembly` SHALL NOT close any open document. When the source
assembly is already open, it SHALL pack the open copy. Documents that were
open before the call SHALL still be open afterwards, with their unsaved
changes.

#### Scenario: The assembly is already open with unsaved changes
- **WHEN** an assembly is open, a part it uses has unsaved changes, and an agent packs the assembly
- **THEN** the call succeeds, the part is still open and still shows unsaved changes, and every document open before the call is open after it

### Requirement: Pack and Go copies the saved files SolidWorks lists

`pack_and_go_assembly` SHALL copy the assembly and every file SolidWorks
lists as its dependency (`GetDependencies2`) into `target_dir`, each under
its own file name. It copies the files as saved on disk: when an open
document among them has unsaved changes, the reply SHALL carry a `warning`
naming it. Two dependencies with the same file name from different folders,
or a dependency missing on disk, SHALL fail the call before anything is
copied, naming the files.

#### Scenario: A part has unsaved changes
- **WHEN** a part of the assembly has unsaved changes and an agent packs the assembly
- **THEN** the saved part is copied and the reply's `warning` names the part, saying its unsaved changes are not in the copy

#### Scenario: A dependency is missing
- **WHEN** a file the assembly uses is not on disk
- **THEN** the call fails naming the file, and nothing is copied

### Requirement: Pack and Go leaves other files in the target folder alone

Without `overwrite`, a `target_dir` that already holds files SHALL be refused
before anything is written. With `overwrite`, only the files Pack and Go
writes SHALL be replaced; any other file in `target_dir` SHALL be left as it
was.

#### Scenario: A folder with an unrelated file
- **WHEN** `target_dir` holds `notes.txt` and an agent packs an assembly into it with `overwrite: true`
- **THEN** the assembly and its parts are written, and `notes.txt` is unchanged

#### Scenario: Packing twice into one folder
- **WHEN** an agent packs the same assembly into the same folder again, with `overwrite: true`
- **THEN** the call succeeds and replaces the files it wrote the first time

#### Scenario: A folder with files, without overwrite
- **WHEN** `target_dir` holds any file and `overwrite` is off
- **THEN** the call fails with `invalid_input`, and nothing in the folder changes

### Requirement: The packed assembly opens from its new folder

The reply SHALL list `copied_files`, and every component of the packed
assembly SHALL resolve to a file inside `target_dir`.

#### Scenario: A two-part assembly
- **WHEN** an assembly of two saved parts is packed into an empty folder
- **THEN** `copied_files` names the assembly and both parts, and opening the copied assembly loads both components from `target_dir`

### Requirement: Pack and Go's inputs are required and its preview is reported

`source_path` and `target_dir` SHALL be required. A `source_path` that does
not exist SHALL fail with `not_found`. When `export_preview` is on and the
preview can't be written, the reply SHALL carry a `warning` saying so.

#### Scenario: The input is left out
- **WHEN** an agent calls `pack_and_go_assembly` with no input
- **THEN** the call fails with `invalid_input` naming `source_path` and `target_dir`

