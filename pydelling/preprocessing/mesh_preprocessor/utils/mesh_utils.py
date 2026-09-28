from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..mesh_preprocessor import MeshPreprocessor
import numpy as np
import sys
import logging

logger = logging.getLogger(__name__)


def progressbar(iter, max, prefix="\t\t    ", size=40, out=sys.stdout):  # Python3.3+
    x = int(size * iter / max)
    if iter != max:
        print("{}".format(prefix) + "\033[1;34m" + "{}".format(u"█" * x) + "\033[1;90m" + "{}".format(
            u"█" * (size - x)) + "\x1b[0m" + " {}/{} cells".format(iter, max), end='\r', file=out, flush=True)
    if iter == max:
        print("{}".format(prefix) + "\033[1;32m" + "{}".format(u"█" * size) + "\x1b[0m" + " {}/{} cells".format(iter,
                                                                                                                max),
              end='\n', file=out, flush=True)
    return iter + 1


def generate_structured_mesh(
        bounds=[[0, 0, 0], [1, 1, 1]],
        nx: int = 10,
        ny: int = 10,
        nz: int = 10,
) -> MeshPreprocessor:
    """Generates a structured mesh sorting the nodes such that the normal's bottom face points towards inside the cell
     following the right-hand rule as we can see in the figure
         7────────6
        /│       /│
       / │      / │
      4────────5  │
      │  3─────│──2
      │ /      │ /
      │/       │/
      0────────1
    """
    from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor
    logger.info("Generating structured mesh")
    p_i = bounds[0]
    p_f = bounds[1]

    Lx = p_f[0] - p_i[0]
    Ly = p_f[1] - p_i[1]
    Lz = p_f[2] - p_i[2]
    dx = Lx / nx
    dy = Ly / ny
    dz = Lz / nz
    nodes = [*range((nx + 1) * (ny + 1) * (nz + 1))]
    nodes_coord = []

    iter = 0
    iter = progressbar(iter, nx * ny * nz)

    nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2]]))
    nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2]]))
    nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2]]))
    nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2]]))
    nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2] + dz]))
    nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2] + dz]))
    nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2] + dz]))
    nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2] + dz]))

    mesh_preprocessor = MeshPreprocessor()

    mesh_preprocessor.add_hexahedra(
        node_ids=nodes[:8],
        node_coords=nodes_coord,
    )
    iter = progressbar(iter, nx * ny * nz)

    if (nx > 1):
        for i in range(2, nx + 1):
            nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1], p_i[2]]))
            nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + dy, p_i[2]]))
            nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1], p_i[2] + dz]))
            nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + dy, p_i[2] + dz]))

        new_nodes = [1, 8, 9, 2, 5, 10, 11, 6]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])

        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        for i in range(2, nx):
            new_nodes = [8 + (i - 2) * 4, 12 + (i - 2) * 4, 13 + (i - 2) * 4, 9 + (i - 2) * 4, 10 + (i - 2) * 4,
                         14 + (i - 2) * 4, 15 + (i - 2) * 4, 11 + (i - 2) * 4]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

    if (nx == 1 and ny > 1):
        for j in range(2, ny + 1):
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2]]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2]]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2] + dz]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2] + dz]))

        new_nodes = [3, 2, 8, 9, 7, 6, 10, 11]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])

        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        for j in range(2, ny):
            new_nodes = [9 + (j - 2) * 4, 8 + (j - 2) * 4, 12 + (j - 2) * 4, 13 + (j - 2) * 4, 11 + (j - 2) * 4,
                         10 + (j - 2) * 4, 14 + (j - 2) * 4, 15 + (j - 2) * 4]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

    if (nx == 1 and ny == 1 and nz > 1):
        for k in range(2, nz + 1):
            nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2] + k * dz]))

        for k in range(1, nz):
            new_nodes = [4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3, 4 * (k + 1), 4 * (k + 1) + 1, 4 * (k + 1) + 2,
                         4 * (k + 1) + 3]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

    if (nx > 1 and ny == 1 and nz > 1):
        for k in range(2, nz + 1):
            nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2] + k * dz]))
            for i in range(2, nx + 1):
                nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1], p_i[2] + k * dz]))
                nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + dy, p_i[2] + k * dz]))

        z3 = 2 * 2 * (nx + 1)
        new_nodes = [4, 5, 6, 7, z3, z3 + 1, z3 + 2, z3 + 3]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])
        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        new_nodes = [5, 10, 11, 6, z3 + 1, z3 + 4, z3 + 5, z3 + 2]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])
        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        for i in range(2, nx):
            new_nodes = [10 + 4 * (i - 2), 14 + 4 * (i - 2), 15 + 4 * (i - 2), 11 + 4 * (i - 2), z3 + 2 * i,
                         z3 + 2 * (i + 1), z3 + 2 * (i + 1) + 1, z3 + 2 * i + 1]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

        for k in range(2, nz):
            new_nodes = [2 * (nx + 1) * k, 2 * (nx + 1) * k + 1, 2 * (nx + 1) * k + 2, 2 * (nx + 1) * k + 3,
                         2 * (nx + 1) * (k + 1), 2 * (nx + 1) * (k + 1) + 1, 2 * (nx + 1) * (k + 1) + 2,
                         2 * (nx + 1) * (k + 1) + 3]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            new_nodes = [2 * (nx + 1) * k + 1, 2 * (nx + 1) * k + 4, 2 * (nx + 1) * k + 5, 2 * (nx + 1) * k + 2,
                         2 * (nx + 1) * (k + 1) + 1, 2 * (nx + 1) * (k + 1) + 4, 2 * (nx + 1) * (k + 1) + 5,
                         2 * (nx + 1) * (k + 1) + 2]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            for i in range(2, nx):
                new_nodes = [2 * (nx + 1) * k + 2 * i, 2 * (nx + 1) * k + 2 * (i + 1),
                             2 * (nx + 1) * k + 2 * (i + 1) + 1, 2 * (nx + 1) * k + 2 * i + 1,
                             2 * (nx + 1) * (k + 1) + 2 * i, 2 * (nx + 1) * (k + 1) + 2 * (i + 1),
                             2 * (nx + 1) * (k + 1) + 2 * (i + 1) + 1,
                             2 * (nx + 1) * (k + 1) + 2 * i + 1]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

    if (nx == 1 and ny > 1 and nz > 1):
        for k in range(2, nz + 1):
            nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2] + k * dz]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2] + k * dz]))
            for j in range(2, ny + 1):
                nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2] + k * dz]))
                nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2] + k * dz]))

        z3 = 4 * (ny + 1)
        new_nodes = [4, 5, 6, 7, z3, z3 + 1, z3 + 2, z3 + 3]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])
        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        z3 = 4 * (ny + 1)
        new_nodes = [7, 6, 10, 11, z3 + 3, z3 + 2, z3 + 4, z3 + 5]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])
        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        for j in range(2, ny):
            new_nodes = [11 + 4 * (j - 2), 10 + 4 * (j - 2), 14 + 4 * (j - 2), 15 + 4 * (j - 2), z3 + 2 * j + 1,
                         z3 + 2 * j, z3 + 2 * j + 2, z3 + 2 * j + 3]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

        for k in range(2, nz):
            new_nodes = [z3 + 2 * (ny + 1) * (k - 2), z3 + 1 + 2 * (ny + 1) * (k - 2), z3 + 2 + 2 * (ny + 1) * (k - 2),
                         z3 + 3 + 2 * (ny + 1) * (k - 2), z3 + 2 * (ny + 1) * (k - 1), z3 + 1 + 2 * (ny + 1) * (k - 1),
                         z3 + 2 + 2 * (ny + 1) * (k - 1), z3 + 3 + 2 * (ny + 1) * (k - 1)]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])
            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            for j in range(1, ny):
                new_nodes = [z3 + 2 * (j - 1) + 3 + 2 * (ny + 1) * (k - 2),
                             z3 + 2 * (j - 1) + 2 + 2 * (ny + 1) * (k - 2),
                             z3 + 2 * (j - 1) + 4 + 2 * (ny + 1) * (k - 2),
                             z3 + 2 * (j - 1) + 5 + 2 * (ny + 1) * (k - 2),
                             z3 + 2 * (j - 1) + 3 + 2 * (ny + 1) * (k - 1),
                             z3 + 2 * (j - 1) + 2 + 2 * (ny + 1) * (k - 1),
                             z3 + 2 * (j - 1) + 4 + 2 * (ny + 1) * (k - 1),
                             z3 + 2 * (j - 1) + 5 + 2 * (ny + 1) * (k - 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

    if (nx > 1 and ny > 1):
        for j in range(2, ny + 1):
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2]]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2]]))
            nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2] + dz]))
            nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2] + dz]))
            for i in range(2, nx + 1):
                nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + j * dy, p_i[2]]))
                nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + j * dy, p_i[2] + dz]))

        y3 = 2 * 2 * (nx + 1)
        new_nodes = [3, 2, y3, y3 + 1, 7, 6, y3 + 2, y3 + 3]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])

        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        new_nodes = [2, 9, y3 + 4, y3, 6, 11, y3 + 5, y3 + 2]
        new_coords = []
        for l in range(8):
            new_coords.append(nodes_coord[new_nodes[l]])

        mesh_preprocessor.add_hexahedra(
            node_ids=new_nodes,
            node_coords=new_coords,
        )
        iter = progressbar(iter, nx * ny * nz)

        for i in range(2, nx):
            new_nodes = [9 + 4 * (i - 2), 13 + 4 * (i - 2), y3 + 6 + 2 * (i - 2), y3 + 4 + 2 * (i - 2),
                         11 + 4 * (i - 2), 15 + 4 * (i - 2), y3 + 7 + 2 * (i - 2), y3 + 5 + 2 * (i - 2)]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

        for j in range(2, ny):
            new_nodes = [y3 + 1 + (nx + 1) * 2 * (j - 2), y3 + (nx + 1) * 2 * (j - 2),
                         y3 + (nx + 1) * 2 * (j - 1), y3 + 1 + (nx + 1) * 2 * (j - 1),
                         y3 + 3 + (nx + 1) * 2 * (j - 2), y3 + 2 + (nx + 1) * 2 * (j - 2),
                         y3 + 2 + (nx + 1) * 2 * (j - 1), y3 + 3 + (nx + 1) * 2 * (j - 1)]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            new_nodes = [y3 + (nx + 1) * 2 * (j - 2), y3 + 4 + (nx + 1) * 2 * (j - 2),
                         y3 + 4 + (nx + 1) * 2 * (j - 1), y3 + (nx + 1) * 2 * (j - 1),
                         y3 + 2 + (nx + 1) * 2 * (j - 2), y3 + 5 + (nx + 1) * 2 * (j - 2),
                         y3 + 5 + (nx + 1) * 2 * (j - 1), y3 + 2 + (nx + 1) * 2 * (j - 1)]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            for i in range(2, nx):
                new_nodes = [y3 + 4 + 2 * (i - 2) + (nx + 1) * 2 * (j - 2),
                             y3 + 6 + 2 * (i - 2) + (nx + 1) * 2 * (j - 2),
                             y3 + 6 + 2 * (i - 2) + (nx + 1) * 2 * (j - 1),
                             y3 + 4 + 2 * (i - 2) + (nx + 1) * 2 * (j - 1),
                             y3 + 5 + 2 * (i - 2) + (nx + 1) * 2 * (j - 2),
                             y3 + 7 + 2 * (i - 2) + (nx + 1) * 2 * (j - 2),
                             y3 + 7 + 2 * (i - 2) + (nx + 1) * 2 * (j - 1),
                             y3 + 5 + 2 * (i - 2) + (nx + 1) * 2 * (j - 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])

                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

        if (nz > 1):
            for k in range(2, nz + 1):
                nodes_coord.append(np.array([p_i[0], p_i[1], p_i[2] + k * dz]))
                nodes_coord.append(np.array([p_i[0] + dx, p_i[1], p_i[2] + k * dz]))
                nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + dy, p_i[2] + k * dz]))
                nodes_coord.append(np.array([p_i[0], p_i[1] + dy, p_i[2] + k * dz]))
                for i in range(2, nx + 1):
                    nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1], p_i[2] + k * dz]))
                    nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + dy, p_i[2] + k * dz]))
                for j in range(2, ny + 1):
                    nodes_coord.append(np.array([p_i[0] + dx, p_i[1] + j * dy, p_i[2] + k * dz]))
                    nodes_coord.append(np.array([p_i[0], p_i[1] + j * dy, p_i[2] + k * dz]))
                    for i in range(2, nx + 1):
                        nodes_coord.append(np.array([p_i[0] + i * dx, p_i[1] + j * dy, p_i[2] + k * dz]))

            z3 = 2 * (nx + 1) * (ny + 1)
            new_nodes = [4, 5, 6, 7, z3, z3 + 1, z3 + 2, z3 + 3]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            new_nodes = [5, 10, 11, 6, z3 + 1, z3 + 4, z3 + 5, z3 + 2]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            for i in range(2, nx):
                new_nodes = [10 + (i - 2) * 4, 14 + (i - 2) * 4, 15 + (i - 2) * 4, 11 + (i - 2) * 4,
                             z3 + 4 + (i - 2) * 2, z3 + 6 + (i - 2) * 2, z3 + 7 + (i - 2) * 2,
                             z3 + 5 + (i - 2) * 2]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])

                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

            new_nodes = [7, 6, y3 + 2, y3 + 3, z3 + 3, z3 + 2, z3 + 2 * (nx + 1), z3 + 2 * (nx + 1) + 1]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            new_nodes = [6, 11, y3 + 5, y3 + 2, z3 + 2, z3 + 5, z3 + 2 * (nx + 1) + 2, z3 + 2 * (nx + 1)]
            new_coords = []
            for l in range(8):
                new_coords.append(nodes_coord[new_nodes[l]])

            mesh_preprocessor.add_hexahedra(
                node_ids=new_nodes,
                node_coords=new_coords,
            )
            iter = progressbar(iter, nx * ny * nz)

            for i in range(2, nx):
                new_nodes = [11 + 4 * (i - 2), 15 + 4 * (i - 2), y3 + 7 + 2 * (i - 2), y3 + 5 + 2 * (i - 2),
                             z3 + 5 + 2 * (i - 2), z3 + 7 + 2 * (i - 2), z3 + 3 + (i - 2) + 2 * (nx + 1),
                             z3 + 2 + (i - 2) + 2 * (nx + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

            for j in range(2, ny):
                new_nodes = [y3 + 3 + 2 * (j - 2) * (nx + 1), y3 + 2 + 2 * (j - 2) * (nx + 1),
                             y3 + 2 + 2 * (j - 1) * (nx + 1), y3 + 3 + 2 * (j - 1) * (nx + 1), z3 + 1 + j * (nx + 1),
                             z3 + j * (nx + 1), z3 + (j + 1) * (nx + 1), z3 + 1 + (j + 1) * (nx + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                new_nodes = [y3 + 2 + 2 * (j - 2) * (nx + 1), y3 + 5 + 2 * (j - 2) * (nx + 1),
                             y3 + 5 + 2 * (j - 1) * (nx + 1), y3 + 2 + 2 * (j - 1) * (nx + 1), z3 + j * (nx + 1),
                             z3 + 2 + j * (nx + 1), z3 + 2 + (j + 1) * (nx + 1), z3 + (j + 1) * (nx + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                for i in range(2, nx):
                    new_nodes = [y3 + 5 + 2 * (i - 2) + 2 * (j - 2) * (nx + 1),
                                 y3 + 7 + 2 * (i - 2) + 2 * (j - 2) * (nx + 1),
                                 y3 + 7 + 2 * (i - 2) + 2 * (j - 1) * (nx + 1),
                                 y3 + 5 + 2 * (i - 2) + 2 * (j - 1) * (nx + 1),
                                 z3 + i + j * (nx + 1), z3 + (i + 1) + j * (nx + 1), z3 + (i + 1) + (j + 1) * (nx + 1),
                                 z3 + i + (j + 1) * (nx + 1)]
                    new_coords = []
                    for l in range(8):
                        new_coords.append(nodes_coord[new_nodes[l]])
                    mesh_preprocessor.add_hexahedra(
                        node_ids=new_nodes,
                        node_coords=new_coords,
                    )
                    iter = progressbar(iter, nx * ny * nz)

            for k in range(2, nz):
                new_nodes = [z3 + (k - 2) * (nx + 1) * (ny + 1), z3 + 1 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 + (k - 2) * (nx + 1) * (ny + 1), z3 + 3 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + (k - 1) * (nx + 1) * (ny + 1), z3 + 1 + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 2 + (k - 1) * (nx + 1) * (ny + 1), z3 + 3 + (k - 1) * (nx + 1) * (ny + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                new_nodes = [z3 + 1 + (k - 2) * (nx + 1) * (ny + 1), z3 + 4 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 5 + (k - 2) * (nx + 1) * (ny + 1), z3 + 2 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 1 + (k - 1) * (nx + 1) * (ny + 1), z3 + 4 + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 5 + (k - 1) * (nx + 1) * (ny + 1), z3 + 2 + (k - 1) * (nx + 1) * (ny + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                for i in range(2, nx):
                    new_nodes = [z3 + 2 * i + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * i + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * i + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + 2 * i + 1 + (k - 1) * (nx + 1) * (ny + 1)]
                    new_coords = []
                    for l in range(8):
                        new_coords.append(nodes_coord[new_nodes[l]])
                    mesh_preprocessor.add_hexahedra(
                        node_ids=new_nodes,
                        node_coords=new_coords,
                    )
                    iter = progressbar(iter, nx * ny * nz)

                new_nodes = [z3 + 3 + (k - 2) * (nx + 1) * (ny + 1), z3 + 2 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + 1 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 3 + (k - 1) * (nx + 1) * (ny + 1), z3 + 2 + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + 1 + (k - 1) * (nx + 1) * (ny + 1)]
                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                new_nodes = [z3 + 2 + (k - 2) * (nx + 1) * (ny + 1), z3 + 5 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + 2 + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + (k - 2) * (nx + 1) * (ny + 1),
                             z3 + 2 + (k - 1) * (nx + 1) * (ny + 1), z3 + 5 + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + 2 + (k - 1) * (nx + 1) * (ny + 1),
                             z3 + 2 * (nx + 1) + (k - 1) * (nx + 1) * (ny + 1)]

                new_coords = []
                for l in range(8):
                    new_coords.append(nodes_coord[new_nodes[l]])
                mesh_preprocessor.add_hexahedra(
                    node_ids=new_nodes,
                    node_coords=new_coords,
                )
                iter = progressbar(iter, nx * ny * nz)

                for i in range(2, nx):
                    new_nodes = [z3 + 2 * i + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + i + 1 + 2 * (nx + 1) + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + i + 2 * (nx + 1) + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + 2 * i + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + 2 * (i + 1) + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + i + 1 + 2 * (nx + 1) + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + i + 2 * (nx + 1) + (k - 1) * (nx + 1) * (ny + 1)]
                    new_coords = []
                    for l in range(8):
                        new_coords.append(nodes_coord[new_nodes[l]])
                    mesh_preprocessor.add_hexahedra(
                        node_ids=new_nodes,
                        node_coords=new_coords,
                    )
                    iter = progressbar(iter, nx * ny * nz)

                for j in range(2, ny):
                    new_nodes = [z3 + (nx + 1) * j + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + 1 + (k - 1) * (nx + 1) * (ny + 1)]
                    new_coords = []
                    for l in range(8):
                        new_coords.append(nodes_coord[new_nodes[l]])
                    mesh_preprocessor.add_hexahedra(
                        node_ids=new_nodes,
                        node_coords=new_coords,
                    )
                    iter = progressbar(iter, nx * ny * nz)

                    new_nodes = [z3 + (nx + 1) * j + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + 2 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + 2 + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + (k - 2) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * j + 2 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + 2 + (k - 1) * (nx + 1) * (ny + 1),
                                 z3 + (nx + 1) * (j + 1) + (k - 1) * (nx + 1) * (ny + 1)]
                    new_coords = []
                    for l in range(8):
                        new_coords.append(nodes_coord[new_nodes[l]])
                    mesh_preprocessor.add_hexahedra(
                        node_ids=new_nodes,
                        node_coords=new_coords,
                    )
                    iter = progressbar(iter, nx * ny * nz)

                    for i in range(2, nx):
                        new_nodes = [z3 + (nx + 1) * j + i + (k - 2) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * j + i + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * (j + 1) + i + 1 + (k - 2) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * (j + 1) + i + (k - 2) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * j + i + (k - 1) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * j + i + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * (j + 1) + i + 1 + (k - 1) * (nx + 1) * (ny + 1),
                                     z3 + (nx + 1) * (j + 1) + i + (k - 1) * (nx + 1) * (ny + 1)]
                        new_coords = []
                        for l in range(8):
                            new_coords.append(nodes_coord[new_nodes[l]])
                        mesh_preprocessor.add_hexahedra(
                            node_ids=new_nodes,
                            node_coords=new_coords,
                        )
                        iter = progressbar(iter, nx * ny * nz)

    return mesh_preprocessor
