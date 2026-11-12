"""The experimental tools (``experimental-tools-to-stable``), checked on real SolidWorks.

Every test calls the tools as an agent would, through the MCP tool functions
with plain dicts, and prints its proof as ``[evidence]`` lines. They run in
three batches, one test per process, each with the maintainer's permission:

1. reading: ``get_file_properties``, ``list_configurations``,
   ``get_dimension`` (a length and an angle), ``classify_feature_tree``;
2. files: ``load_part`` and ``load_assembly``, ``pack_and_go_assembly``;
3. tools that never call SolidWorks, on files SolidWorks wrote:
   ``compare_templates``, ``compare_drawing_versions``, ``generate_vba_code``
   (its macro run by ``execute_macro``).

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_experimental_tools.py::test_file_properties_of_a_saved_then_edited_part

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _saved_block, _sketch
from tests.live.test_live_sw_ujoint_tool_gaps import _plate_and_pin

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool family these tests need, registered on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.automation import register_automation_tools
    from solidworks_mcp.tools.drawing import register_drawing_tools
    from solidworks_mcp.tools.drawing_analysis import register_drawing_analysis_tools
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.macro_recording import register_macro_recording_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools
    from solidworks_mcp.tools.template_management import (
        register_template_management_tools,
    )

    mcp = FastMCP("experimental-tools-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_drawing_tools,
        register_drawing_analysis_tools,
        register_engineering_data_tools,
        register_file_management_tools,
        register_macro_recording_tools,
        register_automation_tools,
        register_template_management_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


def _open_doc(adapter: Any, path: str) -> Any:
    """An open document by its path, as ``IModelDoc2`` (test-side COM)."""
    from solidworks_mcp.adapters import sw_type_info

    doc = adapter.swApp.GetOpenDocumentByName(path)
    assert doc is not None, f"{path} is not open"
    return sw_type_info.flagged(doc, "IModelDoc2")


async def _close_everything(tools: dict[str, Any]) -> None:
    """Close the test's documents (all saved) one at a time, without saving."""
    for _ in range(10):  # a few documents at most; never loop forever
        if not (await tools["list_open_documents"]())["count"]:
            return
        assert (await tools["close_model"]({"save": False}))["status"] == "success"
    raise AssertionError("documents still open after 10 closes")


async def _two_part_assembly(
    scratch: Any, tools: dict[str, Any], folder: Path, tag: str
) -> tuple[str, str, str]:
    """A saved assembly of the plate and the pin; (assembly, plate, pin) paths."""
    adapter = scratch.adapter
    plate, pin = await _plate_and_pin(scratch, tools, folder, tag)
    assert (await tools["create_assembly"]({"name": tag}))["status"] == "success"
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(pin, 40.0, 0.0, 0.0)).is_success
    assembly = str(folder / f"{tag}.SLDASM")
    saved = await tools["save_file"]({"file_path": assembly})
    scratch.written_files.append(assembly)
    assert saved["status"] == "success", saved
    return assembly, plate, pin


# ---- batch 1: reading ----------------------------------------------------------


async def test_file_properties_of_a_saved_then_edited_part(scratch, tmp_path) -> None:
    tools = await _tools(scratch.adapter)
    part = tmp_path / "props.SLDPRT"
    await _saved_block(scratch, tools, part)

    saved = (await tools["get_file_properties"]())["properties"]
    await _sketch(tools, "Front", {"center_x": 0, "center_y": 5, "radius": 2})
    edited = (await tools["get_file_properties"]())["properties"]
    evidence(
        "file properties of a saved part, then after adding a sketch",
        {
            "saved": {
                k: saved[k] for k in ("file_name", "file_size_bytes", "is_dirty")
            },
            "path_matches": Path(saved["file_path"]) == part,
            "edited_is_dirty": edited["is_dirty"],
        },
        call="get_file_properties()",
    )
    assert Path(saved["file_path"]) == part
    assert saved["file_size_bytes"] == part.stat().st_size > 0
    assert saved["modified_date"] is not None
    assert saved["is_dirty"] is False
    assert edited["is_dirty"] is True


