"""Root FlexiBIM sidebar panel.

Subsystem panels (tagging now; drawings and export later) parent themselves to
this panel with ``bl_parent_id = "FLEXIBIM_PT_main"``, so it must be registered
before they are - which is why ``ui`` comes before ``tagging`` in the addon's
module order.
"""

import bpy

PANEL_CATEGORY = "FlexiBIM"


class FLEXIBIM_PT_main(bpy.types.Panel):
    bl_label = "FlexiBIM"
    bl_idname = "FLEXIBIM_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        from ..tagging import api

        layout = self.layout
        obj = getattr(context, "object", None)

        if api.project(getattr(context, "scene", None)) is None:
            layout.label(text="FlexiBIM data not registered", icon="ERROR")
            return

        row = layout.row(align=True)
        if obj is None:
            row.label(text="No active object", icon="INFO")
            return

        tags = api.get_tags(obj)
        if tags:
            row.label(
                text=", ".join(tag.name for tag in tags[:3])
                + (f" +{len(tags) - 3}" if len(tags) > 3 else ""),
                icon="BOOKMARKS",
            )
        else:
            row.label(text="Untagged object", icon="DOT")
            row.operator("flexibim.tag_add", text="", icon="ADD")


classes = (
    FLEXIBIM_PT_main,
)
