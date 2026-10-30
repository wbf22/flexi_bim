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
_SCALE_BAR_H_MM = 2.0
_SCALE_BAR_SPACE_MM = 18.0
_SCALE_FONT_MM = 2.5


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
    scale_bar=None,
    scale_text=None,
):
    segments = list(drawing.segments)
    leaders = list(drawing.leaders)
    dimensions = list(drawing.dimensions)
    regions = list(drawing.regions)

    factor = units_per_model / max(float(scale_denominator), 1e-9)
    points = [p for s in segments for p in (s.a, s.b)]
    points += [leader.target for leader in leaders]
    points += [p for d in dimensions for p in (d.a, d.b)]
    points += [p for region in regions for p in region.points]
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

    if scale_bar is not None or scale_text:
        height += _SCALE_BAR_SPACE_MM
    if scale_bar is not None:
        width = max(width, float(scale_bar[0]) + 2 * margin_mm)

    def place(point):
        x = (point[0] - minx) * factor + margin_mm
        y = (maxy - point[1]) * factor + margin_mm
        return x, y

    def stroke_for(color):
        if colorful:
            return _hex(color)
        return stroke_color or _MONO

    defs, region_pattern = _region_patterns(regions, stroke_for)

    body = []

    fill_parts = []
    for region in regions:
        pid = region_pattern(region)
        if pid is None:
            continue
        pts = [place(p) for p in region.points]
        if len(pts) < 3:
            continue
        path = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in pts) + " Z"
        fill_parts.append(
            f'    <path d="{path}" fill="url(#{pid})" stroke="none" />'
        )
    if fill_parts:
        body.append('  <g id="A-FILL">')
        body.extend(fill_parts)
        body.append("  </g>")

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

    if scale_bar is not None or scale_text:
        body.append('  <g id="A-SCALE">')
        if scale_bar is not None:
            body.extend(
                _scale_bar_svg(scale_bar[0], scale_bar[1], margin_mm, height)
            )
        if scale_text:
            body.append(_scale_text_svg(scale_text, width, height, margin_mm))
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
    if defs:
        header.append("  <defs>")
        header.extend(defs)
        header.append("  </defs>")

    return "\n".join(header + body + ["</svg>", ""])


def _region_patterns(regions, stroke_for):
    """Build the ``<pattern>`` defs; return ``(defs, id_lookup)``.

    Patterns are keyed by (fill, colour, spacing, angle) so identical hatches
    share a single ``<defs>`` entry.
    """
    ids = {}
    defs = []
    for region in regions:
        key = _pattern_key(region, stroke_for)
        if key is None or key in ids:
            continue
        pid = f"hatch{len(ids)}"
        ids[key] = pid
        defs.extend(_pattern_svg(pid, region, stroke_for(region.color)))

    def lookup(region):
        key = _pattern_key(region, stroke_for)
        return None if key is None else ids.get(key)

    return defs, lookup


def _pattern_key(region, stroke_for):
    if region.fill == P.FILL_NONE or str(region.fill).upper() == "NONE":
        return None
    return (
        region.fill,
        stroke_for(region.color),
        round(float(region.spacing), 3),
        round(float(region.angle), 3),
    )


def _pattern_svg(pid, region, color):
    """One ``<pattern>`` holding the repeating fill content."""
    size = max(float(region.spacing), 0.2)
    angle = float(region.angle)
    transform = f' patternTransform="rotate({_fmt(angle)})"' if angle else ""
    parts = [
        f'    <pattern id="{pid}" patternUnits="userSpaceOnUse" '
        f'width="{_fmt(size)}" height="{_fmt(size)}"{transform}>'
    ]
    if region.fill == P.FILL_SOLID:
        parts.append(
            f'      <rect width="{_fmt(size)}" height="{_fmt(size)}" fill="{color}" />'
        )
    elif region.fill == P.FILL_DOTS:
        parts.append(
            f'      <circle cx="{_fmt(size / 2)}" cy="{_fmt(size / 2)}" '
            f'r="{_fmt(max(0.2, size * 0.1))}" fill="{color}" />'
        )
    else:
        stroke = f'stroke="{color}" stroke-width="{_fmt(P.HATCH_WEIGHT)}"'
        parts.append(f'      <line x1="0" y1="0" x2="{_fmt(size)}" y2="0" {stroke} />')
        parts.append(
            f'      <line x1="0" y1="{_fmt(size)}" x2="{_fmt(size)}" '
            f'y2="{_fmt(size)}" {stroke} />'
        )
        if region.fill == P.FILL_CROSS:
            parts.append(f'      <line x1="0" y1="0" x2="0" y2="{_fmt(size)}" {stroke} />')
            parts.append(
                f'      <line x1="{_fmt(size)}" y1="0" x2="{_fmt(size)}" '
                f'y2="{_fmt(size)}" {stroke} />'
            )
    parts.append("    </pattern>")
    return parts


def _scale_bar_svg(total_mm, labels, x_mm, canvas_h_mm):
    """Alternating black/white bar with a real-world label under each tick."""
    total_mm = max(float(total_mm), 1e-6)
    count = max(len(labels) - 1, 1)
    seg = total_mm / count
    bar_y = canvas_h_mm - _SCALE_BAR_SPACE_MM + 4.0
    label_y = bar_y + _SCALE_BAR_H_MM + _SCALE_FONT_MM

    parts = []
    for i in range(count):
        x = x_mm + i * seg
        fill = _MONO if i % 2 == 0 else "#ffffff"
        parts.append(
            f'    <rect x="{_fmt(x)}" y="{_fmt(bar_y)}" width="{_fmt(seg)}" '
            f'height="{_fmt(_SCALE_BAR_H_MM)}" fill="{fill}" stroke="{_MONO}" '
            f'stroke-width="0.15" />'
        )
    char_w = _SCALE_FONT_MM * 0.6
    last_right = None
    for i, label in enumerate(labels):
        x = x_mm + i * seg
        w = len(str(label)) * char_w
        left = x - w / 2.0
        if last_right is not None and left < last_right + char_w / 2.0 \
                and i != count:
            continue
        last_right = x + w / 2.0
        anchor = "middle"
        parts.append(
            f'    <text x="{_fmt(x)}" y="{_fmt(label_y)}" '
            f'font-size="{_fmt(_SCALE_FONT_MM)}" font-family="sans-serif" '
            f'fill="{_MONO}" text-anchor="{anchor}">{escape(str(label))}</text>'
        )
    return parts


def _scale_text_svg(text, canvas_w_mm, canvas_h_mm, margin_mm):
    # Own row below the bar labels so the two never overlap.
    y = (canvas_h_mm - _SCALE_BAR_SPACE_MM + 4.0 + _SCALE_BAR_H_MM
         + _SCALE_FONT_MM * 2 + 1.5)
    return (
        f'    <text x="{_fmt(margin_mm)}" y="{_fmt(y)}" '
        f'font-size="{_fmt(_SCALE_FONT_MM)}" font-family="sans-serif" '
        f'fill="{_MONO}" text-anchor="start">{escape(str(text))}</text>'
    )


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
