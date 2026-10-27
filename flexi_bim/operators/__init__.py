from ..core.registration import register_classes, unregister_classes

classes = ()


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
