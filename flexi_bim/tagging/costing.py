"""Tag resolution and cost arithmetic.

Kept free of ``bpy`` so the money maths can be tested directly.  The functions
here accept duck-typed property groups (anything exposing the same attribute
names) which makes them equally usable from Blender and from tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import quantities as qty
from ..core import units
from . import constants as C


@dataclass
class CostSpec:
    """The effective cost definition of a tag, after library inheritance."""

    mode: str = C.COST_MODE_NONE
    rate: float = 0.0
    measurement: str = C.MEASURE_COUNT
    quantity_source: str = C.QUANTITY_AUTO
    manual_quantity: float = 0.0
    waste_percent: float = 0.0

    @property
    def dimension(self) -> int:
        return C.measure_dimension(self.measurement)


@dataclass
class ResolvedTag:
    """A tag definition in a form that is ready for costing/scheduling."""

    name: str
    category: str = "NONE"
    description: str = ""
    cost: CostSpec = field(default_factory=CostSpec)
    properties: dict = field(default_factory=dict)
    #: True when an object references a tag that no longer exists.
    missing: bool = False


@dataclass
class CostResult:
    """Outcome of costing one tag on one object."""

    tag_name: str
    amount: float = 0.0
    #: Quantity in project units *before* the waste factor.
    quantity: float = 0.0
    #: Quantity actually charged (``quantity`` plus waste).
    charged_quantity: float = 0.0
    measurement: str = C.MEASURE_COUNT
    mode: str = C.COST_MODE_NONE
    rate: float = 0.0
    dimension: int = units.DIMENSION_COUNT
    #: Human readable reason the cost is zero/unknown, if any.
    note: str = ""

    @property
    def priced(self) -> bool:
        return self.mode != C.COST_MODE_NONE


# ---------------------------------------------------------------------------
# Reading property groups
# ---------------------------------------------------------------------------

def cost_spec_from(holder) -> CostSpec:
    """Read a :class:`CostSpec` off a ``FlexiBIMCost`` property group."""
    if holder is None:
        return CostSpec()
    return CostSpec(
        mode=getattr(holder, "mode", C.COST_MODE_NONE),
        rate=float(getattr(holder, "rate", 0.0) or 0.0),
        measurement=getattr(holder, "measurement", C.MEASURE_COUNT),
        quantity_source=getattr(holder, "quantity_source", C.QUANTITY_AUTO),
        manual_quantity=float(getattr(holder, "manual_quantity", 0.0) or 0.0),
        waste_percent=float(getattr(holder, "waste_percent", 0.0) or 0.0),
    )


def properties_from(collection) -> dict:
    """Flatten a collection of key/value property groups into a dict.

    Later entries win, blank keys are skipped, and values are cast according
    to the declared value type.
    """
    result = {}
    for item in collection or ():
        key = (getattr(item, "key", "") or "").strip()
        if not key:
            continue
        result[key] = property_value(item)
    return result


def property_value(item):
    """Cast a custom property group's value to its declared type."""
    value_type = getattr(item, "value_type", C.PROP_TEXT)
    raw = getattr(item, "value", "")
    if value_type == C.PROP_NUMBER:
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return raw
        return int(number) if number.is_integer() else number
    if value_type == C.PROP_BOOL:
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}
    return raw


def resolve(tag) -> ResolvedTag:
    """Build a :class:`ResolvedTag` from a project tag definition."""
    name = (getattr(tag, "name", "") or "").strip()
    return ResolvedTag(
        name=name,
        category=getattr(tag, "category", "NONE"),
        description=getattr(tag, "description", ""),
        cost=cost_spec_from(getattr(tag, "cost", None)),
        properties=properties_from(getattr(tag, "properties", ())),
    )


# ---------------------------------------------------------------------------
# Costing
# ---------------------------------------------------------------------------

