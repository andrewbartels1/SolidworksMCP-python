"""The packaged skill folder and the server instructions (``solidworks_mcp.skills``)."""

from __future__ import annotations

from solidworks_mcp.skills import SERVER_INSTRUCTIONS, SKILL_DIR, SKILL_NAME


def test_the_skill_folder_ships_with_the_package() -> None:
    assert SKILL_DIR.name == SKILL_NAME == "solidworks-mcp"
    assert (SKILL_DIR / "SKILL.md").is_file()
    references = sorted(p.name for p in (SKILL_DIR / "references").glob("*.md"))
    assert references == [
        "errors-and-limits.md",
        "selection-and-units.md",
        "vba-fallback.md",
        "workflows.md",
    ]


def test_the_instructions_point_to_the_skill_resource() -> None:
    assert f"skill://{SKILL_NAME}/SKILL.md" in SERVER_INSTRUCTIONS


def test_instructions_follow_the_toolsets_and_mode() -> None:
    from solidworks_mcp.skills import server_instructions

    default = server_instructions()
    reduced = server_instructions(("core", "drawing"), "list")
    search = server_instructions(("all",), "search")

    assert default == SERVER_INSTRUCTIONS
    assert "Only these toolsets are on: core, drawing." in reduced
    assert "search_tools" not in reduced
    assert "Search mode is on" in search
    assert "`call_tool`, giving its `name`" in search
    assert "Only these toolsets" not in search
