"""Sidebar UI: the tag registry, applying tags to objects, and the cost summary."""

from __future__ import annotations

import bpy

from ..core import units
from . import api
from . import constants as C
from . import costing

PANEL_CATEGORY = "FlexiBIM"


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

class FLEXIBIM_UL_applied(bpy.types.UIList):
    """Tags applied to the active object."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            resolved = api.resolve_tag(context.scene, item)
            row.prop(item, "name", text="", emboss=False,
                     icon=C.category_icon(resolved.category))
            if resolved.missing:
                row.label(text="", icon="ERROR")
        else:
            layout.label(
                text="", icon=C.category_icon(api.resolve_tag(context.scene, item).category)
            )


class FLEXIBIM_UL_tags(bpy.types.UIList):
    """The project tag registry."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "color", text="")
            row.prop(item, "name", text="", emboss=False,
                     icon=C.category_icon(item.category))
            users = len(api.objects_with_tag(context.scene, item.name))
            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            sub.label(text=f"{users}" if users else "-")
        else:
            layout.label(text="", icon=C.category_icon(item.category))


class FLEXIBIM_UL_properties(bpy.types.UIList):
    """Key/value custom properties on a tag."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            split = layout.split(factor=0.45, align=True)
            split.prop(item, "key", text="", emboss=False)
            row = split.row(align=True)
            row.prop(item, "value", text="")
            row.prop(item, "value_type", text="", icon_only=True)
        else:
            layout.label(text=item.key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draw_cost(layout, cost, ctx, *, measurements=None, show_quantity=True):
    """Cost editor for a tag definition."""
    column = layout.column(align=True)
    column.prop(cost, "mode", text="")

    if cost.mode == C.COST_MODE_NONE:
        return

    if cost.mode == C.COST_MODE_FLAT:
        row = column.row(align=True)
        row.prop(cost, "rate", text=f"Amount ({ctx.currency})" if ctx.currency else "Amount")
        return

    column.prop(cost, "measurement", text="Measure")
    dimension = C.measure_dimension(cost.measurement)
    column.prop(cost, "rate", text=f"Rate ({units.rate_suffix(dimension, ctx)})")
    column.prop(cost, "quantity_source", text="Quantity")
    if cost.quantity_source == C.QUANTITY_MANUAL:
        column.prop(
            cost, "manual_quantity", text=f"Amount ({ctx.suffix(dimension)})"
        )
    column.prop(cost, "waste_percent", text="Waste")

    if show_quantity and cost.quantity_source == C.QUANTITY_AUTO:
        spec = costing.cost_spec_from(cost)
        quantity = costing.quantity_for(spec, measurements, ctx)
        box = column.box()
        row = box.row()
        row.label(text="Measured", icon="DRIVER_DISTANCE")
        row.label(text=units.format_quantity(quantity, dimension, ctx))
        if measurements is None:
            box.label(text="No geometry to measure", icon="INFO")


def _draw_properties(layout, tag):
    """Key/value property editor for the active registry tag."""
    header = layout.row(align=True)
    header.label(text="Custom Properties", icon="PROPERTIES")

    row = layout.row()
    row.template_list(
        "FLEXIBIM_UL_properties", "",
        tag, "properties",
        tag, "active_property_index",
        rows=max(2, min(len(tag.properties), 6)),
    )
    side = row.column(align=True)
    side.operator("flexibim.property_add", icon="ADD", text="")
    side.operator("flexibim.property_remove", icon="REMOVE", text="")
    if len(tag.properties) > 1:
        side.separator()
        side.operator("flexibim.property_move", icon="TRIA_UP", text="").direction = "UP"
        side.operator("flexibim.property_move", icon="TRIA_DOWN", text="").direction = "DOWN"


def _active_object(context):
    obj = getattr(context, "object", None)
    return obj if api.object_data(obj) is not None else None


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

class _Sidebar:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY


class FLEXIBIM_PT_apply(_Sidebar, bpy.types.Panel):
    bl_label = "Object Tags"
    bl_description = "Tags applied to the active object"
    bl_idname = "FLEXIBIM_PT_apply"
    bl_parent_id = "FLEXIBIM_PT_main"

    def draw(self, context):
        layout = self.layout
        obj = _active_object(context)
        if obj is None:
            layout.label(text="Select an object to tag", icon="INFO")
            return

        layout.label(text=obj.name, icon="OBJECT_DATA")
        data = obj.flexibim

        row = layout.row()
        row.template_list(
            "FLEXIBIM_UL_applied", "",
            data, "tags",
            data, "active_tag_index",
            rows=max(2, min(len(data.tags), 8)),
        )
        side = row.column(align=True)
        side.operator_menu_enum("flexibim.tag_apply", "name", icon="ADD", text="")
        side.operator("flexibim.tag_unapply", icon="REMOVE", text="")
        if len(data.tags) > 1:
            side.separator()
            side.operator("flexibim.tag_move", icon="TRIA_UP", text="").direction = "UP"
            side.operator("flexibim.tag_move", icon="TRIA_DOWN", text="").direction = "DOWN"


class FLEXIBIM_PT_tags(_Sidebar, bpy.types.Panel):
    bl_label = "Tags"
    bl_description = "Project-wide tag registry: create, edit and cost tags"
    bl_idname = "FLEXIBIM_PT_tags"
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        project = api.project(context.scene)
        if project is None:
            return

        row = layout.row()
        row.template_list(
            "FLEXIBIM_UL_tags", "",
            project, "tags",
            project, "active_tag_index",
            rows=max(2, min(len(project.tags), 8)),
        )
        side = row.column(align=True)
        side.operator("flexibim.tag_create", icon="ADD", text="")
        side.operator("flexibim.tag_delete", icon="REMOVE", text="")
        side.separator()
        side.operator("flexibim.tag_duplicate", icon="DUPLICATE", text="")

        entry = project.active_tag
        if entry is None:
            layout.label(text="No tags yet", icon="INFO")
            return

        ctx = api.unit_context(context.scene)
        box = layout.box()
        column = box.column(align=True)
        column.prop(entry, "name")
        column.prop(entry, "category")
        column.prop(entry, "description")
        column.prop(entry, "color")

        cost_box = box.box()
        cost_box.label(text="Cost", icon="FUND")
        _draw_cost(cost_box, entry.cost, ctx, show_quantity=False)

        _draw_properties(box, entry)


class FLEXIBIM_PT_costs(_Sidebar, bpy.types.Panel):
    bl_label = "Cost Summary"
    bl_description = "Totals for every tag; toggle selected-only from the header"
    bl_idname = "FLEXIBIM_PT_costs"
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header_preset(self, context):
        project = api.project(context.scene)
        if project is not None:
            self.layout.prop(project, "summary_selected_only", text="", icon="RESTRICT_SELECT_OFF")

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        project = api.project(scene)
        if project is None:
            return

        ctx = api.unit_context(scene)
        objects = None
        if project.summary_selected_only:
            objects = [o for o in context.selected_objects if api.is_tagged(o)]

        entries = api.cost_entries(scene, objects, context)
        if not entries:
            layout.label(text="Nothing tagged yet", icon="INFO")
            layout.operator("flexibim.tag_create", icon="ADD")
            return

        row = layout.row(align=True)
        row.prop(project, "summary_show_objects", toggle=True,
                 text="Per Object" if project.summary_show_objects else "Per Tag")
        row.operator("flexibim.refresh_quantities", icon="FILE_REFRESH", text="")

        table = layout.box()
        if project.summary_show_objects:
            totals = {}
            for object_name, _resolved, result in entries:
                totals[object_name] = totals.get(object_name, 0.0) + result.amount
            for object_name, amount in sorted(totals.items(), key=lambda kv: -kv[1]):
                line = table.row()
                line.label(text=object_name, icon="OBJECT_DATA")
                line.label(text=units.format_currency(amount, ctx))
        else:
            for row_data in costing.rollup(entries):
                line = table.row(align=True)
                op = line.operator(
                    "flexibim.tag_select_objects", text="",
                    icon=C.category_icon(row_data.category), emboss=False,
                )
                op.tag_name = row_data.name
                line.label(text=row_data.name)
                if row_data.mixed_units:
                    line.label(text="mixed units")
                elif row_data.mode == C.COST_MODE_MEASURED:
                    line.label(text=units.format_quantity(
                        row_data.charged_quantity, row_data.dimension, ctx, precision=1))
                else:
                    line.label(text=f"x{row_data.object_count}")
                line.label(text=units.format_currency(row_data.amount, ctx))
                for note in row_data.notes:
                    note_row = table.row()
                    note_row.alert = True
                    note_row.label(text=note, icon="ERROR")

        total = layout.row()
        total.scale_y = 1.2
        total.label(text="Project Total" if not project.summary_selected_only else "Selected Total")
        total.label(text=units.format_currency(
            costing.total_amount(entries), ctx))

        export = layout.column(align=True)
        export.operator("flexibim.export_schedule", icon="EXPORT")


class FLEXIBIM_PT_project(_Sidebar, bpy.types.Panel):
    bl_label = "Project Settings"
    bl_description = "Currency, quantity units, model stats and import/export tools"
    bl_idname = "FLEXIBIM_PT_project"
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        project = api.project(scene)
        if project is None:
            return

        ctx = api.unit_context(scene)
        column = layout.column(align=True)
        row = column.row(align=True)
        row.prop(project, "currency")
        row.prop(project, "currency_decimals", text="")
        column.prop(project, "unit_basis")

        info = layout.box()
        info.label(text=f"Quantities in {ctx.suffix(units.DIMENSION_LENGTH)} / "
                        f"{ctx.suffix(units.DIMENSION_AREA)} / "
                        f"{ctx.suffix(units.DIMENSION_VOLUME)}", icon="DRIVER_DISTANCE")
        if ctx.unitless:
            info.label(text="Scene has no unit system set", icon="INFO")

        stats = layout.box()
        tagged = api.tagged_objects(scene)
        untagged = api.untagged_objects(scene)
        stats.label(text=f"{len(tagged)} tagged object(s)", icon="CHECKMARK")
        row = stats.row(align=True)
        row.label(text=f"{len(untagged)} untagged", icon="QUESTION")
        row.operator("flexibim.select_untagged", text="Select")

        tools = layout.column(align=True)
        tools.operator("flexibim.export_tags", icon="EXPORT")
        tools.operator("flexibim.import_tags", icon="IMPORT")
        tools.separator()
        tools.operator("flexibim.tags_clear", icon="TRASH")


classes = (
    FLEXIBIM_UL_applied,
    FLEXIBIM_UL_tags,
    FLEXIBIM_UL_properties,
    FLEXIBIM_PT_apply,
    FLEXIBIM_PT_tags,
    FLEXIBIM_PT_costs,
    FLEXIBIM_PT_project,
)
