## ADDED Requirements

### Requirement: Save the active document as a template

`save_as_template` SHALL save a copy of the active document as a template of
its type: a part as `.prtdot`, an assembly as `.asmdot`, a drawing as
`.drwdot`. The active document SHALL stay open under its own path and
unchanged. The reply SHALL give `file_path`, the document `type`, and
`in_template_folder` (whether the file is in one of SolidWorks' document
template folders).

#### Scenario: A part set up once starts the next one

- **WHEN** a part in MMGS with material 6061-T6 (SS) and a custom property
  `Company` is saved with `save_as_template`, and `create_part` is called
  with that template
- **THEN** the new part has the same units, material and `Company` value,
  and the first part is still open under its own path

#### Scenario: Saved by name into the template folder

- **WHEN** `save_as_template` is called with `name: "Bracket MMGS"` on a part
- **THEN** the template is written as `Bracket MMGS.prtdot` in the first
  folder of SolidWorks' document template locations, and
  `in_template_folder` is true

### Requirement: Paths are checked before SolidWorks is asked

Exactly one of `file_path` and `name` SHALL be given. A `file_path` whose
extension isn't the document's template extension, a folder that doesn't
exist, a file already there without `overwrite`, or a `name` when SolidWorks
lists no template folder SHALL be refused as `invalid_input` with nothing
written.

#### Scenario: The wrong extension

- **WHEN** a part is active and `file_path` ends in `.asmdot`
- **THEN** the call is `invalid_input` and says the path must end in
  `.prtdot`

#### Scenario: A template already there

- **WHEN** the file exists and `overwrite` is not set
- **THEN** the call is `invalid_input`, the file is unchanged, and the
  message says to pass `overwrite: true`

#### Scenario: No document open

- **WHEN** no document is active
- **THEN** the call fails as `no_active_document`
