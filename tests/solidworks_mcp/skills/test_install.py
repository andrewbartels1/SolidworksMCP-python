"""``solidworks-mcp skill install`` (spec: agents/usage-skill, the install requirement)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from solidworks_mcp.skills import SKILL_DIR, SKILL_NAME
from solidworks_mcp.skills.install import (
    app,
    install_skill,
    packaged_files,
    skills_folder,
)

runner = CliRunner()


@pytest.fixture
def places(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A fake home and project folder, so nothing real is written."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)
    return {"home": home, "project": project}


def _same_as_packaged(target: Path) -> bool:
    return all(
        (target / rel).read_bytes() == (SKILL_DIR / rel).read_bytes()
        for rel in packaged_files()
    )


def test_the_default_target_is_claude_codes_user_folder(
    places: dict[str, Path],
) -> None:
    result = runner.invoke(app, ["install"])

    target = places["home"] / ".claude" / "skills" / SKILL_NAME
    assert result.exit_code == 0, result.output
    assert _same_as_packaged(target)
    assert str(target) in result.output.replace("\n", "")


def test_project_installs_into_this_projects_folder(places: dict[str, Path]) -> None:
    result = runner.invoke(app, ["install", "--project"])

    assert result.exit_code == 0, result.output
    assert _same_as_packaged(places["project"] / ".claude" / "skills" / SKILL_NAME)
    assert not (places["home"] / ".claude").exists()


def test_dir_installs_into_any_skills_folder(
    places: dict[str, Path], tmp_path: Path
) -> None:
    other = tmp_path / "codex" / "skills"

    result = runner.invoke(app, ["install", "--dir", str(other)])

    assert result.exit_code == 0, result.output
    assert _same_as_packaged(other / SKILL_NAME)


def test_an_upgrade_replaces_the_skill_and_keeps_the_users_files(
    places: dict[str, Path],
) -> None:
    target = places["home"] / ".claude" / "skills" / SKILL_NAME
    (target / "references").mkdir(parents=True)
    (target / "SKILL.md").write_text("old", encoding="utf-8")
    (target / "my-notes.md").write_text("mine", encoding="utf-8")

    result = runner.invoke(app, ["install"])

    assert result.exit_code == 0, result.output
    assert _same_as_packaged(target)
    assert (target / "my-notes.md").read_text(encoding="utf-8") == "mine"


def test_dry_run_writes_nothing(places: dict[str, Path]) -> None:
    result = runner.invoke(app, ["install", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Would write" in result.output
    assert not (places["home"] / ".claude").exists()


def test_an_unwritable_target_is_an_error_naming_the_path(
    places: dict[str, Path], tmp_path: Path
) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the skills folder should be", encoding="utf-8")

    result = runner.invoke(app, ["install", "--dir", str(blocker)])

    assert result.exit_code == 1
    assert "Could not install the skill" in result.output
    assert str(blocker) in result.output.replace("\n", "")


def test_a_target_outside_the_skill_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    escape = tmp_path / "elsewhere"
    escape.mkdir()
    folder = tmp_path / "skills"
    (folder / SKILL_NAME).mkdir(parents=True)
    real_resolve = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "SKILL.md":
            return escape / "SKILL.md"
        return real_resolve(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)

    with pytest.raises(ValueError, match="Refusing to write outside"):
        install_skill(folder)
    assert not (escape / "SKILL.md").exists()


def test_skills_folder_prefers_dir_then_project_then_home(tmp_path: Path) -> None:
    home, cwd, other = tmp_path / "h", tmp_path / "c", tmp_path / "o"

    assert skills_folder(False, None, home, cwd) == home / ".claude" / "skills"
    assert skills_folder(True, None, home, cwd) == cwd / ".claude" / "skills"
    assert skills_folder(True, other, home, cwd) == other


def test_the_packaged_files_are_the_skill_and_its_references() -> None:
    names = {p.as_posix() for p in packaged_files()}

    assert "SKILL.md" in names
    assert "references/workflows.md" in names
