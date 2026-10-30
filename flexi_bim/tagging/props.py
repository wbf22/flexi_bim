"""Property groups backing the tagging system.

Every tag is a single, project-wide definition: objects **reference** tags by
name rather than carrying their own copy.  Editing a tag therefore updates every
object using it, and there is no local/library split to reason about.

Everything lives in ``PropertyGroup``s attached to IDs, which Blender stores as
ID custom properties in the .blend.  That satisfies the project's "metadata in
custom properties" rule: the data rides on the *object*, not the mesh, so it
survives remeshing, re-topology and geometry replacement.

Layout::

    scene.flexibim                -> FlexiBIMProject
        .tags[]                   -> FlexiBIMTag          (the tag registry)
            .cost                 -> FlexiBIMCost
            .properties[]         -> FlexiBIMProperty     (key/value pairs)
        .currency / .unit_basis   -> project-wide costing settings
    object.flexibim               -> FlexiBIMObject
        .tags[]                   -> FlexiBIMAppliedTag   (references by name)
"""

# NOTE: no `from __future__ import annotations` here. Blender's RNA registration
# reads the real property objects out of ``__annotations__``; PEP 563 would turn
# them into plain strings and registration would fail.

import contextlib

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import constants as C


#: Depth counter for :func:`suspend_rename_propagation`.
_rename_suspended = 0


@contextlib.contextmanager
def suspend_rename_propagation():
    """Assign tag names without re-pointing the objects that reference them.

    The rename callback exists so that renaming a tag in the UI keeps every
    object attached to it.  Code that *builds* tags (duplicate, import, create)
    assigns names for entirely different reasons and must not drag other
    objects' references along with it.
    """
    global _rename_suspended
    _rename_suspended += 1
    try:
        yield
    finally:
        _rename_suspended -= 1


def _redraw(self, context):
    """Nudge the UI (and the cost cache) after a value changes."""
    from . import measure

    measure.invalidate_costs()


# ---------------------------------------------------------------------------
# Custom properties
# ---------------------------------------------------------------------------

class FlexiBIMProperty(PropertyGroup):
    """A single user-defined key/value pair on a tag."""

    key: StringProperty(
        name="Key",
        description="Property name, e.g. 'Fire Rating' or 'Manufacturer'",
        default="",
    )
    value: StringProperty(
        name="Value",
        description="Property value",
        default="",
    )
    value_type: EnumProperty(
        name="Type",
        description="How the value should be interpreted in schedules and exports",
        items=C.PROP_TYPE_ITEMS,
        default=C.PROP_TEXT,
    )


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

class FlexiBIMCost(PropertyGroup):
    """How a tag turns into money."""

    mode: EnumProperty(
        name="Cost Mode",
        description="How this tag is priced",
        items=C.COST_MODE_ITEMS,
        default=C.COST_MODE_NONE,
        update=_redraw,
    )
    rate: FloatProperty(
        name="Rate",
        description="Flat amount, or amount per measured unit",
        default=0.0,
        min=0.0,
        precision=2,
        step=100,
        update=_redraw,
    )
    measurement: EnumProperty(
        name="Measured By",
        description="Which quantity the rate is multiplied by",
        items=C.MEASURE_ITEMS,
        default=C.MEASURE_AREA,
        update=_redraw,
    )
    quantity_source: EnumProperty(
        name="Quantity",
        description="Measure the geometry automatically, or enter the quantity by hand",
        items=C.QUANTITY_SOURCE_ITEMS,
        default=C.QUANTITY_AUTO,
        update=_redraw,
    )
    manual_quantity: FloatProperty(
        name="Manual Quantity",
        description="Quantity in project units, used when Quantity is set to Manual",
        default=0.0,
        min=0.0,
        precision=3,
        update=_redraw,
    )
    waste_percent: FloatProperty(
        name="Waste",
        description="Percentage added to the measured quantity for waste/overage",
        default=0.0,
        min=-100.0,
        soft_max=100.0,
        subtype="PERCENTAGE",
        update=_redraw,
    )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class FlexiBIMTag(PropertyGroup):
    """A tag definition in the project registry (``scene.flexibim.tags``)."""

    def _rename(self, context):
        """Keep object references pointing at this tag when it is renamed."""
        from . import api

        new_name = (self.name or "").strip()
        old_name = self.previous_name
        if _rename_suspended:
            self.previous_name = new_name
            return
        if new_name and old_name and new_name != old_name:
            api.rename_tag_references(
                getattr(context, "scene", None), old_name, new_name
            )
        self.previous_name = new_name
        _redraw(self, context)

    name: StringProperty(
        name="Name",
        description="Tag name - renaming updates every object using this tag",
        default="Tag",
        update=_rename,
    )
    #: Shadow copy used to detect renames (hidden from the UI).
    previous_name: StringProperty(default="", options={"HIDDEN"})
    category: EnumProperty(
        name="Category",
        description="Optional semantic type, used by drawings and schedules",
        items=C.CATEGORY_ITEMS,
        default="NONE",
        update=_redraw,
    )
    description: StringProperty(
        name="Description",
        description="Free text note about this tag",
        default="",
    )
    color: FloatVectorProperty(
        name="Color",
        description="Identifying color for viewport/legend display",
        subtype="COLOR",
        size=3,
        default=(0.35, 0.55, 0.85),
        min=0.0,
        max=1.0,
    )
    fill: EnumProperty(
        name="Fill",
        description="Repeating hatch pattern drawn on this tag's cut faces in section views",
        items=C.FILL_ITEMS,
        default=C.FILL_NONE,
        update=_redraw,
    )
    fill_spacing: FloatProperty(
        name="Fill Spacing",
        description="Size of one hatch tile on paper, in millimetres",
        default=3.0,
        min=0.2,
        soft_max=50.0,
        update=_redraw,
    )
    fill_angle: FloatProperty(
        name="Fill Angle",
        description="Rotation of the hatch lines, in degrees",
        default=45.0,
        soft_min=0.0,
        soft_max=360.0,
        update=_redraw,
    )
    cost: PointerProperty(type=FlexiBIMCost)
    properties: CollectionProperty(type=FlexiBIMProperty)
    active_property_index: IntProperty(name="Active Property", default=0, min=0)


