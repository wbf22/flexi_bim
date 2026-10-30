"""2D drawing primitives produced by the extractor.

Pure data (no ``bpy``): segments live in view-plane coordinates (model units)
and carry a CAD layer, a paper stroke weight (mm) and a colour.  Annotations
(leaders) carry a text note and the model-space point they point at; the SVG
writer decides where to place the text on paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Segment kinds.
CUT = "CUT"
PROJECT = "PROJECT"
HIDDEN = "HIDDEN"

#: Fill pattern identifiers.  These strings are shared with the tag property
#: (see ``tagging.constants.FILL_ITEMS``) and must stay in sync.
FILL_NONE = "NONE"
FILL_SOLID = "SOLID"
FILL_DIAGONAL = "DIAGONAL"
FILL_CROSS = "CROSS"
FILL_DOTS = "DOTS"

#: Default paper stroke widths in millimetres.
WEIGHT_CUT = 0.50
WEIGHT_PROJECT = 0.18
WEIGHT_HIDDEN = 0.13
WEIGHT_LEADER = 0.13
WEIGHT_DIMENSION = 0.13
#: Stroke width of vector hatch lines inside a fill pattern (paper mm).
HATCH_WEIGHT = 0.13

#: Layer used for everything with no semantic category, and for annotations.
DEFAULT_LAYER = "0"
ANNOTATION_LAYER = "A-ANNO"
DIMENSION_LAYER = "A-DIMS"

#: Fallback stroke colour (black) when a tag has none.
DEFAULT_COLOR = (0.0, 0.0, 0.0)

#: Tag category -> CAD layer name.
LAYER_BY_CATEGORY = {
    "WALL": "A-WALL",
    "SLAB": "A-SLAB",
    "ROOF": "A-ROOF",
    "BEAM": "S-BEAM",
    "COLUMN": "S-COLM",
    "JOIST": "S-JOIS",
    "FOUNDATION": "S-FNDN",
    "DOOR": "A-DOOR",
    "WINDOW": "A-GLAZ",
    "STAIR": "A-STR",
    "ROOM": "A-AREA",
    "FIXTURE": "A-FIXT",
    "FINISH": "A-FNSH",
    "MEP": "M-MEP",
    "SITE": "C-SITE",
    "NONE": DEFAULT_LAYER,
    "OTHER": DEFAULT_LAYER,
}


def layer_for(category) -> str:
    return LAYER_BY_CATEGORY.get(category or "NONE", DEFAULT_LAYER)


@dataclass(frozen=True)
class Segment:
    """A line in view-plane coordinates (model units)."""

    a: tuple
    b: tuple
    layer: str = DEFAULT_LAYER
    weight: float = WEIGHT_PROJECT
    kind: str = PROJECT
    color: tuple = DEFAULT_COLOR
    tag: str = ""

    def key(self):
        """Identity for de-duplication: layer + unordered endpoints."""
        return (self.layer, tuple(sorted((self.a, self.b))))


@dataclass(frozen=True)
class Leader:
    """A note attached to a model point by a leader arrow."""

    target: tuple
    text: str
    layer: str = ANNOTATION_LAYER
    color: tuple = DEFAULT_COLOR


@dataclass(frozen=True)
class Dimension:
    """A linear dimension between two points of the model, in view-plane coords.

    ``a`` and ``b`` are the (projected) points being measured - normally the
    nearest points between two objects.  ``offset`` pushes the dimension line to
    one side of them (model units).
    """

    a: tuple
    b: tuple
    text: str = ""
    offset: float = 0.3
    layer: str = DIMENSION_LAYER
    color: tuple = DEFAULT_COLOR


@dataclass(frozen=True)
class Region:
    """A closed area filled with a repeating pattern (poché).

    ``points`` is the polygon outline in view-plane coordinates (model units);
    the outline is implicitly closed.  ``fill`` is one of the ``FILL_*``
    identifiers, ``spacing`` is the tile size on paper (mm) and ``angle`` rotates
    the hatch (degrees).
    """

    points: tuple
    layer: str = DEFAULT_LAYER
    color: tuple = DEFAULT_COLOR
    fill: str = FILL_NONE
    spacing: float = 3.0
    angle: float = 45.0
    tag: str = ""


@dataclass
class Drawing:
    """Everything the extractor produced for one view."""

    segments: list = field(default_factory=list)
    leaders: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    regions: list = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.segments
            and not self.leaders
            and not self.dimensions
            and not self.regions
        )

    def layers(self):
        names = {segment.layer for segment in self.segments}
        names.update(dim.layer for dim in self.dimensions)
        names.update(region.layer for region in self.regions)
        return sorted(names)
