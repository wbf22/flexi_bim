"""Turn tagged 3D geometry into 2D drawing primitives.

Pure Python and ``bpy``-free, so the geometry maths is directly testable.  The
viewer/loader in :mod:`flexi_bim.drawings.views` feeds it ``Source`` objects that
carry world-space vertices/polygons/edges; this module projects them.
"""

from __future__ import annotations

from . import primitives as P

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

#: axis -> (u basis, v basis), chosen so plan (Z, looking down) has +X right
#: and +Y up.
_UV = {
    "X": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "Y": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "Z": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}

_TOL = 1e-6


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------

def _project(point, axis, direction):
    u_axis, v_axis = _UV[axis]
    u = point[0] * u_axis[0] + point[1] * u_axis[1] + point[2] * u_axis[2]
    v = point[0] * v_axis[0] + point[1] * v_axis[1] + point[2] * v_axis[2]
    if direction == "+":
        # Looking the other way flips the drawing horizontally (front vs back,
        # floor plan vs reflected ceiling plan).
        u = -u
    return (round(u, 4), round(v, 4))


def _depth(point, axis):
    return point[_AXIS_INDEX[axis]]


def depth_span(vertices, axis):
    """``(min, max)`` of the vertices along ``axis``."""
    depths = [_depth(v, axis) for v in vertices]
    return (min(depths), max(depths)) if depths else (0.0, 0.0)


def anchor_point(vertices, axis, direction):
    """Projected centroid of ``vertices`` - where a leader arrow points."""
    if not vertices:
        return (0.0, 0.0)
    n = float(len(vertices))
    centroid = (
        sum(v[0] for v in vertices) / n,
        sum(v[1] for v in vertices) / n,
        sum(v[2] for v in vertices) / n,
    )
    return _project(centroid, axis, direction)


def _within(span, lo, hi, contained):
    if lo is None and hi is None:
        return True
    lo = float("-inf") if lo is None else lo
    hi = float("inf") if hi is None else hi
    dmin, dmax = span
    if contained:
        return dmin >= lo and dmax <= hi
    return dmax >= lo and dmin <= hi


# ---------------------------------------------------------------------------
# What to cut / project
# ---------------------------------------------------------------------------

def _triangles(polygon):
    for i in range(1, len(polygon) - 1):
        yield (polygon[0], polygon[i], polygon[i + 1])


def _unique(points):
    out = []
    for p in points:
        if not any(
            abs(p[0] - q[0]) < _TOL and abs(p[1] - q[1]) < _TOL and abs(p[2] - q[2]) < _TOL
            for q in out
        ):
            out.append(p)
    return out


def cut_segments(vertices, polygons, axis, level, direction):
    """Cross-section of ``polygons`` at ``level`` -> 2D ``(a, b)`` pairs."""
    idx = _AXIS_INDEX[axis]
    result = []
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        for tri in _triangles(polygon):
            hits = []
            for k in range(3):
                p0 = vertices[tri[k]]
                p1 = vertices[tri[(k + 1) % 3]]
                d0 = p0[idx] - level
                d1 = p1[idx] - level
                if d0 == 0.0:
                    hits.append(p0)
                if (d0 < 0.0) != (d1 < 0.0):
                    t = d0 / (d0 - d1)
                    hits.append(tuple(p0[j] + t * (p1[j] - p0[j]) for j in range(3)))
            hits = _unique(hits)
            if len(hits) >= 2:
                a = _project(hits[0], axis, direction)
                b = _project(hits[1], axis, direction)
                if a != b:
                    result.append((a, b))
    return result


def _quantize(point):
    """Endpoint key for joining segments (matches :func:`_project` rounding)."""
    return (round(point[0], 4), round(point[1], 4))


