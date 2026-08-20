"""
Module documentation.


"""

from __future__ import annotations
import logging
import json
from pathlib import Path
from typing import List

import meshio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tabulate import tabulate
from tqdm import tqdm
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydelling.preprocessing.dfn_preprocessor import Fault, Fracture

logger = logging.getLogger(__name__)


class DfnPreprocessor(object):
    """Build, inspect, visualize, and export discrete fracture networks.

    Category: preprocessing
    Tags: dfn, fractures, faults, vtk, obj, dfnworks
    Usage: scripts need to load fracture geometry, add faults, summarize DFNs, or export fracture networks.
    """
    dfn: List[Fracture] = []
    faults: List[Fault] = []

    def __getitem__(self, item):
        """
        __getitem__ method.
        
        Args:
            item (Any): Description.
        """
        return self.dfn[item]

    def __init__(self):
        self.clean_dfn()

    def clean_dfn(self):
        """Clear all fractures and faults from this DFN.

        Category: preprocessing
        Tags: dfn, reset, fractures, faults
        Usage: scripts need to reuse a DfnPreprocessor instance for a new network.

        Returns:
            None: clears the fracture and fault lists.
        """
        self.dfn = []
        self.faults = []
        self.surface_networks = []
        self._surface_dfn_cache = None
        self._surface_dfn_cache_key = None

    def _invalidate_surface_cache(self):
        self._surface_dfn_cache = None
        self._surface_dfn_cache_key = None

    @classmethod
    def from_hgs_directory(
        cls,
        directory,
        *,
        companion_mesh,
        variant="aperture",
        groups="physical",
        refinement=4,
        validate_pairs=True,
    ):
        """Create a DFN containing one compact HydroGeoSphere surface network."""

        from .surface_dfn import read_hgs_directory

        instance = cls()
        instance.surface_networks.append(
            read_hgs_directory(
                directory,
                companion_mesh=companion_mesh,
                variant=variant,
                groups=groups,
                refinement=refinement,
                validate_pairs=validate_pairs,
            )
        )
        return instance

    @classmethod
    def from_surface_vtk(cls, filename, *, groups="physical", active_group_names=None):
        """Create a DFN from a triangle VTK with HGS-compatible cell fields."""

        from .surface_dfn import read_surface_vtk

        instance = cls()
        instance.surface_networks.append(
            read_surface_vtk(
                filename,
                groups=groups,
                active_group_names=active_group_names,
            )
        )
        return instance

    def add_surface_network(self, surface):
        """Add an array-backed triangulated fracture network."""

        from .surface_dfn import SurfaceDfn

        if not isinstance(surface, SurfaceDfn):
            raise TypeError("surface must be a SurfaceDfn")
        self.surface_networks.append(surface)
        self._invalidate_surface_cache()

    @staticmethod
    def _triangulate_fracture_polygon(points, *, tolerance=1.0e-8):
        """Triangulate a simple planar polygon while preserving concave boundaries."""

        from shapely.geometry import Polygon
        from shapely.ops import triangulate

        xyz = np.asarray(points, dtype=float)
        if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) < 3:
            raise ValueError("fracture polygon must have shape (n>=3, 3)")
        center = xyz.mean(axis=0)
        _, singular, basis = np.linalg.svd(xyz - center, full_matrices=False)
        scale = max(float(np.linalg.norm(np.ptp(xyz, axis=0))), 1.0)
        if len(singular) < 2 or singular[1] <= tolerance * scale:
            raise ValueError("fracture polygon is degenerate")
        if len(singular) > 2 and singular[2] > tolerance * scale:
            raise ValueError("fracture polygon is not planar")
        uv = (xyz - center) @ basis[:2].T
        polygon = Polygon(uv)
        if not polygon.is_valid or polygon.area <= tolerance * tolerance:
            raise ValueError("fracture polygon is self-intersecting or degenerate")
        triangles = [part for part in triangulate(polygon) if polygon.covers(part.representative_point())]
        if not triangles or not np.isclose(
            sum(part.area for part in triangles), polygon.area, rtol=1.0e-8, atol=tolerance**2
        ):
            raise ValueError("fracture polygon could not be triangulated conservatively")
        connectivity = []
        for part in triangles:
            row = []
            for coordinate in list(part.exterior.coords)[:-1]:
                distances = np.linalg.norm(uv - np.asarray(coordinate), axis=1)
                index = int(np.argmin(distances))
                if distances[index] > tolerance * scale:
                    raise ValueError("triangulation introduced an unsupported boundary vertex")
                row.append(index)
            if len(set(row)) != 3:
                raise ValueError("triangulation produced a degenerate triangle")
            connectivity.append(row)
        return xyz, np.asarray(connectivity, dtype=np.int64)

    def to_surface_dfn(
        self,
        *,
        density=997.16,
        dynamic_viscosity=8.9e-4,
        gravity=9.80665,
        hydraulic_aperture_ratio=1.0,
        use_cache=True,
    ):
        """Merge object and array-backed DFNs into one compact triangulated surface."""

        from .hydraulic_properties import resolve_hydraulic_properties
        from .surface_dfn import SurfaceDfn

        # The production HGS path is already in the target representation;
        # preserve its zero-copy behavior and full-model memory profile.
        if not self.dfn and not self.faults and len(self.surface_networks) == 1:
            return self.surface_networks[0]

        object_signature = []
        for kind, sources in (("fracture", self.dfn), ("fault", self.faults)):
            for source in sources:
                geometry_points = source.side_points if kind == "fracture" else source.meshio_mesh.points
                object_signature.append(
                    (
                        kind,
                        id(source),
                        hash(np.asarray(geometry_points, dtype=float).tobytes()),
                        repr(
                            tuple(
                                vars(source).get(name)
                                for name in (
                                    "aperture", "effective_aperture", "hydraulic_aperture",
                                    "porosity", "_transmissivity", "transmissivity_constant",
                                    "transmissivity", "hydraulic_conductivity", "_storativity", "storativity",
                                    "specific_storage",
                                )
                            )
                        ),
                    )
                )
        key = (
            tuple(object_signature),
            tuple((id(surface), surface.n_triangles) for surface in self.surface_networks),
            float(density), float(dynamic_viscosity), float(gravity), float(hydraulic_aperture_ratio),
        )
        if use_cache and key == self._surface_dfn_cache_key and self._surface_dfn_cache is not None:
            return self._surface_dfn_cache

        point_blocks = []
        triangle_blocks = []
        fields = {name: [] for name in (
            "thickness", "hydraulic_conductivity", "porosity", "specific_storage",
            "group_ids", "fracture_element_ids", "source_kinds", "source_object_ids",
            "source_triangle_ids", "property_origins",
        )}
        group_names = {}
        group_lookup = {}
        point_offset = 0
        warnings = []

        def group_id(name):
            if name not in group_lookup:
                value = len(group_lookup)
                group_lookup[name] = value
                group_names[value] = name
            return group_lookup[name]

        def append_block(points, triangles, properties, *, kind, object_id, names, source_ids=None,
                         triangle_ids=None, origins=None):
            nonlocal point_offset
            points = np.asarray(points, dtype=float)[:, :3]
            triangles = np.asarray(triangles, dtype=np.int64)
            count = len(triangles)
            point_blocks.append(points)
            triangle_blocks.append(triangles + point_offset)
            point_offset += len(points)
            for name in ("thickness", "hydraulic_conductivity", "porosity", "specific_storage"):
                value = np.asarray(properties[name])
                fields[name].append(np.full(count, float(value), dtype=float) if value.ndim == 0 else value)
            fields["group_ids"].append(np.asarray([group_id(name) for name in names], dtype=np.int32))
            source_ids = np.full(count, object_id, dtype=np.int64) if source_ids is None else source_ids
            fields["fracture_element_ids"].append(np.asarray(source_ids, dtype=np.int64))
            fields["source_kinds"].append(np.full(count, kind, dtype="U16"))
            fields["source_object_ids"].append(np.asarray(source_ids, dtype=np.int64))
            fields["source_triangle_ids"].append(
                np.arange(count, dtype=np.int64) if triangle_ids is None else np.asarray(triangle_ids, dtype=np.int64)
            )
            fields["property_origins"].append(
                np.full(count, origins or "input", dtype="U512")
                if np.asarray(origins).ndim == 0 else np.asarray(origins, dtype="U512")
            )

        for surface_index, surface in enumerate(self.surface_networks):
            names = [surface.group_names.get(int(value), f"surface_{surface_index}_{value}") for value in surface.group_ids]
            append_block(
                surface.points, surface.triangles,
                {name: getattr(surface, name) for name in ("thickness", "hydraulic_conductivity", "porosity", "specific_storage")},
                kind="surface" if surface.source_kinds is None else "surface",
                object_id=surface_index,
                names=names,
                source_ids=surface.fracture_element_ids if surface.source_object_ids is None else surface.source_object_ids,
                triangle_ids=surface.source_triangle_ids,
                origins=surface.property_origins if surface.property_origins is not None else "input",
            )
            if surface.source_kinds is not None:
                fields["source_kinds"][-1] = surface.source_kinds

        for kind, sources in (("fracture", self.dfn), ("fault", self.faults)):
            for source in sources:
                resolved = resolve_hydraulic_properties(
                    source,
                    density=density,
                    dynamic_viscosity=dynamic_viscosity,
                    gravity=gravity,
                    hydraulic_aperture_ratio=hydraulic_aperture_ratio,
                )
                if kind == "fracture":
                    points, triangles = self._triangulate_fracture_polygon(source.side_points)
                else:
                    points = np.asarray(source.meshio_mesh.points)[:, :3]
                    blocks = [block.data for block in source.meshio_mesh.cells if block.type == "triangle"]
                    if not blocks:
                        raise ValueError(f"fault {source.local_id} contains no triangles")
                    triangles = np.concatenate(blocks)
                origin = json.dumps(resolved.provenance, sort_keys=True, separators=(",", ":"))
                append_block(
                    points, triangles,
                    {
                        "thickness": resolved.thickness,
                        "hydraulic_conductivity": resolved.hydraulic_conductivity,
                        "porosity": resolved.porosity,
                        "specific_storage": resolved.specific_storage,
                    },
                    kind=kind,
                    object_id=int(source.local_id),
                    names=["fractures" if kind == "fracture" else "faults"] * len(triangles),
                    origins=origin,
                )
                warnings.extend(
                    {"source_kind": kind, "source_id": int(source.local_id), "message": message}
                    for message in resolved.warnings
                )

        if not triangle_blocks:
            raise ValueError("DfnPreprocessor contains no fractures, faults, or surface networks")
        result = SurfaceDfn(
            points=np.concatenate(point_blocks),
            triangles=np.concatenate(triangle_blocks),
            group_names=group_names,
            metadata={
                "source": "DfnPreprocessor.to_surface_dfn",
                "property_warnings": warnings,
                "hydraulic_aperture_ratio": float(hydraulic_aperture_ratio),
            },
            **{name: np.concatenate(values) for name, values in fields.items()},
        )
        self._surface_dfn_cache_key = key
        self._surface_dfn_cache = result
        return result


    def load_fractures(self, pd_df: pd,
                       dip='dip',
                       dip_dir='dip-direction',
                       x='position-x',
                       y='position-y',
                       z='position-z',
                       size='size',
                       aperture=None,
                       hydraulic_aperture=None,
                       aperture_constant=None,
                       rock_type=None,
                       transmissivity_constant=None,
                       storativity_constant=None
                       ):
        """Load fractures from a pandas DataFrame.

        Category: preprocessing
        Tags: dfn, fractures, dataframe, load, aperture
        Usage: scripts have tabular fracture parameters and need to build a DFN.

        Returns:
            None: appends fractures to the DFN.
        """
        for index, row in tqdm(pd_df.iterrows()):
            self.add_fracture(
                dip=row[dip],
                dip_dir=row[dip_dir],
                x=row[x],
                y=row[y],
                z=row[z],
                size=row[size],
                aperture_constant=aperture_constant,
                aperture=aperture,
                hydraulic_aperture=hydraulic_aperture,
                rock_type=rock_type,
                transmissivity_constant=transmissivity_constant,
                storativity_constant=storativity_constant
            )

    def load_fractures_from_polygons_and_apertures(self,
                       polygons,
                       apertures=None,
                       hydraulic_aperture=None,
                       radii=None,
                       aperture_constant=None,
                       rock_type=None,
                       transmissivity_constant=None,
                       storativity_constant=None):
        """Load fractures from polygon geometry and optional aperture arrays.

        Category: preprocessing
        Tags: dfn, fractures, polygons, apertures, load
        Usage: scripts already have fracture polygons from segmentation, raster contours, or external geometry.

        Returns:
            None: appends polygon-backed fractures to the DFN.
        """
        
        logger.info('Loading fractures from polygons and apertures')
        for idx, polygon in tqdm(enumerate(polygons), desc='Loading fractures into the DFN', total=len(polygons)):
            self.add_fracture(
                polygon=polygon,
                aperture=apertures[idx] if apertures is not None else None,
                hydraulic_aperture=hydraulic_aperture[idx] if hydraulic_aperture is not None else None,
                size=radii[idx] * 2 if radii is not None else None,
                aperture_constant=aperture_constant,
                rock_type=rock_type[idx] if rock_type is not None else None,
                transmissivity_constant=transmissivity_constant,
                storativity_constant=storativity_constant,
            )


    def add_fracture(self,
                     x=None,
                     y=None,
                     z=None,
                     dip=None,
                     dip_dir=None,
                     size=None,
                     aperture=None,
                     hydraulic_aperture=None,
                     transmissivity=None,
                     storativity=None,
                     aperture_constant=1E-3,
                     rock_type=None,
                     transmissivity_constant=None,
                     storativity_constant=None,
                     polygon=None,
                     effective_aperture=None,
                     porosity=None,
                     hydraulic_conductivity=None,
                     specific_storage=None,
                     ):
        """Add one fracture from orientation parameters or polygon geometry.

        Category: preprocessing
        Tags: dfn, fracture, add, aperture, polygon
        Usage: scripts need to construct a DFN incrementally from one fracture definition.

        Returns:
            None: appends a Fracture object to dfn.
        """
        from pydelling.preprocessing.dfn_preprocessor import Fracture
        fracture = Fracture(
            dip=dip,
            dip_dir=dip_dir,
            x=x,
            y=y,
            z=z,
            size=size,
            aperture=aperture,
            hydraulic_aperture=hydraulic_aperture,
            transmissivity=transmissivity,
            storativity=storativity,
            aperture_constant=aperture_constant,
            rock_type=rock_type,
            transmissivity_constant=transmissivity_constant,
            storativity_constant=storativity_constant,
            polygon=polygon,
            effective_aperture=effective_aperture,
            porosity=porosity,
            hydraulic_conductivity=hydraulic_conductivity,
            specific_storage=specific_storage,
        )
        fracture.local_id = len(self.dfn)
        self.dfn.append(fracture)
        self._invalidate_surface_cache()

    def add_fault(self, filename=None,
                  mesh=None,
                  aperture=None,
                  transmissivity=None,
                  effective_aperture=None,
                  porosity=None,
                  storativity=None,
                  hydraulic_aperture=None,
                  hydraulic_conductivity=None,
                  specific_storage=None,
                  ):
        """Add one fault from a file path or existing Fault object.

        Category: preprocessing
        Tags: dfn, fault, add, mesh, aperture
        Usage: scripts need to include fault surfaces alongside fractures in a DFN export.

        Returns:
            None: appends a Fault object to faults.
        """
        from pydelling.preprocessing.dfn_preprocessor import Fault
        if aperture is None:
            logger.warning(f'No aperture specified for fault {filename}')
        if isinstance(filename, Fault):
            filename.local_id = len(self.faults)
            self.faults.append(filename)
        elif isinstance(filename, (str, Path)) or mesh is not None:
            fault = Fault(filename=filename,
                          mesh=mesh,
                          aperture=aperture,
                          transmissivity=transmissivity,
                          effective_aperture=effective_aperture,
                          porosity=porosity,
                          storativity=storativity,
                          hydraulic_aperture=hydraulic_aperture,
                          hydraulic_conductivity=hydraulic_conductivity,
                          specific_storage=specific_storage,
                          )
            fault.local_id = len(self.faults)
            self.faults.append(fault)
            logger.info(f"Fault with aperture {aperture} has been added from {filename}")
        else:
            logger.error('Fault filename must be a string or Fault object')
            raise TypeError('Fault filename must be a string or Fault object')
        self._invalidate_surface_cache()

    def summary(self):
        """Print a compact DFN summary table.

        Category: preprocessing
        Tags: dfn, summary, fractures, size
        Usage: scripts need a quick textual report of fracture count and size range.

        Returns:
            None: prints the summary table.
        """
        print(tabulate(
            [
                ['Number of fractures', len(self.dfn)],
                ['Max size', f"{self.max_size:1.2f} m"],
                ['Min size', f"{self.min_size:1.2f} m"]
            ],
            headers=['Parameter', 'Value'],
            tablefmt='grid',
            numalign='center',
        ))

    def __len__(self):
        return len(self.dfn)

    def visualize_dfn(self, add_centroid=True, fracture_color='blue', size_color=False):
        """Render the DFN interactively with Plotly.

        Category: preprocessing
        Tags: dfn, visualize, plotly, fractures, centroids
        Usage: scripts need to show an interactive 3D fracture network.

        Returns:
            None: displays the Plotly figure.
        """
        self.fig = self.generate_dfn_plotly(add_centroid=add_centroid, fracture_color=fracture_color, size_color=size_color)
        self.fig.show()

    def export_dfn_image(self, filename='dfn.png', add_centroid=True, fracture_color='blue', *args, **kwargs, ):
        """Export a static image of the DFN Plotly figure.

        Category: writer
        Tags: dfn, image, plotly, export, visualization
        Usage: scripts need a PNG or other static image of the fracture network.

        Returns:
            None: writes the image file.
        """
        logger.info(f'Exporting dfn image to {filename}')
        self.fig = self.generate_dfn_plotly(add_centroid=add_centroid, fracture_color=fracture_color)
        self.fig.write_image(filename, *args, **kwargs)

    def to_obj(self, filename='dfn.obj', method='v1'):
        """Export fractures and faults to an OBJ surface file.

        Category: writer
        Tags: dfn, obj, export, fractures, faults
        Usage: scripts need a portable surface mesh representation of the DFN.

        Returns:
            None: writes the OBJ file.
        """
        logger.info(f'Exporting dfn + faults object to {filename}')
        obj_file = open(filename, 'w')
        obj_file.write('# Created by pydelling\n')
        obj_file.write('o dfn\n')
        global_id = 1
        for fracture in tqdm(self.dfn):
            obj_file.write(fracture.to_obj(global_id=global_id, method=method))
            global_id += fracture.n_side_points
        for fault in self.faults:
            fault_obj = fault.to_obj(global_id=global_id)
            obj_file.write(fault_obj)
            global_id += fault.num_points

    def to_vtk(self, filename='dfn.vtk', method='v1'):
        """Export fractures and faults to a VTK mesh with aperture cell data.

        Category: writer
        Tags: dfn, vtk, export, aperture, visualization
        Usage: scripts need to visualize a DFN in VTK-compatible tools.

        Returns:
            None: writes the VTK file.
        """
        from pathlib import Path
        logger.info(f'Exporting dfn + faults object to {filename}')
        self.to_obj('buffer.obj', method=method)
        meshio_mesh: meshio.Mesh = meshio.read('buffer.obj')
        meshio_mesh.cell_data = {'aperture': self.apertures}
        meshio.write(filename, meshio_mesh, file_format='vtk')
        Path('buffer.obj').unlink()




    def to_dfnworks(self, filename='dfn.dat', method='v1'):
        """Export fractures to DFNWorks polygon format.

        Category: writer
        Tags: dfn, dfnworks, export, fractures, polygons
        Usage: scripts need a DFNWorks-compatible input file from pydelling fractures.

        Returns:
            None: writes the DFNWorks file.
        """
        logger.info(f'Exporting dfn object to {filename}')
        dfn_file = open(filename, 'w')
        n_total_fractures = len(self.dfn)
        dfn_file.write(f'nPolygons: {n_total_fractures}\n')
        for fracture in tqdm(self.dfn):
            side_points = fracture.get_side_points(method=method)
            dfn_file.write(f'{len(side_points)} ')
            for point in side_points:
                dfn_file.write(f'{{{point[0]},{point[1]},{point[2]}}}')
            dfn_file.write('\n')

    def shift(self, x_shift=0, y_shift=0, z_shift=0):
        """Translate all fractures in the DFN.

        Category: preprocessing
        Tags: dfn, shift, translate, coordinates
        Usage: scripts need to align a fracture network with a mesh or coordinate origin.

        Returns:
            None: mutates fracture coordinates.
        """
        logger.info(f'Shifting dfn object by {x_shift}, {y_shift}, {z_shift}')
        for fracture in self.dfn:
            fracture.shift(x_shift, y_shift, z_shift)
        self._invalidate_surface_cache()


    def generate_dfn_plotly(self, add_centroid=False, size_color=False, fracture_color='blue'):
        """Build a Plotly 3D figure for the DFN.

        Category: preprocessing
        Tags: dfn, plotly, visualize, fractures, centroids
        Usage: scripts need a figure object for display, export, or further customization.

        Returns:
            plotly.graph_objects.Figure: 3D DFN figure.
        """
        logger.info('Generating plotly figure')
        fig = go.Figure()
        for fracture in tqdm(self.dfn):
            fracture_sides = fracture.get_side_points()
            if add_centroid:
                fig.add_trace(go.Scatter3d(
                    x=[fracture.x_centroid],
                    y=[fracture.y_centroid],
                    z=[fracture.z_centroid],
                    mode='markers',
                    marker=dict(
                        size=3.5,
                        color='black',
                        symbol='circle',
                        opacity=0.65
                    )
                ))
            # Add color depending on the fracture size
            if size_color:
                A = 255 / (self.max_size - self.min_size)
                B = 255 - A * self.max_size
                value = int(A * fracture.size + B)
                color = f'rgb({value}, 0, 0)'
            else:
                color = fracture_color
            fig.add_trace(go.Mesh3d(
                x=fracture_sides[:, 0],
                y=fracture_sides[:, 1],
                z=fracture_sides[:, 2],
                color=color,
                opacity=0.75,
            ))

        return fig

    @property
    def max_size(self):
        """Return the maximum fracture size in the DFN.

        Category: preprocessing
        Tags: dfn, size, maximum, statistics
        Usage: scripts need DFN size statistics or size-based color scales.

        Returns:
            float: maximum fracture size.
        """
        return max([fracture.size for fracture in self.dfn])

    @property
    def min_size(self):
        """Return the minimum fracture size in the DFN.

        Category: preprocessing
        Tags: dfn, size, minimum, statistics
        Usage: scripts need DFN size statistics or size-based color scales.

        Returns:
            float: minimum fracture size.
        """
        return min([fracture.size for fracture in self.dfn])

    def plot_radii_histogram(self, filename='radii_histogram.png'):
        """Build a histogram of fracture radii.

        Category: preprocessing
        Tags: dfn, histogram, radii, plot, statistics
        Usage: scripts need the fracture radius distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting radii histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([(fracture.size / 2) for fracture in self.dfn], bins=100)
        return fig, ax

    def plot_aperture_histogram(self, filename='aperture_histogram.png'):
        """Build a histogram of fracture apertures.

        Category: preprocessing
        Tags: dfn, histogram, aperture, plot, statistics
        Usage: scripts need the aperture distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting aperture histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([fracture.aperture for fracture in self.dfn], bins=100)
        return fig, ax

    def plot_hydraulic_aperture_histogram(self, filename='aperture_histogram.png'):
        """Build a histogram of fracture hydraulic apertures.

        Category: preprocessing
        Tags: dfn, histogram, hydraulic-aperture, plot, statistics
        Usage: scripts need the hydraulic aperture distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting hydraulic aperture histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([fracture.hyd_aperture for fracture in self.dfn], bins=100)
        return fig, ax

    def plot_transmissivity_histogram(self, filename='transmissivity_histogram.png'):
        """Build a histogram of fracture transmissivity.

        Category: preprocessing
        Tags: dfn, histogram, transmissivity, plot, statistics
        Usage: scripts need the transmissivity distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting aperture histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([fracture.transmissivity for fracture in self.dfn], bins=100)
        return fig, ax

    def plot_hkx_histogram(self, filename='hkx_histogram.png'):
        """Build a histogram of x hydraulic conductivity estimates.

        Category: preprocessing
        Tags: dfn, histogram, hydraulic-conductivity, plot, statistics
        Usage: scripts need transmissivity divided by aperture as an hk_x distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting hk_x histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([(fracture.transmissivity / fracture.aperture) for fracture in self.dfn], bins=100)
        return fig, ax


    def plot_storativity_histogram(self, filename='storativity_histogram.png'):
        """Build a histogram of fracture storativity.

        Category: preprocessing
        Tags: dfn, histogram, storativity, plot, statistics
        Usage: scripts need the storativity distribution.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting aperture histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([fracture.storativity for fracture in self.dfn], bins=100)
        return fig, ax

    @property
    def apertures(self) -> np.ndarray:
        """Return apertures for fractures and fault mesh triangles.

        Category: preprocessing
        Tags: dfn, aperture, faults, fractures, cell-data
        Usage: scripts need aperture values for VTK cell data or DFN statistics.

        Returns:
            np.ndarray: aperture values for all exported DFN cells.
        """
        fracture_apertures = [fracture.aperture for fracture in self.dfn]
        # Get fault apertures for each trimesh element
        fault_apertures = []
        for fault in self.faults:
            trimesh = fault.trimesh_mesh.triangles_center
            cur_fault_apertures = [fault.aperture for _ in range(len(trimesh))]
            fault_apertures += cur_fault_apertures

        return np.array(fracture_apertures + fault_apertures)

    def __add__(self, other):
        """
        Adds two dfn objects.
        
        Args:
            other (Any): Description.
        """
        if not isinstance(other, DfnPreprocessor):
            raise TypeError(f'{other} is not a DfnPreprocessor object')

        logger.info('Adding dfn objects')
        new_dfn = DfnPreprocessor()
        new_dfn.dfn = self.dfn + other.dfn
        new_dfn.faults = self.faults + other.faults
        return new_dfn

    @property
    def min_x(self):
        """Return the minimum fracture centroid x coordinate.

        Category: preprocessing
        Tags: dfn, bounds, x, minimum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: minimum x centroid.
        """
        return min([fracture.x_centroid for fracture in self.dfn])

    @property
    def max_x(self):
        """Return the maximum fracture centroid x coordinate.

        Category: preprocessing
        Tags: dfn, bounds, x, maximum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: maximum x centroid.
        """
        return max([fracture.x_centroid for fracture in self.dfn])

    @property
    def min_y(self):
        """Return the minimum fracture centroid y coordinate.

        Category: preprocessing
        Tags: dfn, bounds, y, minimum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: minimum y centroid.
        """
        return min([fracture.y_centroid for fracture in self.dfn])

    @property
    def max_y(self):
        """Return the maximum fracture centroid y coordinate.

        Category: preprocessing
        Tags: dfn, bounds, y, maximum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: maximum y centroid.
        """
        return max([fracture.y_centroid for fracture in self.dfn])

    @property
    def min_z(self):
        """Return the minimum fracture centroid z coordinate.

        Category: preprocessing
        Tags: dfn, bounds, z, minimum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: minimum z centroid.
        """
        return min([fracture.z_centroid for fracture in self.dfn])

    @property
    def max_z(self):
        """Return the maximum fracture centroid z coordinate.

        Category: preprocessing
        Tags: dfn, bounds, z, maximum
        Usage: scripts need DFN spatial bounds.

        Returns:
            float: maximum z centroid.
        """
        return max([fracture.z_centroid for fracture in self.dfn])

    def get_json(self):
        """Return a JSON-serializable representation of this DFN.

        Category: preprocessing
        Tags: dfn, json, serialize, fractures, faults
        Usage: scripts need portable fracture and fault metadata.

        Returns:
            dict: DFN representation with fractures and faults.
        """
        export_dict = {}
        export_dict['dfn'] = [fracture.get_json() for fracture in self.dfn]
        export_dict['faults'] = [fault.get_json() for fault in self.faults]
        return export_dict

    def to_json(self, filename):
        """Write this DFN to a JSON file.

        Category: writer
        Tags: dfn, json, export, serialize
        Usage: scripts need to persist fracture and fault metadata.

        Returns:
            None: writes the JSON file.
        """
        import json
        with open(filename, 'w') as f:
            json.dump(self.get_json(), f)

    @classmethod
    def from_json(cls, filename='dfn.json'):
        """Load a DFN from a JSON file.

        Category: preprocessing
        Tags: dfn, json, load, serialize
        Usage: scripts need to restore a saved fracture network from disk.

        Returns:
            DfnPreprocessor: loaded DFN instance.
        """
        import json
        from pydelling.preprocessing.dfn_preprocessor import Fracture, Fault
        with open(filename, 'r') as f:
            Fracture.local_id = 0  # Be careful with this
            Fault.local_id = 0  # Be careful with this
            dfn_dict = json.load(f)
            dfn_object = cls()
            dfn_object.dfn = [Fracture(**fracture) for fracture in dfn_dict['dfn']]
            dfn_object.faults = [Fault(**fault) for fault in dfn_dict['faults']]
            return dfn_object

    @classmethod
    def from_dict(cls, dict: dict):
        """Load a DFN from a dictionary.

        Category: preprocessing
        Tags: dfn, dict, load, serialize
        Usage: scripts already have parsed DFN JSON and need a DfnPreprocessor instance.

        Returns:
            DfnPreprocessor: loaded DFN instance.
        """
        from pydelling.preprocessing.dfn_preprocessor import Fracture, Fault
        Fracture.local_id = 0
        Fault.local_id = 0
        dfn_object = cls()
        dfn_object.dfn = [Fracture(**fracture) for fracture in dict['dfn']]
        dfn_object.faults = [Fault(**fault) for fault in dict['faults']]
        return dfn_object


    def __repr__(self):
        return f'DFN with {len(self.dfn)} fractures and {len(self.faults)} faults'

    def __str__(self):
        return self.__repr__()
