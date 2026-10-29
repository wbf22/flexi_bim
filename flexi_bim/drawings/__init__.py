"""FlexiBIM drawing engine.

Extract 2D views from tagged geometry and export them as vector linework::

    from flexi_bim.drawings import views, svg, primitives as P

    view = views.ViewSpec(axis="Z", mode=P.PROJECT, range=(3, 5),
                          include_tags=("Downlight",))
    drawing = views.render(scene, view)
    svg.write("out/lighting.svg", drawing)

Saved views (create/edit them in the **Drawings** sidebar panel) live on
``scene.flexibim_drawings`` and are turned into a :class:`views.ViewSpec` with
:func:`views.spec_from_view`.
"""

from __future__ import annotations

from ..core.registration import register_classes, unregister_classes
from . import dimensions, extract, operators, primitives, props, svg, ui, views

classes = props.classes + operators.classes + ui.classes


def render(scene, view, context=None):
    """Extract a :class:`~flexi_bim.drawings.primitives.Drawing` for ``view``."""
    return views.render(scene, view, context)


def render_svg(scene, view, context=None, **kwargs):
    """Extract ``view`` and return it as an SVG string."""
    kwargs.setdefault("scale_denominator", view.scale)
    return svg.to_svg(views.render(scene, view, context), **kwargs)


def write_svg(path, scene, view, context=None, **kwargs):
    """Extract ``view`` and write it to ``path`` as SVG."""
    kwargs.setdefault("scale_denominator", view.scale)
    return svg.write(path, views.render(scene, view, context), **kwargs)


def register():
    register_classes(classes)
    props.register_pointers()


def unregister():
    props.unregister_pointers()
    unregister_classes(classes)


__all__ = [
    "dimensions",
    "extract",
    "operators",
    "primitives",
    "props",
    "svg",
    "ui",
    "views",
    "render",
    "render_svg",
    "write_svg",
    "register",
    "unregister",
]
