# docs/llms-txt Specification

## Purpose
`llms.txt` tells agents what this project is and which pages to read. It is built from the project's own docs, so every word in it is a word the docs already say.
## Requirements
### Requirement: llms.txt is built from the docs nav

The project SHALL publish an `llms.txt` at the docs site's root, built by a command from `mkdocs.yml` and the pages it lists, in the llms.txt format: an `# ` title line, a `> ` summary line, then one `## ` section per top-level nav section, each a list of `- [title](url): summary` entries. The title line SHALL be `site_name` and the summary line `site_description`. Pages SHALL appear in nav order. A nav entry that is not a Markdown page in `docs/` (such as the generated API reference) SHALL be left out.

#### Scenario: Building the file
- **WHEN** the build command runs
- **THEN** it writes `docs/llms.txt` with one entry for every Markdown page in the nav, in nav order, under its nav section, and the site serves it at `<site_url>/llms.txt`

#### Scenario: A top-level page
- **WHEN** a page sits at the top level of the nav (such as Home or Demos)
- **THEN** it is listed under a `## Overview` section, which comes first

#### Scenario: The committed file is stale
- **WHEN** a page's title or opening paragraph, or the nav, changes and `docs/llms.txt` is not rebuilt
- **THEN** the check fails, names the first line that differs, and says which command rebuilds the file

### Requirement: Entries are copied word for word from their pages

Each entry's title SHALL be the page's `# ` heading, and its summary the page's first paragraph of prose after that heading, both copied word for word. Prose means a paragraph that is not a blockquote, admonition, list, table, code block, image, badge line or HTML. Links inside the summary SHALL be reduced to their text; other Markdown (inline code, emphasis) SHALL be kept as written. A paragraph broken over several source lines SHALL be joined with single spaces. Nothing in the file SHALL be written by hand.

#### Scenario: A page's opening paragraph
- **WHEN** a page's heading is `# Tools Overview` and its first prose paragraph is "The SolidWorks MCP Server provides 123 specialized tools for CAD automation. This page is a navigation map: …"
- **THEN** its entry is `- [Tools Overview](<site_url>/user-guide/tools-overview/): The SolidWorks MCP Server provides 123 specialized tools …` with the paragraph in full

#### Scenario: A page with no opening paragraph
- **WHEN** a nav page has no `# ` heading, or no prose paragraph before its first `## ` heading
- **THEN** the build fails and names the page, so the page gets a heading and an opening paragraph rather than the file getting hand-written text

#### Scenario: An entry that doesn't match its page
- **WHEN** a line in `docs/llms.txt` is edited by hand so its title or summary differs from its page
- **THEN** the check fails and reports, for that line, the page, the expected text and the text found

### Requirement: llms.txt holds only this project's own content

Every URL in `llms.txt` SHALL be under the docs site (`site_url`) or this repository on GitHub (`repo_url`). The file SHALL contain no HTML tags, no HTML comments, and no invisible or direction-changing characters (zero-width characters, the byte-order mark, bidirectional controls, other format or control characters except the line break). Every line SHALL be one of the shapes the format allows (title, summary, section heading, entry, blank).

#### Scenario: A third-party link
- **WHEN** a summary's source paragraph links to another site
- **THEN** the entry keeps only the link's text, and no URL outside this project appears in the file

#### Scenario: Hidden text
- **WHEN** a page's title or opening paragraph contains a zero-width or bidirectional control character, or an HTML comment
- **THEN** the build fails and names the page and the character's code point

#### Scenario: A line of the wrong shape
- **WHEN** `docs/llms.txt` contains a line that is not a title, summary, section heading, entry or blank line
- **THEN** the check fails and names the line

