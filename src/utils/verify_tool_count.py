"""Verify tool count and documentation completeness."""

import ast
import os
from pathlib import Path
from typing import Dict, List, Set


def find_tools_in_file(file_path: Path) -> List[str]:
    """Find all @mcp.tool() decorated functions in a file.

    Args:
        file_path: Path to the Python file to analyze

    Returns:
        List of tool function names found in the file
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)
        tools = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if function has @mcp.tool() decorator
                for decorator in node.decorator_list:
                    is_tool_decorator = False

                    # Handles @mcp.tool and @tool
                    if (hasattr(decorator, "attr") and decorator.attr == "tool") or (
                        hasattr(decorator, "id") and decorator.id == "tool"
                    ):
                        is_tool_decorator = True

                    # Handles @mcp.tool(...) and @tool(...)
                    if isinstance(decorator, ast.Call):
                        func = decorator.func
                        if (hasattr(func, "attr") and func.attr == "tool") or (
                            hasattr(func, "id") and func.id == "tool"
                        ):
                            is_tool_decorator = True

                    if is_tool_decorator:
                        tools.append(node.name)
                        break

        return tools
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return []


def check_function_docstring(file_path: Path, function_name: str) -> bool:
    """Check if a function has a proper Google-style docstring.

    Args:
        file_path: Path to the Python file
        function_name: Name of the function to check

    Returns:
        True if function has a proper docstring, False otherwise
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function_name
            ):
                # Check if function has a docstring
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    docstring = node.body[0].value.value

                    # Basic Google style checks
                    has_args = "Args:" in docstring or "Arguments:" in docstring
                    has_returns = "Returns:" in docstring or "Return:" in docstring
                    has_description = len(docstring.strip()) > 10

                    return has_description and (has_args or has_returns)

        return False
    except Exception as e:
        print(f"Error checking docstring for {function_name} in {file_path}: {e}")
        return False


def main():
    """Main verification function.

    Returns:
        tuple: (exit_code, total_tools, documented_tools)
    """
    project_root = Path(__file__).resolve().parents[2]
    src_path = project_root / "src" / "solidworks_mcp" / "tools"

    if not src_path.exists():
        print(f"Tools directory not found: {src_path}")
        return 1, 0, 0

    total_tools = 0
    documented_tools = 0
    files_processed = 0

    print("🔍 Analyzing MCP tool documentation...\n")

    for py_file in src_path.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        tools = find_tools_in_file(py_file)
        if not tools:
            continue

        files_processed += 1
        total_tools += len(tools)

        print(f"📁 {py_file.name}: {len(tools)} tools found")

        for tool in tools:
            has_docstring = check_function_docstring(py_file, tool)
            status = "✅" if has_docstring else "❌"
            print(f"  {status} {tool}")

            if has_docstring:
                documented_tools += 1

    print(f"\n📊 Summary:")
    print(f"  Files processed: {files_processed}")
    print(f"  Total tools: {total_tools}")
    print(f"  Documented tools: {documented_tools}")

    if total_tools > 0:
        print(f"  Documentation coverage: {documented_tools / total_tools * 100:.1f}%")
    else:
        print("  Documentation coverage: 0.0% (no tools found)")

    if documented_tools < total_tools:
        print(f"\n⚠️  {total_tools - documented_tools} tools need documentation")
        return 1, total_tools, documented_tools
    else:
        print("\n🎉 All tools are properly documented!")
        return 0, total_tools, documented_tools


def verify_tool_count():
    """Legacy function for backward compatibility.

    Returns:
        int: Total number of tools found
    """
    exit_code, total_tools, documented_tools = main()
    return total_tools


if __name__ == "__main__":
    exit_code, total_tools, documented_tools = main()

    print(f"\n🎯 Tool Count Analysis:")
    print(f"Target: 88+ tools")
    print(f"Found: {total_tools} tools")
    print(f"Status: {'✓ TARGET ACHIEVED' if total_tools >= 88 else '✗ TARGET NOT MET'}")

    if total_tools >= 88:
        print(f"Exceeded target by: {total_tools - 88} tools")
    else:
        print(f"Tools needed: {88 - total_tools}")

    print("\n📋 Tool Category Breakdown:")
    print("- Foundational CAD: Modeling (9), Sketching (17), Drawing (8)")
    print("- Analysis & QA: Analysis (4), Drawing Analysis (10)")
    print("- Data Management: Export (7), File Management (3)")
    print("- Automation: Automation (8), VBA Generation (10)")
    print("- Templates & Macros: Template Management (6), Macro Recording (8)")
    print(f"\n📈 Expected Total: 90 tools (Current: {total_tools})")

    exit(exit_code)
