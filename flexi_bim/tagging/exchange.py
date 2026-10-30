"""Serialisation: CSV cost schedules and JSON tag exchange.

The JSON format is intentionally flat and readable so whole tag registries can
be shared between projects (and eventually mapped onto IFC property sets).  It
stores each tag definition once, plus the list of tag names applied to each
object.
"""

from __future__ import annotations

import csv
import io
import json

from ..core import units
from . import api
from . import constants as C
from . import costing
from . import measure
from . import props

FORMAT_VERSION = 2


# ---------------------------------------------------------------------------
# CSV schedule
# ---------------------------------------------------------------------------

def schedule_rows(scene, objects=None, context=None, per_object=False):
    """Rows (header first) for the cost schedule."""
    ctx = api.unit_context(scene)
    entries = api.cost_entries(scene, objects, context)

    if per_object:
        header = [
            "Object", "Tag", "Category", "Cost Mode", "Measured By",
            "Quantity", "Unit", "Waste %", "Rate", "Amount", "Properties", "Notes",
        ]
        rows = [header]
        for object_name, resolved, result in entries:
            rows.append([
                object_name,
                resolved.name,
                resolved.category,
                result.mode,
                result.measurement if result.mode == C.COST_MODE_MEASURED else "",
                _number(result.charged_quantity),
                ctx.suffix(result.dimension) if result.priced else "",
                _number(resolved.cost.waste_percent),
                _number(result.rate),
                _number(result.amount),
                _properties_text(resolved.properties),
                result.note,
            ])
        return rows

    header = ["Tag", "Category", "Objects", "Quantity", "Unit", "Rate", "Amount", "Notes"]
    rows = [header]
    for row in costing.rollup(entries):
        rows.append([
            row.name,
            row.category,
            row.object_count,
            "" if row.mixed_units else _number(row.charged_quantity),
            "mixed" if row.mixed_units else (ctx.suffix(row.dimension) if row.mode != C.COST_MODE_NONE else ""),
            _number_or_blank(_uniform_rate(entries, row.name)),
            _number(row.amount),
            "; ".join(row.notes),
        ])
    rows.append(["TOTAL", "", "", "", "", "", _number(costing.total_amount(entries)), ""])
    return rows


def _uniform_rate(entries, tag_name):
    """Rate for a tag when every instance shares one, else ``None`` (mixed)."""
    rates = {
        result.rate
        for _obj, resolved, result in entries
        if resolved.name == tag_name and result.priced
    }
    return rates.pop() if len(rates) == 1 else None


def _number_or_blank(value):
    return "" if value is None else _number(value)


def _number(value):
    value = float(value or 0.0)
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _properties_text(properties):
    return "; ".join(f"{key}={value}" for key, value in sorted(properties.items()))


def schedule_csv(scene, objects=None, context=None, per_object=False) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(schedule_rows(scene, objects, context, per_object))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def _cost_to_dict(cost):
    return {
        "mode": cost.mode,
        "rate": round(float(cost.rate), 6),
        "measurement": cost.measurement,
        "quantity_source": cost.quantity_source,
        "manual_quantity": round(float(cost.manual_quantity), 6),
        "waste_percent": round(float(cost.waste_percent), 6),
    }


def _properties_to_list(properties):
    return [
        {"key": item.key, "value": item.value, "type": item.value_type}
        for item in properties
    ]


def _tag_to_dict(tag):
    return {
        "name": tag.name,
        "category": tag.category,
        "description": tag.description,
        "color": [round(float(c), 4) for c in getattr(tag, "color", ())],
        "fill": getattr(tag, "fill", C.FILL_NONE),
        "fill_spacing": round(float(getattr(tag, "fill_spacing", 3.0)), 3),
        "fill_angle": round(float(getattr(tag, "fill_angle", 45.0)), 3),
        "cost": _cost_to_dict(tag.cost),
        "properties": _properties_to_list(tag.properties),
    }


def to_dict(scene, objects=None) -> dict:
    project = api.project(scene)
    if objects is None:
        objects = api.tagged_objects(scene)
    return {
        "format": "flexibim-tags",
        "version": FORMAT_VERSION,
        "project": {
            "currency": project.currency if project else "$",
            "currency_decimals": project.currency_decimals if project else 2,
            "unit_basis": project.unit_basis if project else "PROJECT",
        },
        "tags": [_tag_to_dict(entry) for entry in api.all_tags(scene)],
        "objects": [
            {"name": obj.name, "tags": api.applied_tag_names(obj)}
            for obj in objects
        ],
    }


def dumps(scene, objects=None, indent=2) -> str:
    return json.dumps(to_dict(scene, objects), indent=indent)


