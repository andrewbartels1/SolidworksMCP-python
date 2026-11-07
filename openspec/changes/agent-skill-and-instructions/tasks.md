## 1. The skill package

- [x] 1.1 `src/solidworks_mcp/skills/__init__.py`: `SKILL_DIR` (the packaged
      skill folder, beside the module) and `SERVER_INSTRUCTIONS`;
      tests in `tests/solidworks_mcp/skills/test_init.py`
- [x] 1.2 Write `SKILL.md` (frontmatter `name: solidworks-mcp` and a
      description; build order, units, read-back, map to the references),
      under 500 lines
- [x] 1.3 Write `references/workflows.md`, `references/selection-and-units.md`,
      `references/errors-and-limits.md` and `references/vba-fallback.md`,
      each fact checked against the tool code and descriptions
- [x] 1.4 `tests/integration/test_skill_content.py`: every backticked tool
      name in the skill and the instructions is registered; no recommended
      step names a "Not available yet" tool; `SKILL.md` frontmatter and
      length; instructions at most 1500 characters

## 2. Served by the server

- [x] 2.1 `server.py`: pass `instructions=SERVER_INSTRUCTIONS` to `FastMCP`
      and add `SkillProvider(SKILL_DIR)` when the `FastMCP` instance is built
- [x] 2.2 Tests: the initialize result carries the instructions;
      `skill://solidworks-mcp/SKILL.md` and the manifest are listed and read
      back the packaged text, in mock mode

## 3. `solidworks-mcp skill install`

- [x] 3.1 `src/solidworks_mcp/skills/install.py`: a Typer app with
      `install` (`--project`, `--dir`, `--dry-run`); copies only the
      packaged files into `<folder>/solidworks-mcp/`, replaces them on
      upgrade, leaves other files, reads nothing else, reports the path
- [x] 3.2 `cli_main` routes `skill ...` to it, as it does `setup`; `setup`
      ends with a one-line hint about `skill install`
- [x] 3.3 Tests in `tests/solidworks_mcp/skills/test_install.py`: default,
      `--project` and `--dir` targets (home and cwd redirected to a temp
      folder), upgrade keeps a user file, `--dry-run` writes nothing, an
      unwritable target errors naming the path; and the `cli_main` routing

## 4. Docs

- [x] 4.1 README: a short "Agent skill" section with the install command and
      how other agents use `--dir`
- [x] 4.2 `docs/agents/`: a page on the skill and the instructions, linked
      from mkdocs nav; link the skill from `com-api-pitfalls.md` as the
      user-facing counterpart
- [x] 4.3 `openspec/queue.md`: item 10 notes that fixing a fault also edits
      `references/errors-and-limits.md`; CHANGELOG entry

## 5. Ship

- [x] 5.1 Full mock suite, ruff, 100 % coverage, `mkdocs build --strict`
- [x] 5.2 Ask the user, then run the measurement on real SolidWorks: the
      U-joint prompt (SolidWorks' U-Joint sample, read part by part and
      written as a plain-English prompt) in a fresh agent session without the
      skill, then with it installed, each from a clean folder with the same
      breaker timeout; record tool calls, errors, part volumes against the
      sample and the mates, in `docs/agents/agent-skill.md` (decided
      2026-11-06: the monitor stand was too easy to show a difference)
- [x] 5.3 `tests/live/test_live_sw_ujoint_demo.py`: open on the original
      sample, then the prompt, then replay the with-skill session's calls
      (`tests/live/data/ujoint/`) as captioned frames, each ending as it did
      in the session; record it with `live_demo.ps1 -Record`
- [x] 5.4 README and Demos page: the U-joint as the top demo, above the
      monitor stand, showing the original beside the agent's result and the
      with/without comparison
