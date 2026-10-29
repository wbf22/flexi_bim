"""Render drawing primitives to SVG.

Segments come out of :mod:`flexi_bim.drawings.extract` in model units; here they
are scaled to paper millimetres, grouped into one ``<g>`` per CAD layer, and
stroked with the tag's colour.  Leader annotations get a 45-degree elbow, a
short shelf and an arrowhead pointing back at the element.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from . import primitives as P

_MONO = "#000000"
_ARROW_MM = 2.5
_TICK_MM = 2.0
_EXTENSION_MM = 1.5


def _hex(color):
    try:
        r, g, b = (max(0.0, min(1.0, float(c))) for c in color)
    except (TypeError, ValueError):
        return _MONO
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def _fmt(value):
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def to_svg(
    drawing,
    *,
    units_per_model=1000.0,
    scale_denominator=50.0,
    margin_mm=10.0,
    colorful=True,
    stroke_color=None,
    background=None,
    title=None,
    note_font_mm=2.5,
    note_space_mm=45.0,
    note_gap_mm=6.0,
    shelf_mm=5.0,
):
    segments = list(drawing.segments)
    leaders = list(drawing.leaders)
    dimensions = list(drawing.dimensions)

    factor = units_per_model / max(float(scale_denominator), 1e-9)
    points = [p for s in segments for p in (s.a, s.b)]
    points += [leader.target for leader in leaders]
    points += [p for d in dimensions for p in (d.a, d.b)]
    if points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    else:
        minx = maxx = miny = maxy = 0.0

    width = (maxx - minx) * factor + 2 * margin_mm
    height = (maxy - miny) * factor + 2 * margin_mm
    if leaders:
        width += note_space_mm

    def place(point):
        x = (point[0] - minx) * factor + margin_mm
        y = (maxy - point[1]) * factor + margin_mm
        return x, y

    def stroke_for(color):
        if colorful:
            return _hex(color)
        return stroke_color or _MONO

    body = []

    layers = {}
    for segment in segments:
        layers.setdefault(segment.layer, []).append(segment)
    for layer in sorted(layers):
        body.append(f'  <g id="{escape(layer)}">')
        for segment in layers[layer]:
            x1, y1 = place(segment.a)
            x2, y2 = place(segment.b)
            body.append(
                f'    <line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" '
                f'y2="{_fmt(y2)}" stroke="{stroke_for(segment.color)}" '
                f'stroke-width="{_fmt(segment.weight)}" stroke-linecap="round" />'
            )
        body.append("  </g>")

    if leaders:
        body.append('  <g id="A-ANNO">')
        for leader in leaders:
            body.extend(_leader_svg(leader, place, note_font_mm, note_gap_mm,
                                    shelf_mm, stroke_for))
        body.append("  </g>")

    if dimensions:
        body.append('  <g id="A-DIMS">')
        for dim in dimensions:
            body.extend(_dimension_svg(dim, place, factor, note_font_mm, stroke_for))
        body.append("  </g>")

    header = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_fmt(width)}mm" height="{_fmt(height)}mm" '
        f'viewBox="0 0 {_fmt(width)} {_fmt(height)}">',
    ]
    if title:
        header.append(f"  <title>{escape(title)}</title>")
    if background:
        header.append(
            f'  <rect width="{_fmt(width)}" height="{_fmt(height)}" '
            f'fill="{escape(background)}" />'
        )

    return "\n".join(header + body + ["</svg>", ""])


def _leader_svg(leader, place, font_mm, gap_mm, shelf_mm, stroke_for):
    color = stroke_for(leader.color)
    tx, ty = place(leader.target)
    ex, ey = tx + gap_mm, ty - gap_mm
    sx, sy = ex + shelf_mm, ey

    # Arrowhead at the target, pointing along elbow -> target.
    dx, dy = tx - ex, ty - ey
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    bx, by = tx - ux * _ARROW_MM, ty - uy * _ARROW_MM
    px, py = -uy * (_ARROW_MM * 0.4), ux * (_ARROW_MM * 0.4)

    return [
        f'    <polyline points="{_fmt(tx)},{_fmt(ty)} {_fmt(ex)},{_fmt(ey)} '
        f'{_fmt(sx)},{_fmt(sy)}" fill="none" stroke="{color}" '
        f'stroke-width="{_fmt(P.WEIGHT_LEADER)}" />',
        f'    <polygon points="{_fmt(tx)},{_fmt(ty)} {_fmt(bx + px)},{_fmt(by + py)} '
        f'{_fmt(bx - px)},{_fmt(by - py)}" fill="{color}" />',
        f'    <text x="{_fmt(sx + 1.5)}" y="{_fmt(sy)}" font-size="{_fmt(font_mm)}" '
        f'font-family="sans-serif" fill="{color}" dominant-baseline="central">'
        f"{escape(leader.text)}</text>",
    ]


def _dimension_svg(dim, place, factor, font_mm, stroke_for):
    color = stroke_for(dim.color)
    ax, ay = place(dim.a)
    bx, by = place(dim.b)
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return []
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux

    off = dim.offset * factor
    a2x, a2y = ax + nx * off, ay + ny * off
    b2x, b2y = bx + nx * off, by + ny * off

    # Extension lines stop a touch past the dimension line.
    ext_x, ext_y = nx * _EXTENSION_MM, ny * _EXTENSION_MM
    ex1x, ex1y = a2x + ext_x, a2y + ext_y
    ex2x, ex2y = b2x + ext_x, b2y + ext_y

    # 45-degree architectural ticks at each end (in view-plane space).
    c = 0.70710678
    tx, ty = ux * c - uy * c, ux * c + uy * c
    half = _TICK_MM / 2.0

    stroke = (
        f'stroke="{color}" stroke-width="{_fmt(P.WEIGHT_DIMENSION)}" '
        f'stroke-linecap="round"'
    )
    lines = [
        f'    <line x1="{_fmt(ax)}" y1="{_fmt(ay)}" x2="{_fmt(ex1x)}" y2="{_fmt(ex1y)}" {stroke} />',
        f'    <line x1="{_fmt(bx)}" y1="{_fmt(by)}" x2="{_fmt(ex2x)}" y2="{_fmt(ex2y)}" {stroke} />',
        f'    <line x1="{_fmt(a2x)}" y1="{_fmt(a2y)}" x2="{_fmt(b2x)}" y2="{_fmt(b2y)}" {stroke} />',
        f'    <line x1="{_fmt(a2x - tx * half)}" y1="{_fmt(a2y - ty * half)}" '
        f'x2="{_fmt(a2x + tx * half)}" y2="{_fmt(a2y + ty * half)}" {stroke} />',
        f'    <line x1="{_fmt(b2x - tx * half)}" y1="{_fmt(b2y - ty * half)}" '
        f'x2="{_fmt(b2x + tx * half)}" y2="{_fmt(b2y + ty * half)}" {stroke} />',
    ]

    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90.0:
        angle -= 180.0
    elif angle < -90.0:
        angle += 180.0
    mx, my = (a2x + b2x) / 2.0, (a2y + b2y) / 2.0

    lines.append(
        f'    <text x="{_fmt(mx)}" y="{_fmt(my - 1.5)}" font-size="{_fmt(font_mm)}" '
        f'font-family="sans-serif" fill="{color}" text-anchor="middle" '
        f'dominant-baseline="central" transform="rotate({_fmt(angle)} {_fmt(mx)} {_fmt(my)})">'
        f"{escape(dim.text)}</text>"
    )
    return lines


def write(path, drawing, **kwargs):
    """Write ``drawing`` to ``path`` as SVG and return the path."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(to_svg(drawing, **kwargs))
    return path
