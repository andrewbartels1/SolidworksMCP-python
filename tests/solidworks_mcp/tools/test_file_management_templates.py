"""The save_as_template tool on the mock adapter (queue item 21).

Spec: tools/document-templates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.file_management import (
    SaveAsTemplateInput,
    register_file_management_tools,
)


async def _tool(adapter: Any) -> Any:
    mcp = FastMCP("templates")
    await register_file_management_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}["save_as_template"]


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part("Plate", units="in")
    return adapter


@pytest.mark.asyncio
async def test_by_path_then_a_new_part_from_it(
    part: MockSolidWorksAdapter, tmp_path: Path
) -> None:
    save = await _tool(part)
    target = str(tmp_path / "Plate.prtdot")

    result = await save(SaveAsTemplateInput(file_path=target))
    made = await part.create_part("Next", template=target)

    assert result["message"] == (
        f"Saved the part template {target}; start a new one from it with "
        f"template: {target!r}"
    )
    assert result["data"]["in_template_folder"] is False
    assert made.data.properties["units"] == "in"


@pytest.mark.asyncio
async def test_by_name_into_the_template_folder(
    part: MockSolidWorksAdapter, tmp_path: Path
) -> None:
    part._mock_template_folders = (str(tmp_path), "C:/More")
    save = await _tool(part)

    plain = await save({"name": " Bracket MMGS "})
    with_extension = await save({"name": "Spare.PRTDOT"})

    assert plain["file_path"] == str(tmp_path / "Bracket MMGS.prtdot")
    assert plain["data"]["in_template_folder"] is True
    assert with_extension["file_path"] == str(tmp_path / "Spare.prtdot")


@pytest.mark.asyncio
async def test_refusals_change_nothing(
    part: MockSolidWorksAdapter, tmp_path: Path
) -> None:
    save = await _tool(part)
    existing = tmp_path / "Kept.prtdot"
    existing.write_bytes(b"old")

    wrong = await save({"file_path": str(tmp_path / "Plate.asmdot")})
    there = await save({"file_path": str(existing)})
    replaced = await save({"file_path": str(existing), "overwrite": True})
    no_folder = await save({"name": "Bracket"})

    assert wrong["error_type"] == "invalid_input"
    assert "must end in .prtdot" in wrong["message"]
    assert there["error_type"] == "invalid_input"
    assert existing.read_bytes() == b"old"
    assert replaced["status"] == "success"
    assert no_folder["error_type"] == "invalid_input"
    assert "lists no document template folder" in no_folder["message"]
    assert part._mock_templates().keys() == {str(existing)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("original", "said"),
    [
        (None, "it now exists only as this template"),
        ("C:/work/plate.SLDPRT", "C:/work/plate.SLDPRT is unchanged on disk"),
    ],
)
async def test_the_template_open_in_place_is_warned_about(
    tmp_path: Path, original: str | None, said: str
) -> None:
    class _Real(MockSolidWorksAdapter):
        async def save_as_template(self, file_path: str) -> AdapterResult[Any]:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data={
                    "document_type": "part",
                    "document_path": original,
                    "document_became_template": True,
                },
            )

    adapter = _Real({})
    await adapter.connect()
    await adapter.create_part("Plate")
    target = str(tmp_path / "Plate.prtdot")

    result = await (await _tool(adapter))({"file_path": target})

    assert result["status"] == "success"
    assert result["warning"].startswith(f"SolidWorks now has the template {target}")
    assert said in result["warning"]


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({}, "either file_path or name"),
        ({"file_path": "C:/a.prtdot", "name": "a"}, "either file_path or name"),
        ({"name": "sub/part"}, "file name with no folder"),
        ({"name": "  "}, "file name with no folder"),
    ],
)
def test_the_input_rules(data: dict[str, Any], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        SaveAsTemplateInput(**data)


@pytest.mark.asyncio
async def test_no_document_open() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await (await _tool(adapter))({"name": "x"})

    assert result["error_type"] == "no_active_document"


@pytest.mark.asyncio
async def test_a_failed_folder_read_and_an_adapter_without_templates() -> None:
    class _Broken(MockSolidWorksAdapter):
        async def get_template_folders(self) -> AdapterResult[dict[str, Any]]:
            return AdapterResult(status=AdapterResultStatus.ERROR, error="pref gone")

    broken = _Broken({})
    await broken.connect()

    failed = await (await _tool(broken))({"name": "x"})
    missing = await (await _tool(object()))({"name": "x"})

    assert "pref gone" in failed["message"]
    assert missing["error_type"] == "not_supported"
