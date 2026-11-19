## 1. Fit

- [x] 1.1 `_fit_title_block` fits every linked note after the two named fields; a property shown twice is fitted once; names from `update_title_block`'s fields, else the property; unit tests (a long linked field shrunk, a short one unchanged, a duplicate fitted once, a note with no link left alone)

## 1b. Subtitle (the user's question on #158: follow standard practice)

- [x] 1b.1 ISO 7200: `subtitle` is the supplementary title, the TITLE's second line; the company field holds `company` only; the TITLE at 60% of the format's height (or the caller's cap); unit tests
- [ ] 1b.2 Live: the drawing test passes a subtitle and checks the TITLE's two lines

## 2. Docs

- [x] 2.1 `generate_drawing_package`'s catalog entry, CHANGELOG, queue row 31
- [x] 2.2 Full mock suite at 100% coverage, ruff, mypy, `mkdocs build --strict`

## 3. Live

- [ ] 3.1 `test_generate_drawing_package_on_a_block` asserts every listed field fits; run by the user
- [ ] 3.2 Archive after the user's pass
