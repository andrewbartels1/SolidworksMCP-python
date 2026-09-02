## Purpose

Lets a caller rename an existing feature on the feature tree — the one gap
left after suppress/unsuppress/delete/undo shipped in PR #68.

## ADDED Requirements

### Requirement: Feature can be renamed by its current name
The adapter SHALL expose `rename_feature`, which renames a feature
identified by its current name and returns the applied name.

#### Scenario: Successful rename
- **WHEN** `rename_feature` is called with an existing feature's name and
  a new name
- **THEN** the feature's name is updated and the response reports it

### Requirement: Rename fails clearly instead of silently succeeding
`rename_feature` SHALL return a failed `AdapterResult` — never raise an
unhandled exception or report success — when the feature can't be found,
or when the new name collides with an existing feature on the same tree.

#### Scenario: Feature not found
- **WHEN** `rename_feature` is called with a name matching no feature on
  the active document
- **THEN** the response status indicates failure and nothing is renamed

#### Scenario: Name collision
- **WHEN** the requested new name already belongs to another feature on
  the same tree
- **THEN** the response status indicates failure and the original
  feature's name is unchanged
