## 1. The resolver

- [x] 1.1 `adapters/solidworks/default_entities.py`: `read_defaults` (a short forward walk to the origin), `entity_name` (aliases, case, `@component` suffix), the `not_found` message with the planes and the language
- [x] 1.2 Standard views: `standard_view_name` takes the model's name by position, English fallback (`export_image` already shows views by `swStandardViews_e` ID)
- [x] 1.3 Unit tests with fake trees: English, French, German, renamed, too few planes, unreadable and looping trees, a component suffix, view lists that are too short or not standard

## 2. Call sites

- [x] 2.1 `create_sketch`: the resolver; the alias lists and the fall-through to any default plane removed; `_null_callout()` in the `SelectByID2` fallback (#262); `XY` = Front, `XZ` = Top
- [x] 2.2 `features`: `_select_named_feature`, `_select_reference_entity` and `_select_feature_by_name` (axis plane pairs, reference planes, mirror and pattern planes)
- [x] 2.3 `io` mates (the component's own tree), `assembly._select_named` (explode planes, mirror), `pywin32_adapter.select_feature`, `face_selection.plane_geometry`
- [x] 2.4 Views: `create_drawing_view` by the model's own name, and a `*`-named `view_type` used as given (#262); `generate_drawing_package`'s isometric and front view
- [x] 2.5 Tests beside each changed module
- [x] 2.6 `insert_bom_table`: a table placed by the anchor is kept inside the border, 10 mm in (#262)

## 3. Remove the hook

- [x] 3.1 `l10n.py`, its install on connect and `test_l10n.py` removed
- [x] 3.2 COM pitfall 39 rewritten; CHANGELOG; the `create_sketch` plane description

## 4. Checks and sign-off

- [x] 4.1 Unit suite at 100% coverage, ruff, mypy, mkdocs strict
- [ ] 4.2 Live: `tests/live/test_live_sw_default_entities.py`, three tests (a translated part; the standard view list; a BOM inside the border on SW 2026); ask before running
- [ ] 4.3 Ask the #261 and #262 reporters to try it on French and German (the user decides when and how)
