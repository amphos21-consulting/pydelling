"""
Module documentation.


"""

from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor


class UnstructuredMeshReader(MeshPreprocessor):
    def __init__(self, nodes, vertices):
        """
        __init__ method.
        
        Args:
            nodes (Any): Description.
            vertices (Any): Description.
        """
        super().__init__()
        self.nodes = nodes
        self.vertices = vertices
