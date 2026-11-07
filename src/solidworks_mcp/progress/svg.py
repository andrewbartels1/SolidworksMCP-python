"""The README's progress image: two glossy, striped bars on a dark panel.

Hand-built SVG with no dependencies. It draws its own dark panel, so it
reads the same in GitHub's light and dark themes. The stripes drift slowly
(an SVG animation, which GitHub's image proxy keeps).
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

from ..tools.support_levels import SupportLevel
from .com_coverage import CORE_INTERFACES, ComCoverage

#: Fill colour per level; planned is left as the empty track.
LEVEL_COLOURS: dict[SupportLevel, str] = {
    SupportLevel.STABLE: "#2ea043",
    SupportLevel.BETA: "#d29922",
    SupportLevel.EXPERIMENTAL: "#db6d28",
    SupportLevel.PLANNED: "#484f58",
}

_WIDTH, _HEIGHT = 840, 236
_X, _BAR_W, _BAR_H = 28, 784, 24
_FONT = "font-family=\"-apple-system,'Segoe UI',Helvetica,Arial,sans-serif\""

_DEFS = """<defs>
  <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#161b22"/><stop offset="1" stop-color="#0d1117"/>
  </linearGradient>
  <linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity=".45"/>
    <stop offset=".5" stop-color="#fff" stop-opacity=".08"/>
    <stop offset=".5" stop-color="#000" stop-opacity="0"/>
    <stop offset="1" stop-color="#000" stop-opacity=".18"/>
  </linearGradient>
  <linearGradient id="heat" gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" x2="{x1}" y2="0">
    <stop offset="0" stop-color="#da3633"/><stop offset=".5" stop-color="#d29922"/>
    <stop offset="1" stop-color="#2ea043"/>
  </linearGradient>
  <pattern id="stripes" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="8" height="16" fill="#fff" fill-opacity=".14"/>
    <animateTransform attributeName="patternTransform" type="translate" additive="sum" from="0 0" to="16 0" dur="1.6s" repeatCount="indefinite"/>
  </pattern>
  <clipPath id="track-tools"><rect x="{x0}" y="{y1}" width="{w}" height="{h}" rx="{r}"/></clipPath>
  <clipPath id="track-com"><rect x="{x0}" y="{y2}" width="{w}" height="{h}" rx="{r}"/></clipPath>
</defs>"""


def _pct(part: int, whole: int) -> float:
    return 100.0 * part / whole if whole else 0.0


def _text(
    x: float,
    y: float,
    body: str,
    size: int,
    fill: str,
    anchor: str = "start",
    weight: str = "400",
) -> str:
    return (
        f'<text x="{x:g}" y="{y:g}" {_FONT} font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(body)}</text>'
    )


def _track(y: float, clip: str, fills: list[tuple[float, float, str]]) -> list[str]:
    """One bar: track, coloured segments, stripes and gloss over the filled part."""
    r = _BAR_H / 2
    filled = sum(w for _, w, _ in fills)
    parts = [
        f'<rect x="{_X}" y="{y}" width="{_BAR_W}" height="{_BAR_H}" rx="{r}" '
        'fill="#21262d" stroke="#30363d"/>',
        f'<g clip-path="url(#{clip})">',
    ]
    parts += [
        f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{_BAR_H}" fill="{c}"/>'
        for x, w, c in fills
    ]
    for paint in ("url(#stripes)", "url(#gloss)"):
        parts.append(
            f'<rect x="{_X}" y="{y}" width="{filled:.1f}" height="{_BAR_H}" fill="{paint}"/>'
        )
    parts.append("</g>")
    parts.append(
        f'<rect x="{_X + 0.5}" y="{y + 0.5}" width="{_BAR_W - 1}" height="{_BAR_H - 1}" '
        f'rx="{r}" fill="none" stroke="#fff" stroke-opacity=".08"/>'
    )
    return parts


def render(levels: Mapping[SupportLevel, int], coverage: ComCoverage) -> str:
    """The progress image.

    Args:
        levels: How many tools have each support level.
        coverage: COM coverage of the core interfaces and the whole API.

    Returns:
        str: The SVG document.
    """
    total = sum(levels.values())
    y_tools, y_com = 54, 156
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" aria-label="Project progress">',
        _DEFS.format(
            x0=_X,
            x1=_X + _BAR_W,
            y1=y_tools,
            y2=y_com,
            w=_BAR_W,
            h=_BAR_H,
            r=_BAR_H / 2,
        ),
        f'<rect x=".5" y=".5" width="{_WIDTH - 1}" height="{_HEIGHT - 1}" rx="14" '
        'fill="url(#panel)" stroke="#30363d"/>',
    ]

    ready = levels.get(SupportLevel.STABLE, 0) + levels.get(SupportLevel.BETA, 0)
    out.append(_text(_X, 40, f"MCP tools: {total}", 16, "#e6edf3", weight="600"))
    out.append(
        _text(
            _X + _BAR_W,
            40,
            f"{_pct(ready, total):.0f}% work on SolidWorks today",
            13,
            "#8b949e",
            "end",
        )
    )
    fills, x = [], float(_X)
    for level in (SupportLevel.STABLE, SupportLevel.BETA, SupportLevel.EXPERIMENTAL):
        width = _BAR_W * levels.get(level, 0) / total if total else 0.0
        fills.append((x, width, LEVEL_COLOURS[level]))
        x += width
    out += _track(y_tools, "track-tools", fills)

    lx = float(_X)
    for level in SupportLevel:
        label = f"{level.value} {levels.get(level, 0)}"
        out.append(
            f'<rect x="{lx:g}" y="{y_tools + 38}" width="10" height="10" rx="2" '
            f'fill="{LEVEL_COLOURS[level]}"/>'
        )
        out.append(_text(lx + 16, y_tools + 47, label, 12, "#c9d1d9"))
        lx += 24 + 7.2 * len(label)

    core_pct = _pct(coverage.core_covered, coverage.core_total)
    out.append(
        _text(
            _X,
            y_com - 14,
            f"Core SolidWorks COM API ({len(CORE_INTERFACES)} interfaces)",
            16,
            "#e6edf3",
            weight="600",
        )
    )
    out.append(
        _text(
            _X + _BAR_W,
            y_com - 14,
            f"{coverage.core_covered:,} of {coverage.core_total:,} methods · {core_pct:.1f}%",
            13,
            "#8b949e",
            "end",
        )
    )
    out += _track(
        y_com, "track-com", [(float(_X), _BAR_W * core_pct / 100, "url(#heat)")]
    )
    api_pct = _pct(coverage.api_covered, coverage.api_total)
    out.append(
        _text(
            _X,
            y_com + 50,
            f"Whole API: {coverage.api_covered:,} of {coverage.api_total:,} method "
            f"names ({api_pct:.1f}%), counted by a text scan of the adapters.",
            11,
            "#6e7681",
        )
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"
