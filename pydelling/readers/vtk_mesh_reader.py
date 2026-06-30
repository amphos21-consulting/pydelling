"""
Module documentation.


"""

import logging

from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor

logger = logging.getLogger(__name__)
from tqdm import tqdm
import meshio
from pathlib import Path
import numpy as np


class VTKMeshReader(MeshPreprocessor):
    """Read VTK/VTU meshes and expose them through ``MeshPreprocessor`` helpers.

    Category: mesh reader
    Tags: vtk, vtu, meshio, mesh-preprocessor, kd-tree, streamlit.
    Use when: to load VTK mesh files, inspect point/cell
        variables, or convert supported cell blocks into pydelling mesh
        elements.
    """

    has_kd_tree = False

    def __init__(self, filename,
                 kd_tree=True,
                 st_file=False,
                 generate_internal_mesh=True,
                 ):
        """Load a VTK/VTU mesh or a pickled ``VTKMeshReader`` state.

        Category: mesh reader
        Tags: vtk, vtu, meshio, pickle, kd-tree.
        Use when: creating a reader from a mesh file for interpolation,
            pre-processing, or UI upload workflows.
        Args:
            filename: Path to a ``.vtk``/``.vtu`` mesh file or to a previously
                saved pickle file.
            kd_tree: Whether to build a spatial index after internal mesh
                conversion.
            st_file: Whether this reader is being used inside Streamlit and
                should report progress through Streamlit widgets.
            generate_internal_mesh: Whether to convert meshio cell blocks into
                pydelling mesh elements immediately.
        Side effects:
            Reads mesh data from disk, may populate mesh elements, and may build
            a KD-tree.
        """
        super().__init__()
        self.is_streamlit = st_file

        if Path(filename).suffix == '.vtk' or '.vtu':
            self.meshio_mesh: meshio.Mesh = meshio.read(filename)
            self._coords = self.meshio_mesh.points
            if generate_internal_mesh:
                self.convert_meshio_to_meshpreprocessor()
                if kd_tree:
                    self.create_kd_tree()
                    self.has_kd_tree = True
        else:
            self.load(filename)


    def convert_meshio_to_meshpreprocessor(self):
        """Convert meshio cell blocks into pydelling mesh elements.

        Category: mesh reader
        Tags: meshio, mesh-preprocessor, wedge, hexahedron, tetra, pyramid.
        Use when: mesh data loaded by meshio must be available through
            ``MeshPreprocessor`` element collections and spatial utilities.
        Side effects:
            Adds wedge, hexahedron, tetrahedron, and pyramid elements to the
            inherited mesh preprocessor state; may render Streamlit progress.
        """
        if self.is_streamlit:
            import streamlit as st
        for cell_block in self.meshio_mesh.cells:
            element_type = cell_block.type
            if element_type == "wedge":
                count = 0
                if self.is_streamlit:
                    st.write(f'Creating {len(cell_block.data)} wedge elements')
                    wedge_progress = st.empty()
                    wedge_progress.progress(0)
                for element in tqdm(cell_block.data, desc='Setting up wedge elements'):
                    if self.is_streamlit:
                        proportion = round(count / len(cell_block.data) * 100)
                        wedge_progress.progress(proportion)
                        count += 1

                    self.add_wedge(element, self._coords[element])

            elif element_type == 'hexahedron':
                count = 0
                if self.is_streamlit:
                    st.write(f'Creating {len(cell_block.data)} hexahedron elements')
                    hexahedron_progress = st.empty()
                    hexahedron_progress.progress(0)
                for element in tqdm(cell_block.data, desc='Setting up hexahedron elements'):
                    if self.is_streamlit:
                        proportion = round(count / len(cell_block.data) * 100)
                        hexahedron_progress.progress(proportion)
                        count += 1
                    self.add_hexahedra(element, self._coords[element])

            elif element_type == 'tetra':
                count = 0
                if self.is_streamlit:
                    st.write(f'Creating {len(cell_block.data)} tetrahedra elements')
                    tetra_progress = st.empty()
                    tetra_progress.progress(0)
                for element in tqdm(cell_block.data, desc='Setting up tetra elements'):
                    if self.is_streamlit:
                        proportion = round(count / len(cell_block.data) * 100)
                        tetra_progress.progress(proportion)
                        count += 1

                    self.add_tetrahedra(element, self._coords[element])

            elif element_type == 'pyramid':
                count = 0
                if self.is_streamlit:
                    st.write(f'Creating {len(cell_block.data)} pyramid elements')
                    pyramid_progress = st.empty()
                    pyramid_progress.progress(0)
                for element in tqdm(cell_block.data, desc='Setting up pyramid elements'):
                    if self.is_streamlit:
                        proportion = round(count / len(cell_block.data) * 100)
                        pyramid_progress.progress(proportion)
                        count += 1
                    self.add_pyramid(element, self._coords[element])


    def save(self, filename):
        """Serialize mesh elements, coordinates, and KD-tree state to pickle.

        Category: mesh reader
        Tags: pickle, cache, mesh, kd-tree.
        Use when: a workflow needs to cache a converted VTK mesh for faster
            reloads without reparsing the original mesh file.
        Args:
            filename: Destination pickle path.
        Side effects:
            Writes a pickle file containing ``elements``, ``coords``,
            ``kd_tree``, and ``has_kd_tree``.
        """
        import pickle
        logger.info(f'Saving mesh to {filename}')
        with open(filename, 'wb') as f:
            save_dictionary = {
                'elements': self.elements,
                'coords': self.coords,
                'kd_tree': self.kd_tree,
                'has_kd_tree': self.has_kd_tree,
            }
            pickle.dump(save_dictionary, f)

    def load(self, filename):
        """Restore mesh elements, coordinates, and KD-tree state from pickle.

        Category: mesh reader
        Tags: pickle, cache, mesh, kd-tree.
        Use when: loading a previously saved ``VTKMeshReader`` state instead of
            reading a VTK/VTU file again.
        Args:
            filename: Source pickle path produced by ``save``.
        Side effects:
            Replaces ``elements``, ``_coords``, ``kd_tree``, and
            ``has_kd_tree`` on the reader.
        """
        logger.info(f'Loading mesh from {filename}')
        import pickle
        with open(filename, 'rb') as f:
            save_dictionary = pickle.load(f)
            self.elements = save_dictionary['elements']
            self._coords = save_dictionary['coords']
            self.kd_tree = save_dictionary['kd_tree']
            self.has_kd_tree = save_dictionary['has_kd_tree']

    @property
    def cell_data_values(self) -> dict:
        """Return meshio cell data grouped by variable and cell type.

        Category: mesh reader
        Tags: meshio, cell-data, variables.
        Use when: scripts need per-cell variables while preserving the meshio
            cell-block structure.
        Returns:
            dict: ``meshio_mesh.cell_data_dict``.
        """
        return self.meshio_mesh.cell_data_dict

    @property
    def point_data_values(self) -> dict:
        """Return meshio point data arrays.

        Category: mesh reader
        Tags: meshio, point-data, variables.
        Use when: scripts need variables attached to mesh points.
        Returns:
            dict: ``meshio_mesh.point_data``.
        """
        return self.meshio_mesh.point_data

    @property
    def cell_variables(self) -> list:
        """Return available cell-data variable names.

        Category: mesh reader
        Tags: meshio, cell-data, variables.
        Use when: an MCP tool needs to discover selectable cell variables.
        Returns:
            list: Names of variables in ``meshio_mesh.cell_data``.
        """
        return list(self.meshio_mesh.cell_data.keys())

    @property
    def point_variables(self) -> list:
        """Return available point-data variable names.

        Category: mesh reader
        Tags: meshio, point-data, variables.
        Use when: an MCP tool needs to discover selectable point variables.
        Returns:
            list: Names of variables in ``meshio_mesh.point_data``.
        """
        return list(self.meshio_mesh.point_data.keys())

    @property
    def cell_data_flatten(self) -> dict:
        """Return cell-data variables flattened across cell blocks.

        Category: mesh reader
        Tags: meshio, cell-data, flatten, variables.
        Use when: downstream processing expects one NumPy array per cell
            variable instead of meshio's per-cell-type grouping.
        Returns:
            dict: Mapping of cell variable name to flattened NumPy array.
        """
        data_dict = self.meshio_mesh.cell_data_dict
        temp_dict = {}
        for key, value in data_dict.items():
            temp_dict[key] = []
            for cell_type, cell_values in value.items():
                temp_dict[key] += cell_values.tolist()
            temp_dict[key] = np.array(temp_dict[key])
        return temp_dict





