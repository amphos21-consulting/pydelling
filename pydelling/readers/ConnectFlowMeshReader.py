import numpy as np
from ..preprocessing.mesh_preprocessor import MeshPreprocessor
import logging
import logging

import numpy as np

from ..preprocessing.mesh_preprocessor import MeshPreprocessor

logger = logging.getLogger(__name__)
from tqdm import tqdm
from pathlib import Path
import streamlit as st


class ConnectFlowMeshReader(MeshPreprocessor,

                            ):
    has_kd_tree = False

    def __init__(self, filename, kd_tree=True, st_file=False):
        super().__init__()
        # temporary variables...
        self.nodes_tmp = []
        self.elem_tmp = []
        self.material_tmp = []
        if Path(filename).suffix == '.msh':
            self.read_file(filename)
        else:
            raise ValueError(f"{filename} should have .msh extension.")

    def _map_file(self, filename):
        """
        Gets the id line where starts and ends coordinates and connectivities.
        """
        # Open file.
        with open(filename, mode="r") as f:
            self._texto = list(map(lambda x: x.strip(), filter(lambda x: x.strip(), f)))

        # Get id lines.
        for index, value in enumerate(self._texto):
            if value.strip() == "NODES":
                self._start_coord_line = index + 1
            if value.strip() == "END_NODES":
                self._end_coord_line = index
            if value.strip() == "ELEMENTS":
                self._start_elements_line = index + 1
            if value.strip() == "END_ELEMENTS":
                self._end_elements_line = index

    def read_file(self, filename):
        """ Reads coordinates and elements of a mesh. """
        self._map_file(filename)

        # Coordinates of the nodes
        for index in range(self._start_coord_line, self._end_coord_line):
            self.nodes_tmp.append([float(i) for i in self._texto[index].split()])

        self.nodes_tmp = np.array(self.nodes_tmp)[:, 1:]

        # Element connectivities. (no need by now)

        for index in range(self._start_elements_line, self._end_elements_line):
            cur_data = [int(i) for i in self._texto[index].split()]
            self.elem_tmp.append(cur_data[1:-1])
            self.material_tmp.append(cur_data[-1])
        self.elem_tmp = np.array(self.elem_tmp)[:, :]

        for element_node_ids in tqdm(self.elem_tmp, desc='Reading elements'):
            local_element_node_ids = element_node_ids - 1
            element_coords = self.nodes_tmp[local_element_node_ids]
            element_type = len(local_element_node_ids)
            if element_type == 4:
                self.add_tetrahedra(node_ids=local_element_node_ids, node_coords=element_coords)
            elif element_type == 5:
                self.add_pyramid(node_ids=local_element_node_ids, node_coords=element_coords)
            elif element_type == 6:
                self.add_wedge(node_ids=local_element_node_ids, node_coords=element_coords)
            elif element_type == 8:
                self.add_hexahedra(node_ids=local_element_node_ids, node_coords=element_coords)


    def _read_file(self, filename):
        with open(filename, 'r') as f:
            first_line = f.readline()
            number_of_nodes = int(first_line.split()[0])
            if self.is_streamlit:
                empty_progress = st.empty()
                empty_progress.progress(0)
                st.write(f'Reading {number_of_nodes} nodes')
            for _ in tqdm(range(number_of_nodes), desc='Reading nodes'):
                node_info = f.readline().split()
                prop = int(np.ceil(_ / number_of_nodes * 100))
                if prop > 100:
                    prop = 100
                if self.is_streamlit:
                    if prop % 10 == 0:
                        empty_progress.progress(prop)
                self.aux_nodes[int(node_info[0])] = np.array([float(node_info[1]), float(node_info[2]), float(node_info[3])])
            # Read elements
            number_of_elements = int(f.readline().split()[0])
            if self.is_streamlit:
                empty_progress_elements = st.empty()
                empty_progress_elements.progress(0)
                st.write(f'Generating {number_of_elements} elements')
            for _ in tqdm(range(number_of_elements), desc='Reading elements'):
                prop = int(np.ceil(_ / number_of_elements * 100))
                if prop > 100:
                    prop = 100
                if self.is_streamlit:
                    if prop % 5 == 0:
                        empty_progress_elements.progress(prop)
                element_info = f.readline().split()
                element_type = int(element_info[0])
                element_node_ids = np.array([int(node_id) for node_id in element_info[1:element_type + 1]])
                element_coords = [self.aux_nodes[node_id] for node_id in element_node_ids]
                element_node_ids -= 1  # Node IDs should start at 0
                if element_type == 4:
                    self.add_tetrahedra(node_ids=element_node_ids, node_coords=element_coords)
                elif element_type == 5:
                    self.add_pyramid(node_ids=element_node_ids, node_coords=element_coords)
                elif element_type == 6:
                    self.add_wedge(node_ids=element_node_ids, node_coords=element_coords)
                elif element_type == 8:
                    self.add_hexahedra(node_ids=element_node_ids, node_coords=element_coords)
