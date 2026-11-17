"""The mock adapter's templates carry units, material and properties.

Spec: tools/document-templates.
"""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def adapter() -> MockSolidWorksAdapter:
    mock = MockSolidWorksAdapter({})
    await mock.connect()
    return mock


@pytest.mark.asyncio
async def test_a_new_part_starts_from_the_template(
    adapter: MockSolidWorksAdapter,
) -> None:
    adapter._mock_template_folders = ("C:/Templates",)
    await adapter.create_part("Plate", units="in")
    await adapter.set_material("6061-T6 (SS)")
    await adapter.set_custom_property("Company", "Acme")

    saved = await adapter.save_as_template("C:/Templates/Plate.prtdot")
    # As in SolidWorks, the template is now the open document, with its state.
    assert adapter._current_model.path == "C:/Templates/Plate.prtdot"
    assert (await adapter.get_material()).data["material"] == "6061-T6 (SS)"
    made = await adapter.create_part("Next", template="C:/Templates/Plate.prtdot")
    material = await adapter.get_material()
    properties = await adapter.get_custom_properties()
    blank = await adapter.create_part("Blank", template="C:/Templates/Other.prtdot")

    assert saved.data == {
        "file_path": "C:/Templates/Plate.prtdot",
        "document_type": "part",
        "in_template_folder": True,
        "template_folders": ["C:/Templates"],
        "document_path": None,
        "document_became_template": True,
    }
    assert made.data.properties["units"] == "in"
    assert adapter._current_model.name == "Blank"
    assert blank.data.properties["units"] == "mm"
    assert material.data["material"] == "6061-T6 (SS)"
    assert properties.data["properties"]["Company"]["value"] == "Acme"


@pytest.mark.asyncio
async def test_a_bare_part_template_carries_only_its_units(
    adapter: MockSolidWorksAdapter,
) -> None:
    await adapter.create_part("Plate")
    adapter._current_model.properties["units"] = None
    await adapter.save_as_template("C:/t/Bare.prtdot")

    made = await adapter.create_part("Next", template="C:/t/Bare.prtdot")

    assert made.data.properties["units"] == "mm"
    assert (await adapter.get_material()).data["material"] is None


@pytest.mark.asyncio
async def test_folders_and_refusals(adapter: MockSolidWorksAdapter) -> None:
    empty = await adapter.get_template_folders()
    nothing = await adapter.save_as_template("C:/t/x.prtdot")
    await adapter.create_assembly("Frame")
    assembly = await adapter.get_template_folders()
    wrong = await adapter.save_as_template("C:/t/x.prtdot")

    assert empty.data == {"folders": [], "document_type": None, "extension": None}
    assert nothing.error == "No active model"
    assert assembly.data["extension"] == ".asmdot"
    assert wrong.error == "Assembly templates are .asmdot; 'C:/t/x.prtdot' isn't one."
