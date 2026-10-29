"""View definitions and the ``bpy`` loader that feeds the extractor.

A :class:`ViewSpec` says *what* to draw (which tags), *along which axis*, and
*over what range* - e.g. "electrical fixtures on floor 2" is axis Z, projected,
range = floor 2's band, tags = Electrical/Lighting.  ``build_sources`` gathers
the matching tagged geometry; :func:`render` runs the extractor over it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core import units
from ..tagging import api, measure
from . import dimensions, extract
from . import primitives as P

AXES = ("X", "Y", "Z")
#: Look direction relative to the plane normal: "-" looks against the axis,
#: "+" looks along it (the mirror image).
DIRECTIONS = ("-", "+")
MODES = (P.CUT, P.PROJECT)


def _is_hidden(obj):
    """True when ``obj`` is hidden in the viewport by any means.

    Covers the object's own visibility flags and, when a view layer is
    available, collection/``hide_set`` state via :meth:`bpy.types.Object.visible_get`.
    """
    if getattr(obj, "hide_viewport", False):
        return True
    try:
        if obj.hide_get():
            return True
    except (AttributeError, RuntimeError):
        pass
    visible_get = getattr(obj, "visible_get", None)
    if visible_get is not None:
        try:
            if not visible_get():
                return True
        except (AttributeError, RuntimeError):
            pass
    return False


@dataclass
class ViewSpec:
    """A single drawing view.

    ``axis`` selects the **plane** (Z -> XY cross section, Y -> XZ, X -> YZ) and
    ``direction`` picks which side you look from along that normal.
    """

    axis: str = "Z"
    direction: str = "-"
    mode: str = P.CUT
    #: Where to bisect (CUT only).  ``None`` uses the middle of the range.
    cut_level: float = None
    #: Visible band along the axis as ``(min, max)``; ``None`` means everything.
    range: tuple = None
    #: Only include objects carrying one (ANY) or all (ALL) of these tag names.
    include_tags: tuple = ()
    categories: tuple = ()
    tag_match: str = "ANY"
    #: Require the object's whole extent to sit inside ``range``.
    contained: bool = False
    #: Emit tag notes as leader annotations.
    notes: bool = True
    #: Drawing scale denominator (1:50 -> 50).
    scale: float = 50.0
    #: Linear measurements between pairs of objects.
    measurements: tuple = ()


@dataclass
class MeasurementSpec:
    """A saved gap measurement between two objects."""

    object_a: str
    object_b: str
    offset: float = 0.3
    decimals: int = 2
    include: bool = True


@dataclass
class TagInfo:
    """A snapshot of a tag as needed for drawing."""

    name: str
    note: str = ""
    category: str = "NONE"
    layer: str = P.DEFAULT_LAYER
    color: tuple = P.DEFAULT_COLOR


@dataclass
class Source:
    """One object's geometry plus its tags, ready to extract."""

    name: str
    vertices: list
    polygons: list
    edges: list
    tags: tuple = ()

    @property
    def primary(self):
        return self.tags[0] if self.tags else None


def spec_from_view(view) -> ViewSpec:
    """Build a :class:`ViewSpec` from a stored ``FlexiBIMView`` property group."""
    return ViewSpec(
        axis=view.axis,
        direction=view.direction,
        mode=view.mode,
        cut_level=view.cut_level,
        range=(view.range_min, view.range_max) if view.use_range else None,
        include_tags=tuple(t.name for t in view.include_tags if t.name.strip()),
        categories=tuple(
            c.strip() for c in (view.categories or "").split(",") if c.strip()
        ),
        tag_match=view.tag_match,
        contained=view.contained,
        notes=view.notes,
        scale=view.scale,
        measurements=tuple(
            MeasurementSpec(
                object_a=m.object_a,
                object_b=m.object_b,
                offset=m.offset,
                decimals=m.decimals,
                include=m.include,
            )
            for m in getattr(view, "measurements", ())
        ),
    )


def _tag_color(tag):
    try:
        color = tuple(float(c) for c in tag.color)
    except (AttributeError, TypeError, ValueError):
        return P.DEFAULT_COLOR
    return color if len(color) == 3 else P.DEFAULT_COLOR


