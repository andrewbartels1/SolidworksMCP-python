## ADDED Requirements

### Requirement: VBA source runs only when the user allowed it

`execute_macro` SHALL accept `vba_source` in place of a macro file. When
the server's `allow_vba_source` setting is on, the source SHALL be written
to a new `.swb` file and run as a macro file is, and the reply SHALL give
the file's path and the source that ran. When the setting is off, the call
SHALL be refused with `error_type` `vba_source_off`, and nothing SHALL be
written or run.

#### Scenario: Allowed
- **WHEN** `allow_vba_source` is on and an agent calls `execute_macro` with `vba_source`
- **THEN** a `.swb` holding that source is run, and the reply names the file and repeats the source

#### Scenario: Not allowed
- **WHEN** the setting is off
- **THEN** the reply is an error, `vba_source_off`, naming `SOLIDWORKS_MCP_ALLOW_VBA_SOURCE`, and no file is written

#### Scenario: Two sources
- **WHEN** both `vba_source` and `macro_path` are given
- **THEN** the input is refused as invalid
