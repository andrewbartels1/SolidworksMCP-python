## ADDED Requirements

### Requirement: Model info includes the file's details
`get_model_info` SHALL report, besides what it reports today, the active
document's file size in bytes and its created and modified times, read
from the file on disk. For a document never saved, they SHALL be `null`.

#### Scenario: A saved part
- **WHEN** a part saved to disk is active and an agent calls
  `get_model_info`
- **THEN** the reply has `size_bytes` above 0 and `created` and `modified`
  times, as `get_file_properties` reports them

#### Scenario: A new, unsaved part
- **WHEN** a part never saved is active
- **THEN** `size_bytes`, `created` and `modified` are `null`, and the call
  succeeds
