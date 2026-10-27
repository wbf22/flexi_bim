"""Public Python API for the tagging system.

Other FlexiBIM subsystems (drawings, schedules, export) and user scripts should
go through this module rather than poking at property groups directly::

    from flexi_bim.tagging import api

    api.add_tag(obj, "Exterior Wall", category="WALL")
    api.set_property(api.get_tag(obj, "Exterior Wall"), "Fire Rating", "1 hr")
    for obj in api.objects_with_tag(scene, "Exterior Wall"):
        print(api.object_cost(obj, scene).amount)
"""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from ..core import units
from . import constants as C
from . import costing
from . import measure
from . import props as _props


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def project(scene) -> "bpy.types.PropertyGroup | None":
    """``scene.flexibim``, or ``None`` if the addon is not registered yet."""
    return getattr(scene, "flexibim", None) if scene is not None else None


def object_data(obj):
    """``object.flexibim``, or ``None`` for IDs that cannot carry tags."""
    return getattr(obj, "flexibim", None) if obj is not None else None


def get_tags(obj):
    """Every tag on ``obj`` as a list (empty when untagged)."""
    data = object_data(obj)
    return list(data.tags) if data is not None else []


def tag_names(obj):
    return [tag.name for tag in get_tags(obj)]


def get_tag(obj, name):
    """First tag on ``obj`` matching ``name`` (case-insensitive), else ``None``."""
    wanted = (name or "").strip().lower()
    for tag in get_tags(obj):
        if tag.name.strip().lower() == wanted:
            return tag
    return None


def has_tag(obj, name) -> bool:
    return get_tag(obj, name) is not None


def is_tagged(obj) -> bool:
    data = object_data(obj)
    return bool(data is not None and len(data.tags))


def library_tags(scene):
    data = project(scene)
    return list(data.library) if data is not None else []


def get_library_tag(scene, name):
    wanted = (name or "").strip().lower()
    for entry in library_tags(scene):
        if entry.name.strip().lower() == wanted:
            return entry
    return None


def library_lookup(scene):
    """Callable mapping a tag name to its library definition."""
    index = {}
    for entry in library_tags(scene):
        index.setdefault(entry.name.strip().lower(), entry)
    return lambda name: index.get((name or "").strip().lower())


def unique_tag_name(existing_names, base="Tag") -> str:
    """``base``, ``base.001``... avoiding clashes with ``existing_names``."""
    taken = {str(n).strip().lower() for n in existing_names}
    candidate = (base or "Tag").strip() or "Tag"
    if candidate.lower() not in taken:
        return candidate
    counter = 1
    while True:
        numbered = f"{candidate}.{counter:03d}"
        if numbered.lower() not in taken:
            return numbered
        counter += 1


def _scene_for(obj):
    """The scene an object belongs to, falling back to the active scene."""
    scenes = getattr(obj, "users_scene", None)
    if scenes:
        return scenes[0]
    return _active_scene()


def ensure_library_tag(scene, name, *, category=None, description=None,
                       source_tag=None):
    """Return the reusable library definition for ``name``, creating it if needed.

    This is what makes every tag reusable: any tag that exists in the project
    also exists in the tag library, so it can be re-applied to other objects or
    exported to another project.  When ``source_tag`` is given, its cost and
    custom properties seed the new definition.
    """
    clean = (name or "").strip()
    if not clean:
        return None
    existing = get_library_tag(scene, clean)
    if existing is not None:
        return existing

    data = project(scene)
    if data is None:
        return None

    entry = data.library.add()
    with _props.suspend_rename_propagation():
        entry.name = clean
    entry.previous_name = clean

    if source_tag is not None:
        copy_cost(source_tag.cost, entry.cost)
        copy_properties(source_tag.properties, entry.properties)
        origin_category = getattr(source_tag, "category", None)
        if origin_category and origin_category != "NONE":
            entry.category = origin_category
        origin_description = getattr(source_tag, "description", "")
        if origin_description:
            entry.description = origin_description

    if category is not None:
        entry.category = category
    if description:
        entry.description = description

    measure.invalidate_costs()
    return entry


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def add_tag(obj, name="Tag", *, category=None, source=None,
            description=None, allow_duplicate=False, reusable=True):
    """Add a tag to ``obj`` and return it.

    Every tag is reusable by default: a matching definition is registered in the
    project tag library and the new tag links to it, so the same tag can be
    applied to other objects and shared between projects.  Pass
    ``reusable=False`` to create a lone, object-only tag, or ``source=LOCAL`` to
    keep the tag independent of its library definition.

    Re-adding an existing tag name is a no-op (the existing tag is returned)
    unless ``allow_duplicate`` is set.
    """
    data = object_data(obj)
    if data is None:
        raise TypeError(f"{obj!r} cannot carry FlexiBIM tags")

    clean = (name or "Tag").strip() or "Tag"
    scene = _scene_for(obj)

    if not allow_duplicate:
        existing = get_tag(obj, clean)
        if existing is not None:
            if reusable:
                ensure_library_tag(scene, clean, source_tag=existing)
            return existing

    if reusable:
        definition = ensure_library_tag(scene, clean, category=category,
                                        description=description)
        if source is None:
            source = C.SOURCE_LIBRARY if definition is not None else C.SOURCE_LOCAL

    tag = data.tags.add()
    tag.name = clean
    if category is not None:
        tag.category = category
    if description is not None:
        tag.description = description
    tag.source = source if source is not None else C.SOURCE_LOCAL
    data.active_tag_index = len(data.tags) - 1
    measure.invalidate_costs()
    return tag


