## Why

Issue #96: the `generate_vba_*` tools write VBA, and `execute_macro` runs
only a macro file, so "write a macro and run it" stopped at a hand step in
the VBA editor. The live check of #244 showed `RunMacro2` runs a plain-text
legacy macro (`.swb`) as it runs a binary `.swp`, so no binary file has to
be built: the source can be written to a `.swb` and run.

Running VBA an AI wrote is running code on the user's machine (VBA can
delete files or call the shell), so the user chose (2026-11-17) to make it
opt-in.

## What Changes

- `execute_macro` takes `vba_source`, the macro's text, instead of a file.
  It is written to a new `.swb` under the temp folder and run the same way,
  with the dialog watchdog. The reply gives the file and the exact source.
- Off unless the server is started with
  `SOLIDWORKS_MCP_ALLOW_VBA_SOURCE=1` (config `allow_vba_source`). When off,
  the call is refused as `vba_source_off` and says how to turn it on.
- Exactly one of `macro_path`, `macro_file` and `vba_source` is given.
  Source that can't be written as Windows-1252 text is refused.
- The docs explain the risk and the setting.

## Capabilities

### Modified Capabilities
- `tools/macro-execution`: runs VBA source, when allowed.

## Impact

`config.py`, `tools/macro_recording.py`, the error classifier, the
macro-recording catalog page and the installation guide. No adapter change.
