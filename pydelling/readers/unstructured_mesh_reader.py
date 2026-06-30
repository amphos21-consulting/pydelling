"""
Module documentation.


"""

from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor


class UnstructuredMeshReader(MeshPreprocessor):
    """Wrap unstructured mesh nodes and vertices in ``MeshPreprocessor``.

    Category: mesh reader.
    Tags: unstructured-mesh, nodes, vertices, mesh-preprocessor.
    Use when: an MCP agent needs to represent already-loaded unstructured mesh
        arrays through pydelling's mesh preprocessor interface.
    """

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
