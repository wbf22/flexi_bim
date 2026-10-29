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
    ("X", "X", "Look along the X axis (side view)", 0),
    ("Y", "Y", "Look along the Y axis (front/back view)", 1),
    ("Z", "Z", "Look along the Z axis (plan)", 2),
]
_PROJECTION_ITEMS = [
    ("-", "Down / Front", "Look along the negative axis", 0),
    ("+", "Up / Back", "Look along the positive axis", 1),
]
_MODE_ITEMS = [
    ("CUT", "Cut", "Section through the model at the cut level", 0),
    ("PROJECT", "Project", "Look through the band, no cutting", 1),
]
_TAG_MATCH_ITEMS = [
    ("ANY", "Any", "Objects carrying any listed tag", 0),
    ("ALL", "All", "Objects carrying every listed tag", 1),
]


class FlexiBIMViewTag(PropertyGroup):
    """A tag name included in a view's filter."""

    name: StringProperty(name="Tag", default="")


class FlexiBIMView(PropertyGroup):
    """A saved drawing view."""

    name: StringProperty(name="Name", default="New View")
    axis: EnumProperty(name="Axis", items=_AXIS_ITEMS, default="Z")
    projection: EnumProperty(name="Direction", items=_PROJECTION_ITEMS, default="-")
    mode: EnumProperty(name="Mode", items=_MODE_ITEMS, default="CUT")
    cut_level: FloatProperty(
        name="Cut Level",
        description="Height/position to cut at (model units)",
        default=0.0,
    )

    use_range: BoolProperty(
        name="Limit Range",
        description="Only include objects inside a band along the axis",
        default=False,
    )
    range_min: FloatProperty(name="From", default=0.0)
    range_max: FloatProperty(name="To", default=3.0)
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
    tag_match: EnumProperty(name="Match", items=_TAG_MATCH_ITEMS, default="ANY")

    notes: BoolProperty(
        name="Tag Notes",
        description="Add tag descriptions as leader annotations",
        default=True,
    )
    scale: FloatProperty(
        name="Scale (1:N)",
        description="Drawing scale denominator",
        default=50.0,
        min=1.0,
    )


class FlexiBIMDrawings(PropertyGroup):
    """Scene-level drawing data (``scene.flexibim_drawings``)."""

    views: CollectionProperty(type=FlexiBIMView)
    active_view_index: IntProperty(name="Active View", default=0, min=0)
    output_dir: StringProperty(
        name="Output Folder",
        description="Where Generate writes SVG files (empty = folder of the .blend)",
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
