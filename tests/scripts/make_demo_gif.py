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

Every motion GIF opens on its last frame, the finished result, for
``POSTER_SECONDS`` before the build plays: a recording starts on SolidWorks'
empty start screen, and GitHub shows readers with reduced motion only the
first frame, so the README cell looked empty. ``--poster`` adds that opening
frame to motion GIFs already built::

    python tests/scripts/make_demo_gif.py docs/assets/demos/tool-gaps --poster
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

#: How long a motion GIF shows its finished result before the build plays.
POSTER_SECONDS = 2.0

_FRAME = re.compile(r"^(?P<test>.+)-(?P<index>\d{2})\.png$")
#: The caption panel's background in ``tests/live/evidence.py``.
_CAPTION_BACKGROUND = (24, 24, 28)


def build_gifs(
    directory: Path, width: int, seconds: float, prompt_seconds: float = 4.0
) -> list[Path]:
    """Write one GIF per test found in ``directory``; return their paths.

    The first frame, the prompt, shows for ``prompt_seconds``.
    """
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
                int((prompt_seconds if i == 0 else seconds) * 1000)
                for i in range(len(images))
            ],
            loop=0,
            disposal=2,
            optimize=False,
        )
        written.append(target)
    return written


_STAMP = re.compile(
    r"^(?P<kind>frame|caption|end)-(?P<ms>\d{8})(?:-hold(?P<hold>\d+))?(?:\.png)?$"
)


def _timeline(folder: Path) -> tuple[list, list, int, dict[Path, float]]:
    """A recording's frames and captions as ``(ms, path)``, its end time, and
    the seconds each held caption asks to be shown (``caption-<ms>-hold<ms>``)."""
    frames, captions, end = [], [], 0
    holds: dict[Path, float] = {}
    for path in sorted(folder.iterdir()):
        match = _STAMP.match(path.name)
        if not match:
            continue
        ms = int(match["ms"])
        if match["kind"] == "frame":
            frames.append((ms, path))
        elif match["kind"] == "caption":
            captions.append((ms, path))
            if match["hold"]:
                holds[path] = int(match["hold"]) / 1000.0
        else:
            end = max(end, ms)
    last = max([ms for ms, _ in frames + captions] or [0])
    return frames, captions, max(end, last + 1000), holds


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
    prompt_seconds: float = 4.0,
    end_seconds: float = 5.0,
) -> Path | None:
    """One recording as a GIF; ``None`` when it holds no frames.

    A frame where a new caption appears shows for at least ``min_caption``
    seconds (or the hold the caption was saved with), so a tool call can be read however fast the rest plays; the
    first caption, the prompt, for at least ``prompt_seconds``; and the last
    frame, the result, for at least ``end_seconds`` before the GIF loops.
    """
    frames, captions, end, holds = _timeline(folder)
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
            least = prompt_seconds if first else holds.get(caption_path, min_caption)
            seconds = max(seconds, least)
        if i == len(events) - 1:
            seconds = max(seconds, end_seconds)
        images.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
        durations.append(max(20, int(seconds * 1000)))
    # Open on the finished result (see the module docstring).
    images.insert(0, images[-1])
    durations.insert(0, int(POSTER_SECONDS * 1000))
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


def add_poster(path: Path, seconds: float = POSTER_SECONDS) -> bool:
    """Open an already built motion GIF on its last frame for ``seconds``.

    The poster is spliced in as one more image block ahead of the first
    frame; every original frame's bytes are kept, so the file grows by one
    frame only (re-encoding the whole GIF with Pillow doubled the U-joint's).

    Returns:
        False when it already opens on its last frame.
    """
    with Image.open(path) as gif:
        first = gif.convert("RGB")
        gif.seek(gif.n_frames - 1)
        last = gif.convert("RGB")
        size = gif.size
    if _looks_alike(first, last):
        return False
    data = path.read_bytes()
    at = _first_frame_offset(data)
    path.write_bytes(data[:at] + _poster_block(last, size, seconds) + data[at:])
    return True


def _looks_alike(a: Image.Image, b: Image.Image) -> bool:
    """Two frames that differ only by colour rounding (a poster and its source)."""
    from PIL import ImageStat

    return max(ImageStat.Stat(ImageChops.difference(a, b)).mean) < 2.0


def _skip_sub_blocks(data: bytes, at: int) -> int:
    """The offset after a run of GIF data sub-blocks starting at ``at``."""
    while data[at]:
        at += data[at] + 1
    return at + 1


def _first_frame_offset(data: bytes) -> int:
    """Where the first frame (its graphic control extension or image) starts."""
    at = 13
    if data[10] & 0x80:
        at += 3 * 2 ** ((data[10] & 0x07) + 1)
    while data[at] == 0x21 and data[at + 1] != 0xF9:
        at = _skip_sub_blocks(data, at + 2)
    return at


def _poster_block(image: Image.Image, size: tuple[int, int], seconds: float) -> bytes:
    """One full-canvas frame, with its own colour table, held ``seconds``."""
    from io import BytesIO

    buffer = BytesIO()
    image.quantize(colors=256, method=Image.MEDIANCUT).save(
        buffer, format="GIF", interlace=False
    )
    one = buffer.getvalue()
    flags = one[10]
    table = one[13 : 13 + 3 * 2 ** ((flags & 0x07) + 1)] if flags & 0x80 else b""
    at = 13 + len(table)
    while one[at] == 0x21:
        at = _skip_sub_blocks(one, at + 2)
    width, height = size
    descriptor = (
        b"\x2c\x00\x00\x00\x00"
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
        + bytes([(0x80 | (flags & 0x07)) if table else 0])
    )
    image_data = one[at + 10 : _skip_sub_blocks(one, at + 11)]
    hundredths = int(seconds * 100).to_bytes(2, "little")
    control = b"\x21\xf9\x04\x04" + hundredths + b"\x00\x00"
    return control + descriptor + table + image_data


def build_recordings(
    directory: Path,
    width: int,
    speed: float,
    max_hold: float,
    min_caption: float = 0.6,
    prompt_seconds: float = 4.0,
    end_seconds: float = 5.0,
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
            prompt_seconds,
            end_seconds,
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
        "--poster",
        action="store_true",
        help="only open the motion GIFs already built on their last frame",
    )
    parser.add_argument(
        "--speed", type=float, default=2.5, help="motion GIF playback speed-up"
    )
    parser.add_argument(
        "--max-hold", type=float, default=1.0, help="longest a motion frame shows (s)"
    )
    parser.add_argument(
        "--min-caption",
        type=float,
        default=1.2,
        help="shortest a frame with a new caption shows (s)",
    )
    parser.add_argument(
        "--prompt-seconds",
        type=float,
        default=4.0,
        help="how long the first frame, the prompt, shows (s)",
    )
    parser.add_argument(
        "--end-seconds",
        type=float,
        default=5.0,
        help="how long the last motion frame, the result, shows (s)",
    )
    args = parser.parse_args()
    if args.poster:
        for gif in sorted(args.directory.glob("*-motion.gif")):
            print(f"{gif}: {'poster added' if add_poster(gif) else 'already has one'}")
        return
    paths = build_gifs(args.directory, args.width, args.seconds, args.prompt_seconds)
    if args.recording:
        paths += build_recordings(
            args.directory,
            args.width,
            args.speed,
            args.max_hold,
            args.min_caption,
            args.prompt_seconds,
            args.end_seconds,
        )
    for path in paths:
        print(f"{path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
