## 1. Fillet on every version (#255)

- [x] 1.1 `_add_fillet_impl`: always `IModelDoc2.FeatureFillet3`; the version check and the `IFeatureManager.FeatureFillet3` branch removed
- [x] 1.2 Tests: a 2024 revision takes the same call; the tests that reached the old branch by giving no version move to the model call

## 2. View scale and view_type (#256)

- [x] 2.1 `_place_view`: `UseSheetScale` off, `ScaleDecimal` set, read back for `scale_applied` (and the scale read back in the reply)
- [x] 2.2 `CreateDrawingViewInput.orientation` defaults to none; `view_type` that names a view is used, else `front`
- [x] 2.3 Tests beside each; the drawing catalog entry

## 3. The index folder (#257)

- [x] 3.1 `_INDEX_DIRS`: `~/.solidworks_mcp/docs-index` first (where an index is saved), then the old relative folders (read only)
- [x] 3.2 Tests: a build saves to the user folder; an old relative index is still found; the catalog and tool description

## 4. Checks and sign-off

- [x] 4.1 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check; CHANGELOG
- [x] 4.2 Live on 2026: a fillet, a half-scale view, and a lookup started from a read-only folder
- [ ] 4.3 The user decides what to say on #255, #256, #257 and when; nothing is posted until then (replies drafted 2026-11-20: fixed in the release, then the selftest on 2024)
- [ ] 4.4 After the merge: release 2.1.0 from main (pyproject, version.py, server.json, CHANGELOG heading), tag pushed by the user's OK