def build_sources(scene, view, context=None):
    """Collect geometry for the objects ``view`` selects."""
    depsgraph = measure.depsgraph_for(context)
    wanted = {name.strip().lower() for name in view.include_tags}
    categories = set(view.categories)

    sources = []
    for obj in api.all_objects(scene):
        if getattr(obj, "type", None) not in measure.GEOMETRY_TYPES:
            continue
        if _is_hidden(obj):
            continue

        definitions = api.object_tags(obj, scene)
        names = {d.name.strip().lower() for d in definitions}
        if wanted:
            if view.tag_match == "ALL":
                if not wanted <= names:
                    continue
            elif not (wanted & names):
                continue
        if categories and not any(d.category in categories for d in definitions):
            continue

        geometry = measure.world_geometry(obj, depsgraph)
        if geometry is None:
            continue
        vertices, polygons, edges = geometry
        if not vertices:
            continue

        tags = tuple(
            TagInfo(
                name=d.name,
                note=getattr(d, "description", "") or "",
                category=d.category,
                layer=P.layer_for(d.category),
                color=_tag_color(d),
            )
            for d in definitions
        )
        sources.append(
            Source(name=obj.name, vertices=vertices, polygons=polygons,
                   edges=edges, tags=tags)
        )
    return sources


def _projected_segments(geometry, axis, direction):
    vertices, polygons, edges = geometry
    segments = extract.project_segments(vertices, edges, axis, direction)
    if not segments:
        for polygon in polygons:
            for i in range(len(polygon)):
                a = extract._project(vertices[polygon[i]], axis, direction)
                b = extract._project(vertices[polygon[(i + 1) % len(polygon)]], axis, direction)
                if a != b:
                    segments.append((a, b))
    return segments


def build_measurements(scene, view, context=None):
    """Resolve the view's measurements into :class:`Dimension` primitives."""
    specs = getattr(view, "measurements", ())
    if not specs:
        return []
    depsgraph = measure.depsgraph_for(context)
    ctx = api.unit_context(scene)
    cache = {}

    def segments_for(name):
        if name not in cache:
            obj = scene.objects.get(name)
            geometry = (
                measure.world_geometry(obj, depsgraph)
                if obj is not None and not _is_hidden(obj)
                else None
            )
            cache[name] = (
                _projected_segments(geometry, view.axis, view.direction) if geometry else None
            )
        return cache[name]

    def length_formatter(decimals):
        def fmt(value):
            project = units.convert(value, units.DIMENSION_LENGTH, ctx)
            return units.format_quantity(
                project, units.DIMENSION_LENGTH, ctx, precision=decimals
            )
        return fmt

    result = []
    for measurement in specs:
        if not getattr(measurement, "include", True):
            continue
        segments_a = segments_for(measurement.object_a)
        segments_b = segments_for(measurement.object_b)
        pair = dimensions.nearest_pair(segments_a, segments_b)
        if pair is None:
            continue
        result.extend(dimensions.dimensions_for(
            pair[0], pair[1],
            offset=getattr(measurement, "offset", 0.3),
            decimals=getattr(measurement, "decimals", 2),
            formatter=length_formatter(getattr(measurement, "decimals", 2)),
        ))
    return result


# ---------------------------------------------------------------------------
# Paper scale
# ---------------------------------------------------------------------------

def paper_scale(scene) -> float:
    """Paper millimetres per model (Blender) unit at 1:1.

    Comes straight from ``scene.unit_settings.scale_length`` (metres per Blender
    unit), so a scene modelled in millimetres prints at the right size.
    """
    return api.unit_context(scene).scale_length * 1000.0


def _nice_floor(value):
    """Largest 1/2/5 x 10^n not above ``value`` (``value`` > 0)."""
    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    for step in (5.0, 2.0, 1.0):
        if step * base <= value * (1 + 1e-9):
            return step * base
    return base


def scale_bar(scene, view, total_mm=50.0, divisions=None):
    """A graphic scale bar for ``view`` as ``(total_mm, labels)``.

    The bar represents a round real-world length (1, 2, 5 x 10^n project
    units) no longer than ``total_mm`` on paper, so labels stay short and
    evenly spaced.  Only the last label carries the unit suffix.
    """
    ctx = api.unit_context(scene)
    units_per_model = paper_scale(scene)
    project_per_model = ctx.factor(units.DIMENSION_LENGTH)
    denominator = max(float(view.scale), 1e-9)
    mm_per_project = units_per_model / (project_per_model * denominator)
    if mm_per_project <= 0.0:
        return total_mm, ["0"]
    total_value = _nice_floor(total_mm / mm_per_project)
    if divisions is None:
        mantissa = total_value / 10.0 ** math.floor(math.log10(total_value))
        divisions = 5 if round(mantissa) == 5 else 4
    suffix = ctx.suffix(units.DIMENSION_LENGTH)
    labels = []
    for i in range(divisions + 1):
        value = total_value * i / divisions
        text = f"{value:,.3f}".rstrip("0").rstrip(".")
        labels.append(text)
    labels[-1] = f"{labels[-1]} {suffix}"
    return total_value * mm_per_project, labels


def render(scene, view, context=None) -> P.Drawing:
    """Extract a :class:`Drawing` for ``view`` from ``scene``."""
    drawing = extract.extract_view(view, build_sources(scene, view, context))
    drawing.dimensions = build_measurements(scene, view, context)
    return drawing
