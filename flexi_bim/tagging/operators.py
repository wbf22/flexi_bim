"""Operators for managing the tag registry and applying tags to objects."""

# NOTE: no `from __future__ import annotations` here. Blender's RNA registration
# reads the real property objects out of ``__annotations__``; PEP 563 would turn
# them into plain strings and registration would fail.

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from . import api
from . import constants as C
from . import exchange
from . import measure
from . import props

# Dynamic enum items must be kept alive by Python or Blender shows garbage
# (the strings are not copied into RNA).
_enum_cache = {}

#: Placeholder identifier used when a dynamic enum has nothing to offer.
#: An empty identifier is not safe to hand to RNA, so use a reserved one.
EMPTY_ENUM = "__FLEXIBIM_EMPTY__"


def _tag_enum_items(self, context):
    scene = getattr(context, "scene", None)
    items = []
    for index, entry in enumerate(api.all_tags(scene)):
        name = entry.name or "(unnamed)"
        items.append((name, name, entry.description or "Project tag", index))
    if not items:
        items = [
            (EMPTY_ENUM, "No tags yet", "Create one in the Tags panel", 0)
        ]
    _enum_cache["tags"] = items
    return items


def _select(obj, state=True):
    """``select_set`` that tolerates objects outside the active view layer."""
    try:
        obj.select_set(state)
        return True
    except RuntimeError:
        return False


def _deselect_all(scene):
    for obj in getattr(scene, "objects", ()):  # pragma: no branch
        _select(obj, False)


def _taggable(context):
    obj = getattr(context, "object", None) or getattr(context, "active_object", None)
    return obj if api.object_data(obj) is not None else None


def _selected(context):
    """Selected objects, always including the active one."""
    objects = list(getattr(context, "selected_objects", None) or [])
    active = _taggable(context)
    if active is not None and active not in objects:
        objects.append(active)
    return [obj for obj in objects if api.object_data(obj) is not None]


class _TagOperator:
    """Shared poll: we need an object that can hold tags."""

    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _taggable(context) is not None


