"""Root FlexiBIM sidebar panel.

Subsystem panels (tagging now; drawings and export later) parent themselves to
this panel with ``bl_parent_id = "FLEXIBIM_PT_main"``, so it must be registered
before they are - which is why ``ui`` comes before ``tagging`` in the addon's
module order.  It draws nothing itself.
"""

import bpy

PANEL_CATEGORY = "FlexiBIM"


class FLEXIBIM_PT_main(bpy.types.Panel):
    bl_label = "FlexiBIM"
    bl_description = "FlexiBIM - tag freeform models and generate drawings"
    bl_idname = "FLEXIBIM_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        pass


classes = (
    FLEXIBIM_PT_main,
)
