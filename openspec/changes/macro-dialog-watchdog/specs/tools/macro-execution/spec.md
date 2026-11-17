## ADDED Requirements

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
