## Context

`swconst.tlb` sits beside `sldworks.tlb` and is registered under its own
GUID, `{4687F359-55D0-4CD3-B6CF-2EB42C11F989}`, at the same version (34.0
for SolidWorks 2026, checked with a read-only load). All 983 of its type
infos are enums (`TKIND_ENUM`); each variable's `VARDESC.value` is the
integer.

## Decisions

- **Load by GUID at the main library's version**, with `LoadRegTypeLib`,
  as the main library is loaded. A failure leaves `enums` empty and records
  why in the index (`enums_note`), so the method lookups never fail because
  of it.
- **Saved in the same index** under `enums`: `{name: {description,
  members: [{name, value}]}}`. Format 2.1 makes a 2.0 index rebuild.
- **Member lookup** by scanning the enums for a member of that name: 983
  enums, about 20,000 members, well under a millisecond.
- **`search_solidworks_api_help` is unchanged**; enums are reached through
  the new tool.
