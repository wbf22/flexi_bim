# FlexiBIM

Model freely in Blender, tag what things are, then auto-generate construction drawings. 

Target: Blender 4.4 LTS.

This is still a work in progress, but so far tagging and generating svg drawings works at a basic level.

If you'd like to support us, you can with this link https://github.com/sponsors/wbf22. Thanks!

## Installing and Use

In blender navigate to `Edit > Preferences > Add-ons > (down caret on right) > Install from Disk` and select the zip in this repo `flexi_bim.zip`

The UI lives in View3D > Sidebar (`N`) > **FlexiBIM**. There you can select objects and add tags. Costs can be added to tags to generate estimates for material costs.

Below you can also generate drawings specifying view points and cross sections of varying sizes. This can be useful for generating things like elevation diagrams, electrical system drawings, floor plans, etc...

You can also generate and manually create measurements between objects that will show up in drawings.

## Contributing

Feel free to make a pr and we'll review it! 

If you want to check or discuss an idea before making a pr, make an issue on github and we can talk it over. 


## Building

To test the plugin:

- run `./zip.sh` to zip up the plugin
- open Blender and go to Edit > Preferences > Add-ons > (down caret on right) > Install from Disk
- open the zip there and it's loaded in

The UI lives in View3D > Sidebar (`N`) > **FlexiBIM**.