# ---------------------------------------------------------------------------
# Applying tags to objects
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_tag_apply(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_apply"
    bl_label = "Apply Tag"
    bl_description = "Apply a project tag to the active object (or selection)"

    name: EnumProperty(name="Tag", items=_tag_enum_items)
    apply_to_selected: BoolProperty(
        name="All Selected",
        description="Apply the tag to every selected object",
        default=True,
    )

    def execute(self, context):
        name = self.name
        if not name or name == EMPTY_ENUM:
            self.report({"WARNING"}, "There are no tags yet")
            return {"CANCELLED"}
        targets = _selected(context) if self.apply_to_selected else [_taggable(context)]
        for obj in targets:
            api.apply_tag(obj, name)
        self.report({"INFO"}, f"Applied '{name}' to {len(targets)} object(s)")
        return {"FINISHED"}


class FLEXIBIM_OT_tag_unapply(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_unapply"
    bl_label = "Remove Tag"
    bl_description = "Stop this object using the active tag"

    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        data = api.object_data(_taggable(context))
        index = self.index if self.index >= 0 else data.active_tag_index
        if not api.unapply_tag_at(_taggable(context), index):
            self.report({"WARNING"}, "No tag to remove")
            return {"CANCELLED"}
        return {"FINISHED"}


class FLEXIBIM_OT_tag_move(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_move"
    bl_label = "Move Tag"
    bl_description = "Reorder the active tag on this object"

    direction: EnumProperty(
        items=[("UP", "Up", ""), ("DOWN", "Down", "")], default="UP"
    )

    def execute(self, context):
        data = api.object_data(_taggable(context))
        index = data.active_tag_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (0 <= target < len(data.tags)):
            return {"CANCELLED"}
        data.tags.move(index, target)
        data.active_tag_index = target
        return {"FINISHED"}


class FLEXIBIM_OT_tags_clear(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tags_clear"
    bl_label = "Clear Tags"
    bl_description = "Remove every tag from the selected objects"

    selected_only: BoolProperty(name="Selected Objects", default=True)

    def execute(self, context):
        targets = _selected(context) if self.selected_only else [_taggable(context)]
        removed = sum(api.clear_tags(obj) for obj in targets)
        self.report({"INFO"}, f"Removed {removed} tag(s)")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class FLEXIBIM_OT_tag_select_objects(bpy.types.Operator):
    bl_idname = "flexibim.tag_select_objects"
    bl_label = "Select Tagged Objects"
    bl_description = "Select every object carrying this tag"
    bl_options = {"REGISTER", "UNDO"}

    tag_name: StringProperty(name="Tag", default="")
    extend: BoolProperty(name="Extend", default=False)

    def execute(self, context):
        scene = context.scene
        name = self.tag_name
        if not name:
            active = _taggable(context)
            tag = api.object_data(active).active_tag if active else None
            if tag is None:
                self.report({"WARNING"}, "No tag specified")
                return {"CANCELLED"}
            name = tag.name

        matches = api.objects_with_tag(scene, name)
        if not self.extend:
            _deselect_all(scene)
        for obj in matches:
            _select(obj)
        if matches:
            try:
                context.view_layer.objects.active = matches[0]
            except (AttributeError, RuntimeError):
                pass
        self.report({"INFO"}, f"Selected {len(matches)} object(s) tagged '{name}'")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Managing the tag registry
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_tag_create(bpy.types.Operator):
    bl_idname = "flexibim.tag_create"
    bl_label = "New Tag"
    bl_description = "Create a new tag in the project registry"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", default="New Tag")
    category: EnumProperty(name="Category", items=C.CATEGORY_ITEMS, default="NONE")
    description: StringProperty(name="Description", default="")

    def execute(self, context):
        entry = api.create_tag(
            context.scene, self.name, category=self.category,
            description=self.description,
        )
        if entry is None:
            return {"CANCELLED"}
        self.report({"INFO"}, f"Created tag '{entry.name}'")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class FLEXIBIM_OT_tag_delete(bpy.types.Operator):
    bl_idname = "flexibim.tag_delete"
    bl_label = "Delete Tag"
    bl_description = "Delete the selected tag and remove it from every object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        entry = project.active_tag if project is not None else None
        if entry is None:
            return {"CANCELLED"}
        name = entry.name
        users = len(api.objects_with_tag(context.scene, name))
        api.delete_tag(context.scene, name)
        self.report(
            {"INFO"},
            f"Deleted '{name}'"
            + (f" and untagged {users} object(s)" if users else ""),
        )
        return {"FINISHED"}


class FLEXIBIM_OT_tag_duplicate(bpy.types.Operator):
    bl_idname = "flexibim.tag_duplicate"
    bl_label = "Duplicate Tag"
    bl_description = "Duplicate the selected tag definition"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        source = project.active_tag if project is not None else None
        if source is None:
            return {"CANCELLED"}
        entry = project.tags.add()
        api.copy_tag(source, entry)
        with props.suspend_rename_propagation():
            entry.name = api.unique_tag_name(
                [e.name for e in project.tags if e != entry], source.name
            )
        entry.previous_name = entry.name
        project.active_tag_index = len(project.tags) - 1
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Custom properties (on the active registry tag)
# ---------------------------------------------------------------------------

def _active_registry_tag(context):
    project = api.project(getattr(context, "scene", None))
    return project.active_tag if project is not None else None


class FLEXIBIM_OT_property_add(bpy.types.Operator):
    bl_idname = "flexibim.property_add"
    bl_label = "Add Property"
    bl_description = "Add a custom key/value property to this tag"
    bl_options = {"REGISTER", "UNDO"}

    key: StringProperty(name="Key", default="")
    value: StringProperty(name="Value", default="")
    value_type: EnumProperty(name="Type", items=C.PROP_TYPE_ITEMS, default=C.PROP_TEXT)

    def execute(self, context):
        tag = _active_registry_tag(context)
        if tag is None:
            self.report({"WARNING"}, "No tag selected")
            return {"CANCELLED"}
        item = tag.properties.add()
        item.key = self.key or _unique_key(tag)
        item.value = self.value
        item.value_type = self.value_type
        tag.active_property_index = len(tag.properties) - 1
        measure.invalidate_costs()
        return {"FINISHED"}


class FLEXIBIM_OT_property_remove(bpy.types.Operator):
    bl_idname = "flexibim.property_remove"
    bl_label = "Remove Property"
    bl_description = "Remove the selected custom property"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        tag = _active_registry_tag(context)
        if tag is None:
            return {"CANCELLED"}
        index = self.index if self.index >= 0 else tag.active_property_index
        if not (0 <= index < len(tag.properties)):
            return {"CANCELLED"}
        tag.properties.remove(index)
        tag.active_property_index = min(max(0, index - 1), max(0, len(tag.properties) - 1))
        measure.invalidate_costs()
        return {"FINISHED"}


class FLEXIBIM_OT_property_move(bpy.types.Operator):
    bl_idname = "flexibim.property_move"
    bl_label = "Move Property"
    bl_description = "Reorder the selected custom property"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")], default="UP")

    def execute(self, context):
        tag = _active_registry_tag(context)
        if tag is None:
            return {"CANCELLED"}
        index = tag.active_property_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (0 <= target < len(tag.properties)):
            return {"CANCELLED"}
        tag.properties.move(index, target)
        tag.active_property_index = target
        return {"FINISHED"}


def _unique_key(tag):
    existing = {p.key for p in tag.properties}
    index = 1
    while f"Property {index}" in existing:
        index += 1
    return f"Property {index}"


# ---------------------------------------------------------------------------
# Maintenance / reporting
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_refresh_quantities(bpy.types.Operator):
    bl_idname = "flexibim.refresh_quantities"
    bl_label = "Recalculate Quantities"
    bl_description = "Re-measure tagged geometry and refresh cost totals"
    bl_options = {"REGISTER"}

    def execute(self, context):
        measure.invalidate()
        tagged = api.tagged_objects(context.scene)
        total = api.project_total(context.scene, context=context)
        ctx = api.unit_context(context.scene)
        from ..core import units

        self.report(
            {"INFO"},
            f"{len(tagged)} tagged object(s), total {units.format_currency(total, ctx)}",
        )
        return {"FINISHED"}


class FLEXIBIM_OT_select_untagged(bpy.types.Operator):
    bl_idname = "flexibim.select_untagged"
    bl_label = "Select Untagged"
    bl_description = "Select geometry objects that carry no FlexiBIM tags"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        _deselect_all(scene)
        untagged = api.untagged_objects(scene)
        for obj in untagged:
            _select(obj)
        self.report({"INFO"}, f"{len(untagged)} untagged object(s)")
        return {"FINISHED"}


class _FileOperator:
    """Minimal file-select plumbing (avoids depending on bpy_extras)."""

    bl_options = {"REGISTER"}
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.csv;*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            blend = getattr(bpy.data, "filepath", "") or ""
            base = blend.rsplit(".", 1)[0] if blend else "flexibim"
            self.filepath = base + self.default_suffix
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FLEXIBIM_OT_export_schedule(_FileOperator, bpy.types.Operator):
    bl_idname = "flexibim.export_schedule"
    bl_label = "Export Cost Schedule (CSV)"
    bl_description = "Write the tag/cost schedule to a CSV file"

    default_suffix = "_schedule.csv"
    filter_glob: StringProperty(default="*.csv", options={"HIDDEN"})
    per_object: BoolProperty(
        name="Per Object",
        description="One row per object+tag instead of one row per tag",
        default=False,
    )

    def execute(self, context):
        scene = context.scene
        project = api.project(scene)
        objects = _selected(context) if project and project.summary_selected_only else None
        text = exchange.schedule_csv(scene, objects=objects, context=context,
                                   per_object=self.per_object)
        try:
            with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write file: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Schedule written to {self.filepath}")
        return {"FINISHED"}


class FLEXIBIM_OT_export_tags(_FileOperator, bpy.types.Operator):
    bl_idname = "flexibim.export_tags"
    bl_label = "Export Tags (JSON)"
    bl_description = "Write the tag registry and object tags to a JSON file"

    default_suffix = "_tags.json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        text = exchange.dumps(context.scene)
        try:
            with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write file: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Tags written to {self.filepath}")
        return {"FINISHED"}


class FLEXIBIM_OT_import_tags(_FileOperator, bpy.types.Operator):
    bl_idname = "flexibim.import_tags"
    bl_label = "Import Tags (JSON)"
    bl_description = "Load tag definitions and object tags from a JSON file"
    bl_options = {"REGISTER", "UNDO"}

    default_suffix = "_tags.json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    tags_only: BoolProperty(
        name="Tags Only",
        description="Import the tag definitions but leave object tags alone",
        default=False,
    )
    replace: BoolProperty(
        name="Replace Existing",
        description="Clear current tags before importing",
        default=False,
    )

    def execute(self, context):
        try:
            with open(bpy.path.abspath(self.filepath), "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as error:
            self.report({"ERROR"}, f"Could not read file: {error}")
            return {"CANCELLED"}
        try:
            stats = exchange.loads(context.scene, text, tags_only=self.tags_only,
                                 replace=self.replace)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Imported {stats['tags']} tag(s), {stats['applied']} object tag(s)"
            + (f", {stats['missing']} object(s) not found" if stats["missing"] else ""),
        )
        return {"FINISHED"}


classes = (
    FLEXIBIM_OT_tag_apply,
    FLEXIBIM_OT_tag_unapply,
    FLEXIBIM_OT_tag_move,
    FLEXIBIM_OT_tags_clear,
    FLEXIBIM_OT_tag_select_objects,
    FLEXIBIM_OT_tag_create,
    FLEXIBIM_OT_tag_delete,
    FLEXIBIM_OT_tag_duplicate,
    FLEXIBIM_OT_property_add,
    FLEXIBIM_OT_property_remove,
    FLEXIBIM_OT_property_move,
    FLEXIBIM_OT_refresh_quantities,
    FLEXIBIM_OT_select_untagged,
    FLEXIBIM_OT_export_schedule,
    FLEXIBIM_OT_export_tags,
    FLEXIBIM_OT_import_tags,
)
