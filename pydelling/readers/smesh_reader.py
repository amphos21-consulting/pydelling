"""
Module documentation.


"""

import numpy as np
from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor
import logging
import logging

import numpy as np



logger = logging.getLogger(__name__)
from tqdm import tqdm
from pathlib import Path
try:
    import streamlit as st
except ImportError:  # optional pydelling[webapps] integration
    st = None


class SmeshReader(MeshPreprocessor):
    """Read TetGen-style ``.smesh`` files into the mesh preprocessor.

    Category: mesh reader.
    Tags: smesh, mesh, tetgen, kd-tree, streamlit.
    Usage: to load SMesh nodes/elements and create
        pydelling mesh-preprocessor elements.
    """

    has_kd_tree = False

    def __init__(self, filename, kd_tree=True, st_file=False):
        """Load an SMesh file or cached mesh state.

        Category: mesh reader.
        Tags: smesh, mesh, kd-tree, initialization.
        Usage: constructing a mesh reader from an SMesh file for
            interpolation or preprocessing.
        Args:
            filename: Path to ``.smesh`` file or cached mesh object.
            kd_tree: Whether to create a spatial KD-tree after reading.
            st_file: Whether to emit Streamlit progress widgets.
        Side effects:
            Reads mesh data, may build a KD-tree, and marks ``has_kd_tree``.
        """
        if st_file and st is None:
            raise RuntimeError("Streamlit progress requires the pydelling[webapps] extra.")
        super().__init__()
        self.is_streamlit = st_file

        if Path(filename).suffix == '.smesh':
            self.read_file(filename)
            if kd_tree:
                self.create_kd_tree()
                self.has_kd_tree = True
        else:
            self.load(filename)

    def read_file(self, filename):
        """Parse SMesh nodes and supported element types.

        Category: mesh reader.
        Tags: smesh, nodes, elements, tetrahedra, pyramid, wedge, hexahedra.
        Usage: reading SMesh text data into mesh-preprocessor elements.
        Args:
            filename: SMesh file path.
        Side effects:
            Populates ``aux_nodes`` and adds tetrahedra, pyramid, wedge, or
            hexahedra elements.
        """
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
