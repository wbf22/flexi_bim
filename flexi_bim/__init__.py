bl_info = {
    "name": "FlexiBIM",
    "author": "wfowler",
    "version": (0, 1, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > FlexiBIM",
    "description": "Tag freeform Blender models with BIM semantics and generate construction drawings.",
    "category": "Architecture",
}

from . import core
from . import operators
from . import tagging
from . import ui
from . import drawings
from . import export

# Order matters: `ui` registers the root panel that the tagging panels parent
# themselves to, so it must register before `tagging`.
_modules = (
    core,
    operators,
    ui,
    tagging,
    drawings,
    export,
)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
