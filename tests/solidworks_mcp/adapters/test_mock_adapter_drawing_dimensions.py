"""The mock adapter's drawing-dimension methods mirror the live contract."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def drawing(tmp_path) -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    model = tmp_path / "bracket.SLDPRT"
    model.write_bytes(b"")
    assert (await adapter.create_drawing()).is_success
    assert (
        await adapter.create_technical_drawing({"model_path": str(model)})
    ).is_success
    return adapter


@pytest.mark.asyncio
async def test_insert_reports_the_live_fields_and_never_duplicates(drawing) -> None:
    first = await drawing.insert_model_dimensions()
    again = await drawing.insert_model_dimensions(drawing._drawing_views[0])

    assert set(first.data) == {
        "views",
        "dimensions_added",
        "unique_dimensions",
        "skipped_pictorial_views",
        "method",
        "autodimension_status",
    }
    assert first.data["dimensions_added"] == 3 * len(drawing._drawing_views)
    assert again.data["dimensions_added"] == 0


@pytest.mark.asyncio
async def test_unknown_views_are_named(drawing) -> None:
    views = ", ".join(drawing._drawing_views)
    insert = await drawing.insert_model_dimensions("Side")
    arrange = await drawing.arrange_dimensions("Side")

    assert insert.error == f"No view named 'Side'. Views: {views}"
    assert arrange.error == f"No view named 'Side'. Views: {views}"


@pytest.mark.asyncio
async def test_arrange_counts_one_views_dimensions(drawing) -> None:
    await drawing.insert_model_dimensions()
    one = drawing._drawing_views[0]

    result = await drawing.arrange_dimensions(one)

    assert result.data["dimensions"] == 3
    assert result.data["overlaps_after"] == 0


@pytest.mark.asyncio
async def test_a_drawing_without_views_says_how_to_add_them() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()

    result = await adapter.insert_model_dimensions()

    assert "create_technical_drawing" in (result.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["insert_model_dimensions", "arrange_dimensions"])
async def test_both_need_a_drawing(method) -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await getattr(adapter, method)()

    assert "needs an active drawing document" in (result.error or "")
