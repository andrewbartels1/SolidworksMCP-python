"""Tests for the BOM-table and sheet-scale methods of SolidWorksDocumentationMixin.

A fake drawing stands in for SolidWorks: its views report the document they
show, ``InsertBomTable4`` records its arguments and returns a table, and the
sheet keeps the scale ``SetScale`` gave it for ``GetProperties2`` to read back.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import documentation as doc
from solidworks_mcp.adapters.solidworks.documentation import (
    SolidWorksDocumentationMixin,
)


@pytest.fixture(autouse=True)
def _plain_com(monkeypatch) -> None:
    """Fake objects need no flagging; views come from the fake drawing."""
    monkeypatch.setattr(
        doc, "_sw_type_info", SimpleNamespace(flagged=lambda obj, *_: obj)
    )
    monkeypatch.setattr(doc, "_view_names", lambda _a, drawing: list(drawing.views))
    monkeypatch.setattr(
        doc, "_resolve_drawing_view", lambda _a, drawing, name: drawing.views.get(name)
    )


class _Harness(SolidWorksDocumentationMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any = None, folders: str = "") -> None:
        self.currentModel = model
        self.swApp = SimpleNamespace(GetUserPreferenceStringValue=lambda _p: folders)

    def _handle_com_operation(self, name, operation, *args):
        try:
            data = operation(*args)
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _require_drawing(self):
        if getattr(self.currentModel, "GetType", lambda: 0)() != 3:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="This operation requires a drawing document",
            )
        return None


class _View:
    def __init__(self, shows: Any = 2, table: Any = "table") -> None:
        self.ReferencedDocument = SimpleNamespace(GetType=lambda: shows)
        self.ReferencedConfiguration = "Default"
        self.table = SimpleNamespace(RowCount=3) if table == "table" else table
        self.bom_args: tuple[Any, ...] = ()

    def InsertBomTable4(self, *args):  # noqa: N802
        self.bom_args = args
        return self.table


class _Sheet:
    def __init__(self, accepts: bool = True, props: Any = "scale") -> None:
        self.accepts = accepts
        self.props = props
        self.scale = (1.0, 1.0)

    def SetScale(self, num, den, *_args):  # noqa: N802
        if self.accepts:
            self.scale = (num, den)
        return self.accepts

    def GetProperties2(self):  # noqa: N802
        if self.props == "scale":
            return (8, 12, *self.scale, False, 0.42, 0.297)
        return self.props

    def GetName(self):  # noqa: N802
        return "Sheet1"


class _Drawing:
    def __init__(self, sheet: _Sheet | None = None, **views: _View) -> None:
        self.views = views
        self.sheet = sheet or _Sheet()

    def GetType(self):  # noqa: N802
        return 3

    def GetCurrentSheet(self):  # noqa: N802
        return self.sheet

    def EditRebuild3(self):  # noqa: N802
        return True


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "templates" / "bom-standard.sldbomtbt"
    path.parent.mkdir()
    path.write_bytes(b"")
    return path


# ---- insert_bom_table -----------------------------------------------------------


@pytest.mark.asyncio
async def test_bom_uses_the_library_template_and_the_sheet_anchor(template) -> None:
    view = _View()
    adapter = _Harness(_Drawing(Front=view), folders=f"C:/none;{template.parent}")

    result = await adapter.insert_bom_table("Front")

    assert result.data == {
        "view": "Front",
        "bom_type": "top_level_only",
        "template": str(template),
        "configuration": "Default",
        "row_count": 3,
    }
    use_anchor, x, y, _corner, bom_type, config, used, *_rest = view.bom_args
    assert (use_anchor, x, y, bom_type, config, used) == (
        True,
        0.0,
        0.0,
        2,
        "Default",
        str(template),
    )


@pytest.mark.asyncio
async def test_an_indented_bom_at_a_position_is_numbered_by_level(template) -> None:
    view = _View()
    adapter = _Harness(_Drawing(Front=view))

    result = await adapter.insert_bom_table("Front", str(template), "indented", 30, 40)

    assert result.is_success
    assert view.bom_args[:3] == (False, 0.03, 0.04)
    assert view.bom_args[4] == 3  # swBomType_Indented
    assert view.bom_args[8] == 1  # swNumberingType_Detailed


@pytest.mark.asyncio
async def test_a_view_whose_document_is_unreadable_is_still_tried(template) -> None:
    adapter = _Harness(_Drawing(Front=_View(shows=None)))

    result = await adapter.insert_bom_table("Front", str(template))

    assert result.is_success


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("view", "template_path", "folders", "error"),
    [
        (
            _View(),
            None,
            "",
            "Error in insert_bom_table: No view named 'Side'. Views: Front",
        ),
        (
            _View(shows=1),
            None,
            "",
            "Error in insert_bom_table: insert_bom_table needs an assembly document "
            "in the view: 'Side' shows a part. Use a view of an assembly.",
        ),
        (
            _View(),
            "C:/nope/mine.sldbomtbt",
            "",
            "Error in insert_bom_table: BOM template not found: C:/nope/mine.sldbomtbt",
        ),
        (
            _View(),
            None,
            "",
            "Error in insert_bom_table: No BOM template found: bom-standard.sldbomtbt "
            "is not in the BOM templates folder (not set); pass template_path",
        ),
        (
            _View(),
            None,
            "C:/a; C:/b",
            "Error in insert_bom_table: No BOM template found: bom-standard.sldbomtbt "
            "is not in the BOM templates folder (C:/a; C:/b); pass template_path",
        ),
    ],
)
async def test_bom_failures_say_what_is_wrong(
    view, template_path, folders, error
) -> None:
    views = {"Front": view} if error.endswith("Views: Front") else {"Side": view}
    adapter = _Harness(_Drawing(**views), folders=folders)

    result = await adapter.insert_bom_table("Side", template_path)

    assert result.error == error


@pytest.mark.asyncio
async def test_a_table_solidworks_refuses_is_an_error(template) -> None:
    adapter = _Harness(_Drawing(Front=_View(table=None)))

    result = await adapter.insert_bom_table("Front", str(template))

    assert result.error == (
        "Error in insert_bom_table: InsertBomTable4 made no table for view "
        f"'Front' with template {template}"
    )


@pytest.mark.asyncio
async def test_bom_refuses_an_unknown_type_and_needs_a_drawing() -> None:
    wrong_type = await _Harness(_Drawing()).insert_bom_table("Front", None, "flat")
    no_drawing = await _Harness(SimpleNamespace(GetType=lambda: 1)).insert_bom_table(
        "Front"
    )

    assert wrong_type.error == (
        "bom_type must be one of top_level_only, parts_only, indented"
    )
    assert no_drawing.error == "This operation requires a drawing document"


# ---- set_sheet_scale ------------------------------------------------------------


@pytest.mark.asyncio
async def test_sheet_scale_is_read_back() -> None:
    result = await _Harness(_Drawing()).set_sheet_scale(1, 2)

    assert result.data == {"sheet": "Sheet1", "scale": "1:2"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sheet", "error"),
    [
        (_Sheet(accepts=False), "ISheet::SetScale refused 1:2"),
        (_Sheet(props=None), "The sheet's scale could not be read back"),
        (_Sheet(props=(8, 12, 1.0, 1.0)), "The sheet reads back 1:1, not 1:2"),
    ],
)
async def test_a_scale_that_did_not_take_is_an_error(sheet, error) -> None:
    result = await _Harness(_Drawing(sheet)).set_sheet_scale(1, 2)

    assert result.error == f"Error in set_sheet_scale: {error}"


@pytest.mark.asyncio
async def test_sheet_scale_refuses_zero_and_needs_a_drawing() -> None:
    zero = await _Harness(_Drawing()).set_sheet_scale(0, 2)
    no_drawing = await _Harness(SimpleNamespace(GetType=lambda: 1)).set_sheet_scale(
        1, 2
    )

    assert zero.error == "Scale values must be positive, not 0:2"
    assert no_drawing.error == "This operation requires a drawing document"
