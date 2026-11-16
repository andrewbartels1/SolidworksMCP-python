# docs/link-check Specification

## Purpose
Every link in the README, the docs and `llms.txt` is checked: links within the project offline on every test run, and links to other sites online after each docs deploy and once a week.
## Requirements
### Requirement: Which links are checked

The checks SHALL cover every link in `README.md`, every Markdown page under `docs/`, and `docs/llms.txt`: inline links, reference-style links, autolinks, and images. Links inside fenced or inline code SHALL be left out, since they are examples (such as `http://127.0.0.1:11434`), not links. `mailto:` links SHALL be left out.

#### Scenario: An example URL in a code block
- **WHEN** a page shows `http://YOUR-WINDOWS-IP:8000` inside a code block
- **THEN** neither check visits it

#### Scenario: A link in prose
- **WHEN** a page links to `https://modelcontextprotocol.io` in a sentence or a badge
- **THEN** the online check visits it

### Requirement: Links within the project are checked offline

On every test run, without network access, the check SHALL fail when a relative link, a link to `site_url`, or a `<repo_url>/blob/<branch>/<path>` or `tree` link points at a page or file that does not exist, or at a `#anchor` that the target page has no heading or explicit `{#id}` for. Anchors SHALL be worked out the way the docs site makes them.

#### Scenario: A moved page
- **WHEN** a page links to `getting-started/old-name.md` and that file does not exist
- **THEN** the check fails and names the page, the line and the link

#### Scenario: A missing anchor
- **WHEN** a page links to `tools-overview.md#deprecated-tools` and that page has no heading whose anchor is `deprecated-tools`
- **THEN** the check fails and names the page, the line and the anchor

#### Scenario: An anchor that exists
- **WHEN** a page links to `../progress.md` or to a heading or `{#ujoint}` id that exists
- **THEN** the check passes it

### Requirement: Links to other sites are checked online

A separate command SHALL visit every external URL once and fail when a URL does not answer with success, or when it redirects to a different site. The same site means the same host with `www.` ignored, a subdomain of it (`codecov.io` to `app.codecov.io`), or a host listed with a reason as belonging to it (GitHub's content hosts). A GitHub issue or pull request link SHALL be checked through GitHub's API, which serves scripts, since the pages themselves rate-limit them. A site that refuses every script SHALL be listed with its reason, and the report SHALL show it as "not checked" rather than leave it out. The command SHALL write a report listing every link, where it appears, the result and, for a redirect, where it went. Network trouble that is not the link's fault (a timeout) SHALL be retried before the link is failed. The command SHALL run after each docs deploy and once a week, and SHALL NOT run as part of the unit tests.

#### Scenario: A dead link
- **WHEN** a URL answers 404, or its host does not resolve
- **THEN** the command fails and the report names the URL, every page and line it appears on, and the result

#### Scenario: A redirect to another site
- **WHEN** a URL redirects to a different host (such as a lapsed domain parked elsewhere)
- **THEN** the command fails and the report shows the link and where it ended up, so the link can be updated or removed

#### Scenario: A redirect on the same site
- **WHEN** `https://www.microsoft.com/windows` redirects to `https://www.microsoft.com/en-us/windows`
- **THEN** the link passes, and the report shows where it went

#### Scenario: A subdomain redirect
- **WHEN** `https://codecov.io/gh/owner/repo` redirects to `https://app.codecov.io/gh/owner/repo`
- **THEN** the link passes

#### Scenario: A site that refuses scripts
- **WHEN** a URL's site is on the not-checked list
- **THEN** it is not visited, and the report lists it as "not checked" with the reason

#### Scenario: Every link is reported
- **WHEN** the command finishes
- **THEN** the report lists every external URL it visited, including the ones that passed, so a reader can see that every link was checked

