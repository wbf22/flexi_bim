# FlexiBIM Tagging

Tags are how ordinary Blender geometry becomes construction data. **Any object
can be tagged** — meshes, curves, text, even empties and lights — and an object
can carry as many tags as you like (`Exterior Wall` + `Fire Rated` + `Paint`).

Every tag has:

| Attribute | Meaning |
|---|---|
| **Name** | The key everything is grouped by in schedules, drawings and rollups |
| **Cost** | A flat rate, a per-unit rate against a measured quantity, or nothing |
| **Custom properties** | Any key/value pairs you want (`Fire Rating = 1 hr`) |

Plus two optional extras: a **category** (the semantic type — wall, slab, door…
used later by drawings and schedules) and a free-text **description**.

---

## Where the data lives

```
scene.flexibim                     FlexiBIMProject
  .library[]                       reusable tag definitions
  .currency, .currency_decimals    how money is displayed
  .unit_basis                      which units cost rates are quoted in

object.flexibim                    FlexiBIMObject
  .tags[]                          FlexiBIMTag
      .name, .category, .description
      .source                      LOCAL | LIBRARY
      .cost                        FlexiBIMCost
      .properties[]                FlexiBIMProperty (key / value / value_type)
```

These are `PropertyGroup`s attached to the ID, so Blender stores them as ID
custom properties inside the `.blend`. Two consequences worth knowing:

* Tags live on the **object**, not the mesh, so they survive remeshing,
  retopology and outright replacement of the geometry.
* Duplicating an object (`Shift+D`, `Alt+D`, array of linked copies) duplicates
  its tags too, which is exactly what you want for quantity take-off.

---

## Cost

Three modes:

* **No Cost** — the tag is purely informational (`Phase 2`, `Demolish`, …).
* **Flat Rate** — one lump sum per tagged object: permits, a door unit,
  an appliance.
* **Per Unit** — `rate × measured quantity`, the normal construction case
  (`$14.50/ft²` of wall, `$180/m³` of concrete).

### Measured quantities

Quantities are taken off the **evaluated** object, so modifiers (solidify,
array, booleans) are included, and then converted into project units.

| Measurement | What it measures | Typical use |
|---|---|---|
| `Each` | 1 per object | Doors, windows, fixtures |
| `Length` | Longest bounding-box extent | Beams, headers, trim |
| `Plan Length` | Longest horizontal extent, ignoring height | Wall runs, footings |
| `Edge Length` | Sum of every edge | Perimeters, linework |
| `Face Area` | Length × height | **Wall/panel elevation area** |
| `Surface Area` | Area of every face | Finishes wrapping a whole object |
| `Plan Area` | Top-down projected footprint | Slabs, roofs, floor finishes |
| `Volume` | Enclosed volume | Concrete, excavation, fill |

> **Face Area vs Surface Area.** A 30 ft × 8 ft wall modelled as a solid has
> 240 ft² of *face* area but ~515 ft² of *surface* area (both sides plus the
> edges). Wall rates almost always mean the former — use `Face Area`.

Set **Quantity** to *Manual* to type the number yourself (in project units)
when the geometry cannot be measured or is only indicative — useful for an
untagged stand-in, or a site-wide allowance on an empty.

**Waste** adds a percentage to the measured quantity before pricing, the way a
real take-off carries overage on sheet goods and concrete.

### Units and currency

Quantities are converted from Blender units to the scene's unit system, so an
imperial project quotes `$/ft²` and a metric one `$/m²`; the rate field is
labelled with the live unit so there is no ambiguity.

Because changing the scene's display units would otherwise silently
re-interpret every rate in the project, **Quantity Units** (Project Settings)
can pin take-off to `Metric` or `Imperial` regardless of what the viewport
shows. `scale_length` is honoured as well.

---

## Local tags vs the tag library

A tag's **Source** decides where its cost and default properties come from:

* **Local** — stored on the object. Quick, self-contained, per-object tweaks.
* **Library** — inherited from a definition in `scene.flexibim.library`.

Library tags are the ones that make a project maintainable: define
`Exterior Wall 2x6` once at `$14.50/ft²` and every linked object re-prices the
moment you edit the rate. Renaming a library tag updates every linked object
automatically; deleting one warns you how many objects are left dangling, and
those tags are flagged in both the list and the cost summary rather than
silently costing zero.

Custom properties **merge**: the library supplies defaults, and properties set
on the object override them key by key. The panel shows which keys were
inherited. *Make Local* bakes the current definition onto the object so it can
diverge; *Promote to Library* does the reverse.

---

## UI map (View3D ▸ Sidebar ▸ FlexiBIM)

| Panel | What it does |
|---|---|
| **Tags** | Tag list for the active object, the active tag's cost + custom properties, and tools to apply tags across the selection |
| **Tag Library** | Reusable definitions, their costs/defaults, assign-to-selected, select-users |
| **Cost Summary** | Per-tag or per-object rollup, whole scene or selection only, CSV export |
| **Project Settings** | Currency, quantity units, tagged/untagged counts, JSON import/export |

---

## Python API

```python
from flexi_bim.tagging import api, constants as C

wall = bpy.context.object

tag = api.add_tag(wall, "Exterior Wall 2x6", category="WALL")
tag.cost.mode = C.COST_MODE_MEASURED
tag.cost.measurement = C.MEASURE_WALL_AREA
tag.cost.rate = 14.50
api.set_property(tag, "Fire Rating", "1 hr")
api.set_property(tag, "R Value", 21)          # typed automatically

api.tag_cost(wall, tag, scene).amount          # -> 3480.0
api.object_cost(wall, scene).amount            # every tag on the object
api.cost_rollup(scene)                         # per-tag totals, priciest first
api.project_total(scene)

api.objects_with_tag(scene, "Exterior Wall 2x6")
api.objects_in_category(scene, "WALL")
api.untagged_objects(scene)                    # documentation preflight
api.resolve_tag(tag, scene).properties         # library defaults + overrides
```

Serialisation lives in `flexi_bim.tagging.exchange`:

```python
from flexi_bim.tagging import exchange
exchange.schedule_csv(scene, per_object=True)  # cost schedule
exchange.summary_text(scene)                   # one line per tag
exchange.dumps(scene)                          # JSON: library + object tags
exchange.loads(scene, text, library_only=True) # share a library between projects
```

---

## Notes for the phases that follow

* `api.resolve_tag()` is the single place where inheritance is applied — the
  drawing and schedule generators should read resolved tags, never raw ones.
* `category` is the hook for symbols/linework; `properties` map cleanly onto
  IFC property sets when that day comes.
* `api.untagged_objects()` is the seed of the documentation preflight report.
* Measurements are cached per object and invalidated from a depsgraph handler;
  call `measure.invalidate()` if you generate geometry behind Blender's back.

## Tests

The tagging system is covered by a test suite that runs without Blender, using
a small functional `bpy` mock (`tests/mockbpy`):

```bash
python3 -m pytest tests -q
```

The mock is strict on purpose: panel `draw()` calls are executed against a fake
`UILayout` that validates every property name, operator id and `template_list`
reference, so UI typos fail the suite instead of showing up as a red panel.
