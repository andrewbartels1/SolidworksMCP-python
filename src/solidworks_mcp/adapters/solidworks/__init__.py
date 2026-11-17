"""Grouped SolidWorks mixins for the PyWin32 adapter."""

from .configurations import SolidWorksConfigurationsMixin
from .documentation import SolidWorksDocumentationMixin
from .drawing_pack import SolidWorksDrawingPackMixin
from .drawing_standard import SolidWorksDrawingStandardMixin
from .features import SolidWorksFeaturesMixin
from .io import SolidWorksIOMixin
from .part_features import SolidWorksPartFeaturesMixin
from .selection import SolidWorksSelectionMixin
from .sheet_metal import SolidWorksSheetMetalMixin
from .sketch import SolidWorksSketchMixin
from .templates import SolidWorksTemplatesMixin

__all__ = [
    "SolidWorksConfigurationsMixin",
    "SolidWorksDocumentationMixin",
    "SolidWorksDrawingPackMixin",
    "SolidWorksDrawingStandardMixin",
    "SolidWorksFeaturesMixin",
    "SolidWorksIOMixin",
    "SolidWorksPartFeaturesMixin",
    "SolidWorksSelectionMixin",
    "SolidWorksSheetMetalMixin",
    "SolidWorksSketchMixin",
    "SolidWorksTemplatesMixin",
]
