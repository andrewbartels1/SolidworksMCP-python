"""Turn a live demo's captured evidence frames into one GIF per test.

``tests/live/evidence.py`` saves ``<test>-<NN>.png`` frames when
``SW_DEMO_CAPTURE_DIR`` is set. This groups them by test and writes
``<test>.gif`` beside them, scaled to ``--width`` pixels, each frame held for
``--seconds``. Frames are padded to one size at the bottom and each replaces
the last outright, so a shorter caption leaves no trace of a longer one::

    python tests/scripts/make_demo_gif.py docs/assets/demos/engineering-data
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image

_FRAME = re.compile(r"^(?P<test>.+)-(?P<index>\d{2})\.png$")
#: The caption panel's background in ``tests/live/evidence.py``.
_CAPTION_BACKGROUND = (24, 24, 28)


def build_gifs(directory: Path, width: int, seconds: float) -> list[Path]:
    """Write one GIF per test found in ``directory``; return their paths."""
    frames: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(directory.glob("*.png")):
        match = _FRAME.match(path.name)
        if match:
            frames[match["test"]].append(path)
    written = []
    for test, paths in sorted(frames.items()):
        scaled = []
        for path in paths:
            image = Image.open(path).convert("RGB")
            if image.width > width:
                height = round(image.height * width / image.width)
                image = image.resize((width, height), Image.LANCZOS)
            scaled.append(image)
        size = (max(i.width for i in scaled), max(i.height for i in scaled))
        images = []
        for image in scaled:
            padded = Image.new("RGB", size, _CAPTION_BACKGROUND)
            padded.paste(image, (0, 0))
            images.append(padded.quantize(colors=256, method=Image.MEDIANCUT))
        target = directory / f"{test}.gif"
        images[0].save(
            target,
            save_all=True,
            append_images=images[1:],
            duration=int(seconds * 1000),
            loop=0,
            disposal=2,
            optimize=False,
        )
        written.append(target)
    return written


def main() -> None:
    """Parse arguments and build the GIFs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    for path in build_gifs(args.directory, args.width, args.seconds):
        print(f"{path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
