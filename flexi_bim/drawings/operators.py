"""Operators for managing drawing views and exporting them."""

# NOTE: no `from __future__ import annotations` here (see tagging/props.py).

import os
import re
import tempfile

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from ..tagging import api
from . import props
from . import svg as svg_module
from . import views

# Dynamic enum items must be kept alive by Python or Blender shows garbage.
_enum_cache = {}

EMPTY_ENUM = "__FLEXIBIM_EMPTY__"


def _registry_tag_items(self, context):
    scene = getattr(context, "scene", None)
    items = [
        (entry.name, entry.name, entry.description or "Project tag", index)
        for index, entry in enumerate(api.all_tags(scene))
    ]
    if not items:
        items = [(EMPTY_ENUM, "No tags", "Create tags in the Tags panel", 0)]
    _enum_cache["tags"] = items
    return items


def _data(context):
    return getattr(getattr(context, "scene", None), "flexibim_drawings", None)


def _active_view(context):
    data = _data(context)
    return data.active_view if data is not None else None


def _safe_filename(name, fallback="drawing"):
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("_")
    return stem or fallback


def _output_path(context, name):
    data = _data(context)
    directory = (getattr(data, "output_dir", "") or "").strip()
    if not directory:
        blend = getattr(bpy.data, "filepath", "") or ""
        directory = os.path.dirname(blend) if blend else tempfile.gettempdir()
    directory = bpy.path.abspath(directory)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, _safe_filename(name) + ".svg")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_view_add(bpy.types.Operator):
    bl_idname = "flexibim.view_add"
    bl_label = "New View"
    bl_description = "Create a new drawing view"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", default="New View")

    def execute(self, context):
        data = _data(context)
        if data is None:
            return {"CANCELLED"}
        view = data.views.add()
        view.name = self.name or "New View"
        data.active_view_index = len(data.views) - 1
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class FLEXIBIM_OT_view_remove(bpy.types.Operator):
    bl_idname = "flexibim.view_remove"
    bl_label = "Remove View"
    bl_description = "Delete the selected drawing view"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = _data(context)
        index = data.active_view_index if data is not None else -1
        if data is None or not (0 <= index < len(data.views)):
            return {"CANCELLED"}
        data.views.remove(index)
        data.active_view_index = min(max(0, index - 1), max(0, len(data.views) - 1))
        return {"FINISHED"}


class FLEXIBIM_OT_view_duplicate(bpy.types.Operator):
    bl_idname = "flexibim.view_duplicate"
    bl_label = "Duplicate View"
    bl_description = "Duplicate the selected drawing view"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        data = _data(context)
        source = data.active_view if data is not None else None
        if source is None:
            return {"CANCELLED"}
        target = data.views.add()
        for field in ("axis", "direction", "mode", "cut_level", "use_range",
                      "range_min", "range_max", "contained", "categories",
                      "tag_match", "notes", "scale"):
            setattr(target, field, getattr(source, field))
        target.name = source.name + " copy"
        for tag in source.include_tags:
            target.include_tags.add().name = tag.name
        for measurement in source.measurements:
            copy = target.measurements.add()
            copy.object_a = measurement.object_a
            copy.object_b = measurement.object_b
            copy.offset = measurement.offset
            copy.decimals = measurement.decimals
            copy.include = measurement.include
        data.active_view_index = len(data.views) - 1
        return {"FINISHED"}


class FLEXIBIM_OT_view_tag_add(bpy.types.Operator):
    bl_idname = "flexibim.view_tag_add"
    bl_label = "Include Tag"
    bl_description = "Add a project tag to this view's filter"
    bl_options = {"REGISTER", "UNDO"}

    name: EnumProperty(name="Tag", items=_registry_tag_items)

    def execute(self, context):
        view = _active_view(context)
        if view is None or not self.name or self.name == EMPTY_ENUM:
            self.report({"WARNING"}, "No tag to add")
            return {"CANCELLED"}
        wanted = self.name.strip().lower()
        if any(tag.name.strip().lower() == wanted for tag in view.include_tags):
            return {"FINISHED"}
        view.include_tags.add().name = self.name
        view.active_tag_index = len(view.include_tags) - 1
        return {"FINISHED"}


class FLEXIBIM_OT_view_tag_remove(bpy.types.Operator):
    bl_idname = "flexibim.view_tag_remove"
    bl_label = "Remove Included Tag"
    bl_description = "Remove the selected tag from this view's filter"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        view = _active_view(context)
        if view is None:
            return {"CANCELLED"}
        index = self.index if self.index >= 0 else view.active_tag_index
        if not (0 <= index < len(view.include_tags)):
            return {"CANCELLED"}
        view.include_tags.remove(index)
        view.active_tag_index = min(max(0, index - 1), max(0, len(view.include_tags) - 1))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_measure_add(bpy.types.Operator):
    bl_idname = "flexibim.measure_add"
    bl_label = "Add Measurement"
    bl_description = "Measure the gap between the two selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_view(context) is not None

    def execute(self, context):
        view = _active_view(context)
        selected = list(context.selected_objects)
        if len(selected) != 2:
            self.report({"WARNING"}, "Select exactly two objects to measure between")
            return {"CANCELLED"}
        measurement = view.measurements.add()
        measurement.object_a = selected[0].name
        measurement.object_b = selected[1].name
        view.active_measurement_index = len(view.measurements) - 1
        return {"FINISHED"}


