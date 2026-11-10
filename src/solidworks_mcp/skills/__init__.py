"""The agent skill shipped with the server, and the instructions sent at connection.

The skill folder (``solidworks-mcp/``) is plain files inside the package, so
every install has it: the server serves it as ``skill://`` resources, and
``solidworks-mcp skill install`` copies it into an agent's skills folder.
"""

from __future__ import annotations

from pathlib import Path

#: The skill's name, as in its ``SKILL.md`` frontmatter and its folder name.
SKILL_NAME = "solidworks-mcp"

#: The packaged skill folder.
SKILL_DIR = Path(__file__).parent / SKILL_NAME

#: Sent in the MCP initialize response: only what every session needs.
SERVER_INSTRUCTIONS = """\
SolidWorks MCP server: drive SolidWorks parts, assemblies and drawings.

- Start with `get_model_info` (or `list_open_documents`) to see what is open.
- Build in this order: `create_part`, `create_sketch`, draw (`add_rectangle`, \
`add_circle`, ...), `exit_sketch`, then the feature (`create_extrusion`, \
`create_cut_extrude`, `create_revolve`). Features use the sketch `sketch_name` \nnames, or the one you closed last.
- Inputs are millimetres and degrees unless a field says metres.
- A tool's success does not prove the geometry is right: finish a build with \
`verify_model`, giving the size, volume or counts you expect.
- A tool whose description starts "Not available yet" returns `not_supported`; \
use the tool it names instead.
- On an error, read `error_type` and `hint`; `rebuild_model` names failing \
features and `undo` steps back.

Full guidance (workflows, selection, units, known limits): read the resource \
skill://solidworks-mcp/SKILL.md.
"""
