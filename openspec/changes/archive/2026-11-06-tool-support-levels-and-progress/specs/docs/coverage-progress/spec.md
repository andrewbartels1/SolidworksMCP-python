## ADDED Requirements

### Requirement: COM coverage is counted from a committed snapshot

The project SHALL keep a snapshot of the SolidWorks type library's interface and method names, and count coverage by scanning the adapter source for those method names, without needing SolidWorks.

#### Scenario: Counting coverage
- **WHEN** the generator runs on any platform
- **THEN** it reports, for each core interface, the methods the adapters call out of its total, and the same for the whole API, from the snapshot and the adapter source only

#### Scenario: Refreshing the snapshot
- **WHEN** the snapshot script runs on Windows with SolidWorks installed
- **THEN** it rewrites the snapshot from the installed type library and records the SolidWorks version it came from

### Requirement: Progress bars at the top of the README

The README SHALL open with a generated progress image: the tools by support level and the core COM coverage, with the whole-API figure, linking to the interactive page.

#### Scenario: The image matches the code
- **WHEN** a tool, a level or the adapter's COM calls change and the image and data are not regenerated
- **THEN** the progress check fails and says which command regenerates them

#### Scenario: Readable in both themes
- **WHEN** the README is viewed in GitHub's light or dark theme
- **THEN** the image draws its own dark panel, so the bars and their text look the same

### Requirement: An interactive progress page

The docs site SHALL have a page with the same bars and every tool and core interface, filterable by level and family.

#### Scenario: Filtering
- **WHEN** a reader picks a level or a family
- **THEN** only the matching tools are shown, each coloured by its level, with its description on hover

#### Scenario: Without JavaScript
- **WHEN** the page is read without scripts
- **THEN** the bars and a plain table of every tool and its level still show