class FlexiBIMAppliedTag(PropertyGroup):
    """An object's reference to a project tag, stored by name."""

    name: StringProperty(
        name="Tag",
        description="Name of the project tag this object uses",
        default="",
    )


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

class FlexiBIMObject(PropertyGroup):
    """Per-object FlexiBIM data (``object.flexibim``)."""

    tags: CollectionProperty(type=FlexiBIMAppliedTag)
    active_tag_index: IntProperty(name="Active Tag", default=0, min=0)

    @property
    def active_tag(self):
        if 0 <= self.active_tag_index < len(self.tags):
            return self.tags[self.active_tag_index]
        return None


class FlexiBIMProject(PropertyGroup):
    """Scene-level FlexiBIM data (``scene.flexibim``)."""

    tags: CollectionProperty(type=FlexiBIMTag)
    active_tag_index: IntProperty(name="Active Tag", default=0, min=0)

    currency: StringProperty(
        name="Currency",
        description="Symbol or code used when displaying costs",
        default="$",
        update=_redraw,
    )
    currency_decimals: IntProperty(
        name="Decimals",
        description="Decimal places shown for currency amounts",
        default=2,
        min=0,
        max=6,
        update=_redraw,
    )
    unit_basis: EnumProperty(
        name="Quantity Units",
        description=(
            "Units that cost rates are expressed in. Pinning to metric or imperial keeps "
            "rates meaningful even if the scene's display units change"
        ),
        items=C.UNIT_BASIS_ITEMS,
        default="PROJECT",
        update=_redraw,
    )

    # Cost summary display options
    summary_selected_only: BoolProperty(
        name="Selected Only",
        description="Summarise only the selected objects instead of the whole scene",
        default=False,
        update=_redraw,
    )
    summary_show_objects: BoolProperty(
        name="Per Object",
        description="Break the summary down per object instead of per tag",
        default=False,
    )

    @property
    def active_tag(self):
        if 0 <= self.active_tag_index < len(self.tags):
            return self.tags[self.active_tag_index]
        return None


classes = (
    FlexiBIMProperty,
    FlexiBIMCost,
    FlexiBIMTag,
    FlexiBIMAppliedTag,
    FlexiBIMObject,
    FlexiBIMProject,
)


def register_pointers():
    bpy.types.Object.flexibim = PointerProperty(
        type=FlexiBIMObject,
        name="FlexiBIM",
        description="FlexiBIM tags and metadata for this object",
    )
    bpy.types.Scene.flexibim = PointerProperty(
        type=FlexiBIMProject,
        name="FlexiBIM",
        description="FlexiBIM project settings and tag registry",
    )


def unregister_pointers():
    for owner, attr in ((bpy.types.Object, "flexibim"), (bpy.types.Scene, "flexibim")):
        if hasattr(owner, attr):
            try:
                delattr(owner, attr)
            except (AttributeError, RuntimeError):
                pass
