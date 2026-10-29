"""Linear dimensions between objects, measured in the view plane.

A measurement ties two objects together and reports the **gap** between them -
the distance between their nearest projected points (nearest face, not nearest
corner).  The plane comes from the view, so a Z view yields the XY distance, a
Y view the XZ distance, and so on.

The maths here is pure Python (segments live in view-plane coordinates); the
``bpy`` glue that resolves objects to segments lives in :mod:`views`.
"""

from __future__ import annotations

from . import primitives as P

_TOL = 1e-9


def _sub(p, q):
    return (p[0] - q[0], p[1] - q[1])


def _dot(p, q):
    return p[0] * q[0] + p[1] * q[1]


def _dist(p, q):
    d = _sub(p, q)
    return (d[0] * d[0] + d[1] * d[1]) ** 0.5


def _clamp01(t):
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def _closest_on_segment(point, a, b):
    """Closest point on segment ``a->b`` to ``point``."""
    ab = _sub(b, a)
    length_sq = _dot(ab, ab)
    if length_sq <= _TOL:
        return a
    t = _clamp01(_dot(_sub(point, a), ab) / length_sq)
    return (a[0] + t * ab[0], a[1] + t * ab[1])


def segment_distance(a1, a2, b1, b2):
    """Closest points between two 2D segments -> ``(pa, pb, distance)``.

    Handles the intersecting case (distance 0) as well as the four
    endpoint-to-segment candidates.
    """
    r = _sub(a2, a1)
    s = _sub(b2, b1)
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) > _TOL:
        qp = _sub(b1, a1)
        t = (qp[0] * s[1] - qp[1] * s[0]) / denom
        u = (qp[0] * r[1] - qp[1] * r[0]) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            hit = (a1[0] + t * r[0], a1[1] + t * r[1])
            return (hit, hit, 0.0)

    best = None
    for point, (p, q) in ((a1, (b1, b2)), (a2, (b1, b2)),
                          (b1, (a1, a2)), (b2, (a1, a2))):
        closest = _closest_on_segment(point, p, q)
        distance = _dist(point, closest)
        if best is None or distance < best[2]:
            best = (point, closest, distance)
    return best


def nearest_pair(segments_a, segments_b):
    """Nearest points between two sets of 2D segments.

    Returns ``(point_a, point_b, distance)`` or ``None`` when either side has no
    geometry.
    """
    if not segments_a or not segments_b:
        return None
    best = None
    for a1, a2 in segments_a:
        for b1, b2 in segments_b:
            pa, pb, distance = segment_distance(a1, a2, b1, b2)
            if best is None or distance < best[2]:
                best = (pa, pb, distance)
                if distance <= _TOL:
                    return best
    return best


def format_length(value, decimals=2):
    """Human length for a dimension label: metres when >= 1 m, else millimetres."""
    value = abs(float(value))
    if value >= 1.0:
        return f"{value:.{max(0, int(decimals))}f} m"
    return f"{value * 1000.0:.0f} mm"


def dimension_for(pa, pb, offset=0.3, decimals=2, color=P.DEFAULT_COLOR):
    """Build a :class:`~flexi_bim.drawings.primitives.Dimension`, or ``None``.

    Zero-length gaps (touching objects) yield ``None`` - there is nothing to
    draw between two coincident points.
    """
    distance = _dist(pa, pb)
    if distance <= 1e-6:
        return None
    return P.Dimension(
        a=(round(pa[0], 4), round(pa[1], 4)),
        b=(round(pb[0], 4), round(pb[1], 4)),
        text=format_length(distance, decimals),
        offset=offset,
        color=color,
    )
