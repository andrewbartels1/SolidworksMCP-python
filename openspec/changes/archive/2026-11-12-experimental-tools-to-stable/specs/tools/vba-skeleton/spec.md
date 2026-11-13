## ADDED Requirements

### Requirement: The generated macro is valid VBA that runs without blocking

`generate_vba_code` SHALL return a macro whose Sub name is a valid VBA
identifier whatever `operation_description` says, and which reports through
`Debug.Print`, never a dialog. Run by `execute_macro` on the document type
`target_document` names, it SHALL complete without error and without
waiting on the user.

#### Scenario: A description with punctuation
- **WHEN** an agent asks for a macro described as "Add 3 holes (M6), then save"
- **THEN** the Sub name contains only letters, digits and underscores and starts with a letter, and saved as a `.swb` file, `execute_macro` runs it on an open part and returns success

#### Scenario: Run with execute_macro's default procedure
- **WHEN** the macro is saved as a `.swb` file and `execute_macro` is called with no `proc_name`
- **THEN** its `Sub main()` calls the named Sub, because SolidWorks runs a `.swb` macro only through `main`, and the run returns success

### Requirement: The macro checks the document type it was written for

The macro SHALL stop, printing why, when the active document is not the type
`target_document` names (Part, Assembly or Drawing).

#### Scenario: A part macro run on a drawing
- **WHEN** a macro generated for `target_document: "Part"` runs while a drawing is active
- **THEN** it ends without changing the drawing

### Requirement: Inputs that did nothing are refused

`generate_vba_code` SHALL refuse `parameters` and `code_style` with
`invalid_input`.

#### Scenario: An old caller sends a code style
- **WHEN** an agent calls `generate_vba_code` with `code_style: "advanced"`
- **THEN** the call fails with `invalid_input`, naming the `generate_vba_*` tools that write complete macros
