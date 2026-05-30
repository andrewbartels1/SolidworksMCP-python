"""SolidWorks-as-Code pickup: reverse-engineer manual changes into the script.

When you make changes directly in SolidWorks after the last checkpoint (adding a
fillet, a hole, a sketch, etc.), this module detects them by diffing the current
feature tree against the last saved ModelStateSnapshot and emits new script lines
for the delta.

The pickup result can be appended to the existing generated script, and a new
checkpoint is created so subsequent pickups only diff against the new state.

Feature type coverage
─────────────────────
+--------------------------+--------------------------------------------------+
| Feature type keyword     | Emitted code                                     |
+--------------------------+--------------------------------------------------+
| Boss-Extrude / Extrude   | create_extrusion(ExtrusionParameters(depth=?))   |
| Cut-Extrude / CutExtrude | create_cut_extrude(ExtrusionParameters(depth=?)) |
| Fillet / Round           | add_fillet(radius=?, edge_names=[...])           |
| Chamfer                  | # TODO: add_chamfer(...)                         |
| Sketch                   | create_sketch(...); exit_sketch()                |
| Reference plane          | # TODO: add reference plane                      |
| Mirror / Pattern         | # TODO: mirror / pattern feature                 |
| Everything else          | # TODO: reconstruct <name> (<type>)              |
+--------------------------+--------------------------------------------------+

Depth/radius values cannot be read without a live SolidWorks connection.
Placeholders are left for the user to fill in.

Usage::

    from solidworks_mcp.agents.soc_pickup import pickup_changes

    delta_lines = await pickup_changes(
        adapter,
        session_id="my-session",
        checkpoint_label="post-pickup-1",   # label for the new checkpoint
        output_path="my_part.py",           # append to existing script
    )
    print("\\n".join(delta_lines))
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Feature diff
# ---------------------------------------------------------------------------


def _feature_names(feature_tree: list[dict[str, Any]]) -> list[str]:
    return [f.get("name", "") for f in feature_tree if f.get("name")]


def _feature_map(feature_tree: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {f.get("name", ""): f for f in feature_tree if f.get("name")}


def diff_feature_trees(
    old_tree: list[dict[str, Any]],
    new_tree: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return features present in new_tree but not in old_tree (by name).

    Args:
        old_tree: Feature list from the last ModelStateSnapshot.
        new_tree: Current feature list from list_features().

    Returns:
        List of new feature dicts, in the order they appear in new_tree.
    """
    old_names = set(_feature_names(old_tree))
    return [f for f in new_tree if f.get("name") not in old_names]


# ---------------------------------------------------------------------------
# Code emission for detected features
# ---------------------------------------------------------------------------


def _feature_type(feature: dict[str, Any]) -> str:
    return (feature.get("type") or feature.get("feature_type") or "").lower()


_EXTRUDE_KEYWORDS = ("boss-extrude", "extrusion", "boss_extrude", "boss extrude")
_CUT_KEYWORDS = ("cut-extrude", "cut_extrude", "cut extrude", "cutextrude")
_FILLET_KEYWORDS = ("fillet", "round")
_CHAMFER_KEYWORDS = ("chamfer",)
_SKETCH_KEYWORDS = ("sketch",)
_PLANE_KEYWORDS = ("plane", "refplane", "reference plane")
_MIRROR_KEYWORDS = ("mirror", "mirrorsolid")
_PATTERN_KEYWORDS = ("linearpattern", "circularpattern", "pattern")


def _classify(ftype: str) -> str:
    for kw in _EXTRUDE_KEYWORDS:
        if kw in ftype:
            return "extrude"
    for kw in _CUT_KEYWORDS:
        if kw in ftype:
            return "cut"
    for kw in _FILLET_KEYWORDS:
        if kw in ftype:
            return "fillet"
    for kw in _CHAMFER_KEYWORDS:
        if kw in ftype:
            return "chamfer"
    for kw in _SKETCH_KEYWORDS:
        if kw in ftype:
            return "sketch"
    for kw in _PLANE_KEYWORDS:
        if kw in ftype:
            return "plane"
    for kw in _MIRROR_KEYWORDS:
        if kw in ftype:
            return "mirror"
    for kw in _PATTERN_KEYWORDS:
        if kw in ftype:
            return "pattern"
    return "unknown"


