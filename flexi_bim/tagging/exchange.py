"""Serialisation: CSV cost schedules and JSON tag exchange.

The JSON format is intentionally flat and readable so tag libraries can be
shared between projects (and eventually mapped onto IFC property sets).
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

FORMAT_VERSION = 1


# ---------------------------------------------------------------------------
# CSV schedule
# ---------------------------------------------------------------------------

def schedule_rows(scene, objects=None, context=None, per_object=False):
    """Rows (header first) for the cost schedule."""
    ctx = api.unit_context(scene)
    entries = api.cost_entries(scene, objects, context)

    if per_object:
        header = [
            "Object", "Tag", "Category", "Source", "Cost Mode", "Measured By",
            "Quantity", "Unit", "Waste %", "Rate", "Amount", "Properties", "Notes",
        ]
        rows = [header]
        for object_name, resolved, result in entries:
            rows.append([
                object_name,
                resolved.name,
                resolved.category,
                resolved.source,
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


def _tag_to_dict(tag, include_source=True):
    data = {
        "name": tag.name,
        "category": tag.category,
        "description": tag.description,
        "cost": _cost_to_dict(tag.cost),
        "properties": _properties_to_list(tag.properties),
    }
    if include_source:
        data["source"] = getattr(tag, "source", C.SOURCE_LOCAL)
    return data


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
        "library": [
            _tag_to_dict(entry, include_source=False) for entry in api.library_tags(scene)
        ],
        "objects": [
            {
                "name": obj.name,
                "tags": [_tag_to_dict(tag) for tag in api.get_tags(obj)],
            }
            for obj in objects
        ],
    }


def dumps(scene, objects=None, indent=2) -> str:
    return json.dumps(to_dict(scene, objects), indent=indent)


def _apply_cost(target, data):
    if not isinstance(data, dict):
        return
    mapping = {
        "mode": ("mode", str, [m[0] for m in C.COST_MODE_ITEMS]),
        "measurement": ("measurement", str, [m[0] for m in C.MEASURE_ITEMS]),
        "quantity_source": ("quantity_source", str, [m[0] for m in C.QUANTITY_SOURCE_ITEMS]),
    }
    for key, (attr, _caster, allowed) in mapping.items():
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
    source = data.get("source")
    if hasattr(target, "source") and source in {s[0] for s in C.TAG_SOURCE_ITEMS}:
        target.source = source
    _apply_cost(target.cost, data.get("cost"))
    _apply_properties(target, data.get("properties"))


def from_dict(scene, data, *, library_only=False, replace=False) -> dict:
    """Load tags from a parsed JSON payload. Returns import counts."""
    if not isinstance(data, dict) or data.get("format") != "flexibim-tags":
        raise ValueError("Not a FlexiBIM tag file")
    if int(data.get("version", 0)) > FORMAT_VERSION:
        raise ValueError("Tag file was written by a newer version of FlexiBIM")

    project = api.project(scene)
    stats = {"library": 0, "tags": 0, "objects": 0, "missing": 0}

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
            project.library.clear()
        for entry_data in data.get("library") or ():
            if not isinstance(entry_data, dict):
                continue
            name = str(entry_data.get("name", ""))
            existing = api.get_library_tag(scene, name)
            entry = existing if existing is not None else project.library.add()
            _apply_tag(entry, entry_data)
            entry.previous_name = entry.name
            stats["library"] += 1

    if not library_only:
        by_name = {obj.name: obj for obj in api.all_objects(scene)}
        for object_data in data.get("objects") or ():
            if not isinstance(object_data, dict):
                continue
            obj = by_name.get(object_data.get("name"))
            if obj is None:
                stats["missing"] += 1
                continue
            holder = api.object_data(obj)
            if holder is None:
                stats["missing"] += 1
                continue
            if replace:
                holder.tags.clear()
            for tag_data in object_data.get("tags") or ():
                if not isinstance(tag_data, dict):
                    continue
                name = str(tag_data.get("name", ""))
                existing = api.get_tag(obj, name)
                tag = existing if existing is not None else holder.tags.add()
                _apply_tag(tag, tag_data)
                stats["tags"] += 1
            stats["objects"] += 1

    measure.invalidate_costs()
    return stats


def loads(scene, text, *, library_only=False, replace=False) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {error}") from error
    return from_dict(scene, payload, library_only=library_only, replace=replace)


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
