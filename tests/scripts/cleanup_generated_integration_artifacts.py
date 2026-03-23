"""Cleanup utility for generated SolidWorks integration artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    generated_dir = Path("tests") / ".generated" / "solidworks_integration"

    if not generated_dir.exists():
        print(f"No generated artifacts found at {generated_dir}")
        return 0

    shutil.rmtree(generated_dir)
    print(f"Removed generated integration artifacts: {generated_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
