## Context

PR #261 (merged 2026-11-25) added `adapters/solidworks/l10n.py`: on connect it
replaces `win32com.client.dynamic.CDispatch.__getattr__` so that
`FeatureByName`, `SelectByID2` and `CreateDrawViewFromModelView3` retry a
failed English default name with a local one, learned from the active
document's tree (planes by type and order), its view list (views by
position), or a French table. #263 brought it to 100% coverage. Separately,
`create_sketch` tries hard-coded Spanish, Chinese and Japanese aliases.
`export_image` already shows views by `swStandardViews_e` ID.

## Goals / Non-Goals

**Goals:** default planes, origin and standard views right in every
language, resolved per call and per document, visible in the code at each
call site; no global hook; no translation tables.

**Non-Goals:** Z-up templates; localized names of anything else (feature
names such as `Sketch1` come from SolidWorks in the install's language and
are read, never guessed, already).

## Decisions

### 1. One resolver, in `adapters/solidworks/default_entities.py`

- `read_defaults(adapter, owner) -> DefaultEntities` walks forward from
  `FirstFeature` to the `OriginProfileFeature` and takes the `RefPlane`
  features before it (the first three are Front, Top, Right) and the origin.
  It does not use `walk_feature_tree`: that walks the whole tree and then
  every feature again with `FeatureByPositionReverse`, too slow for every
  call; the origin sits near the top.
- `entity_name(adapter, name, owner=None) -> str` returns the document's
  name for a default plane (`Front`, `Top`, `Right`, `XY` = Front, `XZ` =
  Top, `YZ` = Right as in SolidWorks' Y-up orientation, `Front Plane`, ...,
  any case) or the origin, or `name` unchanged when it isn't one. A
  `@component@assembly` suffix reads that component's tree
  (`GetComponentByName`, then its `FirstFeature`) and keeps the suffix.
- A tree that can't be read (the walk never reaches the origin) keeps the
  English name, as before; one that reaches its origin with fewer than three
  planes fails.
- `create_sketch` mapped `XY` to Top and `XZ` to Front, against SolidWorks
  and `face_selection`; corrected, and recorded in the CHANGELOG as a
  behaviour change.
- Every call reads the tree it needs, so there is nothing to keep in step;
  the walk costs about a millisecond per feature and stops at the origin
  (near the top of the tree).
- When the name is a default but the planes can't be found, it raises
  `not_found` listing the document's `RefPlane` names and the language.

### 2. The call sites

Replace each English default name with `plane_name(...)` where the name is
passed to SolidWorks:

- `sketch._select_sketch_plane` (and its alias lists, removed);
- `features`: `_AXIS_PLANE_PAIRS` (axis from two planes), reference planes,
  mirror and pattern planes;
- `io`: mates (`entity_a`/`entity_b` default `Front Plane`), component
  planes;
- `assembly._DIRECTION_PLANES` (explode steps), `mirror_components`;
- `pywin32_adapter` (the assembly's own Front plane);
- `select_feature` and `face_selection` when given a default plane.

### 3. Standard views

- `_NAMED_VIEWS` keeps the English keys and maps each to its
  `swStandardViews_e` ID. Showing a view uses `ShowNamedView2("", id)`.
- A drawing view from a model view (`create_drawing_view`,
  `drawing_standard`) reads the open model's `GetModelViewNames`; the
  standard views are its first ten, in `swStandardViews_e`-independent
  fixed order (normal to, front, back, left, right, top, bottom,
  isometric, trimetric, dimetric), the order #261 found on French. When the
  list is shorter or its first ten don't start with `*`, the English name is
  used, as today.

### 4. Removing the hook

`l10n.py`, the `l10n.install(app)` calls on connect, `test_l10n.py` and the
progress entry go. COM pitfall 39 is rewritten: names of default entities
are per language and per template; find them by identity.

### 5. Testing without a French install

The plane names come from the part template, not the UI language, so a
part whose default planes and origin are renamed `Plan de face`, `Plan de
dessus`, `Plan de droite` and `Origine` is what a French template makes.
The live test renames them (`IFeature.Name`), then runs `create_sketch`
on `Top`, `create_axis`, a mirror about `Right` and a mate; the views are
checked by ID on the English install. Switching SolidWorks' own language
needs that language installed (Installation Manager, Modify) and a restart,
so it is a manual check, not part of the test; the contributor of #261
can confirm on French.

## Risks / Trade-offs

- [A template whose first three planes aren't Front, Top, Right] → every
  SolidWorks template has them first; a document without them fails with
  its planes listed rather than picking the wrong one.
- [A user deliberately names a plane `Top Plane` that isn't the default] →
  the default (by position) wins for the English names; the user's own
  plane can still be named by any other name. Recorded in the tool
  descriptions.
- [The view list order differs in some release] → the names are checked
  to start with `*`; the English name is the fallback, so it fails no worse
  than today.
