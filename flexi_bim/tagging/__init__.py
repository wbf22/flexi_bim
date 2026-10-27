"""FlexiBIM tagging: semantic tags, costs and custom metadata on any object.

Public entry point is :mod:`flexi_bim.tagging.api`.
"""

from ..core.registration import register_classes, unregister_classes
# Imported in dependency order.
from . import constants, costing, measure, props, api, exchange, operators, ui

classes = props.classes + operators.classes + ui.classes


def register():
    register_classes(classes)
    props.register_pointers()
    measure.register()


def unregister():
    measure.unregister()
    props.unregister_pointers()
    unregister_classes(classes)


__all__ = [
    "api",
    "constants",
    "costing",
    "exchange",
    "measure",
    "operators",
    "props",
    "ui",
    "register",
    "unregister",
]
