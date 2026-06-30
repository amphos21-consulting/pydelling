"""
Module documentation.


"""

import logging
import numpy as np
import functools
import scipy

logger = logging.getLogger(__name__)


class UnitConverter:
    """Convert common time units used in pydelling workflows.

    Category: utilities.
    Tags: units, time, conversion.
    Use when: an MCP agent needs to convert between seconds, minutes, hours,
        days, and years.
    """

    def convert_time(self, value, initial_unit, final_unit):
        """Convert one time value between supported units.

        Category: utilities.
        Tags: units, time, conversion.
        Use when: normalizing time values for simulation inputs or reports.
        Args:
            value: Numeric time value.
            initial_unit: Source unit, one of ``s``, ``min``, ``h``, ``d``, or
                ``y``.
            final_unit: Target unit, one of ``s``, ``min``, ``h``, ``d``, or
                ``y``.
        Returns:
            float: Converted value.
        Raises:
            ValueError: If the unit conversion is unsupported.
        """
        value = float(value)
        if initial_unit == 's' and final_unit == 'd':
            return value / 86400
        elif initial_unit == 'd' and final_unit == 's':
            return value * 86400
        elif initial_unit == 's' and final_unit == 'y':
            return value / 31557600
        elif initial_unit == 'y' and final_unit == 's':
            return value * 31557600
        elif initial_unit == 'd' and final_unit == 'y':
            return value / 365
        elif initial_unit == 'y' and final_unit == 'd':
            return value * 365
        elif initial_unit == 'min' and final_unit == 'y':
            return value / 525600
        elif initial_unit == 'y' and final_unit == 'min':
            return value * 525600
        elif initial_unit == 'min' and final_unit == 'd':
            return value / 1440
        elif initial_unit == 'd' and final_unit == 'min':
            return value * 1440
        elif initial_unit == 'min' and final_unit == 's':
            return value / 60
        elif initial_unit == 's' and final_unit == 'min':
            return value * 60
        elif initial_unit == 'min' and final_unit == 'h':
            return value / 60
        elif initial_unit == 'h' and final_unit == 'min':
            return value * 60
        elif initial_unit == 'h' and final_unit == 'd':
            return value / 24
        elif initial_unit == 'd' and final_unit == 'h':
            return value * 24
        elif initial_unit == 'h' and final_unit == 's':
            return value * 3600
        elif initial_unit == 's' and final_unit == 'h':
            return value / 3600
        elif initial_unit == 'h' and final_unit == 'y':
            return value / 8760
        elif initial_unit == 'y' and final_unit == 'h':
            return value * 8760
        elif initial_unit == final_unit:
            return value
        else:
            raise ValueError(f"Invalid unit conversion: {initial_unit} to {final_unit}")