def add_library_tag(obj, name, *, fallback_local=True):
    """Tag ``obj`` with a library definition, linking it to the library."""
    tag = add_tag(obj, name, source=C.SOURCE_LIBRARY)
    scene = _active_scene()
    if not fallback_local and get_library_tag(scene, name) is None:
        remove_tag(obj, name)
        raise KeyError(f"No library tag named {name!r}")
    tag.source = C.SOURCE_LIBRARY
    return tag


def remove_tag(obj, name) -> bool:
    """Remove the first tag matching ``name``; returns whether it existed."""
    data = object_data(obj)
    if data is None:
        return False
    wanted = (name or "").strip().lower()
    for index, tag in enumerate(data.tags):
        if tag.name.strip().lower() == wanted:
            remove_tag_at(obj, index)
            return True
    return False


def remove_tag_at(obj, index) -> bool:
    data = object_data(obj)
    if data is None or not (0 <= index < len(data.tags)):
        return False
    data.tags.remove(index)
    data.active_tag_index = min(max(0, index - 1), max(0, len(data.tags) - 1))
    measure.invalidate_costs()
    return True


def clear_tags(obj) -> int:
    data = object_data(obj)
    if data is None:
        return 0
    count = len(data.tags)
    data.tags.clear()
    data.active_tag_index = 0
    measure.invalidate_costs()
    return count


def set_property(tag, key, value, value_type=None):
    """Set a custom property on ``tag``, adding it if needed."""
    if tag is None:
        return None
    for item in tag.properties:
        if item.key.strip().lower() == (key or "").strip().lower():
            target = item
            break
    else:
        target = tag.properties.add()
        target.key = key
    if value_type is None:
        value_type = _infer_type(value)
    target.value_type = value_type
    target.value = _value_to_string(value)
    measure.invalidate_costs()
    return target


def get_property(tag, key, default=None):
    if tag is None:
        return default
    wanted = (key or "").strip().lower()
    for item in tag.properties:
        if item.key.strip().lower() == wanted:
            return costing.property_value(item)
    return default


def remove_property(tag, key) -> bool:
    if tag is None:
        return False
    wanted = (key or "").strip().lower()
    for index, item in enumerate(tag.properties):
        if item.key.strip().lower() == wanted:
            tag.properties.remove(index)
            tag.active_property_index = min(
                max(0, index - 1), max(0, len(tag.properties) - 1)
            )
            measure.invalidate_costs()
            return True
    return False


def _infer_type(value):
    if isinstance(value, bool):
        return C.PROP_BOOL
    if isinstance(value, (int, float)):
        return C.PROP_NUMBER
    return C.PROP_TEXT


