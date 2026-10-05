#!/usr/bin/env python3
"""Build Warding's brand kit from one geometry and one palette.

The mark is the Ward Seal: a round seal with a keyhole whose shaft is crossed
by three ward bars, and one drop of wax at two o'clock. The bars are the wards
in a lock, the fixed ridges that stop every wrong key from turning, which is
what the product's policy does to the agent. Everything below derives from the
seal (drawn on a 64-unit grid, with a 16-unit variant for favicon sizes) and
the two palettes, paper and night, so a change here reaches every surface in
one run:

* ``assets/brand/*.svg``: the mark, the bare glyph, the wordmark and lockups
* ``assets/banner.svg``: the README banner
* ``website/src/assets/junction-glyph.svg``: the dashboard's masked glyph
* ``website/electron``: ``icon.png``/``.ico``/``.icns`` (plus nightly), the
  Linux ``build/icons`` set and the macOS menu-bar ``trayTemplate`` images
* ``website/public``: PWA icons
* ``src/junction/static/junction-logo*.png``: the gateway's ``/logo.png``
* ``packaging/installer-assets``: the DMG background and the NSIS header and
  sidebar, as editable SVG plus the TIFF/BMP rasters the installers consume

The ward bars are true cut-outs: the shaft is drawn as segments with the bar
slots left open, and the vermillion wings sit either side of it, so the mark
reads on any surface and survives a CSS ``mask`` (which keeps alpha only).

The wordmark is "warding" outlined from the bundled Fraunces variable font at
wght 600, opsz 144, SOFT 0, WONK 0, tracked -0.015 em, with the ear of the
``g`` squared to echo the bars. The tagline and installer copy are outlined
from IBM Plex Sans. Both fonts live under ``website/public/fonts``, so no SVG
depends on an installed font.

Requires Pillow, fontTools and brotli (``pip install pillow fonttools brotli``),
plus ``npm ci`` in ``website/`` for the Playwright rasterizer. Set ``CHROME`` to
a Chromium binary if Playwright's own browser is not installed. Run from the
repository root::

    python3 assets/brand/build.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "assets" / "brand"
FONTS = ROOT / "website" / "public" / "fonts"

PRODUCT = "Warding"
WORDMARK = "warding"
TAGLINE = "The lamp stays on. The rules stay shut."

# Paper: the light theme, the default on marketing surfaces and the app icon.
PAPER = {
    "bg": "#F3EEE3",
    "surface": "#FBF8F1",
    "fg": "#1A1814",
    "fg2": "#5E584D",
    "line": "#D9D0BF",
    "seal": "#B3301A",
    "lamp": "#B86A00",
    "foil": "#C98A00",
}
# Night: the dark theme, the default on the dashboard, the banner and the
# installers.
NIGHT = {
    "bg": "#0B0E14",
    "surface": "#141A26",
    "raised": "#1C2333",
    "fg": "#ECE8E1",
    "fg2": "#9AA3B5",
    "line": "#2A3244",
    "seal": "#FF7A5C",
    "lamp": "#FFB547",
}

# How the seal is coloured. Stable stamps ink on paper; on a night surface
# (the dark lockup, the banner, the installers) it is warm white with the same
# vermillion; the nightly build stamps that on night with the wax drop lit in
# lamp amber, so the two icons tell apart in a dock at a glance.
STABLE = {"fill": PAPER["bg"], "ink": PAPER["fg"], "bar": PAPER["seal"], "drop": PAPER["seal"]}
ON_NIGHT = {"fill": NIGHT["bg"], "ink": NIGHT["fg"], "bar": NIGHT["seal"], "drop": NIGHT["seal"]}
NIGHTLY = {
    "fill": NIGHT["surface"],
    "ink": NIGHT["fg"],
    "bar": NIGHT["seal"],
    "drop": NIGHT["lamp"],
}

# The seal on a 64-unit grid. Every coordinate sits on the 0.5-unit grid so the
# mark rasterises cleanly at 16, 24, 32, 48, 64, 128 and 256 px.
RIM_R, RIM_STROKE = 28.0, 2.5
RULE_R, RULE_STROKE = 24.0, 0.75
HEAD = (32.0, 25.0, 6.0)
SHAFT = (29.0, 28.0, 6.0, 18.0)
BAR_YS, BAR_H = (33.0, 37.5, 42.0), 2.5
# Bars extend four units past the shaft on each side.
BAR_X0, BAR_X1 = 25.0, 39.0
DROP = (44.0, 18.0, 3.0, 3.0)
CENTER = 32.0
# The rim's outer edge, which is the mark's silhouette.
SEAL_R = RIM_R + RIM_STROKE / 2
SEAL_EDGE = CENTER - SEAL_R
SEAL_SIZE = 2 * SEAL_R

# Sizes, in rendered seal pixels, below which the geometry simplifies: the
# inner rule is dropped first, then the whole mark switches to the 16-unit
# favicon variant (heavier rim, two bars, no wax drop).
RULE_MIN_PX = 64
FAVICON_MAX_PX = 24


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _rect(x: float, y: float, w: float, h: float, fill: str) -> str:
    return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="{fill}"/>'


def _circle(cx: float, cy: float, r: float, fill: str) -> str:
    return f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="{fill}"/>'


def _ring(cx: float, cy: float, r: float, stroke: str, width: float) -> str:
    return (
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="none" stroke="{stroke}"'
        f' stroke-width="{_n(width)}"/>'
    )


def _shaft_with_slots(
    x: float, y: float, w: float, h: float, bars: tuple[float, ...], bar_h: float, fill: str
) -> str:
    """The keyhole shaft as the segments between the bars, so each bar is an
    open slot rather than paint in a surface colour."""
    edges = [y, *(v for b in bars for v in (b, b + bar_h)), y + h]
    d = "".join(
        f"M{_n(x)} {_n(top)}h{_n(w)}v{_n(bottom - top)}h-{_n(w)}z"
        for top, bottom in zip(edges[::2], edges[1::2])
        if bottom > top
    )
    return f'<path d="{d}" fill="{fill}"/>'


def seal(
    ink: str,
    bar: str,
    drop: str | None = None,
    rule: bool = True,
    fill: str | None = None,
    shadow: bool = False,
) -> str:
    """The Ward Seal on the 64-unit grid.

    *fill* paints the disc the seal is stamped on; without it the mark is
    transparent everywhere but its ink. *drop* is the wax drop's colour, and
    ``None`` leaves the drop out. *shadow* wraps the disc in the app-icon
    drop shadow (the ``drop`` filter must be in the document's defs).
    """
    parts = []
    if fill is not None:
        # With a disc the rim is two discs rather than a stroke: the outer one
        # is the mark's silhouette and takes the shadow, so the edge antialiases
        # once instead of twice.
        outer = _circle(CENTER, CENTER, SEAL_R, ink)
        parts.append(f'<g filter="url(#drop)">{outer}</g>' if shadow else outer)
        parts.append(_circle(CENTER, CENTER, RIM_R - RIM_STROKE / 2, fill))
    else:
        parts.append(_ring(CENTER, CENTER, RIM_R, ink, RIM_STROKE))
    if rule:
        parts.append(_ring(CENTER, CENTER, RULE_R, ink, RULE_STROKE))
    parts.append(_circle(*HEAD, ink))
    parts.append(_shaft_with_slots(*SHAFT, BAR_YS, BAR_H, ink))
    sx, sw = SHAFT[0], SHAFT[2]
    for y in BAR_YS:
        parts.append(_rect(BAR_X0, y, sx - BAR_X0, BAR_H, bar))
        parts.append(_rect(sx + sw, y, BAR_X1 - sx - sw, BAR_H, bar))
    if drop is not None:
        parts.append(_rect(*DROP, drop))
    return "".join(parts)


# The favicon variant on a 16-unit grid: rim r=7 at a 1.5 stroke, no inner
# rule, a 3x5 shaft, two 1-unit bars seven wide, no wax drop.
FAV_RIM_R, FAV_RIM_STROKE = 7.0, 1.5
FAV_HEAD = (8.0, 6.0, 1.5)
FAV_SHAFT = (6.5, 7.0, 3.0, 5.0)
FAV_BAR_YS, FAV_BAR_H = (8.0, 10.0), 1.0
FAV_BAR_X0, FAV_BAR_X1 = 4.5, 11.5
FAV_CENTER = 8.0


def favicon_seal(ink: str, bar: str, fill: str | None = None, shadow: bool = False) -> str:
    """The favicon variant, scaled onto the 64-unit grid with the same outer
    extent as the full seal, so it composes and places like it."""
    parts = []
    r_out = FAV_RIM_R + FAV_RIM_STROKE / 2
    k = SEAL_SIZE / (2 * r_out)
    t = SEAL_EDGE - (FAV_CENTER - r_out) * k
    if fill is not None:
        outer = _circle(FAV_CENTER, FAV_CENTER, r_out, ink)
        parts.append(f'<g filter="url(#drop)">{outer}</g>' if shadow else outer)
        parts.append(_circle(FAV_CENTER, FAV_CENTER, FAV_RIM_R - FAV_RIM_STROKE / 2, fill))
    else:
        parts.append(_ring(FAV_CENTER, FAV_CENTER, FAV_RIM_R, ink, FAV_RIM_STROKE))
    parts.append(_circle(*FAV_HEAD, ink))
    parts.append(_shaft_with_slots(*FAV_SHAFT, FAV_BAR_YS, FAV_BAR_H, ink))
    sx, sw = FAV_SHAFT[0], FAV_SHAFT[2]
    for y in FAV_BAR_YS:
        parts.append(_rect(FAV_BAR_X0, y, sx - FAV_BAR_X0, FAV_BAR_H, bar))
        parts.append(_rect(sx + sw, y, FAV_BAR_X1 - sx - sw, FAV_BAR_H, bar))
    return f'<g transform="translate({t:.3f} {t:.3f}) scale({k:.5f})">{"".join(parts)}</g>'


def seal_for(
    px: float, theme: dict[str, str], transparent: bool = False, shadow: bool = False
) -> str:
    """The seal geometry appropriate to a mark rendered *px* pixels across."""
    fill = None if transparent else theme["fill"]
    if px <= FAVICON_MAX_PX:
        return favicon_seal(theme["ink"], theme["bar"], fill, shadow)
    return seal(theme["ink"], theme["bar"], theme["drop"], px >= RULE_MIN_PX, fill, shadow)


def svg(view_box: str, body: str, label: str = PRODUCT) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" role="img"'
        f' aria-label="{label}"><title>{label}</title>{body}</svg>\n'
    )


def mark(theme: dict[str, str] = STABLE, px: float = 512) -> str:
    """The full-colour seal on its disc: PWA icons, ``/logo.png``, the Windows
    icon and the small Linux icons."""
    return svg("0 0 64 64", seal_for(px, theme))


SHADOW_FILTER = (
    '<filter id="drop" x="-15%" y="-15%" width="130%" height="135%">'
    '<feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#000" flood-opacity="0.3"/>'
    "</filter>"
)


def app_icon(theme: dict[str, str] = STABLE, px: float = 1024) -> str:
    """The 1024px desktop icon: the seal filling the platform's 824px icon
    body, with the depth macOS expects under it."""
    body_origin, body_size = 100, 824
    k = body_size / SEAL_SIZE
    offset = body_origin - SEAL_EDGE * k
    return svg(
        "0 0 1024 1024",
        f"<defs>{SHADOW_FILTER}</defs>"
        f'<g transform="translate({offset:.3f} {offset:.3f}) scale({k:.5f})">'
        f"{seal_for(px * body_size / 1024, theme, shadow=True)}</g>",
    )


SEAL_VIEW_BOX = f"{_n(SEAL_EDGE)} {_n(SEAL_EDGE)} {_n(SEAL_SIZE)} {_n(SEAL_SIZE)}"


def tray_template() -> str:
    """macOS template image: the favicon seal in black on transparent, cropped
    to the rim so it fills the menu-bar slot. The OS recolours it for light
    and dark menu bars."""
    return svg(SEAL_VIEW_BOX, favicon_seal("#000", "#000"))


def glyph(color: str, rule: bool = True) -> str:
    """The mono seal (variant b): everything in one colour, bars cut out,
    cropped to the rim."""
    return svg(SEAL_VIEW_BOX, seal(color, color, color, rule))


# --- type ---------------------------------------------------------------

FRAUNCES = FONTS / "fraunces" / "fraunces-latin-full-normal.woff2"
PLEX_SANS = FONTS / "ibm-plex-sans" / "ibm-plex-sans-latin-wght-normal.woff2"

FACES: dict[str, tuple[Path, dict[str, float]]] = {
    "wordmark": (FRAUNCES, {"wght": 600, "opsz": 144, "SOFT": 0, "WONK": 0}),
    "ui": (PLEX_SANS, {"wght": 500}),
    "body": (PLEX_SANS, {"wght": 400}),
}
WORDMARK_TRACKING = -0.015

# The squared ear of the wordmark's ``g``, in Fraunces font units at the
# wordmark instance. Fraunces draws a double-storey g with a ball-terminal
# ear; the brand squares that terminal so it echoes the ward bars. The
# polygon keeps the stem's hairline weight and the glyph's original extent,
# so spacing is unchanged. It is only applied when the ear contour is where
# this instance of the font puts it (see ``_square_ear``).
G_EAR_BOUNDS_MIN = (600.0, 800.0)
G_EAR_FLAG = ((626, 850), (662, 843), (719, 925), (992, 925), (992, 1000), (730, 1000))

_FONT_CACHE: dict[str, TTFont] = {}


def _face(name: str) -> TTFont:
    if name not in _FONT_CACHE:
        path, axes = FACES[name]
        _FONT_CACHE[name] = instancer.instantiateVariableFont(TTFont(path), axes)
    return _FONT_CACHE[name]


def _required_alternates(font: TTFont) -> dict[str, str]:
    """Single substitutions the font's ``rvrn`` feature applies at this
    instance. A shaper applies them for the browser; an outline pass has to
    apply them itself or it draws the default glyph (Fraunces swaps its ``n``)."""
    if "GSUB" not in font:
        return {}
    table = font["GSUB"].table
    indices = {
        i
        for record in table.FeatureList.FeatureRecord
        if record.FeatureTag == "rvrn"
        for i in record.Feature.LookupListIndex
    }
    mapping: dict[str, str] = {}
    for i in sorted(indices):
        for subtable in table.LookupList.Lookup[i].SubTable:
            if subtable.LookupType == 7:
                subtable = subtable.ExtSubTable
            if subtable.LookupType == 1:
                mapping.update(subtable.mapping)
    return mapping


def _kern_subtables(font: TTFont) -> list:
    if "GPOS" not in font:
        return []
    table = font["GPOS"].table
    indices = {
        i
        for record in table.FeatureList.FeatureRecord
        if record.FeatureTag == "kern"
        for i in record.Feature.LookupListIndex
    }
    found = []
    for i in sorted(indices):
        for subtable in table.LookupList.Lookup[i].SubTable:
            if subtable.LookupType == 9:
                subtable = subtable.ExtSubTable
            if subtable.LookupType == 2:
                found.append(subtable)
    return found


def _kern(subtables: list, left: str, right: str) -> float:
    """Pair-adjustment kerning in font units, from the first subtable that
    covers the pair."""
    for subtable in subtables:
        if left not in subtable.Coverage.glyphs:
            continue
        if subtable.Format == 1:
            pair_set = subtable.PairSet[subtable.Coverage.glyphs.index(left)]
            for record in pair_set.PairValueRecord:
                if record.SecondGlyph == right:
                    return getattr(record.Value1, "XAdvance", 0) or 0
        elif subtable.Format == 2:
            c1 = subtable.ClassDef1.classDefs.get(left, 0)
            c2 = subtable.ClassDef2.classDefs.get(right, 0)
            value = subtable.Class1Record[c1].Class2Record[c2].Value1
            return getattr(value, "XAdvance", 0) or 0
    return 0


def _contours(recording: list) -> list[list]:
    contours: list[list] = []
    for op, args in recording:
        if op == "moveTo":
            contours.append([])
        contours[-1].append((op, args))
    return contours


def _signed_area(contour: list) -> float:
    points = [p for _, args in contour for p in args]
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))


def _square_ear(recording: list) -> list:
    """Replace the ball-terminal ear of the ``g`` with ``G_EAR_FLAG``. The ear
    is the contour holding the glyph's topmost point; the flag is wound the
    same way so the nonzero fill unions it with the bowl."""
    contours = _contours(recording)
    ear = max(contours, key=lambda c: max(p[1] for _, args in c for p in args))
    xmin = min(p[0] for _, args in ear for p in args)
    ymin = min(p[1] for _, args in ear for p in args)
    if xmin < G_EAR_BOUNDS_MIN[0] or ymin < G_EAR_BOUNDS_MIN[1]:
        print("warning: the g ear is not where the wordmark face puts it; left as drawn")
        return recording
    flag = list(G_EAR_FLAG)
    if _signed_area(ear) < 0:
        flag.reverse()
    squared = [("moveTo", (flag[0],))] + [("lineTo", (p,)) for p in flag[1:]]
    squared.append(("closePath", ()))
    out: list = []
    for contour in contours:
        out.extend(squared if contour is ear else contour)
    return out


@dataclass
class Outline:
    """Outlined text in font units, y up, origin at the first glyph's origin."""

    d: str
    advance: float
    upem: int
    xmin: float
    ymin: float
    xmax: float
    ymax: float


def outline(text: str, face: str = "ui", tracking: float = 0.0) -> Outline:
    """Outline *text* in *face*, applying the face's required alternates and
    pair kerning. *tracking* is in em."""
    font = _face(face)
    glyph_set, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    alternates = _required_alternates(font)
    kerning = _kern_subtables(font)
    upem = font["head"].unitsPerEm
    track = tracking * upem
    x, parts, previous = 0.0, [], None
    bounds = BoundsPen(glyph_set)
    for ch in text:
        name = alternates.get(cmap[ord(ch)], cmap[ord(ch)])
        if previous is not None:
            x += _kern(kerning, previous, name)
        recorder = RecordingPen()
        glyph_set[name].draw(recorder)
        drawing = recorder.value
        if face == "wordmark" and ch == "g":
            drawing = _square_ear(drawing)
        pen = SVGPathPen(glyph_set, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        for target in (
            TransformPen(pen, (1, 0, 0, -1, x, 0)),
            TransformPen(bounds, (1, 0, 0, 1, x, 0)),
        ):
            for op, args in drawing:
                getattr(target, op)(*args)
        parts.append(pen.getCommands())
        x += hmtx[name][0] + track
        previous = name
    xmin, ymin, xmax, ymax = bounds.bounds or (0, 0, 0, 0)
    return Outline(" ".join(p for p in parts if p), x - track, upem, xmin, ymin, xmax, ymax)


def text(
    content: str,
    face: str,
    em: float,
    x: float,
    baseline: float,
    fill: str,
    anchor: str = "start",
    tracking: float = 0.0,
) -> str:
    """Outlined text at *em* output units per em, so no surface depends on a
    font the viewer has."""
    o = outline(content, face, tracking)
    s = em / o.upem
    if anchor == "middle":
        x -= o.advance * s / 2
    elif anchor == "end":
        x -= o.advance * s
    return (
        f'<path transform="translate({x:.2f} {baseline:.2f}) scale({s:.5f})" fill="{fill}"'
        f' d="{o.d}"/>'
    )


def wordmark_outline() -> Outline:
    return outline(WORDMARK, "wordmark", WORDMARK_TRACKING)


def wordmark(color: str = "currentColor") -> str:
    o = wordmark_outline()
    return svg(
        f"{o.xmin:.0f} {-o.ymax:.0f} {o.xmax - o.xmin:.0f} {o.ymax - o.ymin:.0f}",
        f'<path fill="{color}" d="{o.d}"/>',
        label=WORDMARK,
    )


LOCKUP_GAP_EM = 0.6


@dataclass
class Lockup:
    body: str
    right: float
    em: float
    descent: float
    text_x: float


def lockup_parts(
    height: float,
    x: float,
    baseline: float,
    ink: str,
    bar: str,
    drop: str,
    text_fill: str,
    rule: bool = True,
) -> Lockup:
    """The seal to the left of the wordmark, sized so the rim spans the
    ascender of the ``d`` and sits on the baseline, with a 0.6 em gap."""
    o = wordmark_outline()
    s = height / o.ymax
    em = s * o.upem
    k = height / SEAL_SIZE
    seal_body = seal(ink, bar, drop, rule)
    text_x = x + height + LOCKUP_GAP_EM * em
    body = (
        f'<g transform="translate({x - SEAL_EDGE * k:.3f} {baseline - height - SEAL_EDGE * k:.3f})'
        f' scale({k:.5f})">{seal_body}</g>'
        f'<path transform="translate({text_x:.2f} {baseline:.2f}) scale({s:.5f})"'
        f' fill="{text_fill}" d="{o.d}"/>'
    )
    return Lockup(body, text_x + o.advance * s, em, -o.ymin * s, text_x)


def lockup(night: bool) -> str:
    theme = ON_NIGHT if night else STABLE
    parts = lockup_parts(64, 0, 64, theme["ink"], theme["bar"], theme["drop"], theme["ink"])
    return svg(f"0 0 {parts.right:.1f} {64 + parts.descent:.1f}", parts.body)


def banner() -> str:
    """README banner: the lockup and tagline on night, with one lit window."""
    w, h = 1280, 240
    parts = lockup_parts(
        104, 96, 144, ON_NIGHT["ink"], ON_NIGHT["bar"], ON_NIGHT["drop"], NIGHT["fg"]
    )
    tagline = text(TAGLINE, "ui", 19, parts.text_x + 2, 212, NIGHT["fg2"])
    # The lit window: a lamp-lit pane at the far right, its halo a fill and
    # nowhere near the seal.
    wx, wy, ww, wh = 1124, 96, 40, 52
    window = (
        f'<circle cx="{wx + ww / 2}" cy="{wy + wh / 2}" r="110" fill="url(#halo)"/>'
        f'<rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="3" fill="{NIGHT["lamp"]}"/>'
        f'<path d="M{wx + ww / 2} {wy}v{wh}M{wx} {wy + wh / 2}h{ww}" stroke="{NIGHT["bg"]}"'
        ' stroke-width="4"/>'
    )
    return svg(
        f"0 0 {w} {h}",
        "<defs>"
        '<radialGradient id="halo">'
        f'<stop offset="0" stop-color="{NIGHT["lamp"]}" stop-opacity="0.16"/>'
        f'<stop offset="1" stop-color="{NIGHT["lamp"]}" stop-opacity="0"/>'
        "</radialGradient>"
        "</defs>"
        f'<rect width="{w}" height="{h}" fill="{NIGHT["bg"]}"/>' + window + parts.body + tagline,
        label=f"{PRODUCT}: {TAGLINE}",
    )


def _placed_seal(x: float, y: float, size: float, theme: dict[str, str]) -> str:
    """The seal with its top-left corner at (x, y), *size* across."""
    k = size / SEAL_SIZE
    return (
        f'<g transform="translate({x - SEAL_EDGE * k:.3f} {y - SEAL_EDGE * k:.3f}) scale({k:.5f})">'
        f"{seal_for(size, theme, transparent=True)}</g>"
    )


def dmg_background() -> str:
    """660x420 Finder window. The app icon sits at (170, 246), /Applications at
    (490, 246), both 96px: electron/package.json ``build.dmg.contents``."""
    w, h, y = 660, 420, 246
    return svg(
        f"0 0 {w} {h}",
        f'<rect width="{w}" height="{h}" fill="{NIGHT["bg"]}"/>'
        + text(WORDMARK, "wordmark", 64, w / 2, 88, NIGHT["fg"], "middle", WORDMARK_TRACKING)
        + text(
            f"Drag {PRODUCT} onto the Applications folder",
            "body",
            14,
            w / 2,
            126,
            NIGHT["fg2"],
            "middle",
        )
        # From the app to its destination, in lamp amber.
        + f'<path d="M238 {y}H412" fill="none" stroke="{NIGHT["lamp"]}" stroke-width="5"'
        ' stroke-linecap="round"/>'
        f'<path d="M402 {y - 12}L416 {y}L402 {y + 12}" fill="none" stroke="{NIGHT["lamp"]}"'
        ' stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
        # The three ward bars as the section divider along the foot.
        + f'<path d="M0 378H{w}" stroke="{NIGHT["line"]}" stroke-width="2"/>'
        + _rect(w / 2 - 30, 370, 60, 16, NIGHT["bg"])
        + "".join(_rect(w / 2 - 14, 372.5 + i * 4.5, 28, 2.5, NIGHT["seal"]) for i in range(3)),
    )


def installer_header() -> str:
    """150x57 NSIS header: wordmark left of the seal, on night."""
    return svg(
        "0 0 150 57",
        f'<rect width="150" height="57" fill="{NIGHT["bg"]}"/>'
        f'<path d="M0 56.5H150" stroke="{NIGHT["line"]}"/>'
        + text(WORDMARK, "wordmark", 26, 92, 35, NIGHT["fg"], "end", WORDMARK_TRACKING)
        + _placed_seal(102, 10.5, 36, ON_NIGHT),
    )


def installer_sidebar() -> str:
    """164x314 NSIS welcome/finish sidebar."""
    return svg(
        "0 0 164 314",
        f'<rect width="164" height="314" fill="{NIGHT["bg"]}"/>'
        + _placed_seal(36, 56, 92, ON_NIGHT)
        + text(WORDMARK, "wordmark", 40, 82, 196, NIGHT["fg"], "middle", WORDMARK_TRACKING)
        + _rect(58, 236.5, 48, 2.5, NIGHT["seal"])
        + text("Quick setup", "ui", 12, 82, 266, NIGHT["fg2"], "middle", 0.04),
    )


def _icns_rle(data: bytes) -> bytes:
    """Apple's ICNS channel run-length encoding: a control byte below 0x80
    copies the next n+1 bytes, one at or above 0x80 repeats the next byte
    n-0x80+3 times."""
    out, i, n = bytearray(), 0, len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 130:
            run += 1
        if run >= 3:
            out += bytes([0x80 + run - 3, data[i]])
            i += run
            continue
        literal = bytearray()
        while i < n and len(literal) < 128:
            ahead = 1
            while i + ahead < n and data[i + ahead] == data[i] and ahead < 3:
                ahead += 1
            if ahead >= 3:
                break
            literal.append(data[i])
            i += 1
        out += bytes([len(literal) - 1]) + literal
    return bytes(out)


# ICNS slot -> pixel size. ic04/ic05 (16pt and 32pt @1x) are decoded by macOS
# as raw ARGB, so they carry run-length-encoded channel planes; a PNG body
# there renders as coloured static. Every other slot carries a PNG.
ICNS_SLOTS = {
    "ic04": 16,
    "ic05": 32,
    "ic07": 128,
    "ic08": 256,
    "ic09": 512,
    "ic10": 1024,
    "ic11": 32,
    "ic12": 64,
    "ic13": 256,
    "ic14": 512,
}


def write_icns(path: Path, reps: dict[int, Path]) -> None:
    chunks = b""
    for slot, size in ICNS_SLOTS.items():
        if slot in ("ic04", "ic05"):
            pixels = Image.open(reps[size]).convert("RGBA")
            r, g, b, a = pixels.split()
            body = b"ARGB" + b"".join(_icns_rle(ch.tobytes()) for ch in (a, r, g, b))
        else:
            body = reps[size].read_bytes()
        chunks += slot.encode("ascii") + (len(body) + 8).to_bytes(4, "big") + body
    path.write_bytes(b"icns" + (len(chunks) + 8).to_bytes(4, "big") + chunks)


def write_tiff_hidpi(path: Path, one_x: Path, two_x: Path) -> None:
    """A two-representation TIFF (72 and 144 dpi), which is what Finder reads to
    draw a DMG background sharply on both standard and Retina displays."""
    base = Image.open(one_x).convert("RGBA")
    retina = Image.open(two_x).convert("RGBA")
    retina.encoderinfo = {"dpi": (144, 144)}
    base.save(path, save_all=True, append_images=[retina], dpi=(72, 72), compression="tiff_lzw")


def write_bmp24(path: Path, png: Path) -> None:
    """NSIS takes 24-bit BMPs; the art is opaque, so dropping alpha loses nothing."""
    Image.open(png).convert("RGB").save(path, format="BMP")


def write_template_png(path: Path) -> None:
    """Re-encode a tray template as pure black plus alpha, one filter-0 scanline
    per row. macOS reads only the alpha of a template image; forcing RGB to
    black means antialiased edges can never tint it, and the plain encoding is
    what electron/test/tray-template.test.js decodes without an image library."""
    import struct
    import zlib

    alpha = Image.open(path).convert("RGBA").getchannel("A")
    width, height = alpha.size
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes((0, 0, 0, alpha.getpixel((x, y))))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def rasterize(jobs: list[dict]) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(jobs, fh)
        job_file = fh.name
    try:
        subprocess.run(["node", str(BRAND / "raster.mjs"), job_file], check=True)
    finally:
        os.unlink(job_file)
    for job in jobs:
        out = Path(job["out"])
        if out.is_relative_to(ROOT):
            print(f"wrote {out.relative_to(ROOT)}")


def main() -> int:
    write(BRAND / "mark.svg", mark())
    write(BRAND / "mark-nightly.svg", mark(NIGHTLY))
    write(BRAND / "glyph.svg", glyph("currentColor"))
    write(BRAND / "wordmark.svg", wordmark())
    write(BRAND / "lockup-light.svg", lockup(night=False))
    write(BRAND / "lockup-dark.svg", lockup(night=True))
    write(BRAND / "app-icon.svg", app_icon())
    write(BRAND / "app-icon-nightly.svg", app_icon(NIGHTLY))
    write(ROOT / "assets" / "banner.svg", banner())
    # Monochrome seal for the dashboard, painted as a CSS mask over
    # currentColor by BrandGlyph (components/BrandIcon.tsx) at 24 and 40px,
    # where the inner rule would only smear.
    write(ROOT / "website" / "src" / "assets" / "junction-glyph.svg", glyph("#000", rule=False))

    electron = ROOT / "website" / "electron"
    public = ROOT / "website" / "public"
    static = ROOT / "src" / "junction" / "static"
    tmp = Path(tempfile.mkdtemp(prefix="warding-brand-"))

    jobs: list[dict] = []

    def job(svg_text: str, size: int, out: Path) -> None:
        jobs.append({"svg": svg_text, "w": size, "h": size, "out": str(out)})

    job(app_icon(), 1024, electron / "icon.png")
    job(app_icon(NIGHTLY), 1024, electron / "icon-nightly.png")
    for size in (16, 32, 48):
        job(mark(px=size), size, electron / "build" / "icons" / f"{size}x{size}.png")
    for size in (64, 128, 256, 512):
        job(app_icon(px=size), size, electron / "build" / "icons" / f"{size}x{size}.png")
    job(tray_template(), 18, electron / "trayTemplate.png")
    job(tray_template(), 36, electron / "trayTemplate@2x.png")
    job(mark(px=192), 192, public / "icon-192.png")
    job(mark(px=512), 512, public / "icon-512.png")
    job(mark(px=512), 512, static / "junction-logo.png")
    job(mark(NIGHTLY, px=512), 512, static / "junction-logo-nightly.png")
    ico_sizes = (16, 24, 32, 48, 64, 128, 256)
    for size in ico_sizes:
        job(mark(px=size), size, tmp / f"ico-{size}.png")
        job(mark(NIGHTLY, px=size), size, tmp / f"ico-nightly-{size}.png")
    icns_sizes = sorted(set(ICNS_SLOTS.values()))
    for size in icns_sizes:
        job(app_icon(px=size), size, tmp / f"icns-{size}.png")
        job(app_icon(NIGHTLY, px=size), size, tmp / f"icns-nightly-{size}.png")

    installer = ROOT / "packaging" / "installer-assets"
    art = {
        "dmg-background": (dmg_background(), 660, 420),
        "windows-installer-header": (installer_header(), 150, 57),
        "windows-installer-sidebar": (installer_sidebar(), 164, 314),
    }
    for name, (content, w, h) in art.items():
        write(installer / f"{name}.svg", '<?xml version="1.0" encoding="UTF-8"?>\n' + content)
        jobs.append({"svg": content, "w": w, "h": h, "out": str(tmp / f"{name}.png")})
    # The Retina representation is the same SVG rasterized at twice the size.
    dmg_text, dmg_w, dmg_h = art["dmg-background"]
    jobs.append(
        {"svg": dmg_text, "w": dmg_w * 2, "h": dmg_h * 2, "out": str(tmp / "dmg-background@2x.png")}
    )
    rasterize(jobs)

    for stem, prefix in (("icon", "ico"), ("icon-nightly", "ico-nightly")):
        frames = [Image.open(tmp / f"{prefix}-{size}.png") for size in ico_sizes]
        frames[-1].save(
            electron / f"{stem}.ico",
            format="ICO",
            sizes=[(s, s) for s in ico_sizes],
            append_images=frames[:-1],
        )
        print(f"wrote {(electron / f'{stem}.ico').relative_to(ROOT)}")
    write_icns(electron / "icon.icns", {s: tmp / f"icns-{s}.png" for s in icns_sizes})
    write_icns(
        electron / "icon-nightly.icns", {s: tmp / f"icns-nightly-{s}.png" for s in icns_sizes}
    )
    print("wrote website/electron/icon.icns, website/electron/icon-nightly.icns")
    for name in ("trayTemplate.png", "trayTemplate@2x.png"):
        write_template_png(electron / name)
    write_tiff_hidpi(
        installer / "dmg-background.tiff",
        tmp / "dmg-background.png",
        tmp / "dmg-background@2x.png",
    )
    for name in ("windows-installer-header", "windows-installer-sidebar"):
        write_bmp24(installer / f"{name}.bmp", tmp / f"{name}.png")
    print("wrote packaging/installer-assets rasters (.tiff, .bmp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