def quantity_for(spec: CostSpec, measurements: qty.Quantities, ctx: units.UnitContext) -> float:
    """Quantity for ``spec``, expressed in project units.

    Manual quantities are taken as already being in project units; automatic
    quantities are measured in Blender units and converted.
    """
    if spec.mode == C.COST_MODE_FLAT:
        return 1.0
    if spec.quantity_source == C.QUANTITY_MANUAL:
        return float(spec.manual_quantity)
    if measurements is None:
        return 0.0
    field_name = C.MEASURE_FIELDS.get(spec.measurement, "count")
    raw = float(getattr(measurements, field_name, 0.0) or 0.0)
    return units.convert(raw, spec.dimension, ctx)


def apply_waste(quantity: float, waste_percent: float) -> float:
    return quantity * (1.0 + max(-100.0, float(waste_percent)) / 100.0)


def cost_of(resolved: ResolvedTag, measurements, ctx: units.UnitContext) -> CostResult:
    """Price one resolved tag against one object's measurements."""
    spec = resolved.cost
    result = CostResult(
        tag_name=resolved.name,
        measurement=spec.measurement,
        mode=spec.mode,
        rate=spec.rate,
        dimension=spec.dimension,
    )

    if resolved.missing:
        result.note = f"No tag named '{resolved.name}' in the project"
        return result

    if spec.mode == C.COST_MODE_NONE:
        result.note = "No cost defined"
        return result

    if spec.mode == C.COST_MODE_FLAT:
        result.quantity = 1.0
        result.charged_quantity = 1.0
        result.dimension = units.DIMENSION_COUNT
        result.amount = float(spec.rate)
        return result

    quantity = quantity_for(spec, measurements, ctx)
    charged = apply_waste(quantity, spec.waste_percent)
    result.quantity = quantity
    result.charged_quantity = charged
    result.amount = charged * float(spec.rate)
    if spec.quantity_source == C.QUANTITY_AUTO and measurements is None:
        result.note = "Object has no measurable geometry"
    return result


@dataclass
class RollupRow:
    """Aggregated totals for one tag name across the project."""

    name: str
    category: str = "NONE"
    object_count: int = 0
    quantity: float = 0.0
    charged_quantity: float = 0.0
    amount: float = 0.0
    measurement: str = C.MEASURE_COUNT
    dimension: int = units.DIMENSION_COUNT
    mode: str = C.COST_MODE_NONE
    #: True when the same tag name was costed with different measurements.
    mixed_units: bool = False
    notes: tuple = ()


def rollup(entries) -> list:
    """Aggregate ``(object_name, ResolvedTag, CostResult)`` triples by tag name.

    Rows come back sorted by descending cost so the expensive items lead the
    schedule, with untagged-cost rows last.
    """
    rows = {}
    order = []
    notes = {}
    for _obj_name, resolved, result in entries:
        key = resolved.name
        row = rows.get(key)
        if row is None:
            row = RollupRow(
                name=key,
                category=resolved.category,
                measurement=result.measurement,
                dimension=result.dimension,
                mode=result.mode,
            )
            rows[key] = row
            order.append(key)
            notes[key] = []
        row.object_count += 1
        row.amount += result.amount
        if row.mode == C.COST_MODE_NONE and result.priced:
            # The first priced instance defines the row's units.
            row.mode = result.mode
            row.measurement = result.measurement
            row.dimension = result.dimension
        elif result.priced and (
            result.measurement != row.measurement or result.mode != row.mode
        ):
            row.mixed_units = True
        if not row.mixed_units:
            row.quantity += result.quantity
            row.charged_quantity += result.charged_quantity
        if result.note and result.note not in notes[key]:
            notes[key].append(result.note)

    for key, row in rows.items():
        row.notes = tuple(notes[key])

    return sorted(
        (rows[k] for k in order),
        key=lambda r: (-r.amount, r.name.lower()),
    )


def total_amount(entries) -> float:
    return sum(result.amount for _name, _resolved, result in entries)