async def test_two_configurations_are_listed(scratch, tmp_path) -> None:
    tools = await _tools(scratch.adapter)
    await _saved_block(scratch, tools, tmp_path / "configs.SLDPRT")
    # No tool adds a configuration: add one through the API.
    manager = scratch.adapter.currentModel.ConfigurationManager
    added = manager.AddConfiguration2("Long", "", "", 0, "", "", True)
    assert added is not None

    listed = await tools["list_configurations"]()
    evidence(
        "list_configurations after adding a configuration named Long",
        {"configurations": listed["configurations"], "count": listed["count"]},
        call="list_configurations()",
    )
    assert sorted(listed["configurations"]) == ["Default", "Long"]
    assert listed["count"] == 2


async def test_a_length_and_an_angle_dimension(scratch) -> None:
    """A 10 mm extrusion in mm; a 270° revolve in degrees."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await tools["create_part"]({"name": "dims"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -10, "y1": -10, "x2": 10, "y2": 10})
    boss = await tools["create_extrusion"]({"depth": 10.0})
    assert boss["status"] == "success", boss
    length = await tools["get_dimension"]({"name": "D1@Boss-Extrude1"})

    profile = await _sketch(tools, "Front", {"x1": 20, "y1": 0, "x2": 30, "y2": 10})
    axis = (await adapter.create_axis("y")).data["name"]
    revolve = await tools["create_revolve"](
        {"sketch_name": profile, "axis_entity": axis, "angle": 270}
    )
    assert revolve["status"] == "success", revolve
    feature = revolve["revolve"]["name"]
    listed = await tools["list_model_dimensions"]({"feature_name": feature})
    readings = [
        (await tools["get_dimension"]({"name": d["full_name"]}))["dimension"]
        for d in listed["data"]
    ]
    missing = await tools["get_dimension"]({"name": "D9@Sketch1"})
    evidence(
        "get_dimension: the extrusion's depth, then each of the revolve's dimensions",
        {
            "length": length["dimension"],
            "revolve": readings,
            "missing": missing.get("message"),
        },
        call='get_dimension({"name": "D1@Boss-Extrude1"})',
    )
    assert length["dimension"]["value"] == pytest.approx(10.0)
    assert length["dimension"]["units"] == "mm"
    angles = [r for r in readings if r["units"] == "deg"]
    assert [a["value"] for a in angles] == [pytest.approx(270.0)]
    assert missing["error_type"] == "not_found"
    assert "list_model_dimensions" in missing["message"]


async def test_a_part_and_an_assembly_are_classified(scratch, tmp_path) -> None:
    tools = await _tools(scratch.adapter)
    await _two_part_assembly(scratch, tools, tmp_path, "classify")
    assembly = await tools["classify_feature_tree"]({})
    assert (await tools["create_part"]({"name": "plain"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -10, "y1": -10, "x2": 10, "y2": 10})
    assert (await tools["create_extrusion"]({"depth": 10.0}))["status"] == "success"
    part = await tools["classify_feature_tree"]({})
    evidence(
        "classify_feature_tree on an assembly, then on an extruded part",
        {
            "assembly": assembly["classification"]["family"],
            "part": part["classification"]["family"],
            "part_workflow": part["classification"]["recommended_workflow"],
        },
        call="classify_feature_tree({})",
    )
    assert assembly["classification"]["family"] == "assembly"
    assert part["classification"]["family"] == "extrude"


# ---- batch 2: files ------------------------------------------------------------


async def test_a_part_and_an_assembly_reload(scratch, tmp_path) -> None:
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assembly, plate, _pin = await _two_part_assembly(scratch, tools, tmp_path, "reload")
    await _close_everything(tools)

    part = await tools["load_part"]({"file_path": plate})
    asm = await tools["load_assembly"]({"file_path": assembly})
    wrong = await tools["load_assembly"]({"file_path": plate})
    missing = await tools["load_part"]({"file_path": str(tmp_path / "gone.SLDPRT")})
    evidence(
        "load_part and load_assembly after closing, a wrong type, a missing file",
        {
            "part": part.get("model"),
            "assembly": asm.get("model"),
            "wrong_type": wrong.get("message"),
            "missing": [missing.get("error_type"), missing.get("message")],
        },
        call=f'load_part({{"file_path": "{Path(plate).name}"}})',
    )
    assert part["status"] == "success", part
    assert Path(part["model"]["path"]) == Path(plate)
    assert part["model"]["configuration"] == "Default"
    assert asm["status"] == "success", asm
    assert asm["model"]["type"] == "Assembly"
    assert wrong["error_type"] == "invalid_input"
    assert missing["error_type"] == "not_found"


async def test_pack_and_go_keeps_the_folder_and_the_open_documents(
    scratch, tmp_path
) -> None:
    """A folder with a note, a part with unsaved changes, two packs into one folder."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assembly, plate, _pin = await _two_part_assembly(scratch, tools, tmp_path, "pack")
    target = tmp_path / "packed"
    target.mkdir()
    (target / "notes.txt").write_text("keep me", encoding="utf-8")
    _open_doc(adapter, plate).SetSaveFlag()  # unsaved changes in the plate
    open_before = (await tools["list_open_documents"]())["count"]

    refused = await tools["pack_and_go_assembly"](
        {"source_path": assembly, "target_dir": str(target)}
    )
    first = await tools["pack_and_go_assembly"](
        {"source_path": assembly, "target_dir": str(target), "overwrite": True}
    )
    second = await tools["pack_and_go_assembly"](
        {"source_path": assembly, "target_dir": str(target), "overwrite": True}
    )
    open_after = (await tools["list_open_documents"]())["count"]
    plate_dirty = bool(_open_doc(adapter, plate).GetSaveFlag())
    for name in first.get("copied_files") or []:
        scratch.written_files.append(name)
    evidence(
        "pack_and_go_assembly into a folder holding notes.txt, twice",
        {
            "without_overwrite": refused.get("message"),
            "first": first.get("message"),
            "first_source_files": [
                Path(f).name for f in first.get("source_files") or []
            ],
            "first_save_statuses": first.get("save_statuses"),
            "folder_after": sorted(p.name for p in target.iterdir()),
            "copied": [Path(f).name for f in first.get("copied_files") or []],
            "second": second.get("message"),
            "second_saved_all": second.get("all_files_saved"),
            "notes_kept": (target / "notes.txt").read_text(encoding="utf-8"),
            "open_documents": [open_before, open_after],
            "plate_still_unsaved": plate_dirty,
        },
        call='pack_and_go_assembly({"source_path": "pack.SLDASM", "overwrite": true})',
    )
    assert refused["error_type"] == "invalid_input"
    assert first["status"] == "success", first
    assert sorted(Path(f).name.lower() for f in first["copied_files"]) == [
        "pack.sldasm",
        "pack_pin.sldprt",
        "pack_plate.sldprt",
    ]
    assert second["status"] == "success", second
    assert second["all_files_saved"] is True
    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert open_after >= open_before
    assert plate_dirty is True


