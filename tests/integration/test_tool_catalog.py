"""The tool catalog pages match the registered tools (spec: docs/tool-catalog).

Each page under ``docs/user-guide/tool-catalog/`` is hand-written. This check
keeps it honest: every tool has one entry on its family's page, the entry's
parameter table lists exactly the tool's inputs, and its sample call is JSON
the tool's input model accepts.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import types
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import BaseModel, ValidationError

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools import register_tools

CATALOG = Path(__file__).resolve().parents[2] / "docs" / "user-guide" / "tool-catalog"

_HEADING = re.compile(r"^### `([a-z0-9_]+)`[^\n]*$", re.M)
_ROW = re.compile(r"^\| `([a-z0-9_]+)` \|", re.M)
_SAMPLE = re.compile(r"\*\*Sample call:\*\*\s*```json\n(.*?)\n```", re.S)


@dataclass(frozen=True)
class Entry:
    """One tool's catalog entry.

    Attributes:
        page: The page's file stem.
        parameters: Field names in its parameter table; None when it has no
            ``**Parameters:**`` table.
        sample: The sample call's JSON text, if any.
    """

    page: str
    parameters: frozenset[str] | None
    sample: str | None


def parse_page(page: str, text: str) -> dict[str, Entry]:
    """The entries on one catalog page, by tool name.

    Args:
        page: The page's file stem.
        text: Its markdown.

    Returns:
        Each ``### `name``` entry's parameter names and sample call.
    """
    entries = {}
    headings = list(_HEADING.finditer(text))
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[heading.end() : end]
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        parameters = None
        if "**Parameters:**" in body:
            table = body.split("**Parameters:**", 1)[1]
            table = re.split(r"\n\s*\n(?!\|)", table.lstrip("\n"), maxsplit=1)[0]
            parameters = frozenset(_ROW.findall(table))
        sample = _SAMPLE.search(body)
        entries[heading.group(1)] = Entry(
            page, parameters, sample.group(1) if sample else None
        )
    return entries


#: What a tool takes: its input model, ``dict`` for free-form input whose
#: fields can't be checked, or None for no input.
Inputs = type[BaseModel] | type[dict] | None


def input_model(fn: Any) -> Inputs:
    """What a tool takes as ``input_data`` (see :data:`Inputs`)."""
    hint = typing.get_type_hints(inspect.unwrap(fn)).get("input_data")
    if hint is None:
        return None
    options = typing.get_args(hint) if isinstance(hint, types.UnionType) else (hint,)
    models = [o for o in options if isinstance(o, type) and issubclass(o, BaseModel)]
    return models[0] if models else dict


def catalog_faults(
    tools: dict[str, tuple[str, Inputs]],
    pages: dict[str, str],
) -> list[str]:
    """Every way the catalog pages disagree with the registered tools.

    Args:
        tools: Tool name -> (family tag, what it takes).
        pages: Page file stem -> its markdown.

    Returns:
        One line per fault; empty when the pages match.
    """
    entries: dict[str, list[Entry]] = {}
    for page, text in pages.items():
        for name, entry in parse_page(page, text).items():
            entries.setdefault(name, []).append(entry)
    faults = [
        f"{name}: catalog entry for a tool that isn't registered"
        for name in sorted(set(entries) - set(tools))
    ]
    for name, (family, model) in sorted(tools.items()):
        page = family.replace("_", "-")
        found = entries.get(name, [])
        if [e.page for e in found] != [page]:
            where = ", ".join(e.page for e in found) or "nowhere"
            faults.append(f"{name}: needs one entry on {page}.md, found on {where}")
            continue
        (entry,) = found
        fields = set(model.model_fields) if model and model is not dict else set()
        listed = set(entry.parameters or ())
        if model is dict:
            pass  # free-form input: no fields to compare
        elif fields and entry.parameters is None:
            faults.append(f"{name}: no parameter table")
        elif listed != fields:
            if fields - listed:
                faults.append(f"{name}: table misses {sorted(fields - listed)}")
            if listed - fields:
                faults.append(f"{name}: table lists {sorted(listed - fields)}")
        if entry.sample is None:
            faults.append(f"{name}: no sample call")
            continue
        try:
            sample = json.loads(entry.sample)
        except ValueError as exc:
            faults.append(f"{name}: sample isn't JSON ({exc})")
            continue
        if model is not None and model is not dict:
            try:
                model.model_validate(sample)
            except ValidationError as exc:
                first = exc.errors()[0]
                faults.append(f"{name}: sample refused: {first['loc']} {first['msg']}")
    return faults


@pytest.fixture(scope="module")
def registered() -> dict[str, tuple[str, Inputs]]:
    """Every registered tool's family and input model."""

    async def _tools() -> list[Any]:
        mcp = FastMCP("catalog")
        await register_tools(mcp, MockSolidWorksAdapter({}), {})
        return list(await mcp.list_tools())

    found = {}
    for tool in asyncio.run(_tools()):
        family = next(t for t in tool.tags if ":" not in t)
        found[tool.name] = (family, input_model(tool.fn))
    return found


