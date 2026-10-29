"""Property groups backing the drawing views (stored on the scene).

Layout::

    scene.flexibim_drawings           -> FlexiBIMDrawings
        .views[]                      -> FlexiBIMView
            .include_tags[]           -> FlexiBIMViewTag (names from the registry)
        .output_dir / .active_view_index

Views are just saved :class:`~flexi_bim.drawings.views.ViewSpec`s, so the UI can
create, edit and generate them without any of the extraction logic changing.
"""

# NOTE: no `from __future__ import annotations` here (see tagging/props.py).

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

_AXIS_ITEMS = [
    ("X", "X", "YZ plane - side view", 0),
    ("Y", "Y", "XZ plane - front/back view", 1),
    ("Z", "Z", "XY plane - plan", 2),
]
#: The two look directions that make sense for each plane normal.
_DIRECTIONS = {
    "X": [
        ("-", "Looking left (X-)", "Left elevation, looking toward -X", 0),
        ("+", "Looking right (X+)", "Right elevation, looking toward +X", 1),
    ],
    "Y": [
        ("-", "Looking forward (Y-)", "Front elevation, looking toward -Y", 0),
        ("+", "Looking backward (Y+)", "Back elevation, looking toward +Y", 1),
    ],
    "Z": [
        ("-", "Looking down (Z-)", "Plan, looking down at the XY plane", 0),
        ("+", "Looking up (Z+)", "Reflected ceiling plan, looking up", 1),
    ],
}
_direction_cache = {}


def _direction_items(self, context):
    """Only offer the look directions that apply to the view's plane."""
    items = _DIRECTIONS.get(getattr(self, "axis", "Z"), _DIRECTIONS["Z"])
    _direction_cache["items"] = items
    return items
_MODE_ITEMS = [
    ("CUT", "Cut", "Section through the model at the cut level", 0),
    ("PROJECT", "Project", "Look through the band, no cutting", 1),
]
_TAG_MATCH_ITEMS = [
    ("ANY", "Any", "Objects carrying any listed tag", 0),
    ("ALL", "All", "Objects carrying every listed tag", 1),
]


def _select_measurement_objects(self, context):
    """Select the two objects the active measurement refers to."""
    scene = getattr(context, "scene", None)
    view_layer = getattr(context, "view_layer", None)
    measurement = getattr(self, "active_measurement", None)
    if scene is None or view_layer is None or measurement is None:
        return
    for obj in view_layer.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass
    active = None
    for name in (measurement.object_a, measurement.object_b):
        obj = scene.objects.get(name) if name else None
        if obj is None:
            continue
        try:
            obj.select_set(True)
        except RuntimeError:
            continue
        active = obj
    if active is not None:
        view_layer.objects.active = active


class FlexiBIMViewTag(PropertyGroup):
    """A tag name included in a view's filter."""

    name: StringProperty(
        name="Tag",
        description="Tag from the registry to include in this view's filter",
        default="",
    )


class FlexiBIMMeasurement(PropertyGroup):
    """A gap measurement between two objects, drawn on this view."""

    object_a: StringProperty(
        name="Object A",
        description="First object of the measured pair (by name)",
        default="",
    )
    object_b: StringProperty(
        name="Object B",
        description="Second object of the measured pair (by name)",
        default="",
    )
    offset: FloatProperty(
        name="Offset",
        description="Distance from the geometry to the dimension line, in project units",
        default=0.3,
        unit="LENGTH",
    )
    decimals: IntProperty(
        name="Decimals",
        description="Decimal places shown on the dimension label",
        default=2,
        min=0,
        max=4,
    )
    include: BoolProperty(
        name="Show",
        description="Draw this measurement on the generated view",
        default=True,
    )


class FlexiBIMView(PropertyGroup):
    """A saved drawing view."""

    name: StringProperty(
        name="Name",
        description="Shown in the view list and used for the generated file name",
        default="New View",
    )
    axis: EnumProperty(
        name="Axis",
        description="Plane the view looks along: Z is a plan, X/Y are elevations",
        items=_AXIS_ITEMS,
        default="Z",
    )
    direction: EnumProperty(
        name="View",
        description="Which side of the plane to look from",
        items=_direction_items,
    )
    mode: EnumProperty(
        name="Mode",
        description="Cut a section through the model, or project the whole band",
        items=_MODE_ITEMS,
        default="CUT",
    )
    cut_level: FloatProperty(
        name="Cut Level",
        description="Height/position to cut at, in project units",
        default=0.0,
        unit="LENGTH",
    )

    use_range: BoolProperty(
        name="Limit Range",
        description="Only include objects inside a band along the axis",
        default=False,
    )
    range_min: FloatProperty(
        name="From",
        description="Start of the visible band along the view axis, in project units",
        default=0.0,
        unit="LENGTH",
    )
    range_max: FloatProperty(
        name="To",
        description="End of the visible band along the view axis, in project units",
        default=3.0,
        unit="LENGTH",
    )
    contained: BoolProperty(
        name="Fully Inside",
        description="Require the whole object to sit inside the range",
        default=False,
    )

    include_tags: CollectionProperty(type=FlexiBIMViewTag)
    active_tag_index: IntProperty(name="Active Tag", default=0, min=0)
    categories: StringProperty(
        name="Categories",
        description="Optional comma-separated category ids (e.g. WALL, DOOR)",
        default="",
    )
    tag_match: EnumProperty(
        name="Match",
        description="Include objects carrying any of the listed tags, or all of them",
        items=_TAG_MATCH_ITEMS,
        default="ANY",
    )

    notes: BoolProperty(
        name="Tag Notes",
        description="Add tag descriptions as leader annotations",
        default=True,
    )
    scale: FloatProperty(
        name="Scale (1:N)",
        description="Drawing scale denominator, e.g. 50 for 1:50",
        default=50.0,
        min=1.0,
    )

    measurements: CollectionProperty(type=FlexiBIMMeasurement)
    active_measurement_index: IntProperty(
        name="Active Measurement",
        default=0,
        min=0,
        update=_select_measurement_objects,
    )

    @property
    def active_measurement(self):
        if 0 <= self.active_measurement_index < len(self.measurements):
            return self.measurements[self.active_measurement_index]
        return None


class FlexiBIMDrawings(PropertyGroup):
    """Scene-level drawing data (``scene.flexibim_drawings``)."""

    views: CollectionProperty(type=FlexiBIMView)
    active_view_index: IntProperty(name="Active View", default=0, min=0)
    output_dir: StringProperty(
        name="Output Folder",
        description="Default folder offered when exporting SVG files (empty = folder of the .blend)",
        subtype="DIR_PATH",
        default="",
    )

    @property
    def active_view(self):
        if 0 <= self.active_view_index < len(self.views):
            return self.views[self.active_view_index]
        return None


classes = (
    FlexiBIMViewTag,
    FlexiBIMMeasurement,
    FlexiBIMView,
    FlexiBIMDrawings,
)


def register_pointers():
    bpy.types.Scene.flexibim_drawings = PointerProperty(
        type=FlexiBIMDrawings,
        name="FlexiBIM Drawings",
        description="FlexiBIM drawing views and output settings",
    )


def unregister_pointers():
    if hasattr(bpy.types.Scene, "flexibim_drawings"):
        try:
            del bpy.types.Scene.flexibim_drawings
        except (AttributeError, RuntimeError):
            pass