async def test_the_packed_assembly_opens_from_its_folder(scratch, tmp_path) -> None:
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    source = tmp_path / "src"
    source.mkdir()
    assembly, _plate, _pin = await _two_part_assembly(scratch, tools, source, "moved")
    target = tmp_path / "moved_copy"
    packed = await tools["pack_and_go_assembly"](
        {"source_path": assembly, "target_dir": str(target)}
    )
    assert packed["status"] == "success", packed
    scratch.written_files.extend(packed["copied_files"])
    # Close the originals, so the copy's same-named files are the ones loaded.
    await _close_everything(tools)

    opened = await tools["load_assembly"]({"file_path": str(target / "moved.SLDASM")})
    asm = sw_type_info.flagged(adapter.currentModel, "IAssemblyDoc")
    paths = [
        str(sw_type_info.flagged(c, "IComponent2").GetPathName())
        for c in asm.GetComponents(True)
    ]
    evidence(
        "the packed assembly opened from its new folder: where its parts load from",
        {"opened": opened.get("model"), "components": paths},
        call='load_assembly({"file_path": "moved_copy/moved.SLDASM"})',
    )
    assert opened["status"] == "success", opened
    assert len(paths) == 2
    assert all(Path(p).parent == target for p in paths)


# ---- batch 3: tools that never call SolidWorks, on SolidWorks' files ------------


async def test_templates_are_compared(scratch) -> None:
    adapter = scratch.adapter
    tools = await _tools(adapter)
    part = adapter._resolve_template_path([8, 0, 1, 2, 3], ".prtdot")
    assembly = adapter._resolve_template_path([9, 2, 3, 1, 0], ".asmdot")
    assert part and assembly, (part, assembly)

    same = await tools["compare_templates"](
        {"template1_path": part, "template2_path": part}
    )
    other = await tools["compare_templates"](
        {"template1_path": part, "template2_path": assembly}
    )
    old_switch = await tools["compare_templates"](
        {"template1_path": part, "template2_path": assembly, "include_properties": True}
    )
    evidence(
        "the installed part template against itself, then against the assembly one",
        {
            "same": [
                same["comparison"]["identical"],
                same["comparison"]["size_delta_bytes"],
            ],
            "other": [
                other["comparison"]["identical"],
                other["comparison"]["size_delta_bytes"],
            ],
            "include_properties": old_switch.get("message"),
        },
        call=f'compare_templates({{"template1_path": "{Path(part).name}", ...}})',
    )
    assert same["comparison"]["identical"] is True
    assert other["comparison"]["identical"] is False
    assert other["comparison"]["size_delta_bytes"] == (
        Path(assembly).stat().st_size - Path(part).stat().st_size
    )
    assert old_switch["error_type"] == "invalid_input"


