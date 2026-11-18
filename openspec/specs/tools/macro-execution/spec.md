# tools/macro-execution Specification

## Purpose
How many times `execute_macro` runs a macro, and what its reply says about the
runs.
## Requirements
### Requirement: A macro runs repeat_count times

`execute_macro` SHALL run the macro `repeat_count` times, waiting
`pause_between_runs` seconds between runs. It SHALL stop at the first run that
fails. The reply SHALL give the number of runs that completed, and the message
SHALL state that number, not the number asked for.

#### Scenario: Three runs
- **WHEN** an agent runs a macro that adds one feature with `repeat_count: 3`
- **THEN** three features are added and the reply says 3 runs completed

#### Scenario: A run fails part way
- **WHEN** the second of three runs fails
- **THEN** the reply is an error saying 1 run completed and the second failed, and no third run is attempted

### Requirement: A macro that waits for the user fails cleanly

While `execute_macro` runs a macro, a dialog that SolidWorks' process
keeps open longer than `dialog_timeout` seconds SHALL be answered with
Cancel when it has one, or with its only button when it has just one, or
closed when it has no buttons. The call SHALL then return an error with
`error_type` `macro_waited_for_user` that names the dialog's title and
text and how it was answered. A dialog with several buttons and no Cancel
SHALL be left open and logged. The watchdog SHALL make no COM calls.

#### Scenario: A MsgBox with OK
- **WHEN** a macro shows `MsgBox "Done"` and `dialog_timeout` is 5
- **THEN** after about 5 s the box is answered OK and the reply is an error naming "Done" and the answer

#### Scenario: A prompt with Cancel
- **WHEN** a dialog with OK and Cancel stays open past the timeout
- **THEN** it is answered Cancel, never OK

#### Scenario: Yes and No only
- **WHEN** a dialog's only buttons are Yes and No
- **THEN** neither is pressed, and the log says the dialog needs the user

#### Scenario: No dialog
- **WHEN** a macro runs for longer than the timeout without opening a dialog
- **THEN** it is not interrupted and its result is returned as before

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

