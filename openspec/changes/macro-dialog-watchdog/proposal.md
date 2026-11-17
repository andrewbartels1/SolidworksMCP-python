## Why

Issue #97: a macro that opens a dialog (a `MsgBox`, a user form, a
SolidWorks prompt) waits for an answer nobody gives. `RunMacro2` doesn't
return, so the server hangs; 2 min 17 s was seen live before the dialog was
closed by hand. The tool's description already says a macro must not wait
for the user, but nothing enforces it.

## What Changes

- While `execute_macro` runs a macro, a watchdog thread looks for a dialog
  opened by the SolidWorks process. It uses only Win32 window calls, never
  COM, so the COM threading rule holds.
- When a dialog stays open longer than `dialog_timeout` seconds (a new
  input; default 30), the watchdog:
  - reads its title, text and buttons;
  - answers it with the non-committal choice: **Cancel** when there is
    one, else the only button when there is just one (OK), else it closes
    the window. It never picks Yes, No, Retry or Abort.
- The call then returns an error that names the dialog, what it said and
  how it was answered, and repeats that macros run here must not wait for
  the user. `error_type` is `macro_waited_for_user`.
- A dialog it can't answer that way (for example Yes/No with no Cancel)
  is reported in the log after the timeout and left for the user, as today.
- A macro that runs long without a dialog is not interrupted.

## Capabilities

### Modified Capabilities
- `tools/macro-execution`: a macro that waits for the user fails cleanly.

## Impact

A new `adapters/solidworks/dialog_watch.py`; `pywin32_adapter.py`
(`_invoke_run_macro2`); `tools/macro_recording.py` (the input field); the
error classifier; the catalog entry. Live check: a macro with a `MsgBox`
(left for the user's run).
