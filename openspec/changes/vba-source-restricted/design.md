## Context

#246 added `allow_vba_source: bool`. It isn't merged, so this change
replaces the bool with three levels rather than adding a second setting.

## Decisions

- **An allowlist, not a denylist.** VBA can reach things not written in
  the source only through `CallByName`, `CreateObject`/`GetObject`,
  `Declare` or `Application`, and all of these are refused. So checking
  every name that is written covers what the macro can reach.
- **Tokenizer** (`tools/vba_check.py`), in order:
  1. join `_` line continuations;
  2. drop string literals (`"..."` with `""` escapes) and comments (`'`
     and `Rem`);
  3. find names: `[A-Za-z_][A-Za-z0-9_]*` with an optional type suffix.

  A name right after `.` is a member. It is checked against the type
  library's members minus the blocklist, plus a few VBA object members
  (`Number`, `Description`, `Clear`, `Raise`, `Print`, `Count`, `Item`,
  `Add`, `Remove`). Any other name must be:
  - a keyword or a safe built-in;
  - a declared name;
  - an enum or enum value;
  - a SolidWorks type name (an interface without its leading `I`, or
    `SldWorks`).
- **Declared names:**
  - `Dim`/`Private`/`Public`/`Static`/`Const`/`ReDim` lists;
  - `Sub`/`Function` names and their parameters;
  - `For`/`For Each` loop variables;
  - line labels.

  An implicit variable is refused, with a hint to declare it.
- **File statements are recognised by shape**, so a member with the same
  name (`feature.Name`) isn't confused with them: a line starting `Open`
  that has `For`; a line starting `Name` that has `As`; any `#` file
  number after `Print`, `Write`, `Input`, `Line Input`, `Get`, `Put`,
  `Close`, `Lock`, `Unlock`, `Seek`, `Width`.
- **The blocklist** is fixed in code and printed in the docs. It covers:
  - writing or exporting: `Save*`, `Export*`, `RunBatchSaveProcess`;
  - running: `RunMacro*`, `RunAttachedMacro`, `RunCommand`,
    `RunJournalCmd`, `RunXMLCommand`, `WriteJournalToMacro`,
    `WriteToJournalFile`;
  - opening or loading files: `OpenDoc*`, `OpenCompFile`, `LoadFile*`,
    `LoadPointsFromFile`, `InsertObjectFromFile`, `InsertObject`;
  - closing and quitting: `CloseDoc`, `CloseAllDocuments`,
    `CloseAndReopen*`, `ExitApp`, `Quit`, `QuitDoc`;
  - persistent settings: `SetUserPreference*`,
    `SetCurrentWorkingDirectory`, `ImportSwSettings`,
    `LoadAdminSettingsFile`;
  - add-ins: `LoadAddIn`, `UnloadAddIn`, `GetAddInObject`, `AddIns`;
  - documents on disk: `CopyDocument`, `RenameDocument`;
  - `SendDataForNetworkJob`.

  Restricted macros work on the documents already open. The tools
  (`open_model`, `save_file`, the exports) do the file work.
- **The type library** comes from the API index the lookups build
  (`_index_for_lookup`). If none can be built, restricted mode refuses.
- **Values.** The env var is a string; `off`, `restricted` and `full` are
  accepted. `1`, `true` and anything else stop the server with a message
  to choose one, so nobody gets full access by assuming `1` means the safe
  one.
