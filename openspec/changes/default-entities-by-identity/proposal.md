## Why

On a non-English SolidWorks the default planes, the origin and the standard
views have translated names, and the tools name them in English. #261 made
that work on French by hooking pywin32's dispatch for the whole process:
when `FeatureByName`, `SelectByID2` or `CreateDrawViewFromModelView3` fails
on an English default name, it retries with a local name found from the
tree, the view list or a French table. It works, but:

1. the hook changes how every COM object in the process behaves and can't
   be turned off, which makes a failure hard to trace;
2. it keeps one cache of learned names for the session, filled from
   whichever document is active, which may not be the one being worked on;
3. it only covers those three calls; any other call that takes a default
   name (`ShowNamedView2` with a name, a mate entity by name) still fails.

A plane can be found without its name: the first three reference planes in
any part, assembly or component are Front, Top and Right, in every language
and template, and the standard views have fixed IDs. The user chose this
over translation tables (2026-11-24): find the default entities by identity
at the call sites, for each document, with no global hook.

## What Changes

- **Default planes and the origin are found by identity.** One helper reads
  a document's (or a component's) tree and returns its Front, Top and Right
  planes and its origin by type and order. Every tool that names a default
  plane (`create_sketch`, `create_reference_plane`, `create_axis`, mirrors,
  patterns, mates, explode steps, `select_feature`) resolves `Front`, `Top`,
  `Right`, `XY`, `XZ`, `YZ`, `Front Plane`... through it, in any language.
  A name that isn't a default is used as given.
- **Standard views by ID.** Where SolidWorks takes an ID
  (`ShowNamedView2("", id)`), the view is shown by its
  `swStandardViews_e` ID. Where it needs a name (a drawing view from a
  model view), the name comes from that model's own `GetModelViewNames`,
  read when the view is placed.
- **The global hook and the French table are removed** (`l10n.py`, its
  install on connect, its tests); COM pitfall 39 describes the new way.
- **The install's language** stays in `get_model_info` and the selftest
  report (both read `GetCurrentLanguage` today); a refused default-plane
  name says the language, so a report from a new language is easy to read.
- The hard-coded Spanish, Chinese and Japanese plane aliases in
  `create_sketch` go: the helper covers every language.
- From #262 (German SolidWorks 2025, the same failure): `create_sketch`'s
  `SelectByID2` fallback passes `_null_callout()` instead of a bare `None`
  (the `Typenkonflikt`), and no longer falls through to any default plane
  when the one asked for isn't found; `create_drawing_view` uses a `*`-named
  `view_type` as given; `generate_drawing_package` places its isometric by
  the model's own name; `insert_bom_table` with no position keeps the table
  inside the drawing border. `create_sketch`'s `XY`/`XZ` are corrected to
  Front/Top, as in SolidWorks.
- This change closes #262.

Not in this change: Z-up part templates (some French templates put the Top
plane on XY); the selftest's expectations assume Y-up. That is its own
issue.

## Capabilities

### New Capabilities

- `tools/default-entities`: default planes, the origin and the standard
  views found by identity in any language.

### Modified Capabilities

None (the tools keep their inputs; they now work on any language).

## Impact

- New adapter module `adapters/solidworks/default_entities.py`, on top of
  `feature_walk.walk_feature_tree`.
- Call sites in `sketch.py`, `features.py`, `io.py`, `assembly.py`,
  `pywin32_adapter.py`, `drawing_standard.py`; `l10n.py` and its tests
  removed.
- Docs: COM pitfall 39, the CHANGELOG.
- Tests: fake trees with French and renamed planes; a live test that renames
  a part's default planes and origin (as a translated template would) and
  runs a sketch, an axis, a mirror and a drawing view on it.
- No new dependency; English installs behave as before.
