# tools/document-inspection Specification

## Purpose
The tools that read the active document (`get_file_properties`, `list_configurations`, `classify_feature_tree`, `load_part`, `load_assembly`) report what SolidWorks says, and fail plainly when they can't read it.

## Requirements
### Requirement: File properties describe the active document's file

`get_file_properties` SHALL report the active document's file name, path,
size in bytes, created and modified times, type, active configuration and
whether it has unsaved changes. For a document never saved, the size and
times SHALL be `null`.

#### Scenario: A saved part, then edited
- **WHEN** a part is saved and an agent reads its properties, then adds a feature and reads them again
- **THEN** the first reply has the saved path, a size above 0 and `is_dirty: false`, and the second has `is_dirty: true`

### Requirement: Every configuration is listed

`list_configurations` SHALL list the name of every configuration of the
active part or assembly.

#### Scenario: A part with two configurations
- **WHEN** a part has the configurations "Default" and "Long"
- **THEN** the reply's `configurations` holds both names and `count` is 2

### Requirement: Classification fails when the model can't be read

`classify_feature_tree` SHALL classify the model it reads, or the
`model_info` and `features` passed to it. When it must read the model and
can't, it SHALL fail, not classify an empty model.

#### Scenario: A part and an assembly
- **WHEN** an agent classifies a plain extruded part, then an assembly
- **THEN** the first `family` is a part family and the second is the assembly family

#### Scenario: Nothing is open
- **WHEN** no document is open and an agent classifies without passing `model_info` and `features`
- **THEN** the call fails with `no_active_document`

### Requirement: Opening a part or assembly reports what SolidWorks opened

`load_part` and `load_assembly` SHALL open the file, refusing a path of the
wrong type before calling SolidWorks, and SHALL report the configuration
SolidWorks opened, or `null` when it can't be read, never an assumed
"Default". A path that does not exist SHALL fail with `not_found`.

#### Scenario: A saved part reopened
- **WHEN** a part is saved, closed, and loaded with `load_part`
- **THEN** it is the active document, and the reply's `path` is the file and `configuration` is the one SolidWorks reports

#### Scenario: The wrong file type
- **WHEN** an agent calls `load_assembly` with a `.sldprt` path
- **THEN** the call fails with `invalid_input`, and nothing is opened

