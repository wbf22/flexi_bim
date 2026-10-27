# FlexiBIM

Model freely in Blender, tag what things are, then auto-generate construction
drawings. See [TODO.md](TODO.md) for the roadmap and
[docs/TAGGING.md](docs/TAGGING.md) for the tagging system reference.

Target: Blender 4.4 LTS.

## Setup

To test the plugin:

- run `./zip.sh` to zip up the plugin
- open Blender and go to Edit > Preferences > Add-ons > (down caret on right) >
  Install from Disk
- open the zip there and it's loaded in

The UI lives in View3D > Sidebar (`N`) > **FlexiBIM**.

## What works today

**Tagging (Phase 1).** Any object in the scene can carry any number of tags.
Each tag has a **name**, a **cost** (flat rate, or a rate per measured quantity
in project units), and any **custom key/value properties** you want to attach.

- Tag list on the active object; add/remove/reorder/duplicate, apply a tag to
  the whole selection, select every object sharing a tag.
- **Tag library**: reusable definitions (`Exterior Wall 2x6` @ `$14.50/ft²`)
  that many objects link to, so editing the rate re-prices the whole project.
  Local overrides, promote-to-library and make-local are all supported.
- **Quantity take-off** from the evaluated geometry (modifiers included):
  each, length, plan length, edge length, face area, surface area, plan area
  and volume, converted to the project's units (m/m²/m³ or ft/ft²/ft³), with an
  optional waste percentage and manual-quantity override.
- **Cost summary** per tag or per object, for the scene or just the selection,
  with CSV schedule export and JSON import/export of tags and libraries.
- Metadata is stored in ID custom properties on the *object*, so it survives
  remeshing and re-modelling.

## Development

```bash
python3 -m pytest tests -q     # 150 tests, no Blender required
```

The suite runs the real addon code against a small functional `bpy` mock in
`tests/mockbpy`, including executing every panel's `draw()` against a strict
fake `UILayout`. See the end of [docs/TAGGING.md](docs/TAGGING.md) for details.

Inside a real Blender (checks registration, depsgraph evaluation, modifier-aware
take-off and the operators against the genuine API):

```bash
blender --background --python scripts/blender_smoke.py
```
