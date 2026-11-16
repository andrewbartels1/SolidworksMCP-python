## 1. Reading the docs

- [x] 1.1 `pyyaml` added to the `dev` and `test` extras; the `doc_links` package with `__init__.py` and its test package
- [x] 1.2 `pages.py`: load `mkdocs.yml` with `!!python/...` tags ignored; walk `nav` into (section, nav title, path) in order, leaving out entries that aren't `.md` files in `docs/`; a page's URL from `site_url` with directory URLs; tests
- [x] 1.3 A page's `# ` title and first prose paragraph (the skip rules in design decision 2; links reduced to their text; lines joined); a page with neither raises, naming it; tests for each skipped block kind
- [x] 1.4 Heading ids: the toc slugify with `_1`, `_2` for repeats, plus `{#id}`; tests, and the parity test against `markdown.extensions.toc.slugify` over every docs heading (skipped without `markdown`)

## 2. llms.txt

- [x] 2.1 `llms_txt.py` build: title and summary lines from `mkdocs.yml`, `## Overview` first, then the nav sections, entries in nav order; tests
- [x] 2.2 The content rules shared by build and check: allowed URLs, line shapes, no `Cf`/`Cc` characters except `\n`, no HTML tag or comment; the builder names the page, the checker the line; tests for each rule
- [x] 2.3 Check a committed text: stale (first differing line and the rebuild command); for an entry that differs, the page, the expected text and the text found; tests
- [x] 2.4 `__main__.py` with `build`, `check`, `check-external`; exit codes; loguru output; tests

## 3. Links

- [x] 3.1 `links.py` finder: inline, reference-style, autolinks and images, each with file and line; nothing inside fenced or inline code; `mailto:` skipped; tests
- [x] 3.2 Offline check: relative links from the page (README from the repo root), `site_url` links mapped to `docs/`, non-Markdown files must exist, anchors against the target's heading ids; tests for a missing page, a missing anchor, a good anchor, an image
- [x] 3.3 Online check (design decision 6): one GET per unique URL, the same-host rule, our-URL rule, retries, concurrency, User-Agent; faked transport in the tests for 200, 404, DNS failure, timeout then success, same-host and cross-host redirects
- [x] 3.4 The Markdown report at `tests/.generated/link-report.md` listing every URL with its result and locations; tests

## 4. Run it on the real docs

- [x] 4.1 Run the offline check on the README and docs; fix every broken link and anchor it finds, in the pages
- [x] 4.2 Build `docs/llms.txt`; read every entry, and give each page whose opening reads badly (a "Last updated" line, a sentence ending in a colon, `docs/index.md`'s feedback note) a real opening paragraph, in the page; rebuild
- [x] 4.3 Integration tests in `tests/integration/`: the committed `docs/llms.txt` matches a fresh build, and the offline check passes on the real docs
- [x] 4.4 Run the online check by hand; fix or replace every dead or cross-site link it reports; record the counts in design decision 9

## 5. CI and commands

- [x] 5.1 `deploy-docs.yml`: a link-check job after `deploy`, and a weekly `schedule` that runs only that job; the report uploaded as an artifact
- [x] 5.2 `dev-commands.ps1 dev-llms` / `dev-links` and `make llms` / `make links`
- [x] 5.3 `mkdocs build --strict` copies `llms.txt` to the site root (checked in the built `site/`)

## 6. Docs, review and sign-off

- [x] 6.1 CONTRIBUTING: a short note that `docs/llms.txt` is generated and how to rebuild it, and that page openings are its summaries; the CHANGELOG `Added` entries
- [x] 6.2 Security review of the generated file (design decision 9): entry count, every URL ours, no hidden characters, no summary that reads as an instruction to an agent; recorded in the design
- [x] 6.3 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`, `openspec validate --all`
- [x] 6.4 (merged as #232 2026-11-16) Hand the user the file, the link report and the review (no live SolidWorks demo: nothing here touches SolidWorks); PR closing queue item 19, no attribution; archive and update the queue after the merge
