"""Grouped SolidWorks mixins for the PyWin32 adapter."""

from .features import SolidWorksFeaturesMixin
from .io import SolidWorksIOMixin
from .selection import SolidWorksSelectionMixin
from .sketch import SolidWorksSketchMixin

__all__ = [
    "SolidWorksFeaturesMixin",
    "SolidWorksIOMixin",
    "SolidWorksSelectionMixin",
    "SolidWorksSketchMixin",
]