def _apply_cost(target, data):
    if not isinstance(data, dict):
        return
    mapping = {
        "mode": ("mode", [m[0] for m in C.COST_MODE_ITEMS]),
        "measurement": ("measurement", [m[0] for m in C.MEASURE_ITEMS]),
        "quantity_source": ("quantity_source", [m[0] for m in C.QUANTITY_SOURCE_ITEMS]),
    }
    for key, (attr, allowed) in mapping.items():
        value = data.get(key)
        if value in allowed:
            setattr(target, attr, value)
    for key in ("rate", "manual_quantity", "waste_percent"):
        if key in data:
            try:
                setattr(target, key, float(data[key]))
            except (TypeError, ValueError):
                pass


def _apply_properties(target, items):
    target.properties.clear()
    for entry in items or ():
        if not isinstance(entry, dict):
            continue
        item = target.properties.add()
        item.key = str(entry.get("key", ""))
        item.value = str(entry.get("value", ""))
        value_type = entry.get("type", C.PROP_TEXT)
        if value_type in {p[0] for p in C.PROP_TYPE_ITEMS}:
            item.value_type = value_type


def _apply_tag(target, data):
    with props.suspend_rename_propagation():
        target.name = str(data.get("name", "Tag")) or "Tag"
    category = data.get("category")
    if category in {c[0] for c in C.CATEGORY_ITEMS}:
        target.category = category
    target.description = str(data.get("description", ""))
    color = data.get("color")
    if isinstance(color, (list, tuple)) and len(color) == 3 and hasattr(target, "color"):
        try:
            target.color = tuple(float(c) for c in color)
        except (TypeError, ValueError):
            pass
    if data.get("fill") in {item[0] for item in C.FILL_ITEMS}:
        target.fill = data["fill"]
    for key in ("fill_spacing", "fill_angle"):
        if key in data:
            try:
                setattr(target, key, float(data[key]))
            except (TypeError, ValueError):
                pass
    _apply_cost(target.cost, data.get("cost"))
    _apply_properties(target, data.get("properties"))


def from_dict(scene, data, *, tags_only=False, replace=False) -> dict:
    """Load tags from a parsed JSON payload. Returns import counts."""
    if not isinstance(data, dict) or data.get("format") != "flexibim-tags":
        raise ValueError("Not a FlexiBIM tag file")
    if int(data.get("version", 0)) > FORMAT_VERSION:
        raise ValueError("Tag file was written by a newer version of FlexiBIM")

    project = api.project(scene)
    stats = {"tags": 0, "applied": 0, "objects": 0, "missing": 0}

    settings = data.get("project") or {}
    if project is not None and isinstance(settings, dict):
        if "currency" in settings:
            project.currency = str(settings["currency"])
        if "currency_decimals" in settings:
            try:
                project.currency_decimals = int(settings["currency_decimals"])
            except (TypeError, ValueError):
                pass
        if settings.get("unit_basis") in {b[0] for b in C.UNIT_BASIS_ITEMS}:
            project.unit_basis = settings["unit_basis"]

    if project is not None:
        if replace:
            project.tags.clear()
        for entry_data in data.get("tags") or ():
            if not isinstance(entry_data, dict):
                continue
            name = str(entry_data.get("name", ""))
            existing = api.get_tag(scene, name)
            entry = existing if existing is not None else project.tags.add()
            _apply_tag(entry, entry_data)
            entry.previous_name = entry.name
            stats["tags"] += 1

    if not tags_only:
        by_name = {obj.name: obj for obj in api.all_objects(scene)}
        for object_data in data.get("objects") or ():
            if not isinstance(object_data, dict):
                continue
            obj = by_name.get(object_data.get("name"))
            if obj is None or api.object_data(obj) is None:
                stats["missing"] += 1
                continue
            holder = api.object_data(obj)
            if replace:
                holder.tags.clear()
            for name in object_data.get("tags") or ():
                api.apply_tag(obj, str(name))
                stats["applied"] += 1
            stats["objects"] += 1

    measure.invalidate_costs()
    return stats


def loads(scene, text, *, tags_only=False, replace=False) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {error}") from error
    return from_dict(scene, payload, tags_only=tags_only, replace=replace)


# ---------------------------------------------------------------------------
# Text report (handy for the preflight panel and the console)
# ---------------------------------------------------------------------------

def summary_text(scene, objects=None, context=None) -> str:
    ctx = api.unit_context(scene)
    entries = api.cost_entries(scene, objects, context)
    lines = []
    for row in costing.rollup(entries):
        quantity = (
            "mixed units"
            if row.mixed_units
            else units.format_quantity(row.charged_quantity, row.dimension, ctx)
        )
        lines.append(
            f"{row.name}: {row.object_count} object(s), {quantity}, "
            f"{units.format_currency(row.amount, ctx)}"
        )
    lines.append(f"TOTAL: {units.format_currency(costing.total_amount(entries), ctx)}")
    return "\n".join(lines)
