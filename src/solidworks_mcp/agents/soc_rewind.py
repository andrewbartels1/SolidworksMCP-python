"""SolidWorks-as-Code rewind: roll back to a named checkpoint.

Two complementary operations:

1. **Model rewind** — open the .sldprt saved at a checkpoint in SolidWorks.
2. **Script rewind** — truncate a generated script to the checkpoint boundary,
   returning only the lines up to (and including) the checkpoint comment block.

The combination gives you a clean slate: the model is at checkpoint state and
the script reflects exactly what produced it.  Continue building from there by
appending new tool calls.

Usage::

    from solidworks_mcp.agents.soc_rewind import rewind_to_checkpoint, truncate_script_at

    # Open the model and get the truncated script
    script_so_far = await rewind_to_checkpoint(
        adapter,
        session_id="my-session",
        label="base-extrude",
    )

CLI (model rewind only — prints truncated script to stdout)::

    python -m solidworks_mcp.agents.soc_rewind <session_id> <label>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Script-side rewind (no SolidWorks required)
# ---------------------------------------------------------------------------

# Matches the opening line of a checkpoint comment block:
#   "        # ── checkpoint ──..."
_CP_OPEN_RE = re.compile(r"^\s*#\s*--\s*checkpoint", re.IGNORECASE)
# Matches "        # label:    <value>"
_CP_LABEL_RE = re.compile(r"^\s*#\s*label:\s*(.+)$", re.IGNORECASE)


def parse_script_checkpoints(script_text: str) -> list[dict[str, Any]]:
    """Parse all checkpoint comment blocks from a generated SoC script.

    Returns a list of dicts with keys: label, file, line_start, line_end.
    line_start and line_end are 0-based indices into script_text.splitlines().
    """
    lines = script_text.splitlines()
    checkpoints: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if _CP_OPEN_RE.match(lines[i]):
            block_start = i
            label = ""
            file_path = ""
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("#"):
                m_label = _CP_LABEL_RE.match(lines[j])
                if m_label:
                    label = m_label.group(1).strip()
                m_file = re.match(r"^\s*#\s*file:\s*(.+)$", lines[j], re.IGNORECASE)
                if m_file:
                    file_path = m_file.group(1).strip()
                j += 1
            checkpoints.append(
                {
                    "label": label,
                    "file": file_path,
                    "line_start": block_start,
                    "line_end": j - 1,
                }
            )
            i = j
        else:
            i += 1
    return checkpoints


def truncate_script_at(script_text: str, label: str) -> str:
    """Return the script truncated to (and including) the named checkpoint block.

    Everything after the checkpoint comment is removed.  The result is a valid
    script that can be run to reproduce the model state up to that label.

    Args:
        script_text: Full generated script text.
        label: Checkpoint label to truncate at (e.g. "base-extrude").

    Returns:
        Truncated script text, or the full script if label not found.

    Raises:
        KeyError: If no checkpoint with that label exists in the script.
    """
    checkpoints = parse_script_checkpoints(script_text)
    match = next((c for c in checkpoints if c["label"] == label), None)
    if match is None:
        available = [c["label"] for c in checkpoints]
        raise KeyError(
            f"Checkpoint {label!r} not found in script. Available: {available}"
        )
    lines = script_text.splitlines(keepends=True)
    # Include everything up through the closing rule line of the checkpoint block
    end_line = match["line_end"] + 1
    truncated_lines = lines[:end_line]
    # Append the script footer so the truncated version is still runnable
    if not any("await adapter.disconnect()" in line for line in truncated_lines):
        truncated_lines.append(
            '\n    finally:\n        await adapter.disconnect()\n\n\nif __name__ == "__main__":\n    asyncio.run(build_part())\n'
        )
    return "".join(truncated_lines)


# ---------------------------------------------------------------------------
# Model-side rewind (requires adapter)
# ---------------------------------------------------------------------------


async def rewind_to_checkpoint(
    adapter: Any,
    session_id: str,
    label: str,
    *,
    db_path: Path | None = None,
    script_text: str | None = None,
) -> str | None:
    """Open the checkpoint model in SolidWorks and return the truncated script.

    Args:
        adapter: Connected SolidWorks adapter (CircuitBreakerAdapter or equivalent).
        session_id: The SoC session ID.
        label: Checkpoint label to rewind to.
        db_path: Override default SQLite DB path.
        script_text: If provided, also truncate this script text at the checkpoint.
            Pass the output of export_session() to get the truncated version back.

    Returns:
        Truncated script text if script_text was provided, else None.

    Raises:
        RuntimeError: If the checkpoint is not found in the DB or the file cannot
            be opened.
    """
    from .history_db import get_soc_checkpoint

    cp = get_soc_checkpoint(session_id, label, db_path=db_path)
    if cp is None:
        raise RuntimeError(
            f"Checkpoint {label!r} not found for session {session_id!r}. "
            "Run list_soc_checkpoints() to see available labels."
        )

    file_path = cp["file_path"]
    result = await adapter.open_model(file_path)
    if not result.is_success:
        raise RuntimeError(
            f"Failed to open checkpoint file {file_path!r}: {result.error}"
        )

    if script_text is not None:
        try:
            return truncate_script_at(script_text, label)
        except KeyError:
            # Script doesn't have the comment block yet — return as-is
            return script_text

    return None


def list_checkpoints(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all SoCCheckpoints for a session (DB query).

    Args:
        session_id: The SoC session ID.
        db_path: Override default SQLite DB path.

    Returns:
        Ordered list of checkpoint dicts with keys: id, label, file_path,
        first_record_id, last_record_id, snapshot_id, created_at.
    """
    from .history_db import list_soc_checkpoints

    return list_soc_checkpoints(session_id, db_path=db_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m solidworks_mcp.agents.soc_rewind <session_id> <label>")
        sys.exit(1)
    session_id = sys.argv[1]
    label = sys.argv[2]
    checkpoints = list_checkpoints(session_id)
    match = next((c for c in checkpoints if c["label"] == label), None)
    if match is None:
        available = [c["label"] for c in checkpoints]
        print(f"Checkpoint {label!r} not found. Available: {available}")
        sys.exit(1)
    print(f"Checkpoint: {match['label']}")
    print(f"  file:     {match['file_path']}")
    print(f"  records:  {match['first_record_id']}–{match['last_record_id']}")
    print(f"  created:  {match['created_at']}")
    print()
    print(f"To rewind: open {match['file_path']!r} in SolidWorks")


if __name__ == "__main__":
    _cli()
