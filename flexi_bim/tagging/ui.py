"""Sidebar UI for tags, the tag library and the cost summary."""

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

class FLEXIBIM_UL_tags(bpy.types.UIList):
    """Tags on the active object."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False,
                     icon=C.category_icon(item.category))
            resolved = api.resolve_tag(item, context.scene)
            if resolved.missing_library_entry:
                row.label(text="", icon="ERROR")
            elif item.source == C.SOURCE_LIBRARY:
                row.label(text="", icon="LINKED")
            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            sub.label(text=_cost_label(context, item))
        else:
            layout.label(text="", icon=C.category_icon(item.category))


class FLEXIBIM_UL_library(bpy.types.UIList):
    """Reusable tag definitions."""

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

def _cost_label(context, tag):
    """Short right-aligned cost string for list rows."""
    obj = getattr(context, "object", None)
    scene = context.scene
    ctx = api.unit_context(scene)
    result = api.tag_cost(obj, tag, scene, context)
    if not result.priced:
        return ""
    return units.format_currency(result.amount, ctx)


def _draw_cost(layout, cost, ctx, *, measurements=None, show_quantity=True):
    """Cost editor shared by object tags and library tags."""
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


def _draw_properties(layout, tag, owner):
    """Key/value property editor for ``tag``."""
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
    side.operator("flexibim.property_add", icon="ADD", text="").owner_type = owner
    side.operator("flexibim.property_remove", icon="REMOVE", text="").owner_type = owner
    if len(tag.properties) > 1:
        side.separator()
        up = side.operator("flexibim.property_move", icon="TRIA_UP", text="")
        up.owner_type, up.direction = owner, "UP"
        down = side.operator("flexibim.property_move", icon="TRIA_DOWN", text="")
        down.owner_type, down.direction = owner, "DOWN"


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


class FLEXIBIM_PT_tags(_Sidebar, bpy.types.Panel):
    bl_label = "Tags"
    bl_idname = "FLEXIBIM_PT_tags"
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
            "FLEXIBIM_UL_tags", "",
            data, "tags",
            data, "active_tag_index",
            rows=max(2, min(len(data.tags), 8)),
        )
        side = row.column(align=True)
        side.operator("flexibim.tag_add", icon="ADD", text="")
        side.operator("flexibim.tag_remove", icon="REMOVE", text="")
        side.separator()
        side.operator("flexibim.tag_from_library", icon="ASSET_MANAGER", text="")
        side.operator("flexibim.tag_duplicate", icon="DUPLICATE", text="")
        if len(data.tags) > 1:
            side.separator()
            side.operator("flexibim.tag_move", icon="TRIA_UP", text="").direction = "UP"
            side.operator("flexibim.tag_move", icon="TRIA_DOWN", text="").direction = "DOWN"

        tag = data.active_tag
        if tag is None:
            layout.label(text="Object has no tags", icon="INFO")
            return

        ctx = api.unit_context(context.scene)
        resolved = api.resolve_tag(tag, context.scene)

        box = layout.box()
        column = box.column(align=True)
        column.prop(tag, "name")
        row = column.row(align=True)
        row.prop(tag, "source", expand=True)

        if tag.source == C.SOURCE_LIBRARY:
            if resolved.missing_library_entry:
                warning = box.column(align=True)
                warning.alert = True
                warning.label(text=f"No library tag named '{tag.name}'", icon="ERROR")
                warning.operator("flexibim.library_from_tag", icon="ADD",
                                 text="Create Library Tag")
            else:
                info = box.row(align=True)
                info.label(text="Cost inherited from library", icon="LINKED")
                info.operator("flexibim.tag_localize", text="Make Local")
                box.label(text=f"Category: {resolved.category.title()}")
        else:
            column.prop(tag, "category")

        column.prop(tag, "description")

        cost_box = box.box()
        cost_box.label(text="Cost", icon="FUND")
        if tag.source == C.SOURCE_LIBRARY and not resolved.missing_library_entry:
            entry = api.get_library_tag(context.scene, tag.name)
            sub = cost_box.column(align=True)
            sub.enabled = False
            _draw_cost(sub, entry.cost, ctx, measurements=api.measure_object(obj, context))
        else:
            _draw_cost(cost_box, tag.cost, ctx,
                       measurements=api.measure_object(obj, context))

        result = api.tag_cost(obj, tag, context.scene, context)
        if result.priced:
            row = cost_box.row()
            row.label(text="Tag Cost")
            row.label(text=units.format_currency(result.amount, ctx))

        _draw_properties(box, tag, "TAG")
        if resolved.inherited_keys:
            inherited = box.box()
            inherited.label(text="Inherited from library", icon="LINKED")
            for key in resolved.inherited_keys:
                row = inherited.row()
                row.label(text=key)
                row.label(text=str(resolved.properties[key]))

        tools = layout.column(align=True)
        tools.operator("flexibim.tag_apply_to_selected", icon="PASTEDOWN")
        tools.operator("flexibim.tags_copy_to_selected", icon="COPYDOWN")
        row = tools.row(align=True)
        row.operator("flexibim.tag_select_objects", icon="RESTRICT_SELECT_OFF",
                     text="Select Same Tag").tag_name = tag.name
        row.operator("flexibim.library_from_tag", icon="ASSET_MANAGER", text="To Library")


class FLEXIBIM_PT_library(_Sidebar, bpy.types.Panel):
    bl_label = "Tag Library"
    bl_idname = "FLEXIBIM_PT_library"
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        project = api.project(context.scene)
        if project is None:
            return

        row = layout.row()
        row.template_list(
            "FLEXIBIM_UL_library", "",
            project, "library",
            project, "active_library_index",
            rows=max(2, min(len(project.library), 8)),
        )
        side = row.column(align=True)
        side.operator("flexibim.library_add", icon="ADD", text="")
        side.operator("flexibim.library_remove", icon="REMOVE", text="")
        side.separator()
        side.operator("flexibim.library_duplicate", icon="DUPLICATE", text="")

        entry = project.active_library_tag
        if entry is None:
            layout.label(text="No tag definitions yet", icon="INFO")
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

        _draw_properties(box, entry, "LIBRARY")

        tools = layout.column(align=True)
        tools.operator("flexibim.library_assign", icon="PASTEDOWN")
        tools.operator("flexibim.library_select_users", icon="RESTRICT_SELECT_OFF")


class FLEXIBIM_PT_costs(_Sidebar, bpy.types.Panel):
    bl_label = "Cost Summary"
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
            layout.operator("flexibim.tag_add", icon="ADD")
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
    FLEXIBIM_UL_tags,
    FLEXIBIM_UL_library,
    FLEXIBIM_UL_properties,
    FLEXIBIM_PT_tags,
    FLEXIBIM_PT_library,
    FLEXIBIM_PT_costs,
    FLEXIBIM_PT_project,
)