def test_the_catalog_matches_the_registered_tools(registered) -> None:
    pages = {
        p.stem: p.read_text(encoding="utf-8")
        for p in CATALOG.glob("*.md")
        if p.stem != "index"
    }

    assert catalog_faults(registered, pages) == []


class _Box(BaseModel):
    """A stand-in tool input."""

    width: float
    label: str = "x"


_PAGE = """# Shapes

### `make_box`

Make a box.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `width` | `float` | yes | | Width |
| `label` | `str` | | `"x"` | Label |

**Sample call:**

```json
{ "width": 2 }
```

---

### `list_boxes`

**Parameters:** none

**Sample call:**

```json
{}
```

## Notes
"""


def test_a_matching_page_has_no_faults() -> None:
    tools = {"make_box": ("shapes", _Box), "list_boxes": ("shapes", None)}

    assert catalog_faults(tools, {"shapes": _PAGE}) == []


@pytest.mark.parametrize(
    ("page", "fault"),
    [
        (
            _PAGE.replace("| `label` |", "| `colour` |"),
            "make_box: table misses ['label']",
        ),
        (
            _PAGE.replace("| `label` |", "| `colour` |"),
            "make_box: table lists ['colour']",
        ),
        (
            _PAGE.replace('{ "width": 2 }', '{ "width": null }'),
            "make_box: sample refused",
        ),
        (_PAGE.replace('{ "width": 2 }', "{ width }"), "make_box: sample isn't JSON"),
        (
            _PAGE.replace("**Sample call:**\n\n```json\n{}\n```", ""),
            "list_boxes: no sample call",
        ),
        (
            _PAGE.replace("**Parameters:**\n\n| Parameter", "| Parameter"),
            "make_box: no parameter table",
        ),
    ],
    ids=[
        "missing field",
        "extra field",
        "null sample",
        "bad json",
        "no sample",
        "no table",
    ],
)
def test_each_fault_is_named(page: str, fault: str) -> None:
    tools = {"make_box": ("shapes", _Box), "list_boxes": ("shapes", None)}

    assert any(f.startswith(fault) for f in catalog_faults(tools, {"shapes": page}))


def test_a_missing_and_an_unknown_entry_are_named() -> None:
    tools = {"make_box": ("solids", _Box), "list_boxes": ("shapes", None)}
    page = _PAGE.replace("### `list_boxes`", "### `old_tool`")

    faults = catalog_faults(tools, {"shapes": page})

    assert "old_tool: catalog entry for a tool that isn't registered" in faults
    assert "list_boxes: needs one entry on shapes.md, found on nowhere" in faults
    assert "make_box: needs one entry on solids.md, found on shapes" in faults
