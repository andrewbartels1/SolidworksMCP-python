"""Grouped SolidWorks mixins for the PyWin32 adapter."""

from .documentation import SolidWorksDocumentationMixin
from .drawing_standard import SolidWorksDrawingStandardMixin
from .features import SolidWorksFeaturesMixin
from .io import SolidWorksIOMixin
from .selection import SolidWorksSelectionMixin
from .sketch import SolidWorksSketchMixin

__all__ = [
    "SolidWorksDocumentationMixin",
    "SolidWorksDrawingStandardMixin",
    "SolidWorksFeaturesMixin",
    "SolidWorksIOMixin",
    "SolidWorksSelectionMixin",
    "SolidWorksSketchMixin",
]
