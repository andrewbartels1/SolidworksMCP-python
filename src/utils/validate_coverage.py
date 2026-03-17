#!/usr/bin/env python3
"""
Comprehensive test coverage validation and reporting.

This script runs all tests, validates coverage, and generates reports
to ensure 100% test coverage across the SolidWorks MCP server.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
import coverage


def run_command(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run shell command and return results."""
    print(f"🔧 Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.returncode == 0,
    }


def validate_test_structure(project_root: Path) -> bool:
    """Validate that all expected test files exist."""
    expected_test_files = [
        "test_tools_modeling.py",
        "test_tools_sketching.py",
        "test_tools_drawing.py",
        "test_tools_analysis.py",
        "test_tools_export.py",
        "test_tools_file_management.py",
        "test_tools_automation.py",
        "test_tools_vba_generation.py",
        "test_tools_template_management.py",
        "test_tools_macro_recording.py",
        "test_tools_drawing_analysis.py",
        "test_adapters.py",
        "test_server.py",
        "test_integration.py",
    ]

    print("\n🔍 Validating test structure...", project_root)
    tests_dir = project_root / "tests"
    missing_files = []

    for test_file in expected_test_files:
        if not (tests_dir / test_file).exists():
            missing_files.append(test_file)

    if missing_files:
        print(f"❌ Missing test files: {missing_files}")
        return False

    print("✅ All expected test files found")
    return True


def run_tests_with_coverage(project_root: Path) -> dict[str, Any]:
    """Run pytest with coverage reporting."""
    print("\n" + "=" * 50)
    print("🧪 RUNNING COMPREHENSIVE TEST SUITE")
    print("=" * 50)

    # Set environment for testing
    env = os.environ.copy()
    env["USE_MOCK_SOLIDWORKS"] = "true"
    env["PYTHONPATH"] = str(project_root / "src")

    # Run pytest with coverage
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--verbose",
        "--tb=short",
        "--strict-markers",
        "--strict-config",
        "--color=yes",
        "--durations=10",
        "--cov=src/solidworks_mcp",
        "--cov-report=html:htmlcov",
        "--cov-report=term-missing",
        "--cov-report=xml",
        "--cov-fail-under=90",
        "--asyncio-mode=auto",
        "tests/",
    ]

    result = subprocess.run(cmd, cwd=project_root, env=env, text=True)

    return {"success": result.returncode == 0, "returncode": result.returncode}


def run_specific_test_categories(project_root: Path) -> dict[str, Any]:
    """Run tests by category to validate each tool group."""
    print("\n" + "=" * 50)
    print("📊 RUNNING CATEGORY-SPECIFIC TESTS")
    print("=" * 50)

    categories = [
        ("modeling", "test_tools_modeling.py"),
        ("sketching", "test_tools_sketching.py"),
        ("drawing", "test_tools_drawing.py"),
        ("analysis", "test_tools_analysis.py"),
        ("export", "test_tools_export.py"),
        ("file_management", "test_tools_file_management.py"),
        ("automation", "test_tools_automation.py"),
        ("vba_generation", "test_tools_vba_generation.py"),
        ("template_management", "test_tools_template_management.py"),
        ("macro_recording", "test_tools_macro_recording.py"),
        ("drawing_analysis", "test_tools_drawing_analysis.py"),
    ]

    results = {}
    env = os.environ.copy()
    env["USE_MOCK_SOLIDWORKS"] = "true"
    env["PYTHONPATH"] = str(project_root / "src")

    for category, test_file in categories:
        print(f"\n🔍 Testing {category} tools...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--verbose",
            "-x",  # Stop on first failure
            f"tests/{test_file}",
        ]

        result = subprocess.run(
            cmd, cwd=project_root, env=env, capture_output=True, text=True
        )

        results[category] = {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "output": result.stdout if result.returncode == 0 else result.stderr,
        }

        if result.returncode == 0:
            print(f"✅ {category} tests passed")
        else:
            print(f"❌ {category} tests failed")
            print(f"Error: {result.stderr[:500]}")

    return results


def analyze_coverage_report(project_root: Path) -> dict[str, Any]:
    """Analyze the coverage report and extract key metrics."""
    coverage_file = project_root / ".coverage"

    if not coverage_file.exists():
        return {"error": "Coverage file not found"}

    try:
        cov = coverage.Coverage()
        cov.load()

        # Get coverage data
        total_percent = cov.report(show_missing=False, skip_covered=False)

        # Get detailed file coverage
        analysis = cov.get_data()
        file_coverage = {}

        for filename in analysis.measured_files():
            if "src/solidworks_mcp" in filename:
                file_analysis = cov.analysis2(filename)
                executed_lines = len(file_analysis.executed)
                missing_lines = len(file_analysis.missing)
                total_lines = executed_lines + missing_lines

                if total_lines > 0:
                    file_percent = (executed_lines / total_lines) * 100
                    relative_path = filename.replace(str(project_root), "").lstrip(
                        "/\\"
                    )
                    file_coverage[relative_path] = {
                        "percent": file_percent,
                        "executed": executed_lines,
                        "missing": missing_lines,
                        "total": total_lines,
                    }

        return {"total_percent": total_percent, "file_coverage": file_coverage}

    except Exception as e:
        return {"error": f"Coverage analysis failed: {e}"}