def _value_to_string(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def copy_cost(source, target):
    """Copy every field of a ``FlexiBIMCost`` group."""
    for field in ("mode", "rate", "measurement", "quantity_source",
                  "manual_quantity", "waste_percent"):
        setattr(target, field, getattr(source, field))


def copy_properties(source_collection, target_collection, *, clear=True):
    if clear:
        target_collection.clear()
    for item in source_collection:
        new = target_collection.add()
        new.key = item.key
        new.value = item.value
        new.value_type = item.value_type


def copy_tag(source, target):
    """Copy a tag (local or library definition) onto another tag.

    The name is assigned programmatically, so rename propagation is suspended:
    copying a definition must never re-point other objects' tags at the copy.
    """
    with _props.suspend_rename_propagation():
        target.name = source.name
        target.category = getattr(source, "category", "NONE")
        target.description = getattr(source, "description", "")
        if hasattr(target, "source"):
            target.source = getattr(source, "source", C.SOURCE_LOCAL)
        copy_cost(source.cost, target.cost)
        copy_properties(source.properties, target.properties)
    measure.invalidate_costs()
    return target


def rename_tag_references(scene, old_name, new_name) -> int:
    """Rename every *library-linked* object tag from ``old_name``to ``new_name``.

    Called when a library definition is renamed so existing objects keep their
    link instead of silently losing their cost data.
    """
    if not old_name or not new_name or old_name == new_name:
        return 0
    wanted = old_name.strip().lower()
    changed = 0
    for obj in _iter_objects(scene):
        data = object_data(obj)
        if data is None:
            continue
        for tag in data.tags:
            if tag.source == C.SOURCE_LIBRARY and tag.name.strip().lower() == wanted:
                tag.name = new_name
                changed += 1
    if changed:
        measure.invalidate_costs()
    return changed


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _iter_objects(scene=None):
    if scene is not None and getattr(scene, "objects", None) is not None:
        return list(scene.objects)
    data = getattr(bpy, "data", None)
    return list(getattr(data, "objects", ())) if data else []


def _active_scene():
    scene = getattr(getattr(bpy, "context", None), "scene", None)
    if scene is not None:
        return scene
    scenes = getattr(getattr(bpy, "data", None), "scenes", None)
    return scenes[0] if scenes else None


def all_objects(scene=None):
    """Every object in ``scene`` (falling back to the whole blend file)."""
    return _iter_objects(scene)


def tagged_objects(scene=None):
    """Every object in ``scene`` carrying at least one tag."""
    return [obj for obj in _iter_objects(scene) if is_tagged(obj)]


def untagged_objects(scene=None, geometry_only=True):
    """Objects with no tags - the basis of a documentation preflight check."""
    result = []
    for obj in _iter_objects(scene):
        if is_tagged(obj):
            continue
        if geometry_only and getattr(obj, "type", None) not in measure.GEOMETRY_TYPES:
            continue
        result.append(obj)
    return result


def objects_with_tag(scene, name):
    wanted = (name or "").strip().lower()
    return [
        obj
        for obj in _iter_objects(scene)
        if any(t.name.strip().lower() == wanted for t in get_tags(obj))
    ]


def objects_in_category(scene, category):
    return [
        obj
        for obj in _iter_objects(scene)
        if any(t.category == category for t in get_tags(obj))
    ]


def all_tag_names(scene, include_library=True):
    """Sorted, de-duplicated tag names used in the project."""
    names = {}
    if include_library:
        for entry in library_tags(scene):
            names.setdefault(entry.name.strip().lower(), entry.name)
    for obj in _iter_objects(scene):
        for tag in get_tags(obj):
            names.setdefault(tag.name.strip().lower(), tag.name)
    return [names[key] for key in sorted(names)]


# ---------------------------------------------------------------------------
# Costing
# ---------------------------------------------------------------------------

def unit_context(scene) -> units.UnitContext:
    """Unit/currency context for ``scene``."""
    data = project(scene)
    if data is None:
        return units.context_from_scene(scene)
    return units.context_from_scene(
        scene,
        currency=data.currency,
        decimals=data.currency_decimals,
        basis=data.unit_basis,
    )


def resolve_tag(tag, scene):
    """Apply library inheritance to ``tag``."""
    return costing.resolve(tag, library_lookup(scene))


def resolve_tags(obj, scene):
    lookup = library_lookup(scene)
    return [costing.resolve(tag, lookup) for tag in get_tags(obj)]


def measure_object(obj, context=None):
    """Cached take-off for ``obj`` in Blender units."""
    return measure.measure_object(obj, measure.depsgraph_for(context))


def tag_cost(obj, tag, scene, context=None):
    """Cost of a single tag on a single object."""
    resolved = resolve_tag(tag, scene)
    return costing.cost_of(resolved, measure_object(obj, context), unit_context(scene))


@dataclass
class ObjectCost:
    """Cost breakdown for one object."""

    object_name: str
    amount: float = 0.0
    results: tuple = ()

    def __iter__(self):
        return iter(self.results)


def object_cost(obj, scene, context=None) -> ObjectCost:
    """Total cost of every tag on ``obj``."""
    ctx = unit_context(scene)
    measurements = measure_object(obj, context)
    lookup = library_lookup(scene)
    results = []
    for tag in get_tags(obj):
        resolved = costing.resolve(tag, lookup)
        results.append(costing.cost_of(resolved, measurements, ctx))
    return ObjectCost(
        object_name=getattr(obj, "name", ""),
        amount=sum(r.amount for r in results),
        results=tuple(results),
    )


def cost_entries(scene, objects=None, context=None):
    """``(object_name, ResolvedTag, CostResult)`` for every tag in the project."""
    ctx = unit_context(scene)
    lookup = library_lookup(scene)
    depsgraph = measure.depsgraph_for(context)
    if objects is None:
        objects = tagged_objects(scene)
    entries = []
    for obj in objects:
        measurements = measure.measure_object(obj, depsgraph)
        for tag in get_tags(obj):
            resolved = costing.resolve(tag, lookup)
            entries.append(
                (getattr(obj, "name", ""), resolved, costing.cost_of(resolved, measurements, ctx))
            )
    return entries


def cost_rollup(scene, objects=None, context=None):
    """Per-tag totals for the project (sorted most expensive first)."""
    return costing.rollup(cost_entries(scene, objects, context))


def project_total(scene, objects=None, context=None) -> float:
    return costing.total_amount(cost_entries(scene, objects, context))
