## ADDED Requirements

### Requirement: Restricted VBA source reaches SolidWorks only

With `allow_vba_source` set to `restricted`, `execute_macro` SHALL run
`vba_source` only when every name in it, outside comments and string
literals, is a VBA keyword, a listed safe VBA function, a name the source
declares, a SolidWorks enum or type name, `Application.SldWorks`, or,
after a `.`, a member of the installed SolidWorks type library that isn't
on the blocked list. Otherwise it SHALL refuse with `error_type`
`vba_source_refused`, naming each refused name and its line, and write
nothing. With `full` it SHALL run unchecked; with `off` (the default) it
SHALL refuse as `vba_source_off`.

#### Scenario: A SolidWorks-only macro
- **WHEN** restricted source sketches a point with `Application.SldWorks`, `ActiveDoc`, `SelectByID2` and `SketchManager`
- **THEN** it runs

#### Scenario: Reaching outside SolidWorks
- **WHEN** restricted source calls `Shell`, `CreateObject` or `Kill`, or opens a file with `Open ... For Output`
- **THEN** it is refused as `vba_source_refused`, naming each and its line, and nothing runs

#### Scenario: A blocked SolidWorks member
- **WHEN** restricted source calls `SaveAs3` or `RunMacro2`
- **THEN** it is refused, naming the member

#### Scenario: Hidden in a string or comment
- **WHEN** `Shell` appears only inside quotes or after `'`
- **THEN** it doesn't count, and the source can run

#### Scenario: No type library
- **WHEN** the setting is `restricted` and the SolidWorks type library can't be read
- **THEN** the source is refused, saying the check needs it

### Requirement: The defaults and options are disclosed

The installation guide SHALL list every value of
`SOLIDWORKS_MCP_ALLOW_VBA_SOURCE`, the default, what each allows and
refuses, the blocked SolidWorks members, and what the restricted check
does not promise.

#### Scenario: Reading the guide
- **WHEN** a user reads the VBA source section
- **THEN** it states the default is `off`, and what `restricted` and `full` each allow
