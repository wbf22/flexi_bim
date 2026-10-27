import bpy


def register_classes(classes):
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_classes(classes):
    """Unregister in reverse order, tolerating classes Blender already dropped.

    Reloading an addon can leave classes half-registered; raising here would
    abort the rest of the teardown and leak the remaining classes.
    """
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