class SemistructuredFinder:
    """Cluster point clouds into semi-structured groups.

    Category: util
    Tags: points, clustering, semistructured, dbscan, kmeans
    Use when: scripts need to group 3D points by their projected 2D layout and query nearby clusters.
    """
    engine = None  # The clustering engine used to generate the clusters
    is_run = False
    projection_dict = {'x': 0, 'y': 1, 'z': 2}
    def __init__(self,
                 points,
                 n_clusters=None,
                 eps=0.1,
                 min_samples=10,
                 projection_axis: str = 'z',
                 **kwargs,
                 ):
        """Initializes the class.
        Args:
            points (np.array): A numpy array of points.
            n_clusters (int): The number of clusters to find. If None, the number of clusters is determined automatically.
            eps (float): The maximum distance between two samples for one to be considered as in the neighborhood of the other.
            min_samples (int): The number of samples (or total weight) in a neighborhood for a point to be considered as a core point.
            projection_axis (str): The axis along which to project the points. The axis is assumed to be the third dimension.
            **kwargs: Additional keyword arguments.
        """

        self.points = points  # A list of points to consider
        # Project the points onto the projection axis
        self.projected_points = []
        self.projection_axis = projection_axis
        for i in range(0, 3):
           if i != self.projection_dict[projection_axis]:
                self.projected_points.append(self.points[:, i])
        self.projected_points = np.array(self.projected_points).T

        self._n_clusters = n_clusters  # The number of clusters to generate
        if self._n_clusters is None:
            logger.info(f"Generating clusters of {len(self.projected_points)} points using the DBSCAN algorithm with eps={eps} and min_samples={min_samples}")
            self.clusters = self.generate_clusters_dbscan(eps=eps, min_samples=min_samples, **kwargs)
        else:
            logger.info(f"Generating clusters of {len(self.projected_points)} points using the KMeans algorithm with n_clusters={n_clusters}")
            self.clusters = self.generate_clusters_kmeans(n_clusters=n_clusters, **kwargs)
        self.is_run = True

    def generate_clusters_dbscan(self, eps, min_samples, **kwargs):
        """Generate point clusters using DBSCAN.

        Category: util
        Tags: points, clustering, dbscan, semistructured
        Use when: scripts need automatic cluster count discovery from projected point coordinates.

        Returns:
            list: clusters containing original 3D points.
        """
        import numpy as np
        from sklearn.cluster import DBSCAN
        from sklearn.preprocessing import StandardScaler
        # Standardize the data

        # Compute DBSCAN
        self.engine: DBSCAN = DBSCAN(eps=eps, min_samples=min_samples, **kwargs)
        self.engine.fit(self.projected_points)
        core_samples_mask = np.zeros_like(self.engine.labels_, dtype=bool)
        core_samples_mask[self.engine.core_sample_indices_] = True
        labels = self.engine.labels_

        # Number of clusters in labels, ignoring noise if present.
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

        # Create a list of clusters
        clusters = []
        for i in range(n_clusters_):
            clusters.append([])

        # Add points to clusters
        for i, label in enumerate(labels):
            if label != -1:
                clusters[label].append(self.points[i])

        return clusters

    def generate_clusters_kmeans(self, n_clusters, **kwargs):
        """Generate point clusters using KMeans.

        Category: util
        Tags: points, clustering, kmeans, semistructured
        Use when: scripts know the expected number of semi-structured point groups.

        Returns:
            list: clusters containing original 3D points.
        """
        from sklearn.cluster import KMeans
        self.engine: KMeans = KMeans(n_clusters=self._n_clusters, random_state=0, **kwargs)
        self.engine.fit(self.projected_points)
        labels = self.engine.labels_
        clusters = []
        for i in range(n_clusters):
            clusters.append([])
        for i, label in enumerate(labels):
            clusters[label].append(self.points[i])
        return clusters

    @functools.cached_property
    def n_clusters(self):
        """Return the number of generated clusters.

        Category: util
        Tags: points, clustering, count, metadata
        Use when: scripts need cluster count after DBSCAN or KMeans generation.

        Returns:
            int: number of non-noise clusters.
        """
        return len(self.clusters)

    @functools.cached_property
    def point_idx(self):
        """Return original point indexes grouped by cluster.

        Category: util
        Tags: points, clustering, indexes, metadata
        Use when: scripts need original point ids corresponding to each cluster.

        Returns:
            list: cluster-indexed lists of original point indexes.
        """
        point_idx = []
        for i in range(self.n_clusters):
            point_idx.append([])
        for i, label in enumerate(self.engine.labels_):
            if label != -1:
                point_idx[label].append(i)
        return point_idx

    def get_point_idx_in_cluster(self, cluster_idx):
        """Return original point indexes for one cluster.

        Category: util
        Tags: points, clustering, indexes, lookup
        Use when: scripts need source point ids for a selected cluster.

        Returns:
            list: original point indexes in the cluster.
        """
        return self.point_idx[cluster_idx]

    def get_closest_cluster_from_point(self, point: np.array):
        """Return the cluster whose projected center is closest to a point.

        Category: util
        Tags: points, clustering, nearest, lookup
        Use when: scripts need the nearest semi-structured group for a 3D query point.

        Returns:
            list: points in the nearest cluster.
        """
        dist = []
        # Compute the projected point
        projected_point = []
        for i in range(0, 3):
            if i != self.projection_dict[self.projection_axis]:
                projected_point.append(point[i])
        projected_point = np.array(projected_point)
        for cluster_center in self.projected_cluster_centers:
            dist.append(np.linalg.norm(projected_point - cluster_center))
        return self.clusters[np.argmin(dist)]

    def get_closest_cluster_from_xy(self, x: float, y: float):
        """Return the nearest cluster for x,y coordinates.

        Category: util
        Tags: points, clustering, nearest, xy
        Use when: scripts need the nearest semi-structured group from plan-view coordinates.

        Returns:
            list: points in the nearest cluster.
        """
        return self.get_closest_cluster_from_point(np.array([x, y, 0]))

    def get_closest_point_ids_from_point(self, point: np.array):
        """Return point indexes for the nearest cluster using a KDTree.

        Category: util
        Tags: points, clustering, kdtree, nearest, indexes
        Use when: scripts need fast nearest-cluster lookup and original point ids.

        Returns:
            list: original point indexes in the nearest cluster.
        """
        import numpy as np
        from scipy.spatial import KDTree
        projected_point = []
        for i in range(0, 3):
            if i != self.projection_dict[self.projection_axis]:
                projected_point.append(point[i])
        projected_point = np.array(projected_point)
        dist, idx = self.projected_cluster_centers_kdtree.query(projected_point)
        return self.point_idx[idx]

    def get_closest_point_ids_from_xy(self, x: float, y: float):
        """Return point indexes for the nearest cluster from x,y coordinates.

        Category: util
        Tags: points, clustering, nearest, xy, indexes
        Use when: scripts need original point ids for the nearest plan-view cluster.

        Returns:
            list: original point indexes in the nearest cluster.
        """
        return self.get_closest_point_ids_from_point(np.array([x, y, 0]))

    @functools.cached_property
    def projected_cluster_centers(self):
        """Return cluster centers in projected coordinate space.

        Category: util
        Tags: points, clustering, centers, projection
        Use when: scripts need plan-view or projected cluster centers for nearest lookup.

        Returns:
            list: projected cluster center coordinates.
        """

        centers = []
        for cluster in self.clusters:
            projected_points = []
            for cluster_point in cluster:
                projected_points.append([])
                for i in range(0, 3):
                    if i != self.projection_dict[self.projection_axis]:
                        projected_points[-1].append(cluster_point[i])
            projected_points = np.array(projected_points)
            centers.append(np.mean(projected_points, axis=0))
        return centers

    @functools.cached_property
    def projected_cluster_centers_kdtree(self) -> scipy.spatial.KDTree:
        """Return a KDTree over projected cluster centers.

        Category: util
        Tags: points, clustering, kdtree, centers
        Use when: scripts need fast nearest-center lookup.

        Returns:
            scipy.spatial.KDTree: tree built from projected cluster centers.
        """
        return scipy.spatial.KDTree(self.projected_cluster_centers)



    @functools.cached_property
    def cluster_centers(self):
        """Return cluster centers in full 3D coordinate space.

        Category: util
        Tags: points, clustering, centers, geometry
        Use when: scripts need representative 3D locations for each cluster.

        Returns:
            list: mean 3D coordinates for each cluster.
        """
        centers = []
        for cluster in self.clusters:
            centers.append(np.mean(cluster, axis=0))
        return centers





