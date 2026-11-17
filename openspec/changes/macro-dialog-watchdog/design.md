## Context

`RunMacro2` blocks the connect thread until the macro returns, and COM calls
can't move to another thread (CLAUDE.md, COM threading). Only the user,
or something acting like them on the dialog, can make it return.

## Decisions

- **Watchdog thread, Win32 only.**
  - Before `RunMacro2`, the adapter reads `ISldWorks.GetProcessID()` on the
    connect thread and notes the dialogs that process already has open.
  - A daemon thread then polls every 0.5 s for visible top-level windows
    of that process with a dialog class: `#32770` (message boxes, file
    prompts) or `ThunderDFrame` (VBA user forms).
- **Answer only with the non-committal choice.**
  - A child button whose text, without `&`, is `Cancel`: click it.
  - Else a single button: click it (an OK acknowledgement).
  - Else no buttons: `WM_CLOSE`.
  - Anything else is left for the user and logged once.
- **What the watchdog reads:** title (`GetWindowText`), the static texts,
  the button labels, and what it did. These are returned to the adapter,
  which raises `SolidWorksMCPError` after `RunMacro2` returns. The
  classifier maps "waited for the user" to `macro_waited_for_user`.
- **`dialog_timeout`** is a tool input, 1–600 s, default 30. The adapter
  takes it in the macro params.
- **Testability:** the Win32 calls go through one small object (`Win32Windows`)
  that tests replace. The real one is a thin pass-through over `win32gui`,
  covered with a fake `win32gui` module.
