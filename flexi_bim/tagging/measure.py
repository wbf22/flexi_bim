"""Measuring Blender objects, with caching.

Take-off runs on the *evaluated* object so modifiers (solidify, array,
booleans...) are included, which is what a quantity surveyor would expect.
Results are cached per object and invalidated from a depsgraph handler, so the
cost panels can redraw without re-measuring the whole scene every frame.
"""

from __future__ import annotations

import bpy

from ..core import quantities as qty

#: session_uid -> (signature, Quantities)
_quantity_cache = {}

#: Memoised cost rollups, cleared whenever anything relevant changes.
_cost_cache = {}

#: Object types we can pull a mesh out of.
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


# ---------------------------------------------------------------------------
# Cache control
# ---------------------------------------------------------------------------

def invalidate_costs():
    """Drop memoised cost rollups (cheap, called from property updates)."""
    _cost_cache.clear()


def invalidate(obj=None):
    """Drop cached measurements for ``obj``, or for everything."""
    if obj is None:
        _quantity_cache.clear()
    else:
        _quantity_cache.pop(_cache_key(obj), None)
    invalidate_costs()


def cost_cache():
    return _cost_cache


def _cache_key(obj):
    uid = getattr(obj, "session_uid", None)
    return uid if uid is not None else getattr(obj, "name", id(obj))


def _signature(obj):
    """Cheap fingerprint that changes when the take-off would change."""
    data = getattr(obj, "data", None)
    matrix = getattr(obj, "matrix_world", None)
    try:
        matrix_sig = tuple(round(v, 6) for row in matrix for v in row)
    except TypeError:
        matrix_sig = ()
    verts = len(getattr(data, "vertices", ())) if data is not None else 0
    polys = len(getattr(data, "polygons", ())) if data is not None else 0
    modifiers = len(getattr(obj, "modifiers", ()) or ())
    return (
        getattr(obj, "type", ""),
        getattr(data, "name", ""),
        verts,
        polys,
        modifiers,
        matrix_sig,
    )


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _needs_evaluation(obj):
    """True when the take-off has to go through the dependency graph.

    A plain mesh with no modifiers can be read straight off ``obj.data``, which
    avoids allocating a temporary mesh on every measurement - worth doing
    because measuring can happen while a panel is redrawing.
    """
    if getattr(obj, "type", None) != "MESH":
        return True
    modifiers = getattr(obj, "modifiers", None) or ()
    return any(getattr(m, "show_viewport", True) for m in modifiers)


def _world_geometry(obj, depsgraph=None):
    """Return ``(vertices, polygons, edges)`` in world space, or ``None``."""
    if obj is None or getattr(obj, "type", None) not in GEOMETRY_TYPES:
        return None

    temp_mesh = None
    if not _needs_evaluation(obj):
        mesh = getattr(obj, "data", None)
    else:
        evaluated = obj
        if depsgraph is not None:
            try:
                evaluated = obj.evaluated_get(depsgraph)
            except (AttributeError, RuntimeError):
                evaluated = obj
        try:
            mesh = evaluated.to_mesh()
            temp_mesh = evaluated
        except (AttributeError, RuntimeError):
            # Curves/text with nothing to convert, or an unsupported type.
            mesh = getattr(obj, "data", None)

    if mesh is None or not hasattr(mesh, "vertices"):
        return None

    try:
        matrix = obj.matrix_world
        vertices = [tuple(matrix @ v.co) for v in mesh.vertices]
        polygons = [tuple(p.vertices) for p in getattr(mesh, "polygons", ())]
        edges = [tuple(e.vertices) for e in getattr(mesh, "edges", ())]
    finally:
        if temp_mesh is not None:
            try:
                temp_mesh.to_mesh_clear()
            except (AttributeError, RuntimeError):
                pass

    return vertices, polygons, edges


def world_geometry(obj, depsgraph=None):
    """Public accessor for world-space ``(vertices, polygons, edges)``.

    Used by the drawing extractor.  Returns ``None`` when the object has no
    geometry we can pull out.
    """
    return _world_geometry(obj, depsgraph)


def measure_object(obj, depsgraph=None, use_cache=True):
    """Take off every quantity for ``obj``; ``None`` if it has no geometry."""
    if obj is None:
        return None

    key = _cache_key(obj)
    signature = _signature(obj)
    if use_cache:
        cached = _quantity_cache.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]

    geometry = _world_geometry(obj, depsgraph)
    if geometry is None:
        # Empties, lights and cameras can still carry flat-rate / manual tags.
        result = None
    else:
        vertices, polygons, edges = geometry
        result = qty.measure(vertices, polygons, edges)

    if use_cache:
        _quantity_cache[key] = (signature, result)
    return result


def depsgraph_for(context=None):
    """Best-effort evaluated depsgraph, tolerating headless/odd contexts."""
    context = context or getattr(bpy, "context", None)
    if context is None:
        return None
    getter = getattr(context, "evaluated_depsgraph_get", None)
    if getter is None:
        return None
    try:
        return getter()
    except (AttributeError, RuntimeError):
        return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph=None):
    """Invalidate cached take-offs for objects Blender just changed."""
    if depsgraph is None:
        invalidate()
        return
    dirty = False
    for update in getattr(depsgraph, "updates", ()):
        id_block = getattr(update, "id", None)
        if isinstance(id_block, bpy.types.Object):
            if update.is_updated_geometry or update.is_updated_transform:
                _quantity_cache.pop(_cache_key(id_block), None)
                dirty = True
        elif isinstance(id_block, bpy.types.Mesh):
            # Mesh edits arrive without the owning object; be conservative.
            _quantity_cache.clear()
            dirty = True
    if dirty:
        invalidate_costs()


@bpy.app.handlers.persistent
def _on_load(*_args):
    invalidate()


def register():
    handlers = bpy.app.handlers
    if _on_depsgraph_update not in handlers.depsgraph_update_post:
        handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load not in handlers.load_post:
        handlers.load_post.append(_on_load)


def unregister():
    handlers = bpy.app.handlers
    if _on_depsgraph_update in handlers.depsgraph_update_post:
        handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load in handlers.load_post:
        handlers.load_post.remove(_on_load)
    invalidate()
