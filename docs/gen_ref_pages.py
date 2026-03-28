"""Generate the code reference pages and navigation.

This script scans the src/solidworks_mcp source tree and generates
corresponding markdown files with mkdocstrings directives. These are
then displayed in the "API Reference" section of the documentation.
"""

from pathlib import Path
import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

root = Path(__file__).parent.parent
src = root / "src"
package_src = src / "solidworks_mcp"

for path in sorted(package_src.rglob("*.py")):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("api") / doc_path

    parts = tuple(module_path.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")
    elif parts[-1] == "__main__":
        continue

    if not parts:
        continue

    nav[parts] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        ident = ".".join(parts)
        fd.write(f"# {ident}\n\n")
        fd.write(f"::: {ident}\n")
        fd.write("    options:\n")
        fd.write("      show_root_heading: true\n")
        fd.write("      show_source: true\n")
        fd.write("      members: true\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, Path("../") / path.relative_to(root))

with mkdocs_gen_files.open("api/SUMMARY.md", "w") as nav_file:
    nav_file.write("# API Reference\n\n")
    nav_file.write(
        "This section contains auto-generated API documentation extracted directly from Python docstrings.\n\n"
    )
    nav_file.writelines(nav.build_literate_nav())

print("✓ Generated API documentation pages from src/solidworks_mcp")
