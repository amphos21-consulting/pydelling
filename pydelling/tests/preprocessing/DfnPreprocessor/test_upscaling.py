import numpy as np
import pytest

from pydelling.preprocessing import DfnPreprocessor, MeshPreprocessor
from pydelling.preprocessing.dfn_preprocessor import DfnUpscaler


def legacy_case():
    dfn = DfnPreprocessor()
    dfn.add_fracture(
        polygon=np.asarray([[0, 0, 0], [0, 1, 0], [-1, 0, 1]], dtype=float),
        aperture=0.1,
        transmissivity=0.02,
        storativity=2.0e-6,
    )
    mesh = MeshPreprocessor()
    mesh.add_hexahedra(
        node_ids=np.arange(8),
        node_coords=np.asarray(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
             [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
            dtype=float,
        ),
    )
    mesh.elements[0].associated_fractures[dfn[0].local_id] = {
        "area": 1.0,
        "volume": 0.1,
        "fracture": dfn[0].local_id,
    }
    return dfn, mesh, DfnUpscaler(dfn, mesh, loading=True)


def test_legacy_porosity_honors_matrix_and_is_idempotent():
    _, _, upscaler = legacy_case()
    first = upscaler.upscale_mesh_porosity(matrix_porosity=0.2, truncate=False, engine="legacy")
    second = upscaler.upscale_mesh_porosity(matrix_porosity=0.2, truncate=False, engine="legacy")
    assert first[0] == pytest.approx(0.28)
    assert second[0] == pytest.approx(first[0])


def test_legacy_permeability_preserves_full_symmetric_tensor():
    _, _, upscaler = legacy_case()
    result = upscaler.upscale_mesh_permeability(
        matrix_permeability=1.0e-6,
        mode="full_tensor",
        truncate=False,
        engine="legacy",
    )[0]
    np.testing.assert_allclose(result, result.T)
    assert result[0, 2] < 0
    assert result[0, 2] != result[0, 1]
    assert np.all(np.diag(result) >= 0)


def test_legacy_storativity_honors_matrix_input():
    _, _, upscaler = legacy_case()
    result = upscaler.upscale_mesh_storativity(
        matrix_storativity=1.0e-6, truncate=False, engine="legacy"
    )
    assert result[0] == pytest.approx(1.1e-6)
