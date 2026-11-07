"""The server sends its instructions and serves the usage skill (specs: agents/*)."""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.skills import SERVER_INSTRUCTIONS, SKILL_DIR

_SKILL = "skill://solidworks-mcp"


@pytest.mark.asyncio
async def test_a_client_gets_the_instructions_at_connection(
    mock_config: SolidWorksMCPConfig,
) -> None:
    server = SolidWorksMCPServer(mock_config)

    async with Client(server.mcp) as client:
        result = client.initialize_result

    assert result is not None
    assert result.instructions == SERVER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_the_skill_is_listed_and_reads_back_the_packaged_text(
    mock_config: SolidWorksMCPConfig,
) -> None:
    server = SolidWorksMCPServer(mock_config)

    async with Client(server.mcp) as client:
        uris = {str(r.uri) for r in await client.list_resources()}
        skill = await client.read_resource(f"{_SKILL}/SKILL.md")
        manifest = await client.read_resource(f"{_SKILL}/_manifest")

    assert {f"{_SKILL}/SKILL.md", f"{_SKILL}/_manifest"} <= uris
    assert skill[0].text == (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    listed = {entry["path"] for entry in json.loads(manifest[0].text)["files"]}
    assert "references/workflows.md" in listed


@pytest.mark.asyncio
async def test_a_reference_file_is_read_through_the_skill_template(
    mock_config: SolidWorksMCPConfig,
) -> None:
    server = SolidWorksMCPServer(mock_config)
    expected = (SKILL_DIR / "references" / "errors-and-limits.md").read_text(
        encoding="utf-8"
    )

    async with Client(server.mcp) as client:
        content = await client.read_resource(
            f"{_SKILL}/references/errors-and-limits.md"
        )

    assert content[0].text == expected
