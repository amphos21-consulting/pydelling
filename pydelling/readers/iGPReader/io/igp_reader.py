"""
This class reads the mesh and region information of an iGP project folder. It also builds an internal representation
of the mesh, and controls all the pre-processing functions related to the mesh.


"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List

import h5py
import numpy as np
import pandas as pd
import trimesh
import copy

from pydelling.config import config
# from pydelling.readers.iGPReader.geometry import *
from pydelling.preprocessing.mesh_preprocessor.geometry import BaseElement, BaseFace
from pydelling.readers.iGPReader.io import BaseReader
from pydelling.readers.raster_file_reader import RasterFileReader
from pydelling.readers.iGPReader.utils import get_output_path, RegionOperations
from tqdm import tqdm
import re
from copy import deepcopy
from .csv_writer import CsvWriter
from .pflotran_explicit_writer import PflotranExplicitWriter
from .pflotran_implicit_writer import PflotranImplicitWriter

logger = logging.getLogger(__name__)


class iGPReader(BaseReader, RegionOperations, CsvWriter, PflotranExplicitWriter, PflotranImplicitWriter):
    """Read iGP/GiD project folders and expose mesh, region, boundary, and material operations.

    Category: reader
    Tags: igp, gid, mesh, reader, vtk, regions, boundaries, materials
    Use when: scripts need to inspect, preprocess, export, or convert an iGP/GiD mesh project.
    """
    element_dict = {"4": "T", "5": "P", "6": "W", "8": "H"}
    face_dict = {'T': 3, 'Q': 4}

    def __init__(self, path,
                 project_name='iGP_project',
                 build_mesh=False,
                 output_folder='./results',
                 write_materials=True,
                 ):
        """
        __init__ method.
        
        Args:
            path (Any): Description.
            project_name (Any): Description.
            build_mesh (Any): Description.
            output_folder (Any): Description.
            write_materials (Any): Description.
        """
        self.elements = None
        self.boundaries = {}
        self.element_nodes = None
        logger.info("Initializing iGP Reader module")
        from pydelling.readers.iGPReader.io import AscReader, BoreholeReader, CsvWriter, PflotranExplicitWriter, PflotranImplicitWriter
        self.ExplicitWriter = PflotranExplicitWriter
        self.ImplicitWriter = PflotranImplicitWriter
        self.CsvWriter = CsvWriter
        self.RasterReader = RasterFileReader
        self.BoreholeReader = BoreholeReader
        self.path: Path
        if type(path) is not Path:
            self.path = Path(path)
        else:
            self.path = path
        # Read mesh data
        self.is_igp_present = False
        try:
            self.mesh_data = open(self.path / "data.mesh")
            self.region_data = open(self.path / "source.ss")
            self.centroid_data = open(self.path / "centroid.dat")
            self.is_igp_present = True
        except FileNotFoundError:
            self.is_igp_present = False
            logger.error("iGP project files were not found")
            raise FileNotFoundError("iGP project files were not found")

        self.build_mesh = build_mesh
        self.project_name = project_name
        self.is_write_materials = write_materials
        self.output_folder = output_folder
        self.mesh_info = {}
        self.region_info = {}
        self.region_dict = {}
        self.material_dict = {}
        self.material_info = {}
        self.centroids = None
        self.is_mesh_built = False
        if not self.build_mesh and self.is_igp_present:
            self.read_mesh_data()
            self.read_region_data()
            self.read_centroid_data()

        if self.build_mesh and self.is_igp_present:
            self.read_mesh_data()
            self.read_region_data()
            self.read_centroid_data()
            self.build_mesh_data()
        logger.info("iGP module initialization complete")
        # Create output folder if it is not created
        if self.output_folder:
            os.makedirs(self.output_folder, exist_ok=True)
        self.mesh_data = None
        self.centroid_data = None
        self.region_data = None

    def read_mesh_data(self):
        """Read nodes and element connectivity from the iGP data.mesh file.

        Category: reader
        Tags: igp, mesh, nodes, elements, connectivity
        Use when: the reader must load raw mesh topology before export or inspection.

        Returns:
            None: updates mesh_info, element_nodes, nodes, and nodes_output.
        """
        header = self.mesh_data.readline().split()
        self.mesh_info["n_elements"] = int(header[0])
        self.mesh_info["n_nodes"] = int(header[1])
        _elements = []
        for line in range(self.mesh_info["n_elements"]):
            mesh_line = self.mesh_data.readline().split()
            _elements.append([int(element) - 1 for element in mesh_line[1:]])
        # self.elements = np.array(_elements, dtype=np.int32) - 1  # To local ordering
        self.element_nodes = _elements
        assert len(self.element_nodes) == self.mesh_info["n_elements"], "Element number is incorrect"
        # Read node data
        _nodes = []
        for line in range(self.mesh_info["n_nodes"]):
            mesh_line = self.mesh_data.readline().split()
            _nodes.append(mesh_line)
        self.nodes = np.array(_nodes, dtype=np.float32)
        self.nodes_output = _nodes

        assert len(self.nodes) == self.mesh_info["n_nodes"], "Node number is incorrect"
        logger.info(f"Mesh data has been read from {self.path / 'data.mesh'}")

    def initialize_info_dicts(self):
        """Initialize material name and material metadata dictionaries.

        Category: reader
        Tags: igp, materials, metadata, initialize
        Use when: scripts need material metadata containers before assigning material properties.

        Returns:
            None: resets material_info and material name mappings.
        """
        self._material_names = {}
        for material_id, material in enumerate(self.material_dict):
            self._material_names[material_id] = material
        self.material_info = {}
        for material in self.material_dict:
            self.material_info[material] = {}

    def read_centroid_data(self):
        """Read cell centroid coordinates from centroid.dat.

        Category: reader
        Tags: igp, centroids, mesh, cells
        Use when: scripts need iGP element centroid coordinates for summaries, interpolation, or material assignment.

        Returns:
            None: populates centroids.
        """
        self.centroids = np.zeros(shape=(len(self.element_nodes), 3))
        for _ in range(self.mesh_info["n_elements"]):
            mesh_line = self.centroid_data.readline().split()
            self.centroids[int(mesh_line[-1]) - 1] = np.array(mesh_line[0:3], dtype=np.float32)
        logger.info(f"Centroid data has been read from {self.path / 'centroid.dat'}")

    def read_region_data(self):
        """Read region, boundary, and material assignments from source.ss.

        Category: reader
        Tags: igp, regions, boundaries, materials, source
        Use when: scripts need iGP region faces, boundary names, or material cell assignments.

        Returns:
            None: populates region_dict, material_dict, and region metadata.
        """
        is_reading = True
        header = self.region_data.readline().split()
        self.region_info["n_region"] = int(header[0])
        self.region_info["region_names"] = []
        _temp_array = []
        id_centroids = []
        for i in range(self.region_info["n_region"]):
            line = self.region_data.readline().rstrip()
            escaped_region_name = re.sub('[^A-Za-z0-9]+', '_', line)
            self.region_info["region_names"].append(escaped_region_name)
        for region_name in self.region_info["region_names"]:
            self.region_dict[region_name] = {"elements": [],
                                             "length": None,
                                             "centroid_id": []}
        # Read region entities
        while is_reading:
            is_element = True
            read_line = self.region_data.readline().split()
            if read_line[0] == "END":
                # self.region_data.readline()  # Skip that line
                is_element = False
                if read_line[1] == "IC":
                    is_reading = False
            if is_element:
                # Get the number of vertices expected by reading the face type
                n_vert = self.face_dict[read_line[0]]
                # Escape the region name (special characters or spaces)
                # A region defined with a space in GiD would appear as two different strings when splitting the line
                # by space. Instead, we know where the info (face type, centroid id, nodes, region name) are located
                # on the line depending on the type of face element.
                escaped_region_name = '_'.join(re.sub('[^A-Za-z0-9]+', '_', name) for name in read_line[2+n_vert:])
                self.region_dict[escaped_region_name]["elements"].append(read_line[2:2+n_vert])
                self.region_dict[escaped_region_name]["centroid_id"].append(read_line[1])

        for region_name in self.region_dict:
            self.region_dict[region_name]["elements"] = np.array(self.region_dict[region_name]["elements"],
                                                                 dtype=np.int32) - 1  # Pass to local id
            self.region_dict[region_name]["centroid_id"] = np.array(self.region_dict[region_name]["centroid_id"],
                                                                    dtype=np.int32) - 1  # Pass to local id
            self.region_dict[region_name]["length"] = len(self.region_dict[region_name]["elements"])

        # Read material ids
        self.region_data.readline()  # Skip to start of materials
        is_reading = True  # Activate again the reading of the file
        material_id = 0
        self.material_dict[material_id] = []  # Initialize tuple to add elements
        while is_reading:
            is_material = True  # Assume the line is a material id
            read_line = self.region_data.readline().split()
            if read_line == []:  # The end of the file has been reached
                is_reading = False
                break
            try:
                element_id = int(read_line[0])
                self.material_dict[material_id].append(element_id)
            except ValueError:
                material_name = read_line[0]
                self.material_dict[material_name] = np.array(self.material_dict.pop(material_id))
                material_id += 1
                self.material_dict[material_id] = []  # Initialize new material
        self.material_dict.pop(material_id)  # Take out the last material id (not used)

        logger.info(f"Region data has been read from {self.path / 'source.ss'}")

    # @timer_min
    def implicit_to_explicit(self,
                             dump_mesh_info=True,
                             write_cells=True,
                             write_regions=True,
                             ):
        """Convert an implicit iGP mesh into explicit PFLOTRAN mesh files.

        Category: mesh
        Tags: igp, pflotran, implicit, explicit, mesh, export
        Use when: scripts need PFLOTRAN explicit mesh, connection, region, or material files from an iGP project.

        Returns:
            None: writes explicit mesh artifacts to output_folder.
        """
        if not self.is_mesh_built:
            self.build_mesh_data()
        logger.info("Converting PFLOTRAN implicit mesh to explicit format")
        if write_cells:
            self.find_connectivities()  # Find the connections of the mesh
            # Write mesh file
            logger.info(f'Writing mesh file to {self.output_folder}')
            exp_mesh_filename = f"{self.project_name}.mesh"
            if self.output_folder is None:
                output_file = open(exp_mesh_filename, "w")
            else:
                output_file = open(os.path.join(self.output_folder, exp_mesh_filename), "w")
            self.ExplicitWriter.write_cells(self, output_file)
            self.ExplicitWriter.write_connections(self, output_file)
            if dump_mesh_info:
                self.ImplicitWriter.write_elements(self, output_file)  # Write elements for mesh visualization
                self.ImplicitWriter.write_nodes(self, output_file)  # Write node_ids for mesh visualization
            output_file.close()
            self.write_hdf5_domain()

        # Write condition data
        if write_regions:
            self.ExplicitWriter.write_condition_data(self)
            if self.is_write_materials:
                self.ExplicitWriter.write_materials(self)

    def write_explicit_mesh_in_csv(self):
        """Write explicit mesh cell and connection data as CSV files.

        Category: writer
        Tags: igp, mesh, csv, centroids, connections
        Use when: scripts need tabular explicit mesh geometry for inspection or external processing.

        Returns:
            None: writes CSV files using the configured CsvWriter.
        """
        logger.info(f"Writing explicit mesh in csv format")
        self.CsvWriter.write_csv_cells(self)
        self.CsvWriter.write_csv_connection(self)

    def write_hdf5_domain(self):
        """Write the iGP mesh domain to an HDF5 postprocessing file.

        Category: writer
        Tags: igp, mesh, hdf5, domain, postprocessing
        Use when: scripts need a PFLOTRAN-style HDF5 domain file for postprocessing.

        Returns:
            None: writes the domain HDF5 file.
        """
        if self.output_folder is None:
            hdf5_filename = self.project_name + "-domain.h5"
        else:
            hdf5_filename = os.path.join(self.output_folder, self.project_name + "-domain.h5")
        logger.info(f"Writing mesh to hdf5 ({hdf5_filename})")
        hdf5_file = h5py.File(hdf5_filename, "w")
        self.ExplicitWriter.write_domain_postprocess_hdf5(self, export_file=hdf5_file)
        hdf5_file.close()

    def find_connectivities(self):
        """Find cell-to-cell connectivity by matching shared faces.

        Category: mesh
        Tags: igp, mesh, connectivity, faces, cells
        Use when: scripts need explicit mesh connections before PFLOTRAN export.

        Returns:
            None: populates connections.
        """
        assert self.is_mesh_built, "Mesh is read but not built"
        logger.info("Finding implicit mesh connectivities")
        face_array = []
        for element in self.elements:
            element: BaseElement
            for face in element.faces:
                ordered_face = sorted(element.faces[face].nodes)
                ordered_face.append(element.local_id)
                ordered_face.append(face)
                face_array.append(ordered_face)
        sorted_face_array = sorted(face_array)
        # Connectivity matrix
        conn_dict = {}

        for face_id in range(len(sorted_face_array) - 1):
            face_elements_a = sorted_face_array[face_id][:-2]
            face_elements_b = sorted_face_array[face_id + 1][:-2]
            id_a = sorted_face_array[face_id][-2]
            id_b = sorted_face_array[face_id + 1][-2]
            face_a = sorted_face_array[face_id][-1]
            face_b = sorted_face_array[face_id + 1][-1]
            if face_elements_a == face_elements_b:
                if not id_a in conn_dict:
                    conn_dict[id_a] = {}
                    conn_dict[id_a][id_b] = face_a
                else:
                    conn_dict[id_a][id_b] = face_a
                # if not id_b in conn_dict: # only one way
                #     conn_dict[id_b] = {}
                #     conn_dict[id_b][id_a] = face_b
                # else:
                #     conn_dict[id_b][id_a] = face_b
        conn_dict_ordered = OrderedDict(conn_dict)
        self.connections = sorted(conn_dict_ordered.items())

    def raster_interpolator(self,
                            regions: List,
                            raster_filenames: dict,
                            raster_folder=None,
                            top_regions: List = None,
                            top_region_offset: float = None,
                            second_layer: str = None,
                            second_layer_offset = None,
                            max_error: float = None, # Maximum error allowed in the interpolation
                            ):
        """Interpolate raster layer elevations onto matching iGP mesh regions.

        Category: interpolation
        Tags: igp, raster, interpolation, layers, regions
        Use when: scripts need to move mesh nodes to raster-defined stratigraphic layers.

        Returns:
            None: mutates mesh node coordinates for selected regions.
        """
        logger.info("Interpolating raster regions to mesh")
        if max_error is not None:
            logger.info(f"Maximum error allowed: {max_error} m")
        if top_regions is None:
            top_regions = []
        if raster_folder is None:
            raster_folder = './'

        for region in regions:
            self._raster_max_error = 0.0
            logger.info(f"Interpolating region {region}")
            raster_current_region_filename = os.path.join(raster_folder, raster_filenames[region])
            raster_data = self.RasterReader(raster_current_region_filename)
            # print(f"Elements in face length is {len(iGP_data.region_dict[region]['elements'])}")
            id_list = np.unique(self.region_dict[region]["elements"].flatten())
            _test = []
            if region in top_regions:
                assert top_region_offset is not None, "Top region offset is not defined"
                logger.info(f"An offset of +{top_region_offset} m will be applied in the z-direction to region {region}")
            if region == second_layer:
                assert second_layer_offset is not None, "Second layer offset (difference between the top layer) is not defined"
                logger.info(f"Region {region} has been selected as the second layer region. Thus, its node_ids will be displaced {second_layer_offset}m from the top raster file")
            xy_raster = raster_data.get_xy_data()
            for mesh_id in id_list:
                x_mesh = self.nodes[mesh_id][0]
                y_mesh = self.nodes[mesh_id][1]
                # Raster data
                z_raster = raster_data.get_data_from_coordinates(x_mesh, y_mesh)
                z_offset = top_region_offset if region in top_regions else 0.0
                interpolation_difference = abs((z_raster + z_offset) - self.nodes[mesh_id][2])

                z_second_layer_diff = second_layer_offset if region == second_layer else 0.0  # Corrects the second layer on a layer based mesh
                if max_error is None:
                    self.nodes[mesh_id][2] = z_raster + z_offset + z_second_layer_diff
                    self._raster_max_error = interpolation_difference if interpolation_difference > self._raster_max_error else self._raster_max_error
                else:
                    if interpolation_difference < max_error:
                        self.nodes[mesh_id][2] = z_raster + z_offset + z_second_layer_diff
                        self._raster_max_error = interpolation_difference if interpolation_difference > self._raster_max_error else self._raster_max_error
                    else:
                        pass
            logger.info(f"Interpolation of region {region} completed. Max absolute difference {self._raster_max_error:1.2f}m")

        # node_ids = raster_interpolator(self.path, raster_folder, raster_filenames)
        # self.node_ids = node_ids  # Update the mesh with the moved node_ids
        return self.nodes

    def raster_interpolator_semistructured(self,
                                           regions: List,
                                           raster_filenames: dict,
                                           raster_folder: str | None = None,
                                           n_nearest: int = 5,
                                           material_subset: List = None,
                                           min_samples: int = 10,
                                           eps: float = 0.5,
                                           growth_rate: float = None,
                                           ):
        """Interpolate raster topography through semi-structured vertical mesh columns.

        Category: interpolation
        Tags: igp, raster, interpolation, semi-structured, topography
        Use when: scripts need to move layered mesh nodes proportionally below a raster surface.

        Returns:
            None: mutates mesh node coordinates for selected regions.
        """

        logger.info("Interpolating topography layers to the mesh")
        if raster_folder is None:
            raster_folder = './'

        for region in regions:
            self._raster_max_error = 0.0
            logger.info(f"Interpolating region {region}")
            raster_current_region_filename = os.path.join(raster_folder, raster_filenames[region])
            raster_data = self.RasterReader(raster_current_region_filename)
            # print(f"Elements in face length is {len(iGP_data.region_dict[region]['elements'])}")
            id_list = np.unique(self.region_dict[region]["elements"].flatten())
            _test = []
            for mesh_id in tqdm(id_list, desc=f"Interpolating region {region}"):
                x_mesh = self.nodes[mesh_id][0]
                y_mesh = self.nodes[mesh_id][1]
                # Raster data
                z_raster = raster_data.get_data_from_coordinates(x_mesh, y_mesh)
                # Get the nearest neighbours in the z-direction
                z_nearest_ids = self.get_nodes_from_x_y(
                    x=x_mesh,
                    y=y_mesh,
                    materials=material_subset,
                    min_samples=min_samples,
                    eps=eps,
                    top_region_name=region,
                )
                if n_nearest is not None:
                    z_nearest_ids = z_nearest_ids[-n_nearest:]
                z_nearest_nodes = self.nodes[z_nearest_ids]
                # Proportionally move the mesh node
                z_nearest_new = z_nearest_nodes.copy()
                z_nearest_new[:, 2] -= z_nearest_new[:, 2].min()
                z_nearest_new[:, 2] /= z_nearest_new[:, 2].max()
                # Apply a logarithmic growth
                if growth_rate is not None:
                    z_nearest_new[:, 2] = self.geometric_growth(len(z_nearest_new), growth_rate)
                    if not hasattr(self, "info_geometric_growth"):
                        geometryic_growth_formatted_string = [f"{i:1.2f}" for i in z_nearest_new[:, 2]]
                        logger.info(f"The following geometrical spacing (growth_rate {growth_rate}) has been applied to the z-nodes: {geometryic_growth_formatted_string}")
                        self.info_geometric_growth = True

                z_nearest_new[:, 2] *= (z_raster - z_nearest_nodes[:, 2].min())
                z_nearest_new[:, 2] += z_nearest_nodes[:, 2].min()
                for z_id in z_nearest_ids:
                    self.nodes[z_id][2] = z_nearest_new[z_nearest_ids == z_id][0][2]
            logger.info(f"Interpolation of region {region} completed.")

    def geometric_growth(self, n, growth_rate=0.3) -> list:
        """Generate normalized geometric spacing values from 0 to 1.

        Category: util
        Tags: growth, spacing, interpolation, mesh
        Use when: scripts need nonuniform vertical interpolation weights for layered meshes.

        Returns:
            list: normalized spacing values.
        """
        values = [1.0 - (1.0 - growth_rate) ** i for i in range(n)]
        values = np.array(values)
        values /= values.max()
        return list(values)


    def write_ASCII_meshfile(self, filename):
        """Write the iGP mesh in PFLOTRAN ASCII mesh format.

        Category: writer
        Tags: igp, pflotran, ascii, mesh, export
        Use when: scripts need an implicit PFLOTRAN mesh file from iGP mesh data.

        Returns:
            None: writes the ASCII mesh file.
        """
        # TODO: Set-up default filename
        if self.is_mesh_built:  # We need it to dump it correctly into implicit/explicit format
            if self.output_folder is None:
                file = open(filename, "w")
            else:
                file = open(os.path.join(self.output_folder, filename), "w")
            # Write header
            file.write(f"{self.mesh_info['n_elements']} {self.mesh_info['n_nodes']}\n")
            for element in self.elements:
                file.write(
                    f"{config.globals.element_dict[len(element.nodes)]} {' '.join(map(str, element.nodes + 1))}\n")
            for id, node in enumerate(self.nodes_output):
                file.write(f"{node[0]} {node[1]} {self.nodes[id][2]:5.5f}\n")
                # file.write(f"{node[0]} {node[1]} {node[2]}\n")
            file.write("\n")
            file.close()
        else:  # If mesh is not internally built
            if self.output_folder is None:
                file = open(filename, "w")
            else:
                file = open(os.path.join(self.output_folder, filename), "w")
            file.write(f"{self.mesh_info['n_elements']} {self.mesh_info['n_nodes']}\n")
            for element in self.element_nodes:  # Element data
                file.write(f"{config.globals.element_dict[len(element)]} {' '.join(map(str, element + 1))}\n")
            for id, node in enumerate(self.nodes_output):  # Node coordinates data
                file.write(f"{node[0]} {node[1]} {self.nodes[id][2]:5.5f}\n")
            file.write("\n")
            file.close()
        logger.info(f"Mesh data has been properly exported to PFLOTRAN mesh ASCII format into the {filename} file")

    def write_hdf5_meshfile(self, filename="regions.h5"):
        """Write the iGP mesh and regions in implicit HDF5 format.

        Category: writer
        Tags: igp, pflotran, hdf5, mesh, regions
        Use when: scripts need PFLOTRAN implicit HDF5 domain and region datasets.

        Returns:
            None: writes the HDF5 mesh file.
        """
        hdf5_filename = filename
        if not filename.endswith(".h5"):
            hdf5_filename += ".h5"
        hdf5_file = h5py.File(hdf5_filename, "w")
        self.ImplicitWriter.write_domain_hdf5(self, hdf5_file)
        self.ImplicitWriter.write_regions_hdf5(self, hdf5_file)
        hdf5_file.close()
        logger.info(f"Mesh file has been properly written into '{hdf5_filename}'")

    def set_material_values_from_borehole_data(self):
        """Assign material properties using configured borehole data.

        Category: preprocessing
        Tags: igp, materials, borehole, properties
        Use when: scripts need to populate iGP material properties from borehole inputs.

        Returns:
            None: mutates material information from borehole reader output.
        """
        logger.info("Setting permeability data from borehole files")
        # assert self.is_mesh_built, "Mesh is not built"
        borehole_reader = self.BoreholeReader(igp_reader=self)
        borehole_reader.run()

    def set_material_from_list(self, material_name: str, centroid_list: list):
        """Assign a material name to a list of one-based cell ids.

        Category: preprocessing
        Tags: igp, materials, cells, assignment
        Use when: scripts need to override or create iGP material assignments from selected cells.

        Returns:
            None: updates material_dict.
        """
        self.material_dict[material_name] = np.array(centroid_list)
        logger.info(f"Material {material_name} has been assigned to {len(centroid_list)} centroids")

    def assign_heterogeneous_materials(self):
        """Assign heterogeneous permeability and porosity arrays from configuration.

        Category: preprocessing
        Tags: igp, materials, heterogeneous, permeability, porosity
        Use when: scripts need configured material property distributions written into material_info.

        Returns:
            None: populates heterogeneous material arrays.
        """
        logger.info('Processing heterogeneous material properties')
        for material in config.borehole_processing.heterogeneous_distribution:
            material_properties = {'permeability': [], 'porosity': []}
            for property in config.borehole_processing.heterogeneous_distribution[material]:
                if config.borehole_processing.heterogeneous_distribution[material][property].type == 'constant':
                    material_properties = self._assign_constant_heterogeneous_materials(material=material, property=property, material_properties=material_properties)
                elif config.borehole_processing.heterogeneous_distribution[material][property].type == 'linear':
                    material_properties = self._assign_linear_heterogeneous_materials(material=material, property=property, material_properties=material_properties)
                elif config.borehole_processing.heterogeneous_distribution[material][property].type == 'topography':
                    material_properties = self._assign_topography_heterogeneous_materials(material=material, property=property, material_properties=material_properties)
                elif config.borehole_processing.heterogeneous_distribution[material][property].type == 'step':
                    material_properties = self._assign_step_heterogeneous_materials(material=material, property=property, material_properties=material_properties)
            if material_properties['permeability']:
                self.material_info[material]['heterogeneous_permeability'] = np.array(material_properties['permeability']).astype(np.float)
            if material_properties['porosity']:
                self.material_info[material]['heterogeneous_porosity'] = np.array(material_properties['porosity']).astype(np.float)


    def _assign_constant_heterogeneous_materials(self, material: str, property: str, material_properties: Dict[str, List]) -> Dict[str, List]:
        """
        This method assigns a constant material value to a given material

        Args:
            material: current material to assign properties to
            property: property to be assigned (currently works with porosity and permeabiltiy)
            material_properties: dictionary containing the resulting heterogeneous distributions

        Returns:
            The modified material_properties object
        """
        material_features = config.borehole_processing.heterogeneous_distribution[material][property]
        logger.info(f"Adding constant {property} (value={material_features.value}) to the {material} material")
        for _ in self.material_dict[material] - 1:
            material_properties[property].append(material_features.value)
        return material_properties

    def _assign_step_heterogeneous_materials(self, material: str, property: str, material_properties: Dict[str, List]) -> Dict[str, List]:
        """
        This method assigns a step based material properties to a given material

        Args:
            material: current material to assign properties to
            property: property to be assigned (currently works with porosity and permeabiltiy)
            material_properties: dictionary containing the resulting heterogeneous distributions

        Returns:
            The modified material_properties object
        """
        material_features = config.borehole_processing.heterogeneous_distribution[material][property]
        logger.info(f"Adding step based {property} to the {material} material. Steps: {material_features.z_steps} Values: {material_features.value_list}")
        for centroid in self.centroids[self.material_dict[material] - 1]:
            centroid_bin = np.digitize(centroid[2], material_features.z_steps)
            value = material_features.value_list[centroid_bin - 1]
            material_properties[property].append(value)
        return material_properties

    def _assign_topography_heterogeneous_materials(self, material: str, property: str, material_properties: Dict[str, List]) -> Dict[str, List]:
        """
        This method assigns heterogeneous material properties following that the highest value is set on the topography layer

        Args:
            material: current material to assign properties to
            property: property to be assigned (currently works with porosity and permeabiltiy)
            material_properties: dictionary containing the resulting heterogeneous distributions

        Returns:
            The modified material_properties object
        """
        # Open Topography raster file
        material_features = config.borehole_processing.heterogeneous_distribution[material][property]
        logger.info(
            f"Adding linear {property} value taking into account topography of layer {material_features.topography_region} to material {material} in such a way that f(z_topography) = {material_features.value_top}."
            f"{f' Values below {material_features.z_bot}m are kept constant and equal to {material_features.value_bot}' if material_features.bottom_constant else ''}")
        raster_current_region_filename = Path(config.data_files.raster_file_folder) / config.data_files.raster_filenames[material_features.topography_region]
        raster_data = self.RasterReader(raster_current_region_filename)

        for centroid in self.centroids[self.material_dict[material] - 1]:
            x_mesh = centroid[0]  # x-coordinate of centroid
            y_mesh = centroid[1]  # y-coordinate of centroid
            # Raster data
            d_raster = raster_data.info_dict["cellsize"]
            origin_x = raster_data.info_dict["xllcorner"]
            origin_y = raster_data.info_dict["yllcorner"]
            ix = int(np.floor((x_mesh - origin_x) / (1.001 * d_raster)))  # 1.001 value is used to avoid issues with
            # the floor function
            iy = int(np.floor((y_mesh - origin_y) / (1.001 * d_raster)))  # 1.001 value is used to avoid issues with
            # the floor function
            iy = int(raster_data.info_dict["ncols"] - iy - 1)
            z_offset = config.raster_refinement.top_offset if config.raster_refinement.top_offset else 0.0
            z_raster = raster_data.data[iy, ix] + z_offset

            if material_features.log:
                # z_topography = self.
                value = self.linear_log_distribution(x=centroid[2],
                                                   x_top=z_raster,
                                                   x_bot=material_features.z_bot,
                                                   y_top=material_features.value_top,
                                                   y_bot=material_features.value_bot,
                                                   )
                if material_features.bottom_constant:
                    value = value if centroid[2] > material_features.z_bot else material_features.value_bot
                material_properties[property].append(value)
            else:
                value = self.linear_distribution(x=centroid[2],
                                                   x_top=z_raster,
                                                   x_bot=material_features.z_bot,
                                                   y_top=material_features.value_top,
                                                   y_bot=material_features.value_bot,
                                                   )
                if material_features.bottom_constant:
                    value = value if centroid[2] > material_features.z_bot else material_features.value_bot
                material_properties[property].append(value)
        return material_properties


    def _assign_linear_heterogeneous_materials(self, material: str, property: str, material_properties: Dict[str, List]) -> Dict[str, List]:
        """
        This method assigns heterogeneous properties giving four linear values to a given material

        Args:
            material: current material to assign properties to
            property: property to be assigned (currently works with porosity and permeabiltiy)
            material_properties: dictionary containing the resulting heterogeneous distributions

        Returns:
            The modified material_properties object
        """
        logger.info(f"Adding linear {property} to the {material} material")
        material_features = config.borehole_processing.heterogeneous_distribution[material][property]
        for centroid in self.centroids[self.material_dict[material] - 1]:
            if material_features.log:
                value = self.linear_log_distribution(x=centroid[2],
                                                   x_top=material_features.z_top,
                                                   x_bot=material_features.z_bot,
                                                   y_top=material_features.value_top,
                                                   y_bot=material_features.value_bot,
                                                   )
                if material_features.bottom_constant:
                    value = value if centroid[2] > material_features.z_bot else material_features.value_bot
                material_properties[property].append(value)
            else:
                value = self.linear_distribution(x=centroid[2],
                                                   x_top=material_features.z_top,
                                                   x_bot=material_features.z_bot,
                                                   y_top=material_features.value_top,
                                                   y_bot=material_features.value_bot,
                                                   )
                if material_features.bottom_constant:
                    value = value if centroid[2] > material_features.z_bot else material_features.value_bot
                material_properties[property].append(value)
        return material_properties

    @staticmethod
    def linear_distribution(x, y_bot, y_top, x_bot, x_top):
        """Evaluate a linear interpolation between bottom and top values.

        Category: util
        Tags: interpolation, linear, materials, distribution
        Use when: scripts need depth-based material values between two endpoints.

        Returns:
            Any: interpolated value at x.
        """
        return (y_top - y_bot) / (x_top - x_bot) * x + (y_bot * x_top - y_top * x_bot) / (x_top - x_bot)

    @staticmethod
    def linear_log_distribution(x, x_top, x_bot, y_top, y_bot):
        """Evaluate log-scaled linear interpolation between bottom and top values.

        Category: util
        Tags: interpolation, logarithmic, materials, distribution
        Use when: scripts need depth-based material values that vary logarithmically.

        Returns:
            Any: interpolated positive value at x.
        """
        y_top = np.log10(y_top)
        y_bot = np.log10(y_bot)
        return np.power(10.0, (y_top - y_bot) / (x_top - x_bot) * x + (y_bot * x_top - y_top * x_bot) / (x_top - x_bot))

    def export_materials_in_hdf5(self):
        """Export heterogeneous material properties to PFLOTRAN-style HDF5 datasets.

        Category: writer
        Tags: igp, materials, hdf5, permeability, porosity
        Use when: scripts need heterogeneous permeability or porosity files from material_info.

        Returns:
            None: writes one HDF5 file per exported material property.
        """
        idx_set = np.array([])
        perm_dataset = np.array([])
        porosity_dataset = np.array([])

        for material in self.material_info:
            idx_set = np.concatenate([idx_set, self.material_dict[material]]).astype(np.int)
            if 'heterogeneous_permeability' in self.material_info[material]:
                perm_dataset = np.concatenate([perm_dataset, self.material_info[material]['heterogeneous_permeability']])
            if 'heterogeneous_porosity' in self.material_info[material]:
                porosity_dataset = np.concatenate([porosity_dataset, self.material_info[material]['heterogeneous_porosity']])
        # idx_set = idx_set
        if perm_dataset.size != 0:
            assert perm_dataset.min != 0, "Minimum value of index cannot be 0, change to PFLOTRAN numbering [1, N]"
            self._export_hdf5_dataset(index_dataset=idx_set,
                                      dataset=perm_dataset,
                                      name='permeability')
        if porosity_dataset.size != 0:
            assert porosity_dataset.min != 0, "Minimum value of index cannot be 0, change to PFLOTRAN numbering [1, N]"
            self._export_hdf5_dataset(index_dataset=idx_set,
                                      dataset=porosity_dataset,
                                      name='porosity')

    @staticmethod
    def _export_hdf5_dataset(index_dataset: np.array, dataset: np.array, name):
        """
        _export_hdf5_dataset method.
        
        Args:
            index_dataset (np.array): Description.
            dataset (np.array): Description.
            name (Any): Description.
        """
        hdf5_filename = get_output_path() / f"{name}.h5"
        logger.info(f"Writing {name} dataset to hdf5 ({hdf5_filename})")
        with h5py.File(hdf5_filename, "w") as hdf5_file:
            hdf5_file.create_dataset('Cell Ids', data=index_dataset)
            hdf5_file.create_dataset(name, data=dataset)

    def write_csv(self, filename):
        """Write mesh node coordinates to CSV format.

        Category: writer
        Tags: igp, mesh, csv, nodes, coordinates
        Use when: scripts need a simple CSV export of adjusted iGP mesh node coordinates.

        Returns:
            None: writes the CSV file.
        """
        # TODO: set-up default filename
        if self.output_folder is None:
            file = open(filename, "w")
        else:
            file = open(os.path.join(self.output_folder, filename), "w")
        # Write header
        for id, node in enumerate(self.nodes_output):
            file.write(f"{node[0]},{node[1]},{self.nodes[id][2]:5.5f}\n")
        file.close()
        logger.info(f"Mesh data has been properly exported to csv format into the '{filename}' file")

    def to_vtk(self, filename='mesh.vtk'):
        """Export the iGP/GiD mesh to a VTK file using meshio.

        Category: reader
        Tags: igp, gid, mesh, vtk, export, visualization
        Use when: the user asks to convert an iGP/GiD project into a VTK mesh file.

        Returns:
            None: writes the VTK file to filename.
        """
        import meshio as msh

        cell_type_by_node_count = {
            4: "tetra",
            5: "pyramid",
            6: "wedge",
            8: "hexahedron",
        }
        cells = {}
        for element in self.element_nodes:
            cell_type = cell_type_by_node_count.get(len(element))
            if cell_type is None:
                logger.warning(f"Skipping unsupported VTK cell with {len(element)} nodes")
                continue
            cells.setdefault(cell_type, []).append(element)
        mesh = msh.Mesh(points=self.nodes, cells=cells)
        mesh.write(filename)
        logger.info(f"Mesh data has been properly exported to VTK into the '{filename}' file")

    @staticmethod
    def chunks(l, n):
        """Split a sequence into fixed-size chunks.

        Category: util
        Tags: chunks, multiprocessing, mesh, helper
        Use when: mesh building or classification needs work split across processes.

        Returns:
            list: chunked sequence slices.
        """
        return [l[i:i + n] for i in range(0, len(l), n)]

    def build_mesh_data(self, processes=1,
                        generate_cells=True,
                        generate_boundaries=True,
                        ):
        """Build pydelling mesh element objects from iGP node connectivity.

        Category: mesh
        Tags: igp, mesh, elements, boundaries, preprocessing
        Use when: scripts need explicit mesh objects, boundary objects, or downstream mesh preprocessing.

        Returns:
            None: populates elements, boundaries, and mesh-built state.
        """
        from pydelling.preprocessing.mesh_preprocessor.geometry import TetrahedraElement, WedgeElement, HexahedraElement, TriangleFace, QuadrilateralFace
        if config.general.constant_centroids:
            logger.info('The location of the centroids will not be changed after refining the boundaries')
        if processes == 1:
            logger.info("Building implicit mesh structure")
            temp = []
            amount_read = 0.0
            if generate_cells:
                for id_local, element in tqdm(enumerate(self.element_nodes), total=len(self.element_nodes), desc='Building mesh'):
                    n_type = len(element)
                    if n_type == 4:  # This is a Wedge object
                        temp.append(TetrahedraElement(node_ids=element,
                                                      node_coords=self.nodes[element],
                                                      local_id=id_local,
                                                      centroid_coords=self.centroids[id_local] if config.general.constant_centroids else None,
                                                      # centroid_coords=self.centroids[id_local]
                                                      ))
                    if n_type == 6:  # This is a Wedge object
                        temp.append(WedgeElement(node_ids=element,
                                                 node_coords=self.nodes[element],
                                                 local_id=id_local,
                                                 centroid_coords=self.centroids[id_local] if config.general.constant_centroids else None,
                                                 # centroid_coords=self.centroids[id_local]
                                                 ))
                    if n_type == 8:  # This is a Hexahedra object
                        temp.append(HexahedraElement(node_ids=element,
                                                     node_coords=self.nodes[element],
                                                     local_id=id_local,
                                                     centroid_coords=self.centroids[id_local] if config.general.constant_centroids else None,
                                                     # centroid_coords=self.centroids[id_local]
                                                     ))
                self.elements = temp
            # Generate boundary information
            if generate_boundaries:
                for boundary in tqdm(self.region_dict, desc='Building boundary mesh'):
                    temp_boundary = []
                    for element in self.region_dict[boundary]['elements']:
                        n_type = len(element)
                        if n_type == 4:
                            temp_boundary.append(QuadrilateralFace(
                                node_ids=element,
                                node_coords=self.nodes[element],
                            )
                            )
                        if n_type == 3:
                            temp_boundary.append(TriangleFace(
                                node_ids=element,
                                node_coords=self.nodes[element],
                            )
                            )
                    self.boundaries[boundary] = temp_boundary
            self.is_mesh_built = True
        else:
            logger.info(f"Building internal mesh using multiprocessing with {processes} processes")
            from multiprocessing import Process, Manager
            import multiprocessing as mp
            with Manager() as manager:
                shared_list = manager.list()
                processes_list = []
                total_number_of_elements = len(self.element_nodes)
                number_of_processes = processes if processes is not None else mp.cpu_count() - 1
                chunk_size = int(total_number_of_elements / number_of_processes)
                chunks = self.chunks(self.element_nodes, chunk_size)

                for i, chunk in enumerate(chunks):
                    p = Process(target=parallel_build_mesh_data, args=(chunk, self.nodes, shared_list, i, chunk_size, self.centroids))
                    processes_list.append(p)
                for id, process in enumerate(processes_list):
                    process.start()
                    logger.info(f"Process {id} has been started")
                for id, process in enumerate(processes_list):
                    process.join()
                    logger.info(f"Process {id} has finished")
                self.elements = list(shared_list)
            # Order self.elements list following the local_id
            self.elements = sorted(self.elements, key=lambda x: x.local_id)

            self.is_mesh_built = True

    def set_material_z_ranges(self):
        """Compute min and max centroid z values for each material.

        Category: preprocessing
        Tags: igp, materials, z-range, centroids
        Use when: scripts need vertical material extents for summaries or property assignment.

        Returns:
            None: stores z ranges in material_info.
        """
        logger.debug("Calculating z-ranges of the materials")
        self.material_ranges = {}
        for material in self.material_dict:
            _material_centroids: np.array = self.centroids[self.material_dict[material] - 1]
            _min_z = np.min(_material_centroids[:, 2])
            _max_z = np.max(_material_centroids[:, 2])
            self.material_info[material] = {"min_z": _min_z, "max_z": _max_z}

    def write_input_raster_files(self, downsample_factor=None, file_format="asc"):
        """Export configured input raster files as ASC or CSV.

        Category: writer
        Tags: igp, raster, export, asc, csv
        Use when: scripts need copies or downsampled versions of configured raster refinement inputs.

        Returns:
            None: writes raster files to the output path.
        """
        logger.info(f"Exporting raster files read from {config.data_files.raster_file_folder}")
        for region in config.raster_refinement.regions:
            raster_current_region_filename = os.path.join(config.data_files.raster_file_folder, config.data_files.raster_filenames[region])
            raster_data = self.RasterReader(raster_current_region_filename)
            if downsample_factor:
                raster_data.downsample_data(slice_factor=downsample_factor)
            if file_format == 'asc':
                raster_data.dump_to_asc(output_file=get_output_path() / f"{region}.asc")
            elif file_format == "csv":
                raster_data.dump_to_csv(output_file=get_output_path() / f"{region}.csv")

    def export_recharge_file(self, csv_export=False):
        """Convert configured recharge raster data to model units and export it.

        Category: writer
        Tags: igp, recharge, raster, hdf5, csv
        Use when: scripts need a recharge gridded dataset for PFLOTRAN input.

        Returns:
            None: writes recharge.h5 and optionally recharge.csv.
        """
        if config.data_files.recharge_file:
            logger.info(f"Processing recharge file located at {config.data_files.recharge_file}")
            recharge_data = self.RasterReader(config.data_files.recharge_file)
        else:
            logger.error("A recharge file has to be submitted in the configuration file")
            raise FileNotFoundError("Recharge file was not submitted in the configuration file")
        # Transform recharge data to m/s
        recharge_data.change_data(recharge_data.data / (1000.0 * 365 * 24 * 3600))
        recharge_data.change_data(np.flip(np.transpose(recharge_data.data), axis=1))
        recharge_data.export_to_gridded_dataset(filename="recharge.h5")
        if csv_export:
            recharge_data.dump_to_csv(output_file="recharge.csv")

    def export_region_data(self, regions: List = None):
        """Export node coordinates for selected iGP regions to CSV.

        Category: writer
        Tags: igp, regions, nodes, csv, export
        Use when: scripts need coordinate tables for boundary or region nodes.

        Returns:
            None: writes one CSV file per region.
        """
        regions = regions if regions else config.extract_data.regions
        for region in regions:
            id_list = np.unique(self.region_dict[region]["elements"].flatten())
            node_coordinates_df: pd.DataFrame = pd.DataFrame(self.nodes[id_list], columns=["x", "y", "z"])
            node_coordinates_df.to_csv(get_output_path() / f"{region}_nodes.csv", index=False)

    def get_mesh(self):
        """Return iGP cell centroids for mesh-oriented analysis.

        Category: mesh
        Tags: igp, mesh, centroids, cells
        Use when: scripts need the mesh centroid array from an iGP project.

        Returns:
            Any: centroids loaded from centroid.dat.
        """
        return self.centroids

    @property
    def materials(self) -> pd.DataFrame:
        """Return material assignments from the iGP model.

        Category: reader
        Tags: igp, materials, cells, metadata
        Use when: scripts need material names or cell assignments for an iGP project.

        Returns:
            dict: material assignment mapping.
        """
        return self.material_dict

    @property
    def n_mesh_elements(self) -> int:
        """Return the number of elements in the iGP mesh.

        Category: mesh
        Tags: igp, mesh, elements, count
        Use when: scripts need mesh size metadata for summaries or validation.

        Returns:
            int: total number of mesh elements.
        """
        return self.mesh_info["n_elements"]

    @property
    def n_mesh_nodes(self) -> int:
        """Return the number of nodes in the iGP mesh.

        Category: mesh
        Tags: igp, mesh, nodes, count
        Use when: scripts need mesh size metadata for summaries or validation.

        Returns:
            int: total number of mesh nodes.
        """
        return self.mesh_info["n_nodes"]

    def print_material_info(self):
        """Print material metadata in an indented text format.

        Category: reader
        Tags: igp, materials, summary, metadata
        Use when: scripts need a human-readable material property report.

        Returns:
            None: prints material information.
        """
        for material in self.material_info:
            step = 0
            print(f"{step * '  '}{material}:")
            for property in self.material_info[material]:
                step = 1
                print(f"{step * '  '}{property} = {self.material_info[material][property]}")

    def get_region_centroids(self, region_name):
        """Return centroid coordinates for cells associated with a region.

        Category: reader
        Tags: igp, regions, centroids, cells
        Use when: scripts need spatial samples for one iGP region or boundary.

        Returns:
            np.ndarray: centroid coordinates for the region.
        """
        return self.centroids[self.region_dict[region_name]['centroid_id'] - 1]

    def get_region_nodes(self, region_name):
        """Return unique node coordinates for a region.

        Category: reader
        Tags: igp, regions, nodes, coordinates
        Use when: scripts need boundary or region node coordinates for export or analysis.

        Returns:
            np.ndarray: node coordinates for the region.
        """
        cur_array = self.region_dict[region_name]['elements']
        cur_array = cur_array.flatten()
        cur_array = np.unique(cur_array)
        return self.nodes[cur_array]

    def get_boundary_faces(self, region_name) -> List[BaseFace]:
        """Return built boundary face objects for a region.

        Category: mesh
        Tags: igp, boundaries, faces, mesh, regions
        Use when: scripts need explicit boundary face geometry after build_mesh_data.

        Returns:
            list[BaseFace]: boundary faces for the region.
        """
        assert self.is_mesh_built, "Mesh has to be built before calling this method"
        return self.boundaries[region_name]

    def get_material_elements(self, material_name) -> List[BaseElement]:
        """Return built mesh elements assigned to a material.

        Category: mesh
        Tags: igp, materials, elements, mesh
        Use when: scripts need element objects for a named material.

        Returns:
            list[BaseElement]: material element objects.
        """
        return [self.elements[element_id - 1] for element_id in self.material_dict[material_name]]

    def get_material_centroids(self, material_name):
        """Return centroid coordinates for cells assigned to a material.

        Category: reader
        Tags: igp, materials, centroids, cells
        Use when: scripts need spatial summaries or exports for one material.

        Returns:
            np.ndarray: material centroid coordinates.
        """
        return self.centroids[self.material_dict[material_name]]
    
    def assign_material_from_stl(self, material_dict, stl_files, mpi_comm=None, rank=None, size=None):
        """Assign iGP cells to materials using containing or nearest STL solids.

        Category: preprocessing
        Tags: igp, materials, stl, centroids, classification
        Use when: scripts need to classify mesh cells into materials from STL geometry.

        Returns:
            None: updates material assignments in material_dict.
        """
        def dist(p1, p2):
            """
            Computes the euclidean distance between two points
            """
            return ((p1[0]-p2[0])**2+(p1[1]-p2[1])**2+(p1[2]-p2[2])**2)**(1/2)

        def nearest_material(centroids, stl_meshes, unassigned_centroids, centroid_in_stl):
            """
            Finds a node's nearest material
            """
            for idx in tqdm(unassigned_centroids, "Reassigning unassigned cells"):
                dmin = 1.0e300
                imin = 0
                cell = centroids[idx]
                for stl_idx, stl_mesh in enumerate(stl_meshes):
                    for stl_cell in stl_mesh.triangles_center:
                        d = dist(cell, stl_cell)
                        if d < dmin:
                            dmin = d
                            imin = stl_idx
                centroid_in_stl[imin].append(idx) 
            return centroid_in_stl

        if mpi_comm is not None:
            if rank is None or size is None:
                raise ValueError("rank and size must be provided when using MPI")

        # stl_files and material_dict must follow the same order
        stl_meshes = []
        for file in list(stl_files):
            stl_mesh = trimesh.load_mesh(file)
            stl_meshes.append(stl_mesh)
        
        # Creates lists for each material in material_dict.
        centroid_in_stl = []
        for idx, material in material_dict.items():
            centroid_in_stl.append([])
        
        # Find centroids contained in stl
        i = -1
        unassigned_centroids = []

        if mpi_comm is not None:
            nodes_to_classify = np.array_split(self.centroids, size)
            index_to_classify = np.array_split(list(range(len(self.centroids))), size)

            for cell in tqdm(nodes_to_classify[rank], "Classifying centroids"):
                i += 1
                flag = 0
                for stl_idx, stl_mesh in enumerate(stl_meshes):
                    if stl_mesh.contains([cell]):
                        flag = 1
                        centroid_in_stl[stl_idx].append(index_to_classify[rank][i])
                        break
                if flag == 0: unassigned_centroids.append(index_to_classify[rank][i])

            if rank != 0:
                msg = {'unassigned': unassigned_centroids}
                mpi_comm.send(msg,0,100)
                
            if rank == 0:
                unassigned_centroids_root = copy.deepcopy(unassigned_centroids)
                for r in range(1,size):
                    temp = mpi_comm.recv(source=r,tag=100)
                    unassigned_centroids_root += temp['unassigned']
                
                # Find nearest stl to unassgined centroids
                unassigned_centroids_list = np.array_split(unassigned_centroids_root, size)
                for r in range(1,size):
                    msg = {'centroids_root': unassigned_centroids_list[r]}
                    mpi_comm.send(msg,r,r)
                unassigned_centroids = unassigned_centroids_list[0]

            if rank != 0:
                temp = mpi_comm.recv(source=0, tag=rank)
                unassigned_centroids = temp['centroids_root']

            nearest_material(self.centroids, stl_meshes, unassigned_centroids, centroid_in_stl)

            if rank != 0:
                for stl_idx, stl_mesh in enumerate(stl_meshes):
                    msg = {'stl_idx': stl_idx, 'centroids': centroid_in_stl[stl_idx]}
                    mpi_comm.send(msg,0,stl_idx)
                
            if rank == 0:
                for r in range(1,size):
                    for stl_idx, stl_mesh in enumerate(stl_meshes):
                        temp = mpi_comm.recv(source=r, tag=stl_idx)
                        centroid_in_stl[stl_idx] += temp['centroids']

                for idx, material in material_dict.items():
                    # I wat the idx of the centroids not the value
                    cur_centroids = list(np.array(centroid_in_stl[idx])+1)
                    self.set_material_from_list(material_name=material, centroid_list=cur_centroids)            
                
        
        if mpi_comm is None:
            for cell in tqdm(self.centroids, "Classifying centroids"):
                i += 1
                flag = 0
                for stl_idx, stl_mesh in enumerate(stl_meshes):
                    if stl_mesh.contains([cell]):
                        flag = 1
                        centroid_in_stl[stl_idx].append(i)
                        break
                if flag == 0: unassigned_centroids.append(i)
            
            # Find nearest stl to unassgined centroids
            centroid_in_stl = nearest_material(self.centroids, stl_meshes, unassigned_centroids, centroid_in_stl)

            # Assign material to centroids
            for idx, material in material_dict.items():
                cur_centroids = list(np.array(centroid_in_stl[idx])+1)
                self.set_material_from_list(material_name=material, centroid_list=cur_centroids)


    @property
    def min_x(self):
        """Return the minimum centroid x coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, x
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: minimum centroid x coordinate.
        """
        return min(self.centroids[:, 0])

    @property
    def max_x(self):
        """Return the maximum centroid x coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, x
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: maximum centroid x coordinate.
        """
        return max(self.centroids[:, 0])

    @property
    def min_y(self):
        """Return the minimum centroid y coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, y
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: minimum centroid y coordinate.
        """
        return min(self.centroids[:, 1])

    @property
    def max_y(self):
        """Return the maximum centroid y coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, y
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: maximum centroid y coordinate.
        """
        return max(self.centroids[:, 1])

    @property
    def min_z(self):
        """Return the minimum centroid z coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, z
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: minimum centroid z coordinate.
        """
        return min(self.centroids[:, 2])

    @property
    def max_z(self):
        """Return the maximum centroid z coordinate.

        Category: mesh
        Tags: igp, centroids, bounds, z
        Use when: scripts need iGP cell-centroid spatial bounds.

        Returns:
            float: maximum centroid z coordinate.
        """
        return max(self.centroids[:, 2])

    @property
    def coords_min_x(self):
        """Return the minimum node x coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, x
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: minimum node x coordinate.
        """
        return min(self.nodes[:, 0])

    @property
    def coords_max_x(self):
        """Return the maximum node x coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, x
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: maximum node x coordinate.
        """
        return max(self.nodes[:, 0])

    @property
    def coords_min_y(self):
        """Return the minimum node y coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, y
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: minimum node y coordinate.
        """
        return min(self.nodes[:, 1])

    @property
    def coords_max_y(self):
        """Return the maximum node y coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, y
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: maximum node y coordinate.
        """
        return max(self.nodes[:, 1])

    @property
    def coords_min_z(self):
        """Return the minimum node z coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, z
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: minimum node z coordinate.
        """
        return min(self.nodes[:, 2])

    @property
    def coords_max_z(self):
        """Return the maximum node z coordinate.

        Category: mesh
        Tags: igp, nodes, bounds, z
        Use when: scripts need iGP node-coordinate spatial bounds.

        Returns:
            float: maximum node z coordinate.
        """
        return max(self.nodes[:, 2])

    @property
    def region_names(self):
        """Return all iGP region names.

        Category: reader
        Tags: igp, regions, names, metadata
        Use when: scripts need to list available regions or boundaries.

        Returns:
            list: region names.
        """
        return list(self.region_dict.keys())

    @property
    def boundary_names(self):
        """Return all iGP boundary names.

        Category: reader
        Tags: igp, boundaries, names, metadata
        Use when: scripts need to list named boundaries from the iGP project.

        Returns:
            list: boundary names.
        """
        return list(self.region_dict.keys())

    @property
    def material_names(self):
        """Return all iGP material names.

        Category: reader
        Tags: igp, materials, names, metadata
        Use when: scripts need to list available material assignments.

        Returns:
            list: material names.
        """
        return list(self.material_dict.keys())

    def __repr__(self):
        import rich
        from rich.markdown import Markdown
        text = Markdown(f"""
         iGP mesh with {self.n_mesh_elements} elements and {self.n_mesh_nodes} nodes.
         Boundary names: {list(self.region_dict.keys())}
         Material names: {list(self.material_dict.keys())}
         """)
        rich.print(text)
        return ''

    def __str__(self):
        return self.__repr__()




def parallel_build_mesh_data(elements, nodes, shared_list, chunk_index, chunk_size, centroids):
    """Build mesh element objects for one multiprocessing chunk.

    Category: mesh
    Tags: igp, mesh, multiprocessing, elements, helper
    Use when: iGPReader.build_mesh_data splits element construction across processes.

    Returns:
        None: appends built elements to shared_list.
    """
    from pydelling.preprocessing.mesh_preprocessor.geometry import TetrahedraElement, WedgeElement, HexahedraElement
    amount_read = 0.0
    for id_local, element in enumerate(elements):
        n_type = len(element)
        id_local_chunk = id_local + chunk_size * chunk_index
        if n_type == 4:  # This is a Tetrahedra object
            shared_list.append(TetrahedraElement(node_ids=element,
                                                 node_coords=nodes[element],
                                                 local_id=id_local_chunk,
                                                 centroid_coords=centroids[id_local_chunk] if config.general.constant_centroids else None,
                                                 # centroid_coords=self.centroids[id_local]
                                                 ))
        if n_type == 6:  # This is a Wedge object
            shared_list.append(WedgeElement(node_ids=element,
                                            node_coords=nodes[element],
                                            local_id=id_local_chunk,
                                            centroid_coords=centroids[id_local_chunk] if config.general.constant_centroids else None,
                                            # centroid_coords=self.centroids[id_local]
                                            ))
        if n_type == 8:  # This is a Hexahedra object
            shared_list.append(HexahedraElement(node_ids=element,
                                                node_coords=nodes[element],
                                                local_id=id_local_chunk,
                                                centroid_coords=centroids[id_local_chunk] if config.general.constant_centroids else None,
                                                # centroid_coords=self.centroids[id_local]
                                                ))
        if id_local / int(len(elements)) >= amount_read:
            amount = id_local / int(len(elements))
            logger.info(f"Process {chunk_index} completed amount: {amount * 100:3.0f} %")
            amount_read += 0.1
