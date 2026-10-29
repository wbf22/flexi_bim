"""Sidebar UI for drawing views."""

from __future__ import annotations

import bpy

PANEL_CATEGORY = "FlexiBIM"


class FLEXIBIM_UL_views(bpy.types.UIList):
    """Saved drawing views."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon="IMAGE_DATA")
            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            sub.label(text=f"{item.axis} / {item.mode.title()} 1:{item.scale:g}")
        else:
            layout.label(text="", icon="IMAGE_DATA")


class FLEXIBIM_UL_view_tags(bpy.types.UIList):
    """Tags included in a view's filter."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.prop(item, "name", text="", emboss=False, icon="BOOKMARKS")
        else:
            layout.label(text=item.name)


class FLEXIBIM_UL_measurements(bpy.types.UIList):
    """Measurements on the active view."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.object_a or "?", icon="DRIVER_DISTANCE")
            row.label(text="\u2194")
            row.label(text=item.object_b or "?")
            if not item.include:
                row.label(text="", icon="HIDE_ON")
        else:
            layout.label(text=f"{item.object_a} \u2194 {item.object_b}")


class FLEXIBIM_PT_measurements(bpy.types.Panel):
    bl_label = "Measurements"
    bl_idname = "FLEXIBIM_PT_measurements"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        data = getattr(context.scene, "flexibim_drawings", None)
        view = data.active_view if data is not None else None
        if view is None:
            layout.label(text="No active view", icon="INFO")
            return

        row = layout.row()
        row.template_list(
            "FLEXIBIM_UL_measurements", "",
            view, "measurements",
            view, "active_measurement_index",
            rows=max(2, min(len(view.measurements), 6)),
        )
        side = row.column(align=True)
        side.operator("flexibim.measure_add", icon="ADD", text="")
        side.operator("flexibim.measure_remove", icon="REMOVE", text="")

        measurement = view.active_measurement
        if measurement is not None:
            column = layout.column(align=True)
            column.prop(measurement, "object_a")
            column.prop(measurement, "object_b")
            row = column.row(align=True)
            row.prop(measurement, "offset")
            row.prop(measurement, "decimals")
            column.prop(measurement, "include")

        layout.label(text="Select two objects, then Add", icon="INFO")


class FLEXIBIM_PT_drawings(bpy.types.Panel):
    bl_label = "Drawings"
    bl_idname = "FLEXIBIM_PT_drawings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "FLEXIBIM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        data = getattr(context.scene, "flexibim_drawings", None)
        if data is None:
            layout.label(text="FlexiBIM drawings not registered", icon="ERROR")
            return

        row = layout.row()
        row.template_list(
            "FLEXIBIM_UL_views", "",
            data, "views",
            data, "active_view_index",
            rows=max(2, min(len(data.views), 6)),
        )
        side = row.column(align=True)
        side.operator("flexibim.view_add", icon="ADD", text="")
        side.operator("flexibim.view_remove", icon="REMOVE", text="")
        side.separator()
        side.operator("flexibim.view_duplicate", icon="DUPLICATE", text="")

        view = data.active_view
        if view is None:
            layout.label(text="No views yet", icon="INFO")
            return

        box = layout.box()
        column = box.column(align=True)
        column.prop(view, "name")
        row = column.row(align=True)
        row.prop(view, "axis")
        row.prop(view, "direction")
        column.prop(view, "mode")
        if view.mode == "CUT":
            column.prop(view, "cut_level")

        limits = box.column(align=True)
        limits.prop(view, "use_range")
        if view.use_range:
            row = limits.row(align=True)
            row.prop(view, "range_min")
            row.prop(view, "range_max")
            limits.prop(view, "contained")

        filter_box = layout.box()
        filter_box.label(text="Filter", icon="FILTER")
        filter_box.prop(view, "tag_match")

        tags_row = filter_box.row()
        tags_row.template_list(
            "FLEXIBIM_UL_view_tags", "",
            view, "include_tags",
            view, "active_tag_index",
            rows=max(2, min(len(view.include_tags), 5)),
        )
        tags_side = tags_row.column(align=True)
        tags_side.operator_menu_enum("flexibim.view_tag_add", "name", icon="ADD", text="")
        tags_side.operator("flexibim.view_tag_remove", icon="REMOVE", text="")
        if not len(view.include_tags):
            filter_box.label(text="All tags (no filter)", icon="INFO")

        filter_box.prop(view, "categories")

        options = layout.box()
        options.prop(view, "scale")
        options.prop(view, "notes")

        output = layout.column(align=True)
        output.prop(data, "output_dir", text="")
        row = output.row(align=True)
        row.operator("flexibim.drawing_generate", icon="RENDER_STILL")
        row.operator("flexibim.drawing_export", icon="EXPORT")


classes = (
    FLEXIBIM_UL_views,
    FLEXIBIM_UL_view_tags,
    FLEXIBIM_UL_measurements,
    FLEXIBIM_PT_drawings,
    FLEXIBIM_PT_measurements,
)
