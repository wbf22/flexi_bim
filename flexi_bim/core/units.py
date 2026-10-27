"""Project unit handling.

Quantities are measured in Blender units, but construction data (and therefore
cost rates) needs to be expressed in *project* units: square metres on a metric
job, square feet on an imperial one.

This module is deliberately free of any ``bpy`` import so the conversion and
formatting rules can be unit tested outside Blender.  The only contract with
Blender is :func:`context_from_scene`, which reads the duck-typed attributes
``scene.unit_settings.{system,length_unit,scale_length}``.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Length units
# ---------------------------------------------------------------------------

#: ``length_unit`` identifier -> (metres per unit, suffix)
LENGTH_UNITS = {
    "KILOMETERS": (1000.0, "km"),
    "METERS": (1.0, "m"),
    "CENTIMETERS": (0.01, "cm"),
    "MILLIMETERS": (0.001, "mm"),
    "MICROMETERS": (1e-6, "\u00b5m"),
    "MILES": (1609.344, "mi"),
    "FEET": (0.3048, "ft"),
    "INCHES": (0.0254, "in"),
    "THOU": (2.54e-5, "thou"),
}

#: Fallback when the scene uses an adaptive/unset length unit.
DEFAULT_LENGTH_UNIT = {
    "METRIC": "METERS",
    "IMPERIAL": "FEET",
    "NONE": "METERS",
}

#: Exponent applied to the length conversion factor for each measurement.
DIMENSION_COUNT = 0
DIMENSION_LENGTH = 1
DIMENSION_AREA = 2
DIMENSION_VOLUME = 3


@dataclass(frozen=True)
class UnitContext:
    """Everything needed to convert/format a quantity for a project."""

    system: str = "METRIC"
    length_unit: str = "METERS"
    #: Metres represented by one unit of ``length_unit``.
    meters_per_unit: float = 1.0
    #: ``scene.unit_settings.scale_length`` - metres per Blender unit.
    scale_length: float = 1.0
    currency: str = "$"
    decimals: int = 2

    @property
    def length_suffix(self) -> str:
        return LENGTH_UNITS.get(self.length_unit, (1.0, "m"))[1]

    @property
    def unitless(self) -> bool:
        """True when the scene has no unit system (raw Blender units)."""
        return self.system == "NONE"

    def factor(self, dimension: int) -> float:
        """Multiplier taking a Blender-unit value to project units."""
        if dimension == DIMENSION_COUNT:
            return 1.0
        per_bu = self.scale_length / self.meters_per_unit
        return per_bu**dimension

    def suffix(self, dimension: int) -> str:
        if dimension == DIMENSION_COUNT:
            return "ea"
        if self.unitless:
            base = "bu"
        else:
            base = self.length_suffix
        if dimension == DIMENSION_AREA:
            return base + "\u00b2"
        if dimension == DIMENSION_VOLUME:
            return base + "\u00b3"
        return base


def context_from_scene(scene, currency: str = "$", decimals: int = 2,
                       basis: str = "PROJECT") -> UnitContext:
    """Build a :class:`UnitContext` from a Blender scene.

    ``basis`` pins the quantity units so that flipping the scene's display
    units does not silently re-interpret every cost rate in the project:

    * ``PROJECT``  - follow ``scene.unit_settings`` (default)
    * ``METRIC``   - always metres
    * ``IMPERIAL`` - always feet
    """
    settings = getattr(scene, "unit_settings", None)
    system = getattr(settings, "system", "METRIC") or "METRIC"
    length_unit = getattr(settings, "length_unit", "METERS") or "METERS"
    try:
        scale_length = float(getattr(settings, "scale_length", 1.0) or 1.0)
    except (TypeError, ValueError):
        scale_length = 1.0
    if scale_length <= 0.0:
        scale_length = 1.0

    if basis == "METRIC":
        system, length_unit = "METRIC", "METERS"
    elif basis == "IMPERIAL":
        system, length_unit = "IMPERIAL", "FEET"

    if length_unit not in LENGTH_UNITS:
        # ADAPTIVE or an unknown identifier: pick a sane per-system default.
        length_unit = DEFAULT_LENGTH_UNIT.get(system, "METERS")

    if system == "NONE":
        # No unit system: treat Blender units as the project unit.
        meters_per_unit = scale_length
    else:
        meters_per_unit = LENGTH_UNITS[length_unit][0]

    return UnitContext(
        system=system,
        length_unit=length_unit,
        meters_per_unit=meters_per_unit,
        scale_length=scale_length,
        currency=currency or "",
        decimals=max(0, int(decimals)),
    )


def convert(value: float, dimension: int, ctx: UnitContext) -> float:
    """Convert ``value`` (Blender units) into project units."""
    return float(value) * ctx.factor(dimension)


def format_quantity(value: float, dimension: int, ctx: UnitContext,
                    precision: int = 2, with_suffix: bool = True) -> str:
    """Format an already-converted project-unit quantity."""
    if dimension == DIMENSION_COUNT:
        text = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    else:
        text = f"{value:,.{precision}f}"
    return f"{text} {ctx.suffix(dimension)}" if with_suffix else text


def format_currency(amount: float, ctx: UnitContext) -> str:
    symbol = ctx.currency or ""
    text = f"{amount:,.{ctx.decimals}f}"
    if not symbol:
        return text
    if symbol[-1].isalnum():  # e.g. "USD" / "SEK" read better after the number
        return f"{text} {symbol}"
    return f"{symbol}{text}"


def rate_suffix(dimension: int, ctx: UnitContext) -> str:
    """Label for a unit rate field, e.g. ``$/ft²``."""
    symbol = ctx.currency or ""
    return f"{symbol}/{ctx.suffix(dimension)}"
