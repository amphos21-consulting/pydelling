from .dfn_preprocessor import DfnPreprocessor
from .dfn_upscaler import DfnUpscaler
from .fault import Fault
from .fracture import Fracture
from .polygon_fracture import PolygonFracture
from .dfn_preprocessor_utils import read_dfn_from_file
from .surface_dfn import (
    SurfaceDfn,
    SurfaceDfnError,
    read_hgs_directory,
    read_structured_vertices,
    validate_hgs_directory,
)
from .surface_upscaler import (
    IntersectionIndex,
    IntersectionTable,
    IntersectionView,
    UpscalingResult,
    accumulate_surface_with_mesh,
    intersect_surface_with_mesh,
    upscale_surface_dfn,
)
from .hydraulic_properties import (
    HydraulicPropertyError,
    ResolvedHydraulicProperties,
    resolve_hydraulic_properties,
)
