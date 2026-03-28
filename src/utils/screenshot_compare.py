"""Screenshot equivalence comparison utility.

Computes SSIM and mean-pixel-difference between a reference image and a
generated image to validate that an LLM-generated SolidWorks part is
geometrically equivalent to the reference sample.

Usage:
    # Single comparison
    python src/utils/screenshot_compare.py \\
        --ref  "C:\\Temp\\ref.jpg" \\
        --gen  "C:\\Temp\\gen.jpg" \\
        --out  "C:\\Temp\\diff.png" \\
        --threshold 0.95

    # Batch from manifest JSON
    python src/utils/screenshot_compare.py --batch \\
        --manifest "tests/.generated/screenshot_manifest.json" \\
        --report   "tests/.generated/screenshot_report.json"

Exit codes:
    0 = PASS (SSIM >= threshold)
    1 = FAIL (SSIM < threshold)
    2 = Error (image load failure or missing dependency)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageChops, ImageFilter
    from skimage.metrics import structural_similarity as ssim
except ImportError as exc:
    print(
        f"Missing dependency: {exc}\n"
        "Install with: pip install pillow scikit-image numpy",
        file=sys.stderr,
    )
    sys.exit(2)


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

_BLUR_RADIUS = 1.0  # Pre-blur to suppress anti-aliasing noise
_RESIZE_TARGET = (1280, 720)  # Normalise resolution before comparison


def _load_normalised(path: Path) -> np.ndarray:
    """Load an image, resize to common resolution, convert to greyscale float array."""
    img = Image.open(path).convert("RGB")
    img = img.resize(_RESIZE_TARGET, Image.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))
    grey = img.convert("L")
    return np.array(grey, dtype=np.float32) / 255.0


def compare(ref_path: Path, gen_path: Path, diff_path: Path | None = None) -> dict:
    """Compare two images.  Returns a result dict with SSIM and mpd."""
    ref_arr = _load_normalised(ref_path)
    gen_arr = _load_normalised(gen_path)

    score, diff_arr = ssim(ref_arr, gen_arr, full=True, data_range=1.0)
    mean_px_diff = float(np.mean(np.abs(ref_arr - gen_arr))) * 100.0
    max_px_diff = float(np.max(np.abs(ref_arr - gen_arr))) * 100.0

    if diff_path is not None:
        diff_uint8 = (np.clip(1.0 - diff_arr, 0.0, 1.0) * 255).astype(np.uint8)
        diff_img = Image.fromarray(diff_uint8, mode="L")
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_img.save(diff_path)

    return {
        "ref": str(ref_path),
        "gen": str(gen_path),
        "diff": str(diff_path) if diff_path else None,
        "ssim": round(float(score), 4),
        "mean_px_diff_pct": round(mean_px_diff, 2),
        "max_px_diff_pct": round(max_px_diff, 2),
    }


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _run_single(args: argparse.Namespace) -> int:
    ref_path = Path(args.ref)
    gen_path = Path(args.gen)
    diff_path = Path(args.out) if args.out else None

    if not ref_path.exists():
        print(f"ERROR: ref image not found: {ref_path}", file=sys.stderr)
        return 2
    if not gen_path.exists():
        print(f"ERROR: gen image not found: {gen_path}", file=sys.stderr)
        return 2

    result = compare(ref_path, gen_path, diff_path)
    passed = result["ssim"] >= args.threshold

    icon = "✅" if passed else "❌"
    print(f"\n{icon} SSIM score:   {result['ssim']:.4f}  (threshold: {args.threshold})")
    print(f"   Mean px diff: {result['mean_px_diff_pct']:.1f}%")
    print(f"   Max px diff:  {result['max_px_diff_pct']:.1f}%")
    if diff_path:
        print(f"   Diff image:   {diff_path}")

    return 0 if passed else 1


def _run_batch(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    report_path = Path(args.report) if args.report else None

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    with open(manifest_path, encoding="utf-8") as fh:
        manifest: list[dict] = json.load(fh)

    results: list[dict] = []
    all_pass = True

    for entry in manifest:
        name = entry.get("name", "?")
        ref_path = Path(entry["ref"])
        gen_path = Path(entry["gen"])
        diff_path = Path(entry["diff"]) if entry.get("diff") else None

        if not ref_path.exists() or not gen_path.exists():
            row = {"name": name, "status": "SKIP", "reason": "image not found"}
            results.append(row)
            print(f"⚠️  SKIP  {name}: image not found")
            continue

        result = compare(ref_path, gen_path, diff_path)
        passed = result["ssim"] >= args.threshold
        result["name"] = name
        result["status"] = "PASS" if passed else "FAIL"
        results.append(result)

        icon = "✅" if passed else "❌"
        print(
            f"{icon} {'PASS' if passed else 'FAIL'}  {name}: "
            f"SSIM={result['ssim']:.4f}  MPD={result['mean_px_diff_pct']:.1f}%"
        )
        if not passed:
            all_pass = False

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nReport written: {report_path}")

    pass_count = sum(1 for r in results if r.get("status") == "PASS")
    total = len(manifest)
    print(f"\nSummary: {pass_count}/{total} models passed equivalence check.")

    return 0 if all_pass else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Screenshot equivalence comparison for SolidWorks MCP models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Minimum SSIM score to pass (default: 0.95)",
    )

    sub = parser.add_subparsers(dest="mode")

    # Single mode (default when --ref/--gen provided at root level)
    parser.add_argument("--ref", help="Path to reference image")
    parser.add_argument("--gen", help="Path to generated image")
    parser.add_argument("--out", help="Path to write diff image (optional)")

    # Batch mode
    batch = sub.add_parser("--batch", help="Batch comparison from manifest JSON")
    batch.add_argument("--manifest", required=True, help="Path to manifest JSON")
    batch.add_argument("--report", help="Path to write JSON report")
    batch.add_argument("--threshold", type=float, default=0.95, dest="threshold_batch")

    return parser


def main() -> None:
    # Handle --batch flag before subparser
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        sys.argv.pop(idx)
        parser = argparse.ArgumentParser()
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--report")
        parser.add_argument("--threshold", type=float, default=0.95)
        args = parser.parse_args()
        sys.exit(_run_batch(args))

    parser = _build_parser()
    args = parser.parse_args()

    if not args.ref or not args.gen:
        parser.print_help()
        sys.exit(2)

    sys.exit(_run_single(args))


if __name__ == "__main__":
    main()
