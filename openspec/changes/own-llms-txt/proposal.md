## Why

PR #225 offered an `llms.txt` written by someone we don't know. A file
like that tells agents what this project is and where to read, so whoever
writes it decides what an agent believes about the server, and a
hand-written summary drifts from the docs or carries text we never meant
to publish. The user is closing that PR. We want our own file, built from
our own pages, with nothing in it that the docs don't say. While we are
at it, nothing checks the links in the README and the docs (116 different
URLs today), so a moved page or a lapsed domain goes unnoticed.

Queue item 19. PR #225 is not used as a starting point.

## What Changes

- **A generated `llms.txt`** served at the docs site's root
  (`https://andrewbartels1.github.io/SolidworksMCP-python/llms.txt`). A
  script builds it from the mkdocs `nav`: the site name and summary come
  from `mkdocs.yml`, each section is a nav section, and each entry is a
  page, linked by its published URL, with its title and summary copied
  word for word from that page. Nothing in it is written by hand.
- **An offline check**, run with the unit tests and in CI, that fails
  when:
  - the committed `llms.txt` differs from what the script builds now;
  - an `llms.txt` line's title or summary doesn't match its page word for
    word (the report shows the expected and the actual text);
  - `llms.txt` links anywhere but this project's own site or repository,
    or holds HTML, comments, or invisible or direction-changing
    characters;
  - a link in the README or the docs points at a page or file that
    doesn't exist, or at a heading anchor that page doesn't have.
- **An online check** that follows every external URL in `llms.txt`, the
  README and the docs. It fails on a dead link, or a redirect to a
  different site (a link to this repo that lands somewhere else is always
  a failure). It writes a report of every link and its result. It runs
  after each docs deploy and once a week, and by hand with one command;
  it is not part of the unit tests, which stay offline.
- **The broken links found by the first run are fixed** in the same
  change.
- A **security review** of the generated file, recorded in the design:
  only this project's pages, no third-party links, no hidden text, no
  instructions beyond our own page summaries.

No tool, adapter or COM code changes. The server's behaviour is
unchanged.

## Capabilities

### New Capabilities

- `docs/llms-txt`: how `llms.txt` is built from the docs and what it may
  contain.
- `docs/link-check`: which links are checked, offline and online, and
  what counts as a failure.

### Modified Capabilities

None.

## Impact

- New package `src/solidworks_mcp/doc_links/` (the builder, the link
  finder and both checks), run as
  `python -m solidworks_mcp.doc_links`, with tests under
  `tests/solidworks_mcp/doc_links/` at 100% coverage. Network calls are
  faked in the tests.
- New file `docs/llms.txt` (generated, committed).
- `.github/workflows/deploy-docs.yml`: the online check after deploy; a
  weekly schedule.
- `dev-commands.ps1` and the Makefile: one command each for building
  `llms.txt` and for the online check.
- Docs pages and the README: broken links fixed; a short contributor note
  on regenerating `llms.txt`.
- Uses `httpx`, already a dependency. Does not touch COM or adapter code.
