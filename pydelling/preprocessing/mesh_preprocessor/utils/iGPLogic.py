from typing import List, Dict, TYPE_CHECKING
from ..geometry import *
import logging
from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor
from pydelling.readers.iGPReader.utils.geometry_utils import *

from collections import OrderedDict
from pathlib import Path
import h5py
logger = logging.getLogger(__name__)
import os
import numpy as np


class iGPLogic:
    elements: List[BaseElement]
    boundaries: Dict[str, List[BaseFace]]
    material_dict: Dict[str, List[int]]
    element_dict: dict = {4: "T", 5: "P", 6: "W", 8: "H"}
    explicit_writer_dict: dict = {4: 6, 6: 8, 8: 9}

    def implicit_to_explicit(self: MeshPreprocessor,
                             dump_mesh_info=True,
                             write_cells=True,
                             write_regions=True,
                             output_folder=None,
                             project_name='igp_mesh',
                             ):
        """
        Function that transforms an implicit mesh into an explicit mesh
        :param dump_mesh_info: set it True in order to write the primal mesh into the same unstructured explicit mesh
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

    def find_connectivities(self: MeshPreprocessor):
        """
        Finds the connectivities of a given implicit mesh. It uses an algorithm that sorts all the faces and finds the
        ones that are in contact to each other, and thus, is able to find connecting cells
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


    def write_hdf5_domain(self: MeshPreprocessor):
        """
        Writes a hdf5 file containing the domain for post-processing
        """
        if self.output_folder is None:
            hdf5_filename = self.project_name + "-domain.h5"
        else:
            hdf5_filename = Path(self.output_folder) / f"{self.project_name}-domain.h5"
        logger.info(f"Writing mesh to hdf5 ({hdf5_filename})")
        hdf5_file = h5py.File(hdf5_filename, "w")
        self.write_domain_postprocess_hdf5(export_file=hdf5_file)
        hdf5_file.close()


    def write_cells(self: MeshPreprocessor, export_file):
        export_file.write(f"CELLS {len(self.elements)}\n")
        for element in self.elements:
            export_file.write(
                f"{element.local_id + 1} {element.centroid[0]:1.8e} {element.centroid[1]:1.8e} {element.centroid[2]:1.8e} {element.volume:1.8e}\n")

    def write_connections(self: MeshPreprocessor, export_file):
        # compute number of connection elements
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
                intersection_point = np.mean(line_points, axis=0)
                # intersection_point = line_plane_intersection(line_points=line_points,
                #                                              plane_points=face_nodes)
                # intersection_point = face_obj.centroid

                # compute connection centroid and area
                # intersection_point = face_obj.centroid
                conn_area = face_obj.area
                # export_file.write(f"{prime_element + 1} {connected_element + 1} {conn_centroid[0]:1.4e} {conn_centroid[1]:1.4e} {conn_centroid[2]:1.4e} {conn_area:1.4e}\n")
                export_file.write(
                    f"{prime_element + 1} {connected_element + 1} {intersection_point[0]:1.8e} {intersection_point[1]:1.8e} {intersection_point[2]:1.8e} {conn_area:1.8e}\n")
    def write_condition_data(self: MeshPreprocessor):
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

    def write_domain_postprocess_hdf5(self: MeshPreprocessor, export_file):

        # Create domain group
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

    def write_materials(self: MeshPreprocessor):
        for material_name in self.material_dict:
            if self.output_folder is None:
                file_mat = open(f"{material_name}.mat", "w")
            else:
                file_mat = open(os.path.join(self.output_folder, f"{material_name}.mat"), "w")
            # Write material id elements
            list(map(lambda x: file_mat.write(f"{x + 1}\n"), self.material_dict[material_name]))
            file_mat.close()


    def write_elements(self: MeshPreprocessor, export_file):
        export_file.write(f"ELEMENTS {self.n_elements}\n")
        for element in self.elements:
            export_file.write(
                f"{iGPLogic.element_dict[len(element.coords)]} {' '.join(map(str, np.array(element.nodes) + 1))}\n")

    def write_nodes(self: MeshPreprocessor, export_file):
        export_file.write(f"VERTICES {self.n_nodes}\n")
        for id, node in enumerate(self.nodes):
            export_file.write(f"{node[0]} {node[1]} {self.nodes[id][2]:5.5f}\n")

    def write_domain_hdf5(self: MeshPreprocessor, export_file):
        """
        Writes the domain info (i.e. grid info) into an hdf5 file
        :param export_file: HDF5 File object
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

    def write_regions_hdf5(self: MeshPreprocessor, export_file):
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
