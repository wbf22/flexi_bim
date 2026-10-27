"""Operators for creating, editing and applying tags."""

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


def _library_enum_items(self, context):
    scene = getattr(context, "scene", None)
    items = []
    for index, entry in enumerate(api.library_tags(scene)):
        name = entry.name or "(unnamed)"
        items.append((name, name, entry.description or "Library tag", index))
    if not items:
        items = [
            (EMPTY_ENUM, "No library tags", "Create one in the Tag Library panel", 0)
        ]
    _enum_cache["library"] = items
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
# Object tags
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_tag_add(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_add"
    bl_label = "Add Tag"
    bl_description = "Add a tag to the active object"

    name: StringProperty(name="Name", default="Tag")
    category: EnumProperty(name="Category", items=C.CATEGORY_ITEMS, default="NONE")
    apply_to_selected: BoolProperty(
        name="All Selected",
        description="Add this tag to every selected object",
        default=False,
    )

    def execute(self, context):
        targets = _selected(context) if self.apply_to_selected else [_taggable(context)]
        count = 0
        for obj in targets:
            before = len(api.get_tags(obj))
            api.add_tag(obj, self.name, category=self.category)
            count += len(api.get_tags(obj)) - before
        self.report({"INFO"}, f"Tagged {count} object(s) with '{self.name}'")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class FLEXIBIM_OT_tag_remove(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_remove"
    bl_label = "Remove Tag"
    bl_description = "Remove the active tag from the active object"

    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        obj = _taggable(context)
        data = api.object_data(obj)
        index = self.index if self.index >= 0 else data.active_tag_index
        if not api.remove_tag_at(obj, index):
            self.report({"WARNING"}, "No tag to remove")
            return {"CANCELLED"}
        return {"FINISHED"}


class FLEXIBIM_OT_tag_move(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_move"
    bl_label = "Move Tag"
    bl_description = "Reorder the active tag"

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


class FLEXIBIM_OT_tag_duplicate(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_duplicate"
    bl_label = "Duplicate Tag"
    bl_description = "Duplicate the active tag on this object"

    def execute(self, context):
        obj = _taggable(context)
        data = api.object_data(obj)
        source = data.active_tag
        if source is None:
            return {"CANCELLED"}
        new = data.tags.add()
        api.copy_tag(source, new)
        new.name = api.unique_tag_name(
            [t.name for t in data.tags if t != new], source.name
        )
        data.active_tag_index = len(data.tags) - 1
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


class FLEXIBIM_OT_tag_apply_to_selected(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_apply_to_selected"
    bl_label = "Apply Tag to Selected"
    bl_description = "Copy the active tag onto every other selected object"

    def execute(self, context):
        active = _taggable(context)
        source = api.object_data(active).active_tag
        if source is None:
            self.report({"WARNING"}, "No active tag")
            return {"CANCELLED"}
        count = 0
        for obj in _selected(context):
            if obj == active:
                continue
            existing = api.get_tag(obj, source.name)
            target = existing if existing is not None else api.object_data(obj).tags.add()
            api.copy_tag(source, target)
            count += 1
        self.report({"INFO"}, f"Applied '{source.name}' to {count} object(s)")
        return {"FINISHED"}


class FLEXIBIM_OT_tags_copy_to_selected(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tags_copy_to_selected"
    bl_label = "Copy All Tags to Selected"
    bl_description = "Replace the tags on every selected object with the active object's tags"

    def execute(self, context):
        active = _taggable(context)
        source_tags = api.get_tags(active)
        count = 0
        for obj in _selected(context):
            if obj == active:
                continue
            data = api.object_data(obj)
            data.tags.clear()
            for tag in source_tags:
                api.copy_tag(tag, data.tags.add())
            data.active_tag_index = max(0, len(data.tags) - 1)
            count += 1
        self.report({"INFO"}, f"Copied {len(source_tags)} tag(s) to {count} object(s)")
        return {"FINISHED"}


class FLEXIBIM_OT_tag_from_library(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_from_library"
    bl_label = "Add Library Tag"
    bl_description = "Tag the selected objects with a definition from the project library"

    tag_name: EnumProperty(name="Library Tag", items=_library_enum_items)
    apply_to_selected: BoolProperty(name="All Selected", default=True)

    def execute(self, context):
        name = self.tag_name
        if not name or name == EMPTY_ENUM:
            self.report({"WARNING"}, "The tag library is empty")
            return {"CANCELLED"}
        targets = _selected(context) if self.apply_to_selected else [_taggable(context)]
        for obj in targets:
            tag = api.add_tag(obj, name, source=C.SOURCE_LIBRARY)
            tag.source = C.SOURCE_LIBRARY
        self.report({"INFO"}, f"Tagged {len(targets)} object(s) with '{name}'")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class FLEXIBIM_OT_tag_localize(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.tag_localize"
    bl_label = "Make Local"
    bl_description = "Copy the library definition onto this object so it can be edited independently"

    def execute(self, context):
        obj = _taggable(context)
        tag = api.object_data(obj).active_tag
        if tag is None or tag.source != C.SOURCE_LIBRARY:
            return {"CANCELLED"}
        entry = api.get_library_tag(context.scene, tag.name)
        if entry is not None:
            api.copy_cost(entry.cost, tag.cost)
            existing = {p.key.strip().lower() for p in tag.properties}
            for item in entry.properties:
                if item.key.strip().lower() not in existing:
                    new = tag.properties.add()
                    new.key, new.value, new.value_type = item.key, item.value, item.value_type
            tag.category = entry.category
            if not tag.description:
                tag.description = entry.description
        tag.source = C.SOURCE_LOCAL
        measure.invalidate_costs()
        return {"FINISHED"}


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
# Custom properties
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_property_add(bpy.types.Operator):
    bl_idname = "flexibim.property_add"
    bl_label = "Add Property"
    bl_description = "Add a custom key/value property to this tag"
    bl_options = {"REGISTER", "UNDO"}

    owner_type: EnumProperty(
        name="Owner",
        description="Whether the property belongs to an object tag or a library tag",
        items=[("TAG", "Tag", ""), ("LIBRARY", "Library Tag", "")],
        default="TAG",
    )
    key: StringProperty(name="Key", default="")
    value: StringProperty(name="Value", default="")
    value_type: EnumProperty(name="Type", items=C.PROP_TYPE_ITEMS, default=C.PROP_TEXT)

    def execute(self, context):
        tag = _owner_tag(context, self.owner_type)
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

    owner_type: EnumProperty(
        name="Owner",
        description="Whether the property belongs to an object tag or a library tag",
        items=[("TAG", "Tag", ""), ("LIBRARY", "Library Tag", "")],
        default="TAG",
    )
    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        tag = _owner_tag(context, self.owner_type)
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

    owner_type: EnumProperty(
        name="Owner",
        description="Whether the property belongs to an object tag or a library tag",
        items=[("TAG", "Tag", ""), ("LIBRARY", "Library Tag", "")],
        default="TAG",
    )
    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")], default="UP")

    def execute(self, context):
        tag = _owner_tag(context, self.owner_type)
        if tag is None:
            return {"CANCELLED"}
        index = tag.active_property_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (0 <= target < len(tag.properties)):
            return {"CANCELLED"}
        tag.properties.move(index, target)
        tag.active_property_index = target
        return {"FINISHED"}


def _owner_tag(context, owner_type):
    if owner_type == "LIBRARY":
        project = api.project(getattr(context, "scene", None))
        return project.active_library_tag if project is not None else None
    data = api.object_data(_taggable(context))
    return data.active_tag if data is not None else None


def _unique_key(tag):
    existing = {p.key for p in tag.properties}
    index = 1
    while f"Property {index}" in existing:
        index += 1
    return f"Property {index}"


# ---------------------------------------------------------------------------
# Tag library
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_library_add(bpy.types.Operator):
    bl_idname = "flexibim.library_add"
    bl_label = "New Library Tag"
    bl_description = "Create a reusable tag definition in the project library"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", default="New Tag")

    def execute(self, context):
        project = api.project(context.scene)
        entry = project.library.add()
        with props.suspend_rename_propagation():
            entry.name = api.unique_tag_name(
                [e.name for e in project.library if e != entry], self.name
            )
        entry.previous_name = entry.name
        project.active_library_index = len(project.library) - 1
        measure.invalidate_costs()
        return {"FINISHED"}


class FLEXIBIM_OT_library_remove(bpy.types.Operator):
    bl_idname = "flexibim.library_remove"
    bl_label = "Remove Library Tag"
    bl_description = "Delete the selected library tag definition"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        index = project.active_library_index
        if not (0 <= index < len(project.library)):
            return {"CANCELLED"}
        name = project.library[index].name
        users = len(api.objects_with_tag(context.scene, name))
        project.library.remove(index)
        project.active_library_index = min(
            max(0, index - 1), max(0, len(project.library) - 1)
        )
        measure.invalidate_costs()
        if users:
            self.report(
                {"WARNING"},
                f"{users} object(s) still reference '{name}' and now have no cost definition",
            )
        return {"FINISHED"}


class FLEXIBIM_OT_library_duplicate(bpy.types.Operator):
    bl_idname = "flexibim.library_duplicate"
    bl_label = "Duplicate Library Tag"
    bl_description = "Duplicate the selected library tag definition"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        source = project.active_library_tag
        if source is None:
            return {"CANCELLED"}
        entry = project.library.add()
        api.copy_tag(source, entry)
        with props.suspend_rename_propagation():
            entry.name = api.unique_tag_name(
                [e.name for e in project.library if e != entry], source.name
            )
        entry.previous_name = entry.name
        project.active_library_index = len(project.library) - 1
        return {"FINISHED"}


class FLEXIBIM_OT_library_from_tag(_TagOperator, bpy.types.Operator):
    bl_idname = "flexibim.library_from_tag"
    bl_label = "Promote to Library"
    bl_description = "Save the active object tag as a reusable library definition and link to it"

    def execute(self, context):
        obj = _taggable(context)
        tag = api.object_data(obj).active_tag
        if tag is None:
            return {"CANCELLED"}
        project = api.project(context.scene)
        entry = api.get_library_tag(context.scene, tag.name)
        created = entry is None
        if created:
            entry = project.library.add()
        api.copy_tag(tag, entry)
        with props.suspend_rename_propagation():
            entry.name = tag.name
        entry.previous_name = tag.name
        project.active_library_index = list(project.library).index(entry)
        tag.source = C.SOURCE_LIBRARY
        self.report(
            {"INFO"},
            f"{'Created' if created else 'Updated'} library tag '{entry.name}'",
        )
        return {"FINISHED"}


class FLEXIBIM_OT_library_assign(bpy.types.Operator):
    bl_idname = "flexibim.library_assign"
    bl_label = "Assign to Selected"
    bl_description = "Tag every selected object with the active library definition"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        entry = project.active_library_tag
        if entry is None:
            return {"CANCELLED"}
        targets = _selected(context)
        for obj in targets:
            tag = api.add_tag(obj, entry.name, source=C.SOURCE_LIBRARY)
            tag.source = C.SOURCE_LIBRARY
        self.report({"INFO"}, f"Tagged {len(targets)} object(s) with '{entry.name}'")
        return {"FINISHED"}


class FLEXIBIM_OT_library_select_users(bpy.types.Operator):
    bl_idname = "flexibim.library_select_users"
    bl_label = "Select Users"
    bl_description = "Select every object using the active library tag"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = api.project(context.scene)
        entry = project.active_library_tag
        if entry is None:
            return {"CANCELLED"}
        return bpy.ops.flexibim.tag_select_objects(tag_name=entry.name)


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
    bl_description = "Write tags and the tag library to a JSON file"

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
    bl_description = "Load tags and library definitions from a JSON file"
    bl_options = {"REGISTER", "UNDO"}

    default_suffix = "_tags.json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    library_only: BoolProperty(
        name="Library Only",
        description="Import the reusable tag definitions but leave object tags alone",
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
            stats = exchange.loads(context.scene, text, library_only=self.library_only,
                                 replace=self.replace)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Imported {stats['library']} library tag(s), {stats['tags']} object tag(s)"
            + (f", {stats['missing']} object(s) not found" if stats["missing"] else ""),
        )
        return {"FINISHED"}


classes = (
    FLEXIBIM_OT_tag_add,
    FLEXIBIM_OT_tag_remove,
    FLEXIBIM_OT_tag_move,
    FLEXIBIM_OT_tag_duplicate,
    FLEXIBIM_OT_tags_clear,
    FLEXIBIM_OT_tag_apply_to_selected,
    FLEXIBIM_OT_tags_copy_to_selected,
    FLEXIBIM_OT_tag_from_library,
    FLEXIBIM_OT_tag_localize,
    FLEXIBIM_OT_tag_select_objects,
    FLEXIBIM_OT_property_add,
    FLEXIBIM_OT_property_remove,
    FLEXIBIM_OT_property_move,
    FLEXIBIM_OT_library_add,
    FLEXIBIM_OT_library_remove,
    FLEXIBIM_OT_library_duplicate,
    FLEXIBIM_OT_library_from_tag,
    FLEXIBIM_OT_library_assign,
    FLEXIBIM_OT_library_select_users,
    FLEXIBIM_OT_refresh_quantities,
    FLEXIBIM_OT_select_untagged,
    FLEXIBIM_OT_export_schedule,
    FLEXIBIM_OT_export_tags,
    FLEXIBIM_OT_import_tags,
)
