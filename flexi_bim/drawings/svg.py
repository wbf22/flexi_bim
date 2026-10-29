"""Render drawing primitives to SVG.

Segments come out of :mod:`flexi_bim.drawings.extract` in model units; here they
are scaled to paper millimetres, grouped into one ``<g>`` per CAD layer, and
stroked with the tag's colour.  Leader annotations get a 45-degree elbow, a
short shelf and an arrowhead pointing back at the element.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from . import primitives as P

_MONO = "#000000"
_ARROW_MM = 2.5


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

    factor = units_per_model / max(float(scale_denominator), 1e-9)
    points = [p for s in segments for p in (s.a, s.b)]
    points += [leader.target for leader in leaders]
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


def write(path, drawing, **kwargs):
    """Write ``drawing`` to ``path`` as SVG and return the path."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(to_svg(drawing, **kwargs))
    return path
