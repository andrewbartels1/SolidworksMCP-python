## 1. Tool

- [x] 1.1 `allow_vba_source` in the config
- [x] 1.2 `vba_source` on `MacroPlaybackInput` (one source only; Windows-1252); written to a `.swb` and run; reply gives `source_file` and `vba_source`
- [x] 1.3 Refused as `vba_source_off` when the setting is off

## 2. Checks and docs

- [x] 2.1 Unit tests: allowed, refused, two sources, bad characters
- [x] 2.2 Live test: a sketch added by VBA source (passed live 2026-11-17)
- [x] 2.3 Catalog entry, installation guide (the setting and its risk), CHANGELOG; full suite, ruff, mypy, docs strict
