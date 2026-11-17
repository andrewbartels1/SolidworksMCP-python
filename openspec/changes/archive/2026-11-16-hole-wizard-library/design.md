## Context

See proposal.md, Why. Facts checked on this machine (SolidWorks 2026,
2026-11-15), read-only:

- The live library is `swbrowser.sldedb` under the Toolbox data folder,
  named by the registry value `Toolbox Data Location` in
  `HKCU` (then `HKLM`) `\Software\SolidWorks\SOLIDWORKS <year>\General`;
  here `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS Data`, file
  `lang\english\swbrowser.sldedb`. A copy in the install folder
  (`Toolbox\data utilities\lang\English\`) is the install template.
- It is SQLite 3 (20 MB, 5,272 tables). Text is UTF-8 (`Ø` is `C3 98`).
- Per standard prefix (`ISO`, `AI` = ANSI inch, `AM` = ANSI metric, `DIN`,
  `JIS`, ...):
  - `<P>_Type_Holes`: simple and tapped hole types. Columns `Name`,
    `SWconst_Enum_Value` (the `HoleWizard5` fastener index), `DataTable`
    (`+DATA_HW_DrillSizes` -> table `<P>_DATA_HW_DrillSizes`),
    `ValidHoleTypes`, `enabled`.
  - `<P>_TYPE_BS`: bolts and screws, the types counterbore and countersink
    holes are sized for; same columns (`SWConst_Enum_Value`).
  - `ValidHoleTypes` is a bit mask: 1 counterbore, 2 countersink, 4 simple
    hole, 8 tapped, 16 pipe tap. A fastener index of 0 or -1 is not a Hole
    Wizard type. Names can repeat (JIS); rows with a real index win.
  - Size tables have `SIZE`, `enabled`, and dimension columns that vary by
    table (`Diameter`/`DIAMETER`, `CBORE_DIA`, `CBORE_DEPTH`, `PITCH`, ...).
- Our codes today: ISO simple 143 (Drill sizes), counterbore 139 (Cap
  4762), countersink 141 (CTSK Flat 7046-1), tapped 147; ANSI inch 18, 9,
  15, 27. All match the library.
- `swWzdHoleStandards_e`: ansi_inch 0, ansi_metric 1, din 4, iso 8, jis 9.

## Goals / Non-Goals

**Goals:** read every standard's hole types and sizes; `create_hole` picks a
hole type and refuses a size that doesn't exist, before any COM call.

**Non-Goals:** writing to the library (see Adding sizes); slots and pipe
taps; standards beyond the five named (the reader is generic, so adding one
is a table entry, later).

## Decisions

1. **A file read behind the adapter interface, not COM.** `list_hole_sizes`
   is an adapter method like the others (base, circuit breaker, connection
   pool, real, mock), so tools stay adapter-only and the mock serves tests and
   CI. The real adapter's version calls a pure module,
   `adapters/solidworks/hole_library.py`, with no COM, so it runs without
   SolidWorks and outside `_handle_com_operation` (no settle pause, no
   thread check needed). Alternative: a module the tool calls directly;
   rejected because mock mode would then need Windows paths.
2. **Open read-only and immutable:** `sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)`.
   SolidWorks may have the file open; `immutable` takes no lock and writes
   nothing. Table names come from the library's own rows; every one is
   checked against the file's table list. Revised in review (PR #234,
   Bandit B608): no SQL is built as text. A SQLModel engine over that
   connection (`NullPool`, so it closes after each read) reflects the table
   and reads it with `select()`, so SQLAlchemy quotes every identifier.
3. **Finding the file**, first hit wins: the `SOLIDWORKS_MCP_HOLE_LIBRARY`
   setting (a file path); `Toolbox Data Location` from HKCU, then HKLM, for
   each installed SolidWorks year, newest first, with
   `lang\<language>\swbrowser.sldedb` (English first); then the install
   folder's template. Registry access is `winreg`, imported lazily so the
   module imports on Linux.
4. **One cache per process**, keyed by path and file modification time: the
   type rows and size lists of a standard are read once.
5. **Simple holes and screw sizes.** With no `fastener`, a simple hole whose
   size starts with `M` (metric) or `#` / a fraction (inch) uses that
   standard's "Screw Clearances"; a bare diameter (`6`, `Ø6`, `6 mm`) uses
   "Drill sizes" (ANSI inch: "All Drill sizes") and is written as the table
   writes it (`Ø6.0`). Counterbore, countersink and tapped keep today's
   default types. `simple_iso_size` (2026-11-15) is removed.
6. **Nearest sizes:** by numeric distance of the number in the size
   (`M6` -> 6, `Ø6.6` -> 6.6, `#10` -> 10, `1/4` -> 0.25); up to five, in
   table order. Sizes with no number are listed first five.
7. **Unreadable library:** `list_hole_sizes` fails (the spec forbids an
   empty answer); `create_hole` goes ahead with the codes it has and adds a
   warning, since the hole may still build.

8. **A size with its pitch** (found while building it): the ISO tapped
   table lists coarse threads without the pitch (`M6`, not `M6x1.0`), though
   `HoleWizard5` accepted `M6x1.0` live. `M6x1.0` is matched to the `M6` row
   when that row's pitch is 1.0, and the table's spelling is passed on.
9. **The file is closed after each read** (`contextlib.closing`): `with
   sqlite3.connect()` only commits, and a connection left open would keep
   SolidWorks' own library file locked on Windows. The unit tests found it.
10. **Unit tests never read this machine's library:** a conftest gives the
   real adapter's tests the built-in sample library (`sample_library()`, the
   mock adapter's), and the reader is tested against a SQLite file each test
   builds.

## Adding sizes (not in this change)

The user asked for a way to install whole standards and sizes. Findings so
far: sizes live in the size tables above, with an `enabled` column; Toolbox
Settings (SolidWorks' own UI) edits the same file. Writing it ourselves
means writing a file SolidWorks owns, shared by every user of a Toolbox
folder, often on a network drive, with no API. A later change should decide
between enabling existing disabled sizes (low risk), adding rows from a
config file (backup first, SolidWorks closed), or documenting Toolbox
Settings. Asked for, not designed here.

## Risks / Trade-offs

- [Schema differs between SolidWorks years] -> the reader uses only the
  columns named above, matched case-insensitively; a missing one is a clear
  error naming the table, and the live test runs on the installed year.
- [A Toolbox on a slow network share] -> one read per standard per process.
- [Reading the user's files] -> only the library file, read-only; nothing
  from it is logged beyond counts.
