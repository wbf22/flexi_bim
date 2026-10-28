"""Public Python API for the tagging system.

Every tag is a single, project-wide definition stored in the tag registry
(``scene.flexibim.tags``).  Objects **reference** tags by name, so there is no
local/library distinction: editing a tag in one place updates every object that
uses it.

    from flexi_bim.tagging import api

    api.create_tag(scene, "Exterior Wall", category="WALL")
    api.set_property(api.get_tag(scene, "Exterior Wall"), "Fire Rating", "1 hr")
    api.apply_tag(obj, "Exterior Wall")
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


def _tag_name(value):
    if isinstance(value, str):
        return value.strip()
    return (getattr(value, "name", "") or "").strip()


# ---------------------------------------------------------------------------
# Tag registry
# ---------------------------------------------------------------------------

def all_tags(scene):
    """Every tag definition in the project, in registry order."""
    data = project(scene)
    return list(data.tags) if data is not None else []


def get_tag(scene, name):
    """The project tag named ``name`` (case-insensitive), else ``None``."""
    wanted = _tag_name(name).lower()
    if not wanted:
        return None
    for entry in all_tags(scene):
        if entry.name.strip().lower() == wanted:
            return entry
    return None


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


def create_tag(scene, name="Tag", *, category=None, description=None):
    """Add a new tag definition to the registry and return it."""
    data = project(scene)
    if data is None:
        return None
    clean = _tag_name(name) or "Tag"
    if get_tag(scene, clean) is not None:
        clean = unique_tag_name([e.name for e in data.tags], clean)
    entry = data.tags.add()
    with _props.suspend_rename_propagation():
        entry.name = clean
    entry.previous_name = clean
    if category is not None:
        entry.category = category
    if description is not None:
        entry.description = description
    data.active_tag_index = len(data.tags) - 1
    measure.invalidate_costs()
    return entry


def ensure_tag(scene, name, *, category=None, description=None):
    """Return the tag named ``name``, creating it if it does not exist yet."""
    existing = get_tag(scene, name)
    if existing is not None:
        return existing
    return create_tag(scene, name, category=category, description=description)


def delete_tag(scene, name) -> bool:
    """Remove a tag definition and strip every object reference to it."""
    data = project(scene)
    if data is None:
        return False
    wanted = _tag_name(name).lower()
    for index, entry in enumerate(data.tags):
        if entry.name.strip().lower() == wanted:
            removed_name = entry.name
            data.tags.remove(index)
            data.active_tag_index = min(
                max(0, index - 1), max(0, len(data.tags) - 1)
            )
            rename_tag_references(scene, removed_name, None, previous=wanted)
            measure.invalidate_costs()
            return True
    return False


def rename_tag_references(scene, old_name, new_name, *, previous=None) -> int:
    """Point object references at ``new_name`` instead of ``old_name``.

    Called when a tag is renamed (pass the new name) or deleted (pass ``None``,
    which strips the reference).  ``previous`` lets a delete pass the already
    matching lower-case name.
    """
    wanted = previous if previous is not None else (old_name or "").strip().lower()
    if not wanted:
        return 0
    changed = 0
    for obj in _iter_objects(scene):
        data = object_data(obj)
        if data is None:
            continue
        for index in range(len(data.tags) - 1, -1, -1):
            ref = data.tags[index]
            if ref.name.strip().lower() != wanted:
                continue
            if new_name is None:
                data.tags.remove(index)
            else:
                ref.name = new_name
            changed += 1
        data.active_tag_index = min(
            data.active_tag_index, max(0, len(data.tags) - 1)
        )
    if changed:
        measure.invalidate_costs()
    return changed


# ---------------------------------------------------------------------------
# Applied tags (object <-> registry references)
# ---------------------------------------------------------------------------

def applied_tags(obj):
    """The tag references on ``obj`` (empty when untagged)."""
    data = object_data(obj)
    return list(data.tags) if data is not None else []


def applied_tag_names(obj):
    return [ref.name for ref in applied_tags(obj)]


def get_applied(obj, name):
    """The reference on ``obj`` matching ``name``, else ``None``."""
    wanted = _tag_name(name).lower()
    for ref in applied_tags(obj):
        if ref.name.strip().lower() == wanted:
            return ref
    return None


def has_tag(obj, name) -> bool:
    return get_applied(obj, name) is not None


def is_tagged(obj) -> bool:
    data = object_data(obj)
    return bool(data is not None and len(data.tags))


def apply_tag(obj, name, *, create=True, category=None, description=None):
    """Tag ``obj`` with the tag named ``name`` and return the reference.

    The tag definition is created in the registry first when ``create`` is set
    (the default), so the same tag is available to apply to other objects.
    Applying a tag an object already carries is a no-op.
    """
    data = object_data(obj)
    if data is None:
        return None
    clean = _tag_name(name) or "Tag"
    if create:
        ensure_tag(_scene_for(obj), clean, category=category, description=description)
    ref = get_applied(obj, clean)
    if ref is not None:
        return ref
    ref = data.tags.add()
    ref.name = clean
    data.active_tag_index = len(data.tags) - 1
    measure.invalidate_costs()
    return ref


def unapply_tag(obj, name) -> bool:
    """Remove the first reference to ``name`` on ``obj``."""
    data = object_data(obj)
    if data is None:
        return False
    wanted = _tag_name(name).lower()
    for index, ref in enumerate(data.tags):
        if ref.name.strip().lower() == wanted:
            return unapply_tag_at(obj, index)
    return False


def unapply_tag_at(obj, index) -> bool:
    data = object_data(obj)
    if data is None or not (0 <= index < len(data.tags)):
        return False
    data.tags.remove(index)
    data.active_tag_index = min(max(0, index - 1), max(0, len(data.tags) - 1))
    measure.invalidate_costs()
    return True


def clear_tags(obj) -> int:
    """Remove every tag reference from ``obj``; returns how many were removed."""
    data = object_data(obj)
    if data is None:
        return 0
    count = len(data.tags)
    data.tags.clear()
    data.active_tag_index = 0
    measure.invalidate_costs()
    return count


def object_tags(obj, scene):
    """The tag definitions applied to ``obj`` (references resolved)."""
    result = []
    for ref in applied_tags(obj):
        definition = get_tag(scene, ref.name)
        if definition is not None:
            result.append(definition)
    return result


# ---------------------------------------------------------------------------
# Custom properties
# ---------------------------------------------------------------------------

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
    """Copy a tag definition onto another (duplicate/import).

    The name is assigned programmatically, so rename propagation is suspended:
    copying a definition must never re-point other objects' references.
    """
    with _props.suspend_rename_propagation():
        target.name = source.name
        target.category = getattr(source, "category", "NONE")
        target.description = getattr(source, "description", "")
        if hasattr(target, "color") and hasattr(source, "color"):
            target.color = tuple(source.color)
        copy_cost(source.cost, target.cost)
        copy_properties(source.properties, target.properties)
    measure.invalidate_costs()
    return target


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


def _scene_for(obj):
    """The scene an object belongs to, falling back to the active scene."""
    scenes = getattr(obj, "users_scene", None)
    if scenes:
        return scenes[0]
    return _active_scene()


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
    wanted = _tag_name(name).lower()
    return [
        obj
        for obj in _iter_objects(scene)
        if any(ref.name.strip().lower() == wanted for ref in applied_tags(obj))
    ]


def objects_in_category(scene, category):
    return [
        obj
        for obj in _iter_objects(scene)
        if any(tag.category == category for tag in object_tags(obj, scene))
    ]


def all_tag_names(scene):
    """Sorted, de-duplicated tag names in the project registry."""
    names = {entry.name.strip().lower(): entry.name for entry in all_tags(scene)}
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


def resolve_tag(scene, tag) -> costing.ResolvedTag:
    """Resolve a tag reference (or definition, or name) to a ``ResolvedTag``."""
    if tag is None:
        return costing.ResolvedTag(name="")
    if isinstance(tag, str):
        definition = get_tag(scene, tag)
        return (
            costing.resolve(definition)
            if definition is not None
            else costing.ResolvedTag(name=tag, missing=True)
        )
    if hasattr(tag, "cost"):
        return costing.resolve(tag)
    definition = get_tag(scene, _tag_name(tag))
    if definition is not None:
        return costing.resolve(definition)
    return costing.ResolvedTag(name=_tag_name(tag), missing=True)


def resolve_tags(obj, scene):
    return [resolve_tag(scene, ref) for ref in applied_tags(obj)]


def measure_object(obj, context=None):
    """Cached take-off for ``obj`` in Blender units."""
    return measure.measure_object(obj, measure.depsgraph_for(context))


def tag_cost(obj, tag, scene, context=None):
    """Cost of a single tag on a single object."""
    resolved = resolve_tag(scene, tag)
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
    results = [
        costing.cost_of(resolve_tag(scene, ref), measurements, ctx)
        for ref in applied_tags(obj)
    ]
    return ObjectCost(
        object_name=getattr(obj, "name", ""),
        amount=sum(r.amount for r in results),
        results=tuple(results),
    )


def cost_entries(scene, objects=None, context=None):
    """``(object_name, ResolvedTag, CostResult)`` for every tag in the project."""
    ctx = unit_context(scene)
    depsgraph = measure.depsgraph_for(context)
    if objects is None:
        objects = tagged_objects(scene)
    entries = []
    for obj in objects:
        measurements = measure.measure_object(obj, depsgraph)
        for ref in applied_tags(obj):
            resolved = resolve_tag(scene, ref)
            entries.append(
                (getattr(obj, "name", ""), resolved, costing.cost_of(resolved, measurements, ctx))
            )
    return entries


def cost_rollup(scene, objects=None, context=None):
    """Per-tag totals for the project (sorted most expensive first)."""
    return costing.rollup(cost_entries(scene, objects, context))


def project_total(scene, objects=None, context=None) -> float:
    return costing.total_amount(cost_entries(scene, objects, context))
