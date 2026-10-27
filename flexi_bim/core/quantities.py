"""Geometric quantity take-off helpers.

Pure maths on plain sequences so the measurement rules can be tested without
Blender.  Callers pass **world-space** vertex coordinates; see
``flexi_bim.tagging.measure`` for the ``bpy`` glue that evaluates modifiers and
applies ``matrix_world``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

Vector3 = "tuple[float, float, float]"


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a):
    return _dot(a, a) ** 0.5


def polygon_normal(points):
    """Newell's method: area vector of a (possibly non-planar) polygon.

    Its magnitude is twice the polygon area, its direction the normal.
    """
    nx = ny = nz = 0.0
    count = len(points)
    if count < 3:
        return (0.0, 0.0, 0.0)
    for i in range(count):
        cur = points[i]
        nxt = points[(i + 1) % count]
        nx += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        ny += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        nz += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
    return (nx * 0.5, ny * 0.5, nz * 0.5)


def polygon_area(points) -> float:
    return _length(polygon_normal(points))


def surface_area(vertices, polygons) -> float:
    """Total area of every face."""
    total = 0.0
    for poly in polygons:
        total += polygon_area([vertices[i] for i in poly])
    return total


def footprint_area(vertices, polygons) -> float:
    """Plan (top-down) area.

    Sums the XY projection of upward-facing faces, which gives the expected
    answer both for a closed solid (its silhouette, when convex) and for a
    single flat slab modelled as one face.  Falls back to the bounding box
    footprint when nothing faces up (e.g. a downward-facing plane).
    """
    total = 0.0
    for poly in polygons:
        normal = polygon_normal([vertices[i] for i in poly])
        if normal[2] > 0.0:
            total += normal[2]
    if total > 1e-12:
        return total
    lo, hi = bounding_box(vertices)
    return (hi[0] - lo[0]) * (hi[1] - lo[1])


def volume(vertices, polygons) -> float:
    """Enclosed volume via the divergence theorem (absolute value).

    Non-manifold or open meshes have no well defined volume; the result is
    whatever the signed tetrahedra sum to, which is why callers should offer
    a manual override.
    """
    total = 0.0
    for poly in polygons:
        if len(poly) < 3:
            continue
        a = vertices[poly[0]]
        for i in range(1, len(poly) - 1):
            b = vertices[poly[i]]
            c = vertices[poly[i + 1]]
            # Signed volume of the tetrahedron (world origin, a, b, c).
            total += _dot(a, _cross(b, c)) / 6.0
    return abs(total)


def bounding_box(vertices):
    """Axis-aligned ``(min, max)`` corners of the supplied points."""
    if not vertices:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def bounding_box_size(vertices):
    lo, hi = bounding_box(vertices)
    return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


def longest_dimension(vertices) -> float:
    """Longest world-axis extent - the practical "run" of a wall or beam."""
    size = bounding_box_size(vertices)
    return max(size) if size else 0.0


def plan_run(vertices) -> float:
    """Longest horizontal extent, ignoring height."""
    size = bounding_box_size(vertices)
    return max(size[0], size[1])


def wall_area(vertices) -> float:
    """Face ("elevation") area of a wall-like object.

    Longest horizontal extent multiplied by height, i.e. what a $/ft2 wall
    rate actually refers to - as opposed to :func:`surface_area`, which counts
    both faces plus the edges of the mesh.
    """
    size = bounding_box_size(vertices)
    return max(size[0], size[1]) * size[2]


def total_edge_length(vertices, edges) -> float:
    total = 0.0
    for a, b in edges:
        total += _length(_sub(vertices[a], vertices[b]))
    return total


@dataclass(frozen=True)
class Quantities:
    """Every measurement FlexiBIM knows how to take off an object."""

    count: float = 1.0
    length: float = 0.0
    plan_run: float = 0.0
    surface_area: float = 0.0
    wall_area: float = 0.0
    footprint_area: float = 0.0
    volume: float = 0.0
    edge_length: float = 0.0
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0

    def as_dict(self):
        return asdict(self)


def measure(vertices, polygons=(), edges=()) -> Quantities:
    """Take off every supported quantity from world-space geometry."""
    vertices = list(vertices)
    polygons = [tuple(p) for p in polygons]
    size = bounding_box_size(vertices)
    return Quantities(
        count=1.0,
        length=max(size) if vertices else 0.0,
        plan_run=max(size[0], size[1]) if vertices else 0.0,
        surface_area=surface_area(vertices, polygons),
        wall_area=max(size[0], size[1]) * size[2] if vertices else 0.0,
        footprint_area=footprint_area(vertices, polygons) if vertices else 0.0,
        volume=volume(vertices, polygons),
        edge_length=total_edge_length(vertices, edges),
        size_x=size[0],
        size_y=size[1],
        size_z=size[2],
    )


EMPTY = Quantities(count=1.0)