async def test_drawing_versions_are_compared(scratch, tmp_path) -> None:
    """Saved, re-saved unchanged, and saved again after adding a view."""
    tools = await _tools(scratch.adapter)
    part = tmp_path / "drawn.SLDPRT"
    await _saved_block(scratch, tools, part)
    assert (await tools["create_drawing"]({"name": "versions"}))["status"] == "success"
    views = await tools["create_technical_drawing"]({"model_file": str(part)})
    assert views["status"] == "success", views
    first = tmp_path / "v1.SLDDRW"
    scratch.written_files.append(str(first))
    assert (await tools["save_file"]({"file_path": str(first)}))["status"] == "success"
    kept = tmp_path / "v1_copy.SLDDRW"
    shutil.copyfile(first, kept)
    assert (await tools["save_file"]({}))["status"] == "success"  # unchanged
    resaved = await tools["compare_drawing_versions"](
        {"drawing_version_1": str(kept), "drawing_version_2": str(first)}
    )
    iso = await tools["add_drawing_view"](
        {"model_file": str(part), "view_type": "isometric", "position": [230, 100]}
    )
    assert iso["status"] == "success", iso
    second = tmp_path / "v2.SLDDRW"
    scratch.written_files.append(str(second))
    assert (await tools["save_as"]({"file_path": str(second)}))["status"] == "success"
    changed = await tools["compare_drawing_versions"](
        {"drawing_version_1": str(kept), "drawing_version_2": str(second)}
    )
    evidence(
        "a drawing re-saved unchanged, then saved again with one more view",
        {
            "unchanged_resave_identical": resaved["comparison"]["identical"],
            "with_a_view_identical": changed["comparison"]["identical"],
            "size_delta_bytes": changed["comparison"]["size_delta_bytes"],
        },
        call='compare_drawing_versions({"drawing_version_1": "v1", ...})',
    )
    assert resaved["status"] == "success"  # identical or not: recorded above
    assert changed["comparison"]["identical"] is False


async def test_a_generated_macro_runs(scratch, tmp_path) -> None:
    """Generated for a part: it runs on a part, and stops on a drawing."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    generated = await tools["generate_vba_code"](
        {
            "operation_description": "Add 3 holes (M6), then save",
            "target_document": "Part",
        }
    )
    vba = generated["vba_code"]
    macro = tmp_path / "skeleton.swb"
    macro.write_text(vba["code"], encoding="ascii")
    part = tmp_path / "macro_part.SLDPRT"
    await _saved_block(scratch, tools, part)

    on_part = await tools["execute_macro"](
        {"macro_path": str(macro), "proc_name": vba["sub_name"]}
    )
    assert (await tools["create_drawing"]({"name": "macro_drawing"}))[
        "status"
    ] == "success"
    drawing = sw_type_info.flagged(adapter.currentModel, "IModelDoc2")
    dirty_before = bool(drawing.GetSaveFlag())
    on_drawing = await tools["execute_macro"](
        {"macro_path": str(macro), "proc_name": vba["sub_name"]}
    )
    dirty_after = bool(drawing.GetSaveFlag())
    evidence(
        "a generated macro run on a part, then on a drawing (it stops there)",
        {
            "sub_name": vba["sub_name"],
            "on_part": on_part.get("message"),
            "on_drawing": on_drawing.get("message"),
            "drawing_changed": dirty_before != dirty_after,
        },
        call=f'execute_macro({{"macro_path": "skeleton.swb", "proc_name": "{vba["sub_name"]}"}})',
    )
    assert vba["sub_name"] == "Add_3_holes_M6_then_save"
    assert on_part["status"] == "success", on_part
    assert on_drawing["status"] == "success", on_drawing
    assert dirty_before == dirty_after
