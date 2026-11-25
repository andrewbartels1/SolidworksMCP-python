## 1. The resolver

- [ ] 1.1 `adapters/solidworks/default_entities.py`: `default_planes` (walk, first three `RefPlane` before the origin), `plane_name` (aliases, case, `@component` suffix), the `not_found` message with the planes and the language
- [ ] 1.2 Standard views: `swStandardViews_e` IDs; the model's view name by position, English fallback
- [ ] 1.3 Unit tests with fake trees: English, French, renamed, too few planes, a component suffix, a view list that's too short

## 2. Call sites

- [ ] 2.1 `create_sketch`: the resolver; the alias lists removed
- [ ] 2.2 `features`: axis plane pairs, reference planes, mirror and pattern planes
- [ ] 2.3 `io` mates, `assembly` explode planes and mirror, `pywin32_adapter`, `select_feature`, `face_selection`
- [ ] 2.4 Views: `ShowNamedView2` by ID; drawing views by the model's own name
- [ ] 2.5 Tests beside each changed module

## 3. Remove the hook

- [ ] 3.1 `l10n.py`, its install on connect and `test_l10n.py` removed (after #263 is merged)
- [ ] 3.2 COM pitfall 39 rewritten; CHANGELOG

## 4. Checks and sign-off

- [ ] 4.1 Unit suite at 100% coverage, ruff, mypy, mkdocs strict
- [ ] 4.2 Live: `tests/live/test_live_sw_default_entities.py` renames a part's default planes and origin to the French names, then a sketch on `Top`, an axis, a mirror about `Right`, a mate, and an isometric drawing view; ask before running
- [ ] 4.3 Ask the #261 contributor to run the selftest on French (the user decides when and how)
