from ..MeshPreprocessor import MeshPreprocessor


def generate_structured_mesh(
        bounds = [[0, 0, 0], [1, 1, 1]],
        nx: int = 10,
        ny: int = 10,
        nz: int = 10,
        ) -> MeshPreprocessor:
    """Explicar el que fa"""
    mesh_preprocessor = MeshPreprocessor()