class FLEXIBIM_OT_measure_remove(bpy.types.Operator):
    bl_idname = "flexibim.measure_remove"
    bl_label = "Remove Measurement"
    bl_description = "Delete the selected measurement"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Index", default=-1)

    def execute(self, context):
        view = _active_view(context)
        if view is None:
            return {"CANCELLED"}
        index = self.index if self.index >= 0 else view.active_measurement_index
        if not (0 <= index < len(view.measurements)):
            return {"CANCELLED"}
        view.measurements.remove(index)
        view.active_measurement_index = min(
            max(0, index - 1), max(0, len(view.measurements) - 1)
        )
        return {"FINISHED"}


class FLEXIBIM_OT_measure_generate(bpy.types.Operator):
    bl_idname = "flexibim.measure_generate"
    bl_label = "Auto Generate Measurements"
    bl_description = (
        "Add gap measurements between consecutive objects in this view, "
        "ordered along its axis"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_view(context) is not None

    def execute(self, context):
        view = _active_view(context)
        sources = views.build_sources(context.scene, view, context)
        if len(sources) < 2:
            self.report({"WARNING"}, "View needs at least two objects to measure")
            return {"CANCELLED"}

        axis_index = {"X": 0, "Y": 1, "Z": 2}.get(view.axis, 2)

        def center(source):
            if not source.vertices:
                return 0.0
            return sum(v[axis_index] for v in source.vertices) / len(source.vertices)

        ordered = sorted(sources, key=center)
        existing = {frozenset((m.object_a, m.object_b)) for m in view.measurements}

        added = 0
        for a, b in zip(ordered, ordered[1:]):
            pair = frozenset((a.name, b.name))
            if pair in existing:
                continue
            measurement = view.measurements.add()
            measurement.object_a = a.name
            measurement.object_b = b.name
            existing.add(pair)
            added += 1

        if not added:
            self.report({"INFO"}, "No new measurements to add")
            return {"CANCELLED"}
        view.active_measurement_index = len(view.measurements) - 1
        self.report({"INFO"}, f"Added {added} measurement(s)")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class FLEXIBIM_OT_drawing_generate(bpy.types.Operator):
    bl_idname = "flexibim.drawing_generate"
    bl_label = "Generate SVG"
    bl_description = "Render the selected view and write it to the output folder"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_view(context) is not None

    def execute(self, context):
        view = _active_view(context)
        drawing = views.render(context.scene, views.spec_from_view(view), context)
        path = _output_path(context, view.name)
        try:
            svg_module.write(path, drawing, scale_denominator=view.scale,
                             title=view.name)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write file: {error}")
            return {"CANCELLED"}
        if drawing.is_empty:
            self.report({"WARNING"}, f"Nothing to draw; empty SVG written to {path}")
        else:
            self.report(
                {"INFO"},
                f"Wrote {len(drawing.segments)} segment(s) to {path}",
            )
        return {"FINISHED"}


class FLEXIBIM_OT_drawing_export(bpy.types.Operator):
    bl_idname = "flexibim.drawing_export"
    bl_label = "Export SVG..."
    bl_description = "Render the selected view and choose where to save it"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.svg", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return _active_view(context) is not None

    def invoke(self, context, event):
        view = _active_view(context)
        if not self.filepath:
            blend = getattr(bpy.data, "filepath", "") or ""
            base = blend.rsplit(".", 1)[0] if blend else "flexibim"
            self.filepath = f"{base}_{_safe_filename(view.name)}.svg"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        view = _active_view(context)
        drawing = views.render(context.scene, views.spec_from_view(view), context)
        try:
            svg_module.write(bpy.path.abspath(self.filepath), drawing,
                             scale_denominator=view.scale, title=view.name)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write file: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Wrote {self.filepath}")
        return {"FINISHED"}


classes = (
    FLEXIBIM_OT_view_add,
    FLEXIBIM_OT_view_remove,
    FLEXIBIM_OT_view_duplicate,
    FLEXIBIM_OT_view_tag_add,
    FLEXIBIM_OT_view_tag_remove,
    FLEXIBIM_OT_measure_add,
    FLEXIBIM_OT_measure_remove,
    FLEXIBIM_OT_measure_generate,
    FLEXIBIM_OT_drawing_generate,
    FLEXIBIM_OT_drawing_export,
)
