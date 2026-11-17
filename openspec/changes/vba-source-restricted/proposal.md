## Why

Item 26 (#246, not merged) lets `execute_macro` run VBA source when the
server allows it, with full access: VBA runs inside SolidWorks with the
user's Windows rights, so a macro can also delete files or start programs.
The user asked (2026-11-17) for a mode that gives a macro SolidWorks and
nothing else, with every default and option disclosed in the docs.

Windows can't take rights away from one macro inside SolidWorks, so the
limit is a check of the source before it runs: only names known to be
safe are allowed, and anything else is refused.

## What Changes

- `SOLIDWORKS_MCP_ALLOW_VBA_SOURCE` takes three values instead of on/off:
  - `off`, the default: VBA source is refused (`vba_source_off`);
  - `restricted`: the source runs only if it passes the check below;
  - `full`: it runs unchecked, as #246 did with `1`.

  Any other value stops the server at start with the valid ones listed.
- **The restricted check** reads the source, ignoring comments and quoted
  text. Every name must be one of these:
  - a VBA keyword;
  - a safe VBA function (maths, text, conversions, dates, `MsgBox`,
    `InputBox`, `Debug.Print`, `Err`);
  - a name the macro declares itself;
  - a SolidWorks enum name or value;
  - a SolidWorks type name;
  - after a `.`, a member of the installed SolidWorks type library.
- **Refused even so:**
  - VBA that reaches outside SolidWorks: `Shell`, `CreateObject`,
    `GetObject`, `CallByName`, `Declare` (direct Windows calls), file
    statements (`Open`, `Kill`, `Name ... As`, `MkDir`, `Print #` and
    the like), `Environ`, `SendKeys`;
  - `Application`, apart from `Application.SldWorks`;
  - about 100 SolidWorks members that write or open files, run macros or
    commands, close or quit, or change saved settings or add-ins. The
    list is in the docs.
- A refused source is an error, `vba_source_refused`, that lists every
  name and line refused. Nothing is written or run.
- The installation guide gets a full table: each value, what it allows and
  refuses, the default, the blocked members, and what the check can't
  promise (it checks the source; it is not a sandbox).

## Capabilities

### Modified Capabilities
- `tools/macro-execution`: the three levels and the restricted check.

## Impact

- `config.py`: `allow_vba_source` becomes `off`/`restricted`/`full`.
- New `tools/vba_check.py`, a pure checker with no COM.
- `tools/macro_recording.py`, the error classifier, the installation
  guide, the catalog entry and the live test.