def emit_feature_lines(feature: dict[str, Any]) -> list[str]:
    """Emit Python code lines for a single newly-detected feature.

    Values that require querying the COM API are left as '?' placeholders.
    """
    name = feature.get("name", "unknown")
    ftype = _feature_type(feature)
    kind = _classify(ftype)

    lines: list[str] = []
    lines.append(f"        # [pickup] {name!r} ({ftype or 'unknown type'})")

    if kind == "extrude":
        lines += [
            "        require(",
            "            await adapter.create_extrusion(",
            "                ExtrusionParameters(",
            "                    depth=?,  # TODO: fill in depth (mm)",
            "                )",
            "            ),",
            f'            "create_extrusion {name}",',
            "        )",
        ]
    elif kind == "cut":
        lines += [
            "        require(",
            "            await adapter.create_cut_extrude(",
            "                ExtrusionParameters(",
            "                    depth=?,  # TODO: fill in depth (mm)",
            "                )",
            "            ),",
            f'            "create_cut_extrude {name}",',
            "        )",
        ]
    elif kind == "fillet":
        lines += [
            "        require(",
            f"            await adapter.add_fillet(radius=?, edge_names=[]),  # TODO: radius + edges for {name}",
            f'            "add_fillet {name}",',
            "        )",
        ]
    elif kind == "sketch":
        lines += [
            "        require(await adapter.create_sketch('?'), 'create_sketch')  # TODO: pick plane",
            "        # TODO: add sketch entities here",
            "        require(await adapter.exit_sketch(), 'exit_sketch')",
        ]
    elif kind in ("chamfer", "plane", "mirror", "pattern"):
        lines.append(
            f"        # TODO: reconstruct {name!r} ({kind}) — no automatic emitter yet"
        )
    else:
        lines.append(
            f"        # TODO: reconstruct {name!r} — unknown feature type {ftype!r}"
        )

    lines.append("")
    return lines


def generate_pickup_lines(new_features: list[dict[str, Any]]) -> list[str]:
    """Generate script lines for a list of new features.

    Args:
        new_features: Features returned by diff_feature_trees().

    Returns:
        List of Python source lines (without trailing newlines).
    """
    if not new_features:
        return ["        # [pickup] no new features detected"]

    header = [
        "        # ── pickup ──────────────────────────────────────────────",
        f"        # {len(new_features)} new feature(s) detected since last checkpoint",
        "        # Fill in '?' placeholders before running.",
        "        # ──────────────────────────────────────────────────────────",
        "",
    ]
    body: list[str] = []
    for feat in new_features:
        body.extend(emit_feature_lines(feat))

    return header + body


# ---------------------------------------------------------------------------
# Main async entry point
# ---------------------------------------------------------------------------


async def pickup_changes(
    adapter: Any,
    session_id: str,
    *,
    checkpoint_label: str = "pickup",
    output_path: str | Path | None = None,
    db_path: Path | None = None,
) -> list[str]:
    """Diff current feature tree against last snapshot and emit delta lines.

    Args:
        adapter: Connected SolidWorks adapter.
        session_id: The SoC session ID.
        checkpoint_label: Label for the new checkpoint created after pickup.
        output_path: If set, append the pickup lines to this .py script file.
        db_path: Override default SQLite DB path.

    Returns:
        List of generated Python source lines for the new features.
    """
    from .history_db import (
        insert_model_state_snapshot,
        list_model_state_snapshots,
    )

    # 1. Get current feature tree
    feat_result = await adapter.list_features()
    if not feat_result.is_success:
        raise RuntimeError(f"list_features failed: {feat_result.error}")
    current_tree: list[dict[str, Any]] = feat_result.data or []

    # 2. Get last snapshot for this session
    snapshots = list_model_state_snapshots(session_id, db_path=db_path)
    old_tree: list[dict[str, Any]] = []
    if snapshots:
        raw = snapshots[0].get("feature_tree_json")
        if raw:
            try:
                old_tree = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                old_tree = []

    # 3. Diff
    new_features = diff_feature_trees(old_tree, current_tree)

    # 4. Generate pickup lines
    pickup_lines = generate_pickup_lines(new_features)

    # 5. Append to script file if requested
    if output_path is not None:
        path = Path(output_path)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        # Insert before the finally block
        insertion = "\n".join(pickup_lines) + "\n"
        if "    finally:" in existing:
            existing = existing.replace("    finally:", insertion + "    finally:", 1)
        else:
            existing = existing.rstrip("\n") + "\n" + insertion
        path.write_text(existing, encoding="utf-8")

    # 6. Save updated snapshot and create new checkpoint
    model_info_result = await adapter.get_model_info()
    model_path = ""
    if model_info_result.is_success and isinstance(model_info_result.data, dict):
        model_path = str(model_info_result.data.get("file_path") or "")

    insert_model_state_snapshot(
        session_id=session_id,
        model_path=model_path or None,
        feature_tree_json=json.dumps(current_tree, default=str),
        db_path=db_path,
    )

    if hasattr(adapter, "soc_create_checkpoint"):
        await adapter.soc_create_checkpoint(
            checkpoint_label,
            model_path or "",
            feature_tree=current_tree,
        )

    return pickup_lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m solidworks_mcp.agents.soc_pickup <session_id> "
            "[checkpoint_label]"
        )
        sys.exit(1)
    print(
        "soc_pickup CLI requires a running SolidWorks adapter. "
        "Call pickup_changes() from a script instead."
    )
    sys.exit(1)


if __name__ == "__main__":
    _cli()
