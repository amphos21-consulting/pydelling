"""
connectflow_mesh.py
====================

Targets:
    - ConnectFlowMeshReader()
        Reads the CONNECTFLOW mesh format.

    - self.to_vtk()
        Export mesh into .vtk format.

"""

from pydelling.readers.connect_flow_mesh_reader import ConnectFlowMeshReader

# Reads the CONNECTFLOW mesh format.
path_cf_mesh = "dummy_cf_2cell_mesh"
reader = ConnectFlowMeshReader(path_cf_mesh + ".msh")

# Export to vtk.
reader.to_vtk(path_cf_mesh + ".vtk")

# Find boundary elements and set the topography.
reader.find_mesh_connections()
reader.find_boundary_elements()
reader.set_topography_boundaries(z_coord=0.25, keys=["land", "sea"])

# reader.boundaries is a dictionary with the faces of the land and sea.
print(reader.boundaries)