def generate_coverage_summary(coverage_data: dict[str, Any]) -> None:
    """Generate and print coverage summary."""
    print("\n" + "=" * 50)
    print("📈 COVERAGE ANALYSIS SUMMARY")
    print("=" * 50)

    if "error" in coverage_data:
        print(f"❌ Coverage analysis error: {coverage_data['error']}")
        return

    total_percent = coverage_data.get("total_percent", 0)
    file_coverage = coverage_data.get("file_coverage", {})

    print(f"\n🎯 Overall Coverage: {total_percent:.1f}%")

    if total_percent >= 95:
        print("🏆 EXCELLENT coverage!")
    elif total_percent >= 90:
        print("✅ GOOD coverage")
    elif total_percent >= 80:
        print("⚠️ FAIR coverage - consider adding more tests")
    else:
        print("❌ LOW coverage - significant testing needed")

    # Show tool coverage
    tool_files = [f for f in file_coverage.keys() if "tools/" in f]
    if tool_files:
        print(f"\n📁 Tool Coverage ({len(tool_files)} files):")
        print("-" * 60)

        for file_path in sorted(tool_files):
            data = file_coverage[file_path]
            percent = data["percent"]

            status = "✅" if percent >= 90 else "⚠️" if percent >= 80 else "❌"
            tool_name = Path(file_path).stem.replace("tools_", "").replace("_", " ")
            print(
                f"{status} {tool_name:<20} {percent:6.1f}% ({data['executed']}/{data['total']} lines)"
            )

    # Show files needing attention
    low_coverage_files = [
        (path, data)
        for path, data in file_coverage.items()
        if data["percent"] < 90 and "tools/" in path
    ]

    if low_coverage_files:
        print(f"\n🔍 Files needing more tests (< 90% coverage):")
        print("-" * 60)
        for file_path, data in sorted(
            low_coverage_files, key=lambda x: x[1]["percent"]
        ):
            print(
                f"❌ {file_path}: {data['percent']:.1f}% ({data['missing']} lines missing)"
            )


def validate_documentation(project_root: Path) -> dict[str, Any]:
    """Validate that documentation files exist and are up to date."""
    print("\n" + "=" * 50)
    print("📚 DOCUMENTATION VALIDATION")
    print("=" * 50)

    required_docs = [
        "docs/index.md",
        "docs/getting-started/installation.md",
        "docs/getting-started/quickstart.md",
        "mkdocs.yml",
        "docs/DOCUMENTATION_PROGRESS.md",
    ]

    missing_docs = []
    for doc in required_docs:
        if not (project_root / doc).exists():
            missing_docs.append(doc)

    if missing_docs:
        print(f"❌ Missing documentation files: {missing_docs}")
        return {"success": False, "missing": missing_docs}

    print("✅ All required documentation files found")

    # Try to build docs
    print("\n🔨 Building documentation...")
    result = run_command(["mkdocs", "build", "--strict"], cwd=project_root)

    if result["success"]:
        print("✅ Documentation builds successfully")
        return {"success": True, "build_output": result["stdout"]}
    else:
        print(f"❌ Documentation build failed: {result['stderr']}")
        return {"success": False, "build_error": result["stderr"]}


def main():
    """Main test validation and coverage analysis."""
    project_root = Path(__file__).resolve().parents[2]

    print("🚀 SolidWorks MCP Server - Comprehensive Test Suite")
    print(f"📁 Project root: {project_root}")
    print(f"⏰ Starting at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Validate test structure
    if not validate_test_structure(project_root):
        sys.exit(1)

    # Run comprehensive tests
    test_results = run_tests_with_coverage(project_root)

    # Run category-specific tests
    category_results = run_specific_test_categories(project_root)

    # Analyze coverage
    coverage_data = analyze_coverage_report(project_root)
    generate_coverage_summary(coverage_data)

    # Validate documentation
    doc_results = validate_documentation(project_root)

    # Final summary
    print("\n" + "=" * 50)
    print("🏁 FINAL TEST SUITE SUMMARY")
    print("=" * 50)

    total_passed = test_results["success"]
    category_failures = sum(1 for r in category_results.values() if not r["success"])
    docs_valid = doc_results["success"]

    coverage_percent = coverage_data.get("total_percent", 0)
    coverage_target_met = coverage_percent >= 90

    print(f"🧪 Overall tests: {'✅ PASSED' if total_passed else '❌ FAILED'}")
    print(
        f"📊 Category tests: {len(category_results) - category_failures}/{len(category_results)} passed"
    )
    print(
        f"📈 Coverage target (90%): {'✅ MET' if coverage_target_met else '❌ MISSED'} ({coverage_percent:.1f}%)"
    )
    print(f"📚 Documentation: {'✅ VALID' if docs_valid else '❌ ISSUES'}")

    overall_success = (
        total_passed and category_failures == 0 and coverage_target_met and docs_valid
    )

    if overall_success:
        print("\n🎉 ALL VALIDATION CHECKS PASSED!")
        print("✅ Ready for production deployment")
    else:
        print("\n⚠️ Some validation checks failed")
        print("🔧 Please address issues before deployment")
        sys.exit(1)


if __name__ == "__main__":
    main()
