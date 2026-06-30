"""
Module documentation.


"""

from typing import List, Dict, TYPE_CHECKING
from ..geometry import *
import logging
if TYPE_CHECKING:
    from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor
from pydelling.readers.iGPReader.utils.geometry_utils import *

from collections import OrderedDict
from pathlib import Path
import h5py
logger = logging.getLogger(__name__)
import os
import numpy as np


class iGPLogic:
    """Mixin for exporting implicit mesh data to iGP explicit mesh artifacts.

    Category: preprocessing
    Tags: mesh, iGP, explicit, hdf5, export
    Usage: mesh preprocessors need iGP-compatible mesh, region, material, and post-processing files.
    """
    elements: List[BaseElement]
    boundaries: Dict[str, List[BaseFace]]
    material_dict: Dict[str, List[int]]
    element_dict: dict = {4: "T", 5: "P", 6: "W", 8: "H"}
    explicit_writer_dict: dict = {4: 6, 6: 8, 8: 9}

    def implicit_to_explicit(self,
                             dump_mesh_info=True,
                             write_cells=True,
                             write_regions=True,
                             output_folder=None,
                             project_name='igp_mesh',
                             weight_by_volume=True,
                             ):
        """Export implicit mesh data into iGP explicit mesh files.

        Category: writer
        Tags: mesh, iGP, explicit, cells, regions
        Usage: scripts need .mesh, .ex, .mat, and domain HDF5 files for iGP-style workflows.

        Returns:
            None: writes mesh and optional region/material artifacts.
        """
        self.output_folder = output_folder if output_folder is not None else 'output'
        self.project_name = project_name
        Path(self.output_folder).mkdir(parents=True, exist_ok=True)

        if write_cells:
            self.find_connectivities()  # Find the connections of the mesh
            # Write mesh file
            logger.info(f'Writing mesh file to {self.output_folder}')
            exp_mesh_filename = f"igp_mesh.mesh"
            if self.output_folder is None:
                output_file = open(exp_mesh_filename, "w")
            else:
                output_file = open(Path(self.output_folder) / exp_mesh_filename, "w")
            self.write_cells(output_file)
            self.write_connections(output_file)
            if dump_mesh_info:
                self.write_elements(output_file)  # Write elements for mesh visualization
                self.write_nodes(output_file)  # Write node_ids for mesh visualization
            output_file.close()
            self.write_hdf5_domain()

        # Write condition data
        if write_regions:
            self.write_condition_data()
            self.write_materials()

    def find_connectivities(self,
                           ):
        """Find neighboring cells by matching sorted face node ids.

        Category: preprocessing
        Tags: mesh, connectivity, faces, adjacency, iGP
        Usage: explicit mesh export needs cell-to-cell connection records.

        Returns:
            None: stores ordered connectivity data in connections.
        """
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
                #     conn_dict[id_b][id_a] = face_b
                # else:
                #     conn_dict[id_b][id_a] = face_b
        conn_dict_ordered = OrderedDict(conn_dict)
        self.connections = sorted(conn_dict_ordered.items())


    def write_hdf5_domain(self,
                         ):
        """Write the post-processing domain HDF5 file.

        Category: writer
        Tags: mesh, hdf5, domain, postprocessing, iGP
        Usage: explicit mesh export should include an HDF5 domain artifact.

        Returns:
            None: writes the project domain HDF5 file.
        """
        if self.output_folder is None:
            hdf5_filename = self.project_name + "-domain.h5"
        else:
            hdf5_filename = Path(self.output_folder) / f"{self.project_name}-domain.h5"
        logger.info(f"Writing mesh to hdf5 ({hdf5_filename})")
        hdf5_file = h5py.File(hdf5_filename, "w")
        self.write_domain_postprocess_hdf5(export_file=hdf5_file)
        hdf5_file.close()


    def write_cells(self,
                   export_file):
        """Write iGP CELLS records to an open mesh file.

        Category: writer
        Tags: mesh, iGP, cells, centroids, volume
        Usage: creating an explicit mesh file from element centroids and volumes.

        Returns:
            None: writes cell records to export_file.
        """
        export_file.write(f"CELLS {len(self.elements)}\n")
        for element in self.elements:
            export_file.write(
                f"{element.local_id + 1} {element.centroid[0]:1.8e} {element.centroid[1]:1.8e} {element.centroid[2]:1.8e} {element.volume:1.8e}\n")

    def write_connections(self,
                          export_file,
                          weight_by_volume=True,
                          ):
        # compute number of connection elements
        """Write iGP CONNECTIONS records to an open mesh file.

        Category: writer
        Tags: mesh, iGP, connections, faces, area
        Usage: explicit mesh export needs cell-to-cell connection centroids and areas.

        Returns:
            None: writes connection records and stores n_conn.
        """
        n_conn = 0
        for element in self.connections:
            n_conn += len(element[1])
        self.n_conn = n_conn  # set the number of connections of the mesh
        export_file.write(f"CONNECTIONS {self.n_conn}\n")
        for element in self.connections:
            prime_element = element[0]
            for connected_element in element[1]:
                face_id = element[1][connected_element]
                face_obj = self.elements[prime_element].faces[face_id]
                face_nodes = face_obj.coords
                # Compute line-face intersection
                line_points = np.array([self.elements[prime_element].centroid_coords,
                                        self.elements[connected_element].centroid_coords])
                # print(face_obj.centroid)
                if weight_by_volume:
                    vol_1 = self.elements[prime_element].volume
                    vol_2 = self.elements[connected_element].volume
                    r = vol_1 / (vol_1 + vol_2)
                    intersection_point = line_points[0] + r * (line_points[1] - line_points[0])
                    # print(f"r = {r}")
                else:
                    intersection_point = np.mean(line_points, axis=0)
                # v1 = line_points[1] - line_points[0]
                # v2 = line_points[1] - face_obj.centroid
                # print(v1, v2)
                # dot = np.dot(v1, v2)
                # print(dot / (np.linalg.norm(v1)))

                # intersection_point = line_plane_intersection(line_points=line_points,
                #                                              plane_points=face_nodes)
                # intersection_point = face_obj.centroid

                # compute connection centroid and area
                # intersection_point = face_obj.centroid
                v1 = line_points[1] - line_points[0]
                v2 = face_obj.centroid - line_points[0]
                cos_v1_v2 = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                conn_area = face_obj.area * cos_v1_v2
                # print(f"cos_v1_v2 = {cos_v1_v2}")
                # export_file.write(f"{prime_element + 1} {connected_element + 1} {conn_centroid[0]:1.4e} {conn_centroid[1]:1.4e} {conn_centroid[2]:1.4e} {conn_area:1.4e}\n")
                export_file.write(
                    f"{prime_element + 1} {connected_element + 1} {intersection_point[0]:1.8e} {intersection_point[1]:1.8e} {intersection_point[2]:1.8e} {conn_area:1.8e}\n")
    def write_condition_data(self,
                            ):
        """Write boundary condition connection files.

        Category: writer
        Tags: mesh, iGP, boundaries, conditions, export
        Usage: region boundary faces should become .ex files for iGP input.

        Returns:
            None: writes one condition file per boundary.
        """
        for condition in self.boundaries:
            # Open file for dumping connection data
            if self.output_folder is None:
                file_cond = open(f"{condition}.ex", "w")
            else:
                file_cond = open(os.path.join(self.output_folder, f"{condition}.ex"), "w")
            file_cond.write(f"CONNECTIONS {len(self.boundaries[condition])}\n")
            for id_number, face in self.boundaries[condition].items():
                n_coords = len(face.coords)

                if n_coords == 3:
                    conn_face = TriangleFace(node_ids=face.nodes,
                                             node_coords=face.coords)
                elif n_coords == 4:
                    conn_face = QuadrilateralFace(node_ids=face.nodes,
                                                  node_coords=face.coords)
                conn_area = conn_face.area
                # conn_element_id = self.region_dict[condition]["centroid_id"][id_number]
                # line_point = self.elements[conn_element_id].centroid_coords
                # intersection_point = line_plane_perpendicular_intersection(line_point=line_point,
                #                                                            plane_points=conn_coords)
                intersection_point = face.centroid
                file_cond.write(
                    f"{id_number + 1} {intersection_point[0]:1.8e} {intersection_point[1]:1.8e} {intersection_point[2]:1.8e} {conn_area:1.8e}\n")
            file_cond.close()

    def write_domain_postprocess_hdf5(self,
                                     export_file):

        # Create domain group
        """Write Domain datasets for post-processing HDF5 output.

        Category: writer
        Tags: mesh, hdf5, domain, cells, vertices
        Usage: scripts need mesh connectivity and vertices in HDF5 format.

        Returns:
            None: creates Domain/Cells and Domain/Vertices datasets.
        """
        domain_group = export_file.create_group("Domain")
        # Create Cells dataset
        _cells = []
        for element in self.elements:
            element_length = len(element.coords)
            _cells.append(iGPLogic.explicit_writer_dict[element_length])
            # Add elements on the _cells dataset
            list(map(lambda x: _cells.append(x), element.nodes))
        domain_group.create_dataset("Cells", data=_cells)
        # Create Vertices
        domain_group.create_dataset("Vertices", data=self.nodes)

    def write_materials(self,
                       ):
        """Write material element-id files.

        Category: writer
        Tags: mesh, materials, iGP, export
        Usage: material groups should be exported as .mat files.

        Returns:
            None: writes one material file per material name.
        """
        for material_name in self.material_dict:
            if self.output_folder is None:
                file_mat = open(f"{material_name}.mat", "w")
            else:
                file_mat = open(os.path.join(self.output_folder, f"{material_name}.mat"), "w")
            # Write material id elements
            list(map(lambda x: file_mat.write(f"{x + 1}\n"), self.material_dict[material_name]))
            file_mat.close()


    def write_elements(self,
                      export_file):
        """Write element connectivity records for mesh visualization.

        Category: writer
        Tags: mesh, elements, connectivity, visualization, iGP
        Usage: the explicit mesh file should include element topology for diagnostics.

        Returns:
            None: writes ELEMENTS records to export_file.
        """
        export_file.write(f"ELEMENTS {self.n_elements}\n")
        for element in self.elements:
            export_file.write(
                f"{iGPLogic.element_dict[len(element.coords)]} {' '.join(map(str, np.array(element.nodes) + 1))}\n")

    def write_nodes(self,
                   export_file):
        """Write vertex coordinate records for mesh visualization.

        Category: writer
        Tags: mesh, nodes, vertices, coordinates, iGP
        Usage: the explicit mesh file should include node coordinates for diagnostics.

        Returns:
            None: writes VERTICES records to export_file.
        """
        export_file.write(f"VERTICES {self.n_nodes}\n")
        for id, node in enumerate(self.nodes):
            export_file.write(f"{node[0]} {node[1]} {self.nodes[id][2]:5.5f}\n")

    def write_domain_hdf5(self,
                         export_file):
        """Write mesh domain cells and vertices to HDF5.

        Category: writer
        Tags: mesh, hdf5, domain, cells, vertices
        Usage: scripts need domain grid data in HDF5 format.

        Returns:
            None: creates Domain datasets in export_file.
        """
        #  Pre-process cell data
        cell_data = np.zeros(shape=(self.n_elements, 9), dtype=np.int32)
        for id, cell in enumerate(self.elements):
            n_cell = len(cell.n_nodes)
            cell_data[id][0] = n_cell
            np.put(cell_data[id], range(1, cell.n_nodes + 1), cell.nodes)
        # Pre-process node data
        node_data = np.array(self.nodes)
        domain_group = export_file.create_group("Domain")
        domain_group.create_dataset("Cells", data=cell_data)
        domain_group.create_dataset("Vertices", data=node_data)

    def write_regions_hdf5(self,
                          export_file):
        """Write material and boundary regions to HDF5.

        Category: writer
        Tags: mesh, hdf5, regions, materials, boundaries
        Usage: scripts need PFLOTRAN-style region and material groups in HDF5 output.

        Returns:
            None: creates Regions datasets in export_file.
        """
        def add_dataset(hdf5_file, group_name, dataset_type, data):
            temp_group = hdf5_file.create_group(group_name)
            temp_dataset = temp_group.create_dataset(dataset_type, data=data)

        def preprocess_region(dataset):
            """
            Pre-process a face dataset into PFLOTRAN hdf5 format
            :param dataset: input dataset
            :return: pre-processed face dataset
            """
            face_data = np.zeros(shape=(len(dataset), 4), dtype=np.int32)
            for id, face in enumerate(dataset):
                n_face = len(face)
                face_data[id][0] = n_face
                face = np.array(face)
                np.put(face_data[id], range(1, len(face)), face)
            return face_data

        # Pre-process datasets
        region_group = export_file.create_group("Regions")
        # Add materials
        #  Create 'all' material
        data_all = np.array(range(self.n_elements)) + 1
        add_dataset(region_group, "all", "Cell Ids", data_all)
        for material_name in self.material_dict:
            add_dataset(region_group, material_name, "Cell Ids", self.material_dict[material_name])
        # Add regions
        for region_name in self.boundaries:
            preprocess_region_dataset = preprocess_region(self.boundaries[region_name])
            add_dataset(region_group, region_name, "Vertex Ids", preprocess_region_dataset)
