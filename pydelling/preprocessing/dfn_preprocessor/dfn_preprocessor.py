"""
Module documentation.


"""

from __future__ import annotations
import logging
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
                     aperture_constant=1E-3,
                     rock_type=None,
                     transmissivity_constant=None,
                     storativity_constant=None,
                     polygon=None,
                     ):
        """Add one fracture from orientation parameters or polygon geometry.

        Category: preprocessing
        Tags: dfn, fracture, add, aperture, polygon
        Usage: scripts need to construct a DFN incrementally from one fracture definition.

        Returns:
            None: appends a Fracture object to dfn.
        """
        from pydelling.preprocessing.dfn_preprocessor import Fracture
        self.dfn.append(Fracture(
            dip=dip,
            dip_dir=dip_dir,
            x=x,
            y=y,
            z=z,
            size=size,
            aperture=aperture,
            hydraulic_aperture=hydraulic_aperture,
            aperture_constant=aperture_constant,
            rock_type=rock_type,
            transmissivity_constant=transmissivity_constant,
            storativity_constant=storativity_constant,
            polygon=polygon,
        ))

    def add_fault(self, filename=None,
                  mesh=None,
                  aperture=None,
                  transmissivity=None,
                  effective_aperture=None,
                  porosity=None,
                  storativity=None,
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
            self.faults.append(filename)
        elif isinstance(filename, str) or isinstance(filename, Path):
            self.faults.append(Fault(filename=filename,
                                     mesh=mesh,
                                     aperture=aperture,
                                     transmissivity=transmissivity,
                                     effective_aperture=effective_aperture,
                                     porosity=porosity,
                                     storativity=storativity,
                                     ))
            logger.info(f"Fault with aperture {aperture} has been added from {filename}")
        else:
            logger.error('Fault filename must be a string or Fault object')
            raise TypeError('Fault filename must be a string or Fault object')

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



