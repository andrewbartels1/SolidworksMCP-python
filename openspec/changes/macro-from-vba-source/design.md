## Decisions

- **`.swb`, not `.swp`.** The live run of #244 ran three text `.swb`
  macros through `RunMacro2` with `errors == 0`. Building a binary `.swp`
  (OLE2 streams, or the MacroBuilder library) isn't needed for running;
  it stays out of scope.
- **The setting lives in the config** (`allow_vba_source`, from
  `SOLIDWORKS_MCP_ALLOW_VBA_SOURCE` like every other setting), read when
  the tool runs. Default off.
- **Files:** `<temp>/solidworks_mcp/macros/vba-<random>.swb`, written as
  Windows-1252 text (what the VBA editor reads). They are kept, so what
  ran can be looked at afterwards; the reply names the file.
- **Refusal** raises `ToolOperationError` with a message the classifier
  maps to `vba_source_off`.
