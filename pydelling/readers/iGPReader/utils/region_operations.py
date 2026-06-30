"""
Module documentation.


"""

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pydelling.readers.iGPReader import iGPReader
    from pydelling.readers.iGPReader.geometry import BaseElement
import logging
from copy import deepcopy

logger = logging.getLogger(__name__)
import numpy as np
from pydelling.utils.utility_subclasses import SemistructuredFinder
# Import a kd-tree class from scipy.spatial
from scipy.spatial import cKDTree as KDTree
from typing import List, Union


class RegionOperations:
    """Mixin with region splitting and nearest-node helpers for iGP readers.

    Category: iGP region operations.
    Tags: igp, regions, boundaries, kd-tree, clustering, nodes.
    Usage: to understand how iGP regions can be split,
        queried by x/y location, or linked to element centroids.
    """

    boundaries: dict
    region_dict: dict
    # Add iGPReader class methods to this class namespace

    def divide_topography_by_z(self: iGPReader,
                               z: float,
                               region_name: str,
                               name_below: str = 'below',
                               name_above: str = 'above',
                               cache_old_results: bool = False,
                               ) -> None:
        """Split a boundary region into below/above regions by centroid z.

        Category: iGP region operations.
        Tags: igp, regions, topography, z-split, boundaries.
        Usage: separating a topographic boundary into two named regions for
            material assignment, export, or boundary-condition workflows.
        Args:
            z: The z coordinate to divide the topography by.
            region_name: The name of the region to divide.
            name_below: The name of the region below the z coordinate.
            name_above: The name of the region above the z coordinate.
            cache_old_results: If True, each time this method is called the original region_dict will be used.
        Side effects:
            Mutates ``self.boundaries`` and ``self.region_dict`` by replacing
            ``region_name`` with the below/above regions. Optionally caches old
            dictionaries for reuse.
        """
        if cache_old_results:
            if hasattr(self, 'old_region_dict'):
                self.region_dict = self.old_region_dict
            if hasattr(self, 'old_boundaries'):
                self.boundaries = self.old_boundaries
        boundary_faces = self.get_boundary_faces(region_name)
        name_below = name_below if name_below != 'below' else f"{region_name}_below"
        name_above = name_above if name_above != 'above' else f"{region_name}_above"
        logger.info(f'Dividing topography by z={z} into regions {name_below} and {name_above}')

        new_boundaries = {name_below: [],
                          name_above: []}

        for face_idx, face in enumerate(boundary_faces):
            if face.centroid[2] < z:
                new_boundaries[name_below].append(face_idx)
            else:
                new_boundaries[name_above].append(face_idx)

        # Update the boundaries dict
        if cache_old_results:
            self.old_boundaries = deepcopy(self.boundaries)
        for name in new_boundaries:
            self.boundaries[name] = [boundary_faces[idx] for idx in new_boundaries[name]]
        self.boundaries.pop(region_name)

        # Update the region dict
        if cache_old_results:
            self.old_region_dict = deepcopy(self.region_dict)
        get_old_region = self.region_dict[region_name]
        # Divide the region elements based on the found idx
        self.region_dict[name_below] = {'elements': get_old_region['elements'][new_boundaries[name_below]],
                                        'centroid_id': get_old_region['centroid_id'][new_boundaries[name_below] ],
                                        'length': len(new_boundaries[name_below])}
        self.region_dict[name_above] = {'elements': get_old_region['elements'][new_boundaries[name_above]],
                                        'centroid_id': get_old_region['centroid_id'][new_boundaries[name_above]],
                                        'length': len(new_boundaries[name_above])}

        # Remove the old region
        self.region_dict.pop(region_name)

    def get_nodes_from_x_y(self: iGPReader,
                           x: float,
                           y: float,
                           materials: list = None,
                           top_region_name: str = None,
                           tol: float = 5.0,
                           eps: float = 2.5,
                           min_samples: int = 20,
                           ) -> list:
        """Return node ids nearest to an x/y coordinate within a clustered subset.

        Category: iGP region operations.
        Tags: igp, nodes, clustering, nearest, xy.
        Usage: locating mesh nodes by surface x/y coordinates, optionally
            constrained by material or top-region context.
        Args:
            self: The iGPReader object that calls this method.
            x: The x-coordinate for which to find closest nodes.
            y: The y-coordinate for which to find closest nodes.
            materials: The materials of the nodes to consider.
            top_region_name: The top region name of the nodes to consider.
            tol: The tolerance used in the computation.
            eps: The epsilon value used in clustering.
            min_samples: The minimum number of samples required for a cluster.
        Returns:
            np.ndarray: Node ids in ``self.node_id_subset`` selected by the
            closest cluster ids.
        Side effects:
            Lazily initializes ``node_id_subset`` and ``cluster_engine`` when no
            subset has been generated.
        """


        if not hasattr(self, 'is_subset_generated'):
            self._setup_cluster_and_subset(eps=eps,
                                           min_samples=min_samples,
                                           top_region_name=top_region_name,
                                           materials=materials,
                                           )
            self.is_subset_generated = True

        closest_cluster_ids = self.cluster_engine.get_closest_point_ids_from_xy(x, y)
        closest_cluster_nodes = self.nodes[self.node_id_subset[closest_cluster_ids]]
        # Sort the closest_cluster_ids by z coordinate


        return self.node_id_subset[closest_cluster_ids]
        # Order


    def _setup_cluster_and_subset(self: iGPReader,
                                    eps: float,
                                    min_samples: int,
                                    top_region_name: str = None,
                                    materials: list = None,
                                    ):

        """
        Initialize the cluster engine (DBSCAN) and create a subset of nodes from the material specified

        Args:
            eps: The maximum distance between two samples for one to be considered as in the neighborhood of the other
            min_samples: The number of samples in a neighborhood for a point to be considered as a core point.
            top_region_name: The name of the top region.
            materials: List of materials.

        """
        logger.info(f'Setting up cluster engine (DBSCAN with eps={eps} and min_samples={min_samples}) and subset of nodes for materials {materials}')
        self.is_subset_generated = False
        temp_node_id = []
        if materials is not None:
            for material in materials:
                element_nodes = [self.element_nodes[element_id] for element_id in self.get_material_elements(material)]
                element_nodes = np.unique(np.array(element_nodes).flatten())
                temp_node_id.append(element_nodes)
        else:
            element_nodes = np.unique(np.array(self.element_nodes).flatten())
            temp_node_id.append(element_nodes)
        temp_node_id = np.concatenate(temp_node_id)
        self.node_id_subset = np.unique(temp_node_id)
        self.cluster_engine = SemistructuredFinder(self.nodes[self.node_id_subset], eps=eps, min_samples=min_samples)
        logger.info(f'A total of {self.cluster_engine.n_clusters} clusters were found in the subset of nodes. Play with eps (eps={eps}) and min_samples (min_samples={min_samples}) to find more clusters.')
        try:
            top_region_elements = self.get_region_nodes(top_region_name)
            if self.cluster_engine.n_clusters != len(top_region_elements):
                logger.warning(f'The number of clusters found ({self.cluster_engine.n_clusters}) does not match the number of elements in the top region ({len(top_region_elements)}).')
        except:
            logger.warning(f'No top region was provided. The number of clusters found ({self.cluster_engine.n_clusters}) may not match the number of elements in the top region.')
            
    

    def get_closest_region_node_from_x_y(self: iGPReader,
                                         region_name: str,
                                         x: float,
                                         y: float,
                                         ) -> list:
        """Return the closest node coordinates in a region for an x/y point.

        Category: iGP region operations.
        Tags: igp, regions, nearest, kd-tree, xy.
        Usage: projecting an x/y location onto the nearest node of a named
            region.
        Args:
            region_name: Region whose nodes should be searched.
            x: Query x coordinate.
            y: Query y coordinate.
        Returns:
            np.ndarray: Coordinates of the closest region node.
        Side effects:
            Lazily creates a region KD-tree attribute when missing.
        """
        # Carry out a
        if not hasattr(self, f"{region_name}_kd_tree"):
            kd_tree = self._setup_kd_tree_on_region(region_name)
        else:
            kd_tree = getattr(self, f"{region_name}_kd_tree")
        # Find the closest node id
        closest_node_z = kd_tree.query([x, y])[1]
        return self.get_region_nodes(region_name)[closest_node_z]

    def get_closest_region_node_from_elements(self: iGPReader,
                                         region_name: str,
                                         elements: Union[BaseElement, list],
                                         ) -> list:
        """Return closest region node coordinates for one or more elements.

        Category: iGP region operations.
        Tags: igp, regions, elements, nearest, kd-tree.
        Usage: mapping element centroids onto their nearest node in a named
            region.
        Args:
            region_name: Region whose nodes should be searched.
            elements: A single ``BaseElement`` or a list of elements with
                ``centroid_coords``.
        Returns:
            list: Region-node coordinates closest to the element centroid x/y
            positions.
        Side effects:
            Lazily creates a region KD-tree attribute when missing.
        """
        # Carry out a
        if not hasattr(self, f"{region_name}_kd_tree"):
            kd_tree = self._setup_kd_tree_on_region(region_name)
        else:
            kd_tree = getattr(self, f"{region_name}_kd_tree")
        # Find the closest node id
        from pydelling.readers.iGPReader.geometry import BaseElement
        if isinstance(elements, BaseElement):
            element_centroid = elements.centroid_coords
            closest_nodes_z = [kd_tree.query(element_centroid[:2])[1]]
        else:
            element_centroids = [element.centroid_coords for element in elements]
            element_centroids_2d = [element_centroid[:2] for element_centroid in element_centroids]
            closest_nodes_z = kd_tree.query(element_centroids_2d)[1]
        region_nodes = self.get_region_nodes(region_name)
        region_coords = [region_nodes[closest_node_z] for closest_node_z in closest_nodes_z]
        return region_coords


    def _setup_kd_tree_on_region(self: iGPReader, region_name):
        """Build a 2D KD-tree over the x/y coordinates of a region's nodes.

        Category: iGP region operations.
        Tags: igp, regions, kd-tree, xy.
        Usage: nearest-node region queries need a spatial index.
        Args:
            region_name: Region whose nodes should be indexed.
        Returns:
            scipy.spatial.cKDTree: KD-tree built from x/y node coordinates.
        """
        region_nodes = self.get_region_nodes(region_name)
        # Get only the x and y coordinates
        region_nodes = region_nodes[:, :2]
        # Setup the KD tree
        kd_tree = KDTree(region_nodes)
        return kd_tree

