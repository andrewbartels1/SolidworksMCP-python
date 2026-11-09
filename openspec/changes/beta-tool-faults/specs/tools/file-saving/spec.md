## Purpose

How `save_as` treats a file that already exists at the target path.

## ADDED Requirements

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
