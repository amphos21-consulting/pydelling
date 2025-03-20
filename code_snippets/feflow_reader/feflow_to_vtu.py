"""
feflow_to_vtu.py
================
Writes a point dataset .dat (FEFLOW format) into a Paraview .vtu format
"""

import numpy as np
import meshio
from pydelling.readers.feflow_reader import FeflowReader
from pydelling.interpolation.sparse_data_interpolator import SparseDataInterpolator

# Reads the concentration field from FEFLOW
path_dat = "c_layer_b_tf.dat"
reader = FeflowReader()
field = reader.read_field_dat(path_dat)
mesh1_data = np.array([field["x"], field["y"], field["z"], field["Concentration"]]).T

# Reads the mesh in .vtu format and interpolates.
path_vtu_mesh = "mesh_layer_b.vtu"
mesh_2_aux = meshio.read(path_vtu_mesh)
mesh2 = mesh_2_aux.points
interp = SparseDataInterpolator()
interp.add_data(mesh1_data)
interp.add_mesh(mesh2)
interp.run()

# Writes the dataset
path_write = "dataset.vtu"
mesh_2_aux.point_data["Concentration"] = interp.interpolated_data
mesh_2_aux.write(path_write, file_format="vtu", binary=False)

