"""
Contains the logic to preprocess and work with a generic unstructured mesh


"""

from __future__ import annotations

import logging
from typing import *

import meshio as msh
import numpy as np
import math
from scipy.spatial import KDTree
from tqdm import tqdm

import pydelling.preprocessing.mesh_preprocessor.geometry as geometry
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pydelling.preprocessing.dfn_preprocessor.fracture import Fracture
from pydelling.preprocessing.mesh_preprocessor.geometry import BaseElement
from pydelling.utils.geometry_utils import compute_polygon_area
from .utils import iGPLogic
logger = logging.getLogger(__name__)


class MeshPreprocessor(iGPLogic):
    """Preprocess generic unstructured meshes and export meshio-compatible geometry.

    Category: mesh
    Tags: mesh, preprocessing, vtk, meshio, elements, boundaries
    Usage: scripts need to build, inspect, subset, annotate, or export unstructured mesh data.
    """
    elements: List[geometry.base_element]
    external_boundaries: Dict[str, List[geometry.base_face]]
    boundaries: Dict[str, List[geometry.base_face]]
    material_dict: Dict[str, List[int]]
    coords: List[np.ndarray]
    centroids: List[np.ndarray]
    meshio_mesh: msh.Mesh = None
    kd_tree: KDTree = None
    point_data = {}
    cell_data = {}
    _coords = None
    _centroids = None
    is_intersected = False
    is_streamlit = False
    aux_nodes = {}
    has_kd_tree: bool = False
    is_connections_found: bool = False

    def __init__(self, *args, **kwargs):
        """Initialize an empty unstructured mesh workspace.

        Category: mesh
        Tags: mesh, preprocessing, initialize, elements, boundaries
        Usage: scripts need a mutable mesh container before adding elements or loading saved geometry.
        """
        self.unordered_nodes = {}
        self.elements = []
        self.material_dict = {}
        self.external_boundaries = {}
        self.boundaries = {}
        self.external_boundaries = {}
        self.cell_data = {}
        self.point_data = {}
        self.meshio_mesh = None
        self._coords = None
        self._centroids = None
        self.kd_tree = None
        self.has_kd_tree = False
        self.is_intersected = False
        self.is_connections_found = False
        self.aux_nodes = {}
        self._array_mesh_cache = None
        self._array_mesh_cache_key = None
        BaseElement.local_id = 0
        self.is_streamlit = bool(kwargs.get('st_file', False))

        self.find_intersection_stats = {
            'total_intersections': 0,
            'intersection_points':
                {
                }
        }

    def _invalidate_geometry_cache(self):
        """Invalidate derived arrays after nodes or elements change."""

        self._coords = None
        self._centroids = None
        self.kd_tree = None
        self.has_kd_tree = False
        self.meshio_mesh = None
        self._array_mesh_cache = None
        self._array_mesh_cache_key = None

    def to_array_mesh(self, *, material_ids=None, use_cache=True):
        """Return a compact array view while preserving source node and element IDs."""

        from .array_mesh import ArrayMesh, CELL_NODE_COUNTS
        from scipy.spatial import ConvexHull

        if not self.elements:
            raise ValueError("cannot convert an empty MeshPreprocessor")
        type_lookup = {
            "tetrahedra": "T", "tetra": "T",
            "pyramid": "P",
            "wedge": "W", "triangular_prism": "W",
            "hexahedra": "H", "hexahedron": "H",
        }
        signature = tuple(
            (
                id(element), int(element.local_id), str(element.type),
                tuple(map(int, element.nodes)), hash(np.asarray(element.coords, dtype=float).tobytes()),
            )
            for element in self.elements
        )
        inferred_materials = tuple(
            getattr(element, "material_id", getattr(element, "rock_type", None))
            for element in self.elements
        )
        material_signature = inferred_materials if material_ids is None else hash(np.asarray(material_ids).tobytes())
        key = (signature, material_signature)
        if use_cache and key == self._array_mesh_cache_key and self._array_mesh_cache is not None:
            return self._array_mesh_cache

        point_ids = np.asarray(sorted({int(node) for element in self.elements for node in element.nodes}), dtype=np.int64)
        remap = {int(source): local for local, source in enumerate(point_ids)}
        source_coordinates = {}
        for element in self.elements:
            for source, coordinate in zip(element.nodes, element.coords):
                source = int(source)
                coordinate = np.asarray(coordinate, dtype=float)
                if source in source_coordinates and not np.allclose(source_coordinates[source], coordinate):
                    raise ValueError(f"source node {source} has inconsistent coordinates")
                source_coordinates[source] = coordinate
        points = np.asarray([source_coordinates[int(source)] for source in point_ids], dtype=float)
        n = len(self.elements)
        connectivity = np.full((n, 8), -1, dtype=np.int64)
        cell_types = np.empty(n, dtype="U1")
        cell_ids = np.empty(n, dtype=np.int64)
        centroids = np.empty((n, 3), dtype=float)
        volumes = np.empty(n, dtype=float)
        if len({int(element.local_id) for element in self.elements}) != n:
            raise ValueError("mesh element local IDs must be unique")
        for row, element in enumerate(self.elements):
            try:
                code = type_lookup[str(element.type).lower()]
            except KeyError as exc:
                raise ValueError(f"unsupported mesh element type {element.type!r}") from exc
            nodes = np.asarray([remap[int(node)] for node in element.nodes], dtype=np.int64)
            if len(nodes) != CELL_NODE_COUNTS[code]:
                raise ValueError(f"element {element.local_id} has invalid {code} connectivity")
            connectivity[row, :len(nodes)] = nodes
            cell_types[row] = code
            cell_ids[row] = int(element.local_id)
            vertices = np.asarray(element.coords, dtype=float)
            centroids[row] = vertices.mean(axis=0)
            volumes[row] = float(ConvexHull(vertices).volume)

        if material_ids is None:
            inferred = list(inferred_materials)
            material_ids = None if any(value is None for value in inferred) else np.asarray(inferred, dtype=np.int32)
        else:
            material_ids = np.asarray(material_ids, dtype=np.int32)
            if material_ids.shape != (n,):
                raise ValueError(f"material_ids must have shape ({n},)")
        compact_cell_data = {}
        for name, values in self.cell_data.items():
            array = np.asarray(values)
            if array.ndim >= 1 and len(array) == n and array.dtype != object:
                compact_cell_data[name] = array.copy()
        result = ArrayMesh(
            points=points,
            connectivity=connectivity,
            cell_types=cell_types,
            cell_ids=cell_ids,
            centroids=centroids,
            volumes=volumes,
            point_ids=point_ids,
            material_ids=material_ids,
            cell_data=compact_cell_data,
            metadata={"source": "MeshPreprocessor.to_array_mesh"},
        )
        self._array_mesh_cache_key = key
        self._array_mesh_cache = result
        return result

    def add_element(self, element: geometry.base_element):
        """Append an already-built mesh element to this mesh.

        Category: mesh
        Tags: mesh, element, add, preprocessing
        Usage: scripts already have a pydelling geometry element and need it included in the mesh.

        Returns:
            None: mutates the mesh element list.
        """
        self.elements.append(element)
        self._invalidate_geometry_cache()

    def add_tetrahedra(self, node_ids: List[int] or np.ndarray, node_coords: List[np.ndarray]):
        """Add one tetrahedral cell to the mesh.

        Category: mesh
        Tags: mesh, tetrahedra, element, nodes, cell
        Usage: building an unstructured mesh from tetrahedral connectivity and coordinates.

        Returns:
            None: appends a tetrahedral element and stores its node coordinates.
        """
        self.elements.append(geometry.TetrahedraElement(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_hexahedra(self, node_ids: List[int] or np.ndarray, node_coords: List[np.ndarray]):
        """Add one hexahedral cell to the mesh.

        Category: mesh
        Tags: mesh, hexahedra, element, nodes, cell
        Usage: building an unstructured mesh from hexahedral connectivity and coordinates.

        Returns:
            None: appends a hexahedral element and stores its node coordinates.
        """
        self.elements.append(geometry.HexahedraElement(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_wedge(self, node_ids: List[int] or np.ndarray, node_coords: List[np.ndarray]):
        """Add one wedge cell to the mesh.

        Category: mesh
        Tags: mesh, wedge, element, nodes, cell
        Usage: building an unstructured mesh from wedge connectivity and coordinates.

        Returns:
            None: appends a wedge element and stores its node coordinates.
        """
        self.elements.append(geometry.WedgeElement(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_pyramid(self, node_ids: List[int] or np.ndarray, node_coords: List[np.ndarray]):
        """Add one pyramid cell to the mesh.

        Category: mesh
        Tags: mesh, pyramid, element, nodes, cell
        Usage: building an unstructured mesh from pyramid connectivity and coordinates.

        Returns:
            None: appends a pyramid element and stores its node coordinates.
        """
        self.elements.append(geometry.PyramidElement(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_triangular_prism(self, node_ids: List[int] or np.ndarray, node_coords: List[np.ndarray]):
        """Add one triangular-prism cell to the mesh as a wedge element.

        Category: mesh
        Tags: mesh, triangular-prism, wedge, element, nodes
        Usage: source connectivity names triangular prisms instead of wedge cells.

        Returns:
            None: appends a wedge element and stores its node coordinates.
        """
        self.elements.append(geometry.WedgeElement(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    @property
    def coords(self) -> np.ndarray:
        """Return node coordinates ordered by node id.

        Category: mesh
        Tags: mesh, coordinates, nodes, array
        Usage: scripts need the mesh point array for export, bounds, or spatial analysis.

        Returns:
            np.ndarray: ordered node coordinate array.
        """
        if self._coords is None:
            if not self.unordered_nodes:
                return np.empty((0, 3), dtype=float)
            # Keep source node IDs addressable for legacy geometry code.  VTK
            # export compacts them separately, so gaps never become points.
            aux_nodes = np.full((max(self.unordered_nodes) + 1, 3), np.nan, dtype=float)
            for idx, node in self.unordered_nodes.items():
                aux_nodes[idx] = node
            self._coords = aux_nodes
        return self._coords

    @property
    def nodes(self) -> np.ndarray:
        """Return mesh node coordinates.

        Category: mesh
        Tags: mesh, nodes, coordinates, array
        Usage: scripts need the node coordinate array using a common mesh naming convention.

        Returns:
            np.ndarray: ordered node coordinate array.
        """
        return self.coords

    def add_quadrilateral(self, node_ids: List[int], node_coords: List[np.ndarray]):
        """Add one quadrilateral face to the mesh.

        Category: mesh
        Tags: mesh, quadrilateral, face, nodes, boundary
        Usage: building surface or boundary geometry from four-node faces.

        Returns:
            None: appends a quadrilateral face and stores its node coordinates.
        """
        self.elements.append(geometry.quadrilateral_face(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_triangle(self, node_ids: List[int], node_coords: List[np.ndarray]):
        """Add one triangular face to the mesh.

        Category: mesh
        Tags: mesh, triangle, face, nodes, boundary
        Usage: building surface or boundary geometry from three-node faces.

        Returns:
            None: appends a triangular face and stores its node coordinates.
        """
        self.elements.append(geometry.triangle_face(node_ids=node_ids, node_coords=node_coords))
        for idx, node in enumerate(node_coords):
            self.unordered_nodes[node_ids[idx]] = node
        self._invalidate_geometry_cache()

    def add_node(self, node: np.ndarray):
        """Append one node to the coordinate array.

        Category: mesh
        Tags: mesh, node, coordinates, deprecated
        Usage: maintaining older scripts that add nodes directly instead of through elements.

        Returns:
            None: mutates the coordinate collection.
        """
        source_id = max(self.unordered_nodes, default=-1) + 1
        self.unordered_nodes[source_id] = np.asarray(node, dtype=float)
        self._invalidate_geometry_cache()

    @property
    def n_nodes(self):
        """Return the number of unique mesh nodes.

        Category: mesh
        Tags: mesh, nodes, count, metadata
        Usage: scripts need mesh size metadata.

        Returns:
            int: number of known nodes.
        """
        return len(self.unordered_nodes)

    @property
    def n_elements(self):
        """Return the number of mesh elements.

        Category: mesh
        Tags: mesh, elements, count, metadata
        Usage: scripts need mesh size metadata.

        Returns:
            int: number of elements.
        """
        return len(self.elements)

    def convert_mesh_to_meshio(self):
        """Convert the internal mesh representation into a meshio Mesh.

        Category: mesh
        Tags: mesh, meshio, convert, cells, points
        Usage: scripts need a meshio object before export or downstream geometry processing.

        Returns:
            meshio.Mesh: converted mesh object stored on meshio_mesh.
        """

        points, elements_in_meshio = self._compact_meshio_geometry(self.elements)
        self.meshio_mesh = msh.Mesh(
            points=points,
            cells=elements_in_meshio,
            cell_data=self.cell_data,
            point_data=self.point_data
        )

    def to_vtk(self, filename='mesh.vtk'):
        """Export the preprocessed mesh to VTK using meshio.

        Category: mesh
        Tags: mesh, vtk, export, meshio, visualization
        Usage: the user asks to write a mesh visualization file from MeshPreprocessor data.

        Returns:
            None: writes the VTK file to filename.
        """
        logger.info(f'Converting mesh to vtk and exporting to {filename}')
        self.convert_mesh_to_meshio()
        self.meshio_mesh.write(filename)

    def subset_to_vtk(self, elements: List[geometry.base_abstract_mesh_object], filename='subset.vtk'):
        """Export a subset of mesh elements to a VTK file.

        Category: mesh
        Tags: mesh, subset, vtk, export, elements
        Usage: the user asks to visualize or download selected mesh elements only.

        Returns:
            None: writes the subset VTK file to filename.
        """
        assert len(elements) > 0, 'No elements to export'
        subset_mesh = self._convert_subset_to_meshio(elements)
        subset_mesh.write(filename)

    def _convert_subset_to_meshio(self, elements: List[geometry.base_abstract_mesh_object]) -> msh.Mesh:
        """Converts a subset of the mesh into a meshio mesh
        Args:
            elements: list of element indices
        Returns:
            meshio mesh
        """
        points, elements_in_meshio = self._compact_meshio_geometry(elements)
        return msh.Mesh(
            points=points,
            cells=elements_in_meshio,
        )

    def _compact_meshio_geometry(self, elements):
        """Return compact points/connectivity for arbitrary source node IDs."""

        used = sorted({int(node) for element in elements for node in element.nodes})
        remap = {source_id: local_id for local_id, source_id in enumerate(used)}
        points = np.asarray([self.unordered_nodes[source_id] for source_id in used], dtype=float)
        cells = self._create_meshio_dict(elements)
        for cell_type, connectivity in cells.items():
            cells[cell_type] = [[remap[int(node)] for node in row] for row in connectivity]
        return points, cells

    def _create_meshio_dict(self, elements: List[geometry.base_abstract_mesh_object]) -> Dict[str, List[List[int]]]:
        """
        _create_meshio_dict method.
        
        Args:
            elements (List[geometry.base_abstract_mesh_object]): Description.
        """
        grouped = {
            "wedge": [],
            "pyramid": [],
            "tetrahedra": [],
            "hexahedra": [],
            "triangle": [],
            "quadrilateral": [],
        }
        for element in elements:
            if element.type not in grouped:
                raise ValueError(f"unsupported mesh element type {element.type!r}")
            grouped[element.type].append(element.nodes.tolist())
        names = {
            "wedge": "wedge",
            "pyramid": "pyramid",
            "tetrahedra": "tetra",
            "hexahedra": "hexahedron",
            "triangle": "triangle",
            "quadrilateral": "quad",
        }
        return {names[key]: values for key, values in grouped.items() if values}

    def nodes_to_csv(self, filename='node_ids.csv'):
        """Export mesh node coordinates to a CSV file.

        Category: writer
        Tags: mesh, nodes, csv, export, coordinates
        Usage: scripts need a simple coordinate table for mesh nodes.

        Returns:
            None: writes the CSV file.
        """
        node_array = np.array(self.coords)
        np.savetxt(filename, node_array, delimiter=',')

    @property
    def centroids(self):
        """Return centroid coordinates for all mesh elements.

        Category: mesh
        Tags: mesh, centroids, elements, coordinates
        Usage: scripts need cell centers for nearest-neighbor queries, interpolation, or summaries.

        Returns:
            np.ndarray: element centroid coordinate array.
        """
        if self._centroids is None:
            centroids = []
            for element in self.elements:
                centroids.append(element.centroid)
            self._centroids = np.array(centroids)
        return self._centroids

    def create_kd_tree(self, kd_tree_config=None):
        """Create a KD-tree over mesh element centroids.

        Category: mesh
        Tags: mesh, kd-tree, centroids, nearest, spatial
        Usage: scripts need fast nearest-element or radius queries.

        Returns:
            None: stores the KDTree on kd_tree.
        """
        if kd_tree_config is None:
            kd_tree_config = {}
        self.kd_tree = KDTree(self.centroids, **kd_tree_config)
        self.has_kd_tree = True

    def get_k_nearest_mesh_elements(self, point, k=15, distance_upper_bound=None):
        """Return the k nearest mesh elements to a point.

        Category: mesh
        Tags: mesh, nearest, kd-tree, point, elements
        Usage: scripts need nearby cells for interpolation, sampling, or material assignment.

        Returns:
            list: nearest mesh element objects.
        """
        if self.kd_tree is None:
            self.create_kd_tree()
        if distance_upper_bound:
            ids = self.kd_tree.query(point, k=k, distance_upper_bound=distance_upper_bound)[1]
        else:
            ids = self.kd_tree.query(point, k=k)[1]

        assert len(ids) != 0, "No elements found"
        return [self.elements[i] for i in ids]

    def get_closest_mesh_elements(self, point, distance=None):
        """Return mesh elements within a radius of a point.

        Category: mesh
        Tags: mesh, nearest, radius, kd-tree, elements
        Usage: scripts need all cells inside a spatial search radius.

        Returns:
            list: mesh elements within the radius.
        """
        if self.kd_tree is None:
            self.create_kd_tree()

        ids = self.kd_tree.query_ball_point(point, distance)
        # assert len(ids) != 0, "No elements found"
        return [self.elements[i] for i in ids]

    def get_closest_n_mesh_elements(self,
                                    point,
                                    n=1
                                    ):
        """Return the closest n mesh elements to a point.

        Category: mesh
        Tags: mesh, nearest, kd-tree, point, elements
        Usage: scripts need a fixed number of nearby cells for a coordinate.

        Returns:
            list: closest mesh element objects.
        """
        if self.kd_tree is None:
            self.create_kd_tree()

        ids = np.atleast_1d(self.kd_tree.query(point, k=n)[1])
        return [self.elements[int(i)] for i in ids]

    def clear(self):
        """Remove all nodes and elements from this mesh.

        Category: mesh
        Tags: mesh, clear, reset, elements
        Usage: scripts need to reuse a MeshPreprocessor instance with new geometry.

        Returns:
            None: clears mesh nodes and elements.
        """
        self.unordered_nodes = {}
        self.elements = []
        self.cell_data = {}
        self.point_data = {}
        self._invalidate_geometry_cache()

    @staticmethod
    def _intersect_fracture_with_element(element, fracture):
        """
        Returns the intersection of a fracture with an element.
        Args:
            element: The element to intersect with.
            fracture: The fracture to intersect with.
        Returns:
            The intersection of the fracture and the element.
        """
        return element.intersect(fracture)

    def _is_fracture_intersected(self, fracture: 'Fracture', element: geometry.base_element):
        """
        Checks if a fracture is intersected by an element.
        Args:
            fracture: The fracture to intersect with.
            element: The element to intersect with.
        Returns:
            True if the fracture is intersected by the element, False otherwise.
        """
        signs = []
        bounding_box: List = fracture.get_bounding_box()
        for coord in element.coords:
            # Check if coord in bounding box
            if bounding_box[0] < coord[0] < bounding_box[1] and bounding_box[2] < coord[1] < bounding_box[3] and \
                    bounding_box[4] < coord[2] < bounding_box[5]:

                distance_to_fracture = fracture.distance_to_point(coord)
                signs.append(np.sign(distance_to_fracture))
            else:
                return False

        if not np.all(np.array(signs) == signs[0]):
            return True


    def find_the_intersection_between_fracture_and_mesh(self, fracture: 'Fracture'):
        """Find mesh elements intersected by a fracture and export them to VTK.

        Category: mesh
        Tags: mesh, fracture, intersection, vtk, subset
        Usage: scripts need a VTK subset of cells cut by a fracture.

        Returns:
            None: writes intersections.vtk.
        """
        intersections = []
        for element in self.elements:
            if self._is_fracture_intersected(fracture, element):
                intersections.append(element)
        self.subset_to_vtk(intersections, filename='intersections.vtk')

    def find_intersection_points_between_fracture_and_mesh(self, fracture: 'Fracture', export_stats=False):
        """Compute fracture intersection points and areas for nearby mesh elements.

        Category: mesh
        Tags: mesh, fracture, intersection, area, aperture
        Usage: scripts need fracture-cell intersection metadata for DFN or flow preprocessing.

        Returns:
            list: intersection points found for the processed elements.
        """

        intersection_points = []
        kd_tree_filtered_elements = self.get_closest_mesh_elements(fracture.centroid, distance=fracture.size)
        counter = 0
        for element in kd_tree_filtered_elements:
            element: geometry.base_element
            counter += 1
            intersection_points = element.intersect_with_fracture(fracture)

            if len(intersection_points) >= 3:
                intersection_area = compute_polygon_area(intersection_points)
                fracture.intersection_dictionary[element.local_id] = intersection_area
                element.associated_fractures[fracture.local_id] = {
                    'area': intersection_area,
                    'volume': intersection_area * fracture.aperture,
                    'fracture': fracture,
                }
            n_intersections = len(intersection_points)
            if not n_intersections in self.find_intersection_stats['intersection_points'].keys():
                self.find_intersection_stats['intersection_points'][n_intersections] = 0
            self.find_intersection_stats['intersection_points'][n_intersections] += 1
            self.find_intersection_stats['total_intersections'] += 1

        self.is_intersected = True

        return intersection_points


    def export_intersection_stats(self, filename='intersection_stats.txt'):
        # Export the run_stats dictionary to file
        """Export accumulated fracture-intersection statistics to JSON.

        Category: writer
        Tags: mesh, fracture, intersection, stats, json
        Usage: scripts need a diagnostic file after fracture-mesh intersection.

        Returns:
            None: writes run_stats.json.
        """
        assert self.is_intersected, 'The mesh has not been intersected yet.'
        import json
        with open('run_stats.json', 'w') as fp:
            json.dump(self.find_intersection_stats, fp)

    @staticmethod
    def intersect_edge_plane(edge: np.ndarray,
                             edge_point: np.ndarray,
                             plane: 'Fracture',
                             ) -> np.ndarray or None:
        """Intersect one edge ray with a fracture plane.

        Category: mesh
        Tags: mesh, fracture, plane, edge, intersection
        Usage: scripts need the geometric intersection point between a mesh edge and fracture plane.

        Returns:
            np.ndarray | None: intersection point inside the plane bounds, if present.
        """

        edge_dot = np.dot(edge, plane.unit_normal_vector)
        if edge_dot == 0:
            return None
        else:
            t = -np.dot((edge_point - plane.centroid), plane.unit_normal_vector) / edge_dot
            if t < 1.0 and t > 0.0:
                point = edge_point + t * edge
                if plane.point_inside_bounding_box(point):
                    return point
            else:
                return None

    @property
    def min_x(self):
        """Return the minimum mesh x coordinate.

        Category: mesh
        Tags: mesh, bounds, x, minimum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: minimum x coordinate.
        """
        return self.coords[:, 0].min()

    @property
    def max_x(self):
        """Return the maximum mesh x coordinate.

        Category: mesh
        Tags: mesh, bounds, x, maximum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: maximum x coordinate.
        """
        return self.coords[:, 0].max()

    @property
    def min_y(self):
        """Return the minimum mesh y coordinate.

        Category: mesh
        Tags: mesh, bounds, y, minimum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: minimum y coordinate.
        """
        return self.coords[:, 1].min()

    @property
    def max_y(self):
        """Return the maximum mesh y coordinate.

        Category: mesh
        Tags: mesh, bounds, y, maximum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: maximum y coordinate.
        """
        return self.coords[:, 1].max()

    @property
    def min_z(self):
        """Return the minimum mesh z coordinate.

        Category: mesh
        Tags: mesh, bounds, z, minimum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: minimum z coordinate.
        """
        return self.coords[:, 2].min()

    @property
    def max_z(self):
        """Return the maximum mesh z coordinate.

        Category: mesh
        Tags: mesh, bounds, z, maximum
        Usage: scripts need mesh spatial bounds.

        Returns:
            float: maximum z coordinate.
        """
        return self.coords[:, 2].max()


    def save(self, filename):
        """Serialize mesh elements, coordinates, and KD-tree state with pickle.

        Category: writer
        Tags: mesh, save, pickle, serialize
        Usage: scripts need to persist a preprocessed mesh for later reuse.

        Returns:
            None: writes the pickle file.
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
        """Load mesh elements, coordinates, and KD-tree state from a pickle file.

        Category: mesh
        Tags: mesh, load, pickle, serialize
        Usage: scripts need to restore a previously saved MeshPreprocessor state.

        Returns:
            None: mutates this instance with saved mesh data.
        """
        logger.info(f'Loading mesh from {filename}')
        import pickle
        with open(filename, 'rb') as f:
            save_dictionary = pickle.load(f)
            self.elements = save_dictionary['elements']
            self._coords = save_dictionary['coords']
            self.kd_tree = save_dictionary['kd_tree']
            self.has_kd_tree = save_dictionary['has_kd_tree']

    def get_json(self):
        """Return a JSON-serializable dictionary for this mesh.

        Category: mesh
        Tags: mesh, json, serialize, elements, coordinates
        Usage: scripts need portable mesh metadata or will write the mesh as JSON.

        Returns:
            dict: JSON-ready mesh representation.
        """
        logger.info('Exporting mesh to json')
        save_dictionary = {}
        _elements = [element.get_json() for element in self.elements]
        save_dictionary['elements'] = _elements
        save_dictionary['coords'] = self.coords.tolist()
        save_dictionary['has_kd_tree'] = self.has_kd_tree
        return save_dictionary

    def to_json(self, filename='mesh.json'):
        """Write this mesh to a JSON file.

        Category: writer
        Tags: mesh, json, export, serialize
        Usage: scripts need a portable JSON representation of mesh elements and coordinates.

        Returns:
            None: writes the JSON file.
        """
        import json
        with open(filename, 'w') as f:
            json.dump(self.get_json(), f)

    @classmethod
    def from_json(self, filename='mesh.json'):
        """Create a MeshPreprocessor from a JSON mesh file.

        Category: mesh
        Tags: mesh, json, load, serialize
        Usage: scripts need to restore mesh geometry from a JSON export.

        Returns:
            MeshPreprocessor: loaded mesh instance.
        """
        logger.info(f'Loading mesh from {filename}')
        BaseElement.local_id = 0
        import json
        with open(filename, 'r') as f:
            save_dictionary = json.load(f)
            mesh = MeshPreprocessor()
            mesh._coords = np.array(save_dictionary['coords'])
            mesh.has_kd_tree = save_dictionary['has_kd_tree']
            MeshPreprocessor.load_elements(mesh, save_dictionary['elements'])
            if mesh.has_kd_tree:
                mesh.create_kd_tree()
            return mesh

    @classmethod
    def from_dict(cls, dict: dict):
        """Create a MeshPreprocessor from a mesh dictionary.

        Category: mesh
        Tags: mesh, dict, load, serialize
        Usage: scripts already have parsed mesh JSON and need a MeshPreprocessor instance.

        Returns:
            MeshPreprocessor: loaded mesh instance.
        """
        BaseElement.local_id = 0
        mesh = MeshPreprocessor()
        mesh._coords = np.array(dict['coords'])
        mesh.has_kd_tree = dict['has_kd_tree']
        MeshPreprocessor.load_elements(mesh, dict['elements'])
        if mesh.has_kd_tree:
            mesh.create_kd_tree()
        return mesh

    @staticmethod
    def load_elements(mesh: MeshPreprocessor, element_dict):
        """Load serialized elements into a MeshPreprocessor.

        Category: mesh
        Tags: mesh, elements, load, serialize
        Usage: reconstructing a mesh from JSON or dictionary data.

        Returns:
            None: appends reconstructed elements to the mesh.
        """
        elements = []
        source_coords = np.asarray(mesh._coords, dtype=float).copy()
        for local_id, element in tqdm(enumerate(element_dict), desc='Loading elements'):
            if element['type'] == 'tetrahedra':
                mesh.add_tetrahedra(node_ids=element['nodes'],
                                    node_coords=source_coords[element['nodes']])
            elif element['type'] == 'hexahedra':
                mesh.add_hexahedra(node_ids=element['nodes'],
                                   node_coords=source_coords[element['nodes']])
            elif element['type'] == 'wedge':
                mesh.add_wedge(node_ids=element['nodes'],
                               node_coords=source_coords[element['nodes']])
            elif element['type'] == 'pyramid':
                mesh.add_pyramid(node_ids=element['nodes'],
                                 node_coords=source_coords[element['nodes']])
            associated_fractures_dict = element_dict[local_id]['associated_fractures']
            temp_associated_fractures = {}
            for key in associated_fractures_dict:
                cur_fracture = associated_fractures_dict[key]
                temp_fracture = {key: value for key, value in cur_fracture.items() if key != 'fracture'}
                temp_fracture['fracture'] = cur_fracture['fracture']
                temp_associated_fractures[key] = temp_fracture
            mesh.elements[local_id].associated_fractures = temp_associated_fractures

    def refactor_array_by_element_type(self, array: np.ndarray or list) -> list:
        """Group per-element values by meshio cell type order.

        Category: mesh
        Tags: mesh, cell-data, meshio, element-types
        Usage: attaching cell data to a meshio export that groups cells by type.

        Returns:
            list: values grouped by element type.
        """
        if isinstance(array, np.ndarray):
            array = array.tolist()
        final_array = []
        temp_dict = {
            'wedge': [],
            'pyramid': [],
            'tetrahedra': [],
            'hexahedra': [],
            'triangle': [],
            'quadrilateral': [],
        }
        for element in self.elements:
            temp_dict[element.type].append(array[element.local_id])
        for key in temp_dict:
            if len(temp_dict[key]) > 0:
                final_array.append(temp_dict[key])
        return final_array

    def __repr__(self):
        return f'Mesh with {len(self.elements)} elements and {len(self.coords)} nodes.'

    def add_cell_data(self, name, data):
        """Attach named cell data to the mesh for meshio export.

        Category: mesh
        Tags: mesh, cell-data, meshio, variables, export
        Usage: scripts need VTK or meshio outputs with per-cell variables.

        Returns:
            None: stores grouped cell data under name.
        """
        self.cell_data[name] = self.refactor_array_by_element_type(data)

    def add_point_data(self, name, data):
        """Attach named point data to the mesh for meshio export.

        Category: mesh
        Tags: mesh, point-data, meshio, variables, export
        Usage: scripts need VTK or meshio outputs with per-node variables.

        Returns:
            None: stores point data under name.
        """
        self.point_data[name] = data

    def find_mesh_connections(self):
        """Find neighboring mesh elements that share faces.

        Category: mesh
        Tags: mesh, connections, faces, adjacency, topology
        Usage: scripts need element adjacency before boundary detection or topology analysis.

        Returns:
            None: populates element connection maps.
        """
        logger.info('Finding mesh connections')
        aux_vec = []
        for element in tqdm(self.elements, desc='Creating auxiliar vector'):
            for face in element.faces.values():
                aux_vec.append((sorted(list(face.nodes)), element.local_id))

        aux_vec.sort(key=lambda x: x[0])
        # Make a sorted list of the faces
        for i in tqdm(range(len(aux_vec) - 1), desc='Finding connections'):
            connection_1 = aux_vec[i]
            connection_2 = aux_vec[i + 1]
            if connection_1[0] == connection_2[0]:
                elem_1 = self.elements[connection_1[1]]
                elem_2 = self.elements[connection_2[1]]
                face_1 = elem_1.detect_face(connection_1[0])
                face_2 = elem_2.detect_face(connection_2[0])

                elem_1.connections[elem_2.local_id] = [face_1, face_2]
                elem_2.connections[elem_1.local_id] = [face_2, face_1]
        self.is_connections_found = True

    def find_boundary_elements(self):
        """Find elements that have external boundary faces.

        Category: mesh
        Tags: mesh, boundaries, external-faces, topology
        Usage: scripts need boundary elements after mesh connections have been computed.

        Returns:
            None: populates external_boundaries.
        """
        # self.find_mesh_connections() should be obtained first.
        if not self.is_connections_found:
            raise ValueError("Connections should be computed. Run self.find_mesh_connections()")
        logger.info('Finding boundary elements')
        for element in tqdm(self.elements, desc="Finding boundary elements"):
            if not len(element.connections) == len(element.faces):
                self.external_boundaries[element.local_id] = element.external_faces

    def get_topography_faces(self) -> dict:
        """Return upward-facing external faces as topography candidates.

        Category: mesh
        Tags: mesh, topography, boundaries, faces, normals
        Usage: scripts need top surface faces for boundary assignment or terrain extraction.

        Returns:
            dict: element ids mapped to topography face objects.
        """
        if not self.external_boundaries:
            raise ValueError("self.boundaries is None.")
        elem_vector = {}
        for local_id, val in tqdm(self.external_boundaries.items(), desc="Finding topography elements"):
            for face in self.elements[local_id].external_faces:
                unit_face_vector_z = self.elements[local_id].faces[face.face_id].unit_normal_vector[2]
                if unit_face_vector_z > 0:
                    elem_vector[local_id] = face

        return elem_vector

    def set_topography_boundaries(self, z_coord: float = 0.0, keys: list[str] = ["land", "sea"]):
        """Split topography faces into two named boundary groups by z coordinate.

        Category: mesh
        Tags: mesh, topography, boundaries, z, groups
        Usage: scripts need land/sea or upper/lower topography boundary groups.

        Returns:
            None: populates boundary groups named by keys.
        """

        for key in keys:
            self.boundaries[key] = {}

        topo_faces = self.get_topography_faces()
        for id_element, face in tqdm(topo_faces.items(), desc="Assigning topography boundaries."):
            z_mean = np.mean(face.coords, axis=0)[2]
            if z_mean > z_coord:
                self.boundaries[keys[0]][id_element] = face
            else:
                self.boundaries[keys[1]][id_element] = face

    def plot_topography_centroids(self):
        """Plot topography boundary centroids for visual diagnostics.

        Category: mesh
        Tags: mesh, topography, plot, centroids, diagnostics
        Usage: scripts need a quick matplotlib diagnostic of assigned topography boundaries.

        Returns:
            None: displays a matplotlib plot.
        """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        logger.info('Ploting topography centroids')
        if self.boundaries["sea"]:
            for key, face in self.boundaries["sea"].items():
                ax.scatter(face.centroid[0], face.centroid[1], marker="x", c="b", s=10.0)
        if self.boundaries["land"]:
            for key, face in self.boundaries["land"].items():
                ax.scatter(face.centroid[0], face.centroid[1], marker="x", c="g", s=10.0)
        plt.show()

    def get_boundary_elements_given_unit_vector(self,
                                                unit_vector: np.array or list,
                                                tolerance: float = 0.1
                                                ) -> List[geometry.base_face]:
        """Return external faces whose normals match a target unit vector.

        Category: mesh
        Tags: mesh, boundaries, normals, faces, direction
        Usage: scripts need top, bottom, north, south, east, or west boundary faces by normal direction.

        Returns:
            dict: element ids mapped to matching external face objects.
        """
        if not self.external_boundaries:
            raise ValueError("self.boundaries is None.")
        elem_vector = {}
        logger.info(f'Finding boundary elements from unit vector: {unit_vector}')
        for i_elem, val in tqdm(self.external_boundaries.items(), desc="Finding boundary elements from a unit vector"):
            for face in self.elements[i_elem].external_faces:
                u_vector_face = self.elements[i_elem].faces[face.face_id].unit_normal_vector

                # Compute the dot product of the vectors
                dot_product = np.dot(unit_vector, u_vector_face)
                if dot_product < 1E-16:
                    continue

                # Compute the magnitudes of the vectors
                magnitude1 = np.linalg.norm(unit_vector)
                magnitude2 = np.linalg.norm(u_vector_face)

                # Compute the cosine of the angle between the vectors
                cosine_angle = dot_product / (magnitude1 * magnitude2)

                # Check if the cosine angle is close to 1 within the given tolerance
                if abs(cosine_angle - 1) < tolerance:
                    elem_vector[i_elem] = face
        return elem_vector

    def assign_automatic_six_face_boundaries(self):
        """Assign six axis-aligned boundary groups from external face normals.

        Category: mesh
        Tags: mesh, boundaries, normals, top, bottom, sides
        Usage: scripts need automatic top, bottom, north, south, east, and west boundary groups.

        Returns:
            None: populates the boundaries dictionary.
        """
        self.boundaries['top']    = self.get_boundary_elements_given_unit_vector([0, 0, 1])
        self.boundaries['bottom'] = self.get_boundary_elements_given_unit_vector([0, 0, -1])
        self.boundaries['north']  = self.get_boundary_elements_given_unit_vector([0, 1,  0])
        self.boundaries['south']  = self.get_boundary_elements_given_unit_vector([0, -1, 0])
        self.boundaries['east']   = self.get_boundary_elements_given_unit_vector([1, 0, 0])
        self.boundaries['west']   = self.get_boundary_elements_given_unit_vector([-1, 0, 0])