def chain_loops(segments):
    """Join 2D segments into closed loops; open chains are dropped.

    Simple greedy walk - good for the watertight solids a section view usually
    cuts.  Branches or non-manifold geometry may yield approximate loops.
    """
    edges = {}
    adjacency = {}
    seen = set()
    for a, b in segments:
        ka, kb = _quantize(a), _quantize(b)
        if ka == kb:
            continue
        key = frozenset((ka, kb))
        if key in seen:
            continue
        seen.add(key)
        index = len(edges)
        edges[index] = (ka, kb)
        adjacency.setdefault(ka, []).append(index)
        adjacency.setdefault(kb, []).append(index)

    used = set()
    loops = []
    for first in range(len(edges)):
        if first in used:
            continue
        loop = _walk_loop(first, edges, adjacency, used)
        if loop is not None and len(loop) >= 3:
            loops.append(tuple(loop))
    return loops


def _walk_loop(first, edges, adjacency, used):
    start, current = edges[first]
    used.add(first)
    loop = [start, current]
    while current != start:
        candidates = [e for e in adjacency.get(current, ()) if e not in used]
        if not candidates:
            return None
        nxt = candidates[0]
        used.add(nxt)
        a, b = edges[nxt]
        current = b if a == current else a
        loop.append(current)
    return loop[:-1]


def cut_loops(vertices, polygons, axis, level, direction):
    """Closed cross-section outlines at ``level`` -> list of 2D point loops."""
    return chain_loops(cut_segments(vertices, polygons, axis, level, direction))


def project_segments(vertices, edges, axis, direction):
    """Every edge projected onto the view plane -> 2D ``(a, b)`` pairs."""
    result = []
    for edge in edges:
        if len(edge) < 2:
            continue
        a = _project(vertices[edge[0]], axis, direction)
        b = _project(vertices[edge[1]], axis, direction)
        if a != b:
            result.append((a, b))
    return result


def dedupe(segments):
    """Drop duplicate segments (same layer + endpoints)."""
    seen = set()
    out = []
    for segment in segments:
        key = segment.key()
        if key in seen:
            continue
        seen.add(key)
        out.append(segment)
    return out


# ---------------------------------------------------------------------------
# The view
# ---------------------------------------------------------------------------

def extract_view(view, sources) -> P.Drawing:
    """Extract segments and note-leaders for ``view`` from ``sources``."""
    lo, hi = view.range if view.range else (None, None)
    segments = []
    leaders = []
    regions = []
    noted = set()

    for source in sources:
        span = depth_span(source.vertices, view.axis)
        if not _within(span, lo, hi, view.contained):
            continue

        primary = source.primary
        layer = primary.layer if primary is not None else P.DEFAULT_LAYER
        color = primary.color if primary is not None else P.DEFAULT_COLOR
        tag_name = primary.name if primary is not None else ""

        if view.mode == P.CUT:
            level = view.cut_level
            if level is None:
                level = (span[0] + span[1]) / 2.0
            pairs = cut_segments(source.vertices, source.polygons, view.axis, level, view.direction)
            weight, kind = P.WEIGHT_CUT, P.CUT
            if primary is not None and primary.fill != P.FILL_NONE:
                for loop in chain_loops(pairs):
                    regions.append(
                        P.Region(points=loop, layer=layer, color=color,
                                 fill=primary.fill, spacing=primary.fill_spacing,
                                 angle=primary.fill_angle, tag=tag_name)
                    )
        else:
            pairs = project_segments(source.vertices, source.edges, view.axis, view.direction)
            weight, kind = P.WEIGHT_PROJECT, P.PROJECT

        for a, b in pairs:
            segments.append(
                P.Segment(a=a, b=b, layer=layer, weight=weight, kind=kind,
                          color=color, tag=tag_name)
            )

        if view.notes and pairs:
            anchor = anchor_point(source.vertices, view.axis, view.direction)
            for info in source.tags:
                key = info.name.strip().lower()
                if not info.note or key in noted:
                    continue
                noted.add(key)
                leaders.append(
                    P.Leader(target=anchor, text=info.note, layer=P.ANNOTATION_LAYER,
                             color=info.color)
                )

    return P.Drawing(segments=dedupe(segments), leaders=leaders, regions=regions)
