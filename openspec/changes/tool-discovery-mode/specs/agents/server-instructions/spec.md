## ADDED Requirements

### Requirement: The instructions follow the tool mode
The server's instructions SHALL name the active toolsets. In search mode
they SHALL tell the agent to find tools with `search_tools` and run them
with `call_tool`, and SHALL name no tool the agent can't see.

#### Scenario: Search mode
- **WHEN** a client connects to a server in search mode
- **THEN** the instructions say to search before calling, and every tool
  they name directly is `search_tools`, `call_tool` or an always-visible
  tool

#### Scenario: Core only
- **WHEN** the toolsets are `core`
- **THEN** the instructions don't mention the drawing workflow
