## ADDED Requirements

### Requirement: The skill teaches cross-tool use of the server

The package SHALL include a skill named `solidworks-mcp`: a `SKILL.md` with
a name and a description in its frontmatter, plus reference files. It SHALL
cover:

- the build order: create or open a document, `create_sketch`, draw,
  `exit_sketch`, then the feature tool; and `verify_model` as the last step;
- units: inputs in millimetres and degrees, naming each input that takes
  metres instead;
- choosing planes, faces and edges, and preferring a whole face over a point
  on an edge;
- reading back after every change, and what a success does and does not
  prove;
- recovering from a failure (`rebuild_model`, `undo`, `get_model_info`);
- the tools that can't run yet and the known faults agents must work around;
- when to use the VBA generation tools instead.

`SKILL.md` SHALL stay under 500 lines and put detail in the reference files.

#### Scenario: An agent reads the skill

- **WHEN** an agent loads `SKILL.md`
- **THEN** its frontmatter has `name: solidworks-mcp` and a description that
  says when to use it
- **AND** its body lists the build order and the unit rule

### Requirement: The skill names only real tools, correctly

Every tool name the skill mentions SHALL be a tool the server registers. A
tool the skill tells agents to call SHALL NOT be one that can't run yet
(every call returns `not_supported`).

#### Scenario: A tool is renamed or removed

- **WHEN** a tool the skill names is no longer registered
- **THEN** the test suite fails, naming the tool and the skill file

#### Scenario: The skill recommends a tool that can't run

- **WHEN** the skill's build steps name a tool that returns `not_supported`
  for every call
- **THEN** the test suite fails

### Requirement: The server serves the skill

The server SHALL expose the skill as MCP resources: `SKILL.md` at
`skill://solidworks-mcp/SKILL.md`, a manifest listing its files, and each
reference file. Reading them SHALL need no SolidWorks connection.

#### Scenario: A client lists the server's resources

- **WHEN** a client lists resources on a running server, in mock mode or real
- **THEN** `skill://solidworks-mcp/SKILL.md` is listed
- **AND** reading it returns the same text as the packaged `SKILL.md`

### Requirement: One command installs the skill into an agent

`solidworks-mcp skill install` SHALL copy the packaged skill into
`<skills folder>/solidworks-mcp/`. The skills folder SHALL be Claude Code's
user folder (`~/.claude/skills`) by default, the current project's
`.claude/skills` with `--project`, or any folder given with `--dir`. It
SHALL report the path it wrote.

It SHALL write only inside `<skills folder>/solidworks-mcp/`, SHALL NOT read
or change any other file (no client config, no other skill), and SHALL work
offline with no account or token. When the folder already holds the skill,
it SHALL replace the packaged files and leave any other file in that folder
alone. `--dry-run` SHALL report what it would write without writing.

#### Scenario: First install for Claude Code

- **WHEN** a user runs `solidworks-mcp skill install`
- **THEN** `~/.claude/skills/solidworks-mcp/SKILL.md` exists, identical to
  the packaged one
- **AND** the command prints that path

#### Scenario: Upgrading after a new release

- **WHEN** the skill folder already holds an older copy and a file the user
  added
- **THEN** the packaged files are replaced
- **AND** the user's file is unchanged

#### Scenario: Another agent

- **WHEN** a user runs `solidworks-mcp skill install --dir <folder>`
- **THEN** the skill is written to `<folder>/solidworks-mcp/`

#### Scenario: The target can't be written

- **WHEN** the skills folder can't be created or written
- **THEN** the command exits with an error that names the path
- **AND** nothing outside that path has changed
