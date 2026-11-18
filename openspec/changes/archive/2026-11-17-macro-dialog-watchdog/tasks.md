## 1. Watchdog

- [x] 1.1 `adapters/solidworks/dialog_watch.py`: `DialogWatch` (start/stop, the answer rules), `Win32Windows`
- [x] 1.2 `_invoke_run_macro2` runs the macro inside the watch and raises when a dialog was answered
- [x] 1.3 `dialog_timeout` on `MacroPlaybackInput`; classifier rule `macro_waited_for_user`

## 2. Checks

- [x] 2.1 Unit tests: each answer rule, pre-existing dialogs ignored, no dialog, the adapter error
- [x] 2.2 Live test (passed 2026-11-17, run by the user): a `MsgBox` answered OK and an OK/Cancel prompt answered Cancel after 3 s (`tests/live/test_live_sw_macro_dialog.py`)
- [x] 2.3 Catalog entry, CHANGELOG, full suite at 100%, ruff, mypy
