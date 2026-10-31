"""Turn a live demo's captured evidence frames into one GIF per test.

``tests/live/evidence.py`` saves ``<test>-<NN>.png`` frames when
``SW_DEMO_CAPTURE_DIR`` is set. This groups them by test and writes
``<test>.gif`` beside them, scaled to ``--width`` pixels, each frame held for
``--seconds``. Frames are padded to one size at the bottom and each replaces
the last outright, so a shorter caption leaves no trace of a longer one::

    python tests/scripts/make_demo_gif.py docs/assets/demos/engineering-data

With ``--recording`` it also builds ``<test>-motion.gif`` from each recording
under ``<directory>/recording/<test>/`` (``tests/live/recorder.py``): every
changed frame with the caption current at that moment beneath it. Each frame
plays for as long as it was on screen, divided by ``--speed`` and capped at
``--max-hold``, so motion plays as it happened and a wait collapses to a
moment::

    python tests/scripts/make_demo_gif.py docs/assets/demos/readme --recording
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

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
            duration=[
                int((_PROMPT_SECONDS if i == 0 else seconds) * 1000)
                for i in range(len(images))
            ],
            loop=0,
            disposal=2,
            optimize=False,
        )
        written.append(target)
    return written


_STAMP = re.compile(r"^(?P<kind>frame|caption|end)-(?P<ms>\d{8})(?:\.png)?$")


#: How long the first frame (the prompt and the plan) shows.
_PROMPT_SECONDS = 4.0


def _timeline(folder: Path) -> tuple[list, list, int]:
    """A recording's frames and captions as ``(ms, path)``, and its end time."""
    frames, captions, end = [], [], 0
    for path in sorted(folder.iterdir()):
        match = _STAMP.match(path.name)
        if not match:
            continue
        ms = int(match["ms"])
        if match["kind"] == "frame":
            frames.append((ms, path))
        elif match["kind"] == "caption":
            captions.append((ms, path))
        else:
            end = max(end, ms)
    last = max([ms for ms, _ in frames + captions] or [0])
    return frames, captions, max(end, last + 1000)


def _latest(items: list, ms: int) -> Path | None:
    """The last item stamped at or before ``ms``."""
    found = None
    for at, path in items:
        if at > ms:
            break
        found = path
    return found


def build_recording(
    folder: Path,
    out: Path,
    width: int,
    speed: float,
    max_hold: float,
    min_caption: float = 0.6,
) -> Path | None:
    """One recording as a GIF; ``None`` when it holds no frames.

    A frame where a new caption appears shows for at least ``min_caption``
    seconds, so a tool call can be read however fast the rest plays.
    """
    frames, captions, end = _timeline(folder)
    if not frames:
        return None
    events = sorted(
        {ms for ms, _ in frames} | {ms for ms, _ in captions if ms >= frames[0][0]}
    )

    def scaled(path: Path) -> Image.Image:
        image = Image.open(path).convert("RGB")
        height = round(image.height * width / image.width)
        return image.resize((width, height), Image.LANCZOS)

    caption_height = max(
        (
            round(Image.open(p).height * width / Image.open(p).width)
            for _, p in captions
        ),
        default=0,
    )
    palette = _shared_palette([p for _, p in frames] + [p for _, p in captions], scaled)
    images, durations = [], []
    shot_cache: dict[Path, Image.Image] = {}
    for i, ms in enumerate(events):
        shot_path = _latest(frames, ms)
        caption_path = _latest(captions, ms)
        if shot_path not in shot_cache:
            shot_cache.clear()
            shot_cache[shot_path] = scaled(shot_path)
        shot = shot_cache[shot_path]
        frame = Image.new(
            "RGB", (width, shot.height + caption_height), _CAPTION_BACKGROUND
        )
        frame.paste(shot, (0, 0))
        if caption_path is not None:
            frame.paste(scaled(caption_path), (0, shot.height))
        following = events[i + 1] if i + 1 < len(events) else end
        seconds = min((following - ms) / 1000.0 / speed, max_hold)
        if caption_path is not None and caption_path != _latest(captions, ms - 1):
            # The first caption is the prompt: give it time to be read.
            first = caption_path == captions[0][1]
            seconds = max(seconds, _PROMPT_SECONDS if first else min_caption)
        images.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
        durations.append(max(20, int(seconds * 1000)))
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        disposal=1,
        optimize=False,
    )
    return out


def _shared_palette(paths: list[Path], scaled: Any) -> Image.Image:
    """One 256-colour palette for every frame of a recording.

    With one palette, a frame that differs from the last only where
    SolidWorks redrew is stored as just that region (Pillow writes the
    changed box); a palette per frame makes every pixel differ, and a
    recording of a few hundred frames ran to 41 MB.
    """
    step = max(1, len(paths) // 16)
    sample = [scaled(p) for p in paths[::step][:24]]
    strip = Image.new("RGB", (sample[0].width, sum(i.height for i in sample)))
    y = 0
    for image in sample:
        strip.paste(image, (0, y))
        y += image.height
    return strip.quantize(colors=256, method=Image.MEDIANCUT)


def build_recordings(
    directory: Path,
    width: int,
    speed: float,
    max_hold: float,
    min_caption: float = 0.6,
) -> list[Path]:
    """``<test>-motion.gif`` for every recording under ``directory/recording``."""
    root = directory / "recording"
    if not root.is_dir():
        return []
    written = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        gif = build_recording(
            folder,
            directory / f"{folder.name}-motion.gif",
            width,
            speed,
            max_hold,
            min_caption,
        )
        if gif is not None:
            written.append(gif)
    return written


def main() -> None:
    """Parse arguments and build the GIFs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--seconds", type=float, default=2.5)
    parser.add_argument(
        "--recording", action="store_true", help="also build the motion GIFs"
    )
    parser.add_argument(
        "--speed", type=float, default=5.0, help="motion GIF playback speed-up"
    )
    parser.add_argument(
        "--max-hold", type=float, default=0.6, help="longest a motion frame shows (s)"
    )
    parser.add_argument(
        "--min-caption",
        type=float,
        default=0.6,
        help="shortest a frame with a new caption shows (s)",
    )
    args = parser.parse_args()
    paths = build_gifs(args.directory, args.width, args.seconds)
    if args.recording:
        paths += build_recordings(
            args.directory, args.width, args.speed, args.max_hold, args.min_caption
        )
    for path in paths:
        print(f"{path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
