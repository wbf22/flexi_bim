# FlexiBIM — Blender BIM Plugin TODO

Model freely in Blender, tag what things are, then auto-generate construction drawings.

## Locked Decisions
- **Audience:** General-purpose, but residential-first (design data model to generalize later)
- **Blender target:** 4.4 LTS (4.4.3 installed)
- **Drawing engine:** Geometry-based extraction (custom cut/slice + edge projection)
- **Metadata store:** Custom properties on objects

## Core Concept

Five separable systems:
1. **Geometry** — ordinary Blender meshes/objects (no rigid BIM authoring required)
2. **Semantic tags** — Wall, Slab, Beam, Column, Window, Door, Roof, Room, etc.
3. **Assemblies & materials** — layers, thicknesses, products, ratings, finishes
4. **Drawing generator** — plans, elevations, sections, dimensions, linework
5. **Document generator** — sheets, schedules, legends, title blocks, PDF/IFC/DXF

Three coexisting modeling levels:
- **L1 Visual** — untagged geometry, still appears in drawings
- **L2 Tagged** — object has a type; drives symbols, labels, schedules
- **L3 Constructible** — assemblies, framing, connections, details

## Done
- Addon boilerplate, repo structure, sidebar panel (registers cleanly on Blender 4.4.3)
- Packaged `flexi_bim.zip`; verified install-from-disk layout (package at zip root)
- Tagging system: tags on any object, costs, custom properties, tag library,
  quantity take-off, cost rollup/schedules (see `docs/TAGGING.md`)
- Every created tag auto-registers in the reusable tag library and links to it
  (re-applying the same name reuses the definition; `reusable=False` opts out)
- Restored `tagging/measure.py` (had been overwritten by a copy of `exchange.py`)
- Root sidebar panel wired into `ui/panel.py`; orphaned `tagging/panel.py` removed
- All FlexiBIM panels verified to draw without error on Blender 4.4.3

## Tooling
- [ ] Test suite + `tests/mockbpy` (referenced by README, currently missing)
- [ ] `scripts/blender_smoke.py` (referenced by README, currently missing)

## Phase 1 — Tagging
- [x] Define semantic type enum (wall, slab, beam, column, window, door, roof, room...)
- [x] Operator/UI to assign + edit type, name on selected objects
- [x] Store metadata in custom properties (survives remesh/re-model)
- [x] Property group + panel showing tags on active object
- [x] Tag inspector / list view of all tagged objects (per tag + per object rollup)
- [x] Cost per tag: flat rate or rate per measured quantity in project units
- [x] Arbitrary custom key/value properties per tag
- [x] Reusable tag library with inheritance + local overrides
- [x] CSV cost schedule export, JSON tag/library import-export
- [ ] Auto-numbering (e.g. W-01, D-01, R-101) — needs an instance-level ID
      alongside the tag name
- [ ] Assign tags from the Outliner / right-click context menu
- [ ] Viewport colour overlay driven by library tag colour

## Phase 2 — Orthographic Drawings
- [ ] Generate plan view (top-down ortho) from geometry
- [ ] Generate elevation views (4 sides)
- [ ] Generate section cuts (bisect/clip plane through model)
- [ ] Cut-line weight (thick) vs. elements behind cut (light)
- [ ] Vector line output via custom geometry extraction
- [ ] View regenerate without destroying manual edits

## Phase 3 — Architectural Linework
- [ ] Line styles by type (cut, projection, hidden)
- [ ] Hatching for materials (poché for cut walls)
- [ ] Symbols for doors/windows/stairs/fixtures
- [ ] Level markers + elevation markers
- [ ] Clean SVG/DXF vector export

## Phase 4 — Dimensions & Annotations
- [ ] Linear dimension tool (associative, updates with geometry)
- [ ] Dimension chains for layout
- [ ] Room name + area labels (boundary recognition)
- [ ] Text notes / leader annotations

## Phase 5 — Schedules
- [ ] Door schedule (from tagged doors)
- [ ] Window schedule (from tagged windows)
- [ ] Room finish schedule
- [ ] Wall type schedule
- [ ] Material quantities / takeoff
- [ ] Table → sheet rendering

## Phase 6 — Assemblies & Validation
- [ ] Assembly presets (exterior insulated wood frame, etc.)
- [ ] Layer stack editor (name, function, thickness) summing to overall thickness
- [ ] Structural flag, fire rating, insulation R-value, finishes
- [ ] Documentation preflight checker (report missing info)
- [ ] IDS/IFC-aligned metadata schema (design early, implement later)

## Phase 7 — Sheets & Export
- [ ] Sheet layout (viewport frames on a page)
- [ ] Multiple views per sheet with independent scales
- [ ] Title block, sheet numbers, legends, notes
- [ ] Reusable detail library (detail templates tied to assemblies)
- [ ] Export: PDF, DXF, and eventually IFC

## Cross-Cutting Constraints
- [ ] Generated drawings must refresh without overwriting manual annotations/sheet layouts
- [ ] Detail automation = template selection + user override (never silently invent connections)
