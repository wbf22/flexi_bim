"""Enum identifiers and shared vocabulary for the tagging system."""

from __future__ import annotations

from ..core import units

# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

COST_MODE_NONE = "NONE"
COST_MODE_FLAT = "FLAT"
COST_MODE_MEASURED = "MEASURED"

COST_MODE_ITEMS = [
    (COST_MODE_NONE, "No Cost", "This tag carries no cost (informational only)", "BLANK1", 0),
    (COST_MODE_FLAT, "Flat Rate", "One lump sum per tagged object", "FUND", 1),
    (
        COST_MODE_MEASURED,
        "Per Unit",
        "Rate multiplied by a measured quantity in project units",
        "DRIVER_DISTANCE",
        2,
    ),
]

# Measurement identifiers -------------------------------------------------
MEASURE_COUNT = "COUNT"
MEASURE_LENGTH = "LENGTH"
MEASURE_PLAN_RUN = "PLAN_RUN"
MEASURE_EDGE_LENGTH = "EDGE_LENGTH"
MEASURE_AREA = "AREA"
MEASURE_WALL_AREA = "WALL_AREA"
MEASURE_FOOTPRINT = "FOOTPRINT"
MEASURE_VOLUME = "VOLUME"

MEASURE_ITEMS = [
    (MEASURE_COUNT, "Each", "One unit per tagged object", 0),
    (MEASURE_LENGTH, "Length", "Longest bounding-box extent (beam/wall run)", 1),
    (MEASURE_PLAN_RUN, "Plan Length", "Longest horizontal extent, ignoring height", 2),
    (MEASURE_EDGE_LENGTH, "Edge Length", "Sum of every edge (perimeters, linework)", 3),
    (
        MEASURE_WALL_AREA,
        "Face Area",
        "Length x height of the object - the elevation area of a wall or panel",
        4,
    ),
    (
        MEASURE_AREA,
        "Surface Area",
        "Total area of every face (both sides of a wall, plus its edges)",
        5,
    ),
    (MEASURE_FOOTPRINT, "Plan Area", "Top-down projected (footprint) area", 6),
    (MEASURE_VOLUME, "Volume", "Enclosed volume of the mesh", 7),
]

#: measurement -> attribute on :class:`flexi_bim.core.quantities.Quantities`
MEASURE_FIELDS = {
    MEASURE_COUNT: "count",
    MEASURE_LENGTH: "length",
    MEASURE_PLAN_RUN: "plan_run",
    MEASURE_EDGE_LENGTH: "edge_length",
    MEASURE_WALL_AREA: "wall_area",
    MEASURE_AREA: "surface_area",
    MEASURE_FOOTPRINT: "footprint_area",
    MEASURE_VOLUME: "volume",
}

#: measurement -> unit dimension used for conversion/labelling
MEASURE_DIMENSIONS = {
    MEASURE_COUNT: units.DIMENSION_COUNT,
    MEASURE_LENGTH: units.DIMENSION_LENGTH,
    MEASURE_PLAN_RUN: units.DIMENSION_LENGTH,
    MEASURE_EDGE_LENGTH: units.DIMENSION_LENGTH,
    MEASURE_WALL_AREA: units.DIMENSION_AREA,
    MEASURE_AREA: units.DIMENSION_AREA,
    MEASURE_FOOTPRINT: units.DIMENSION_AREA,
    MEASURE_VOLUME: units.DIMENSION_VOLUME,
}


def measure_dimension(measurement: str) -> int:
    return MEASURE_DIMENSIONS.get(measurement, units.DIMENSION_COUNT)


# Where the quantity comes from -------------------------------------------
QUANTITY_AUTO = "AUTO"
QUANTITY_MANUAL = "MANUAL"

QUANTITY_SOURCE_ITEMS = [
    (QUANTITY_AUTO, "From Geometry", "Measure the object and convert to project units", 0),
    (QUANTITY_MANUAL, "Manual", "Type the quantity by hand, in project units", 1),
]

# ---------------------------------------------------------------------------
# Tag plumbing
# ---------------------------------------------------------------------------

# Optional semantic type, the hook for Phase 1 of the roadmap.
CATEGORY_ITEMS = [
    ("NONE", "Unspecified", "No semantic type", 0),
    ("WALL", "Wall", "", 1),
    ("SLAB", "Slab / Floor", "", 2),
    ("ROOF", "Roof", "", 3),
    ("BEAM", "Beam", "", 4),
    ("COLUMN", "Column", "", 5),
    ("JOIST", "Joist / Rafter", "", 6),
    ("FOUNDATION", "Foundation", "", 7),
    ("DOOR", "Door", "", 8),
    ("WINDOW", "Window", "", 9),
    ("STAIR", "Stair", "", 10),
    ("ROOM", "Room / Space", "", 11),
    ("FIXTURE", "Fixture / Equipment", "", 12),
    ("FINISH", "Finish", "", 13),
    ("MEP", "Building Systems (MEP)", "", 14),
    ("SITE", "Site", "", 15),
    ("OTHER", "Other", "", 16),
]

CATEGORY_ICONS = {
    "NONE": "DOT",
    "WALL": "MOD_BUILD",
    "SLAB": "MESH_PLANE",
    "ROOF": "MOD_TRIANGULATE",
    "BEAM": "MESH_CUBE",
    "COLUMN": "MESH_CYLINDER",
    "JOIST": "MOD_ARRAY",
    "FOUNDATION": "MOD_SOLIDIFY",
    "DOOR": "MOD_LATTICE",
    "WINDOW": "MOD_WIREFRAME",
    "STAIR": "MOD_MULTIRES",
    "ROOM": "SNAP_VOLUME",
    "FIXTURE": "OUTLINER_OB_LIGHT",
    "FINISH": "MATERIAL",
    "MEP": "PLUGIN",
    "SITE": "WORLD",
    "OTHER": "DOT",
}


def category_icon(category: str) -> str:
    return CATEGORY_ICONS.get(category, "DOT")


# Custom property value types ----------------------------------------------
PROP_TEXT = "TEXT"
PROP_NUMBER = "NUMBER"
PROP_BOOL = "BOOL"

PROP_TYPE_ITEMS = [
    (PROP_TEXT, "Text", "Free text value", 0),
    (PROP_NUMBER, "Number", "Numeric value", 1),
    (PROP_BOOL, "Yes/No", "Boolean value", 2),
]

# Scene-level unit basis for cost rates ------------------------------------
UNIT_BASIS_ITEMS = [
    ("PROJECT", "Follow Scene", "Use the scene's unit system for quantities and rates", 0),
    ("METRIC", "Metric (m)", "Always quantify in metres regardless of display units", 1),
    ("IMPERIAL", "Imperial (ft)", "Always quantify in feet regardless of display units", 2),
]
