from ..core.registration import register_classes, unregister_classes
from . import panel

classes = panel.classes


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
