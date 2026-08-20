"""
Module documentation.


"""

from pathlib import Path

import meshio
import numpy as np
import trimesh
import trimesh.proximity as proximity


class Fault:
    """Represent a triangulated fault surface with hydrogeologic properties.

    Category: preprocessing
    Tags: dfn, fault, mesh, trimesh, hydrogeology
    Usage: scripts need fault geometry, distance queries, or fault properties during DFN upscaling.
    """
    local_id = 0
    def __init__(self, filename=None,
                 mesh=None,
                 polygon=None,
                 aperture=None,
                 transmissivity=None,
                 porosity=None,
                 storativity=None,
                 effective_aperture=None,
                 hydraulic_aperture=None,
                 hydraulic_conductivity=None,
                 specific_storage=None,
                 ):

        """Initialize fault geometry and optional hydraulic properties.

        Category: preprocessing
        Tags: dfn, fault, mesh, properties, trimesh
        Usage: scripts need to load a fault surface from disk or wrap an existing mesh object.

        Returns:
            None: stores geometry, local id, and hydraulic properties.
        """
        if filename is not None:
            self.meshio_mesh = meshio.read(filename)
        if mesh is not None:
            self.meshio_mesh: meshio.Mesh = mesh
        if not hasattr(self, "meshio_mesh"):
            raise ValueError("Fault requires filename or mesh")
        triangle_blocks = [block.data for block in self.meshio_mesh.cells if block.type == "triangle"]
        if not triangle_blocks:
            raise ValueError("Fault mesh must contain triangle cells")
        self.trimesh_mesh = trimesh.Trimesh(
            vertices=np.asarray(self.meshio_mesh.points)[:, :3],
            faces=np.concatenate(triangle_blocks),
            process=False,
        )
        self.aperture = aperture
        self.associated_elements = []
        self.transmissivity = transmissivity
        self.porosity = porosity
        self.storativity = storativity
        self.filename = filename
        self.local_id = Fault.local_id
        self.effective_aperture=effective_aperture
        self.hydraulic_aperture = hydraulic_aperture
        self.hydraulic_conductivity = hydraulic_conductivity
        self.specific_storage = specific_storage
        Fault.local_id += 1

    def distance(self, points: np.ndarray, n_max: int = 2500):
        # if len(points) == 0:
            # return np.array([])
        """Compute signed distances from points to the fault surface.

        Category: preprocessing
        Tags: dfn, fault, distance, points, trimesh
        Usage: upscaling needs to identify mesh cells near or intersecting a fault.

        Returns:
            numpy.ndarray: signed distance for each input point.
        """
        points = np.asarray(points, dtype=float)
        if points.ndim == 1:
            if points.shape != (3,):
                raise ValueError("points must have shape (3,) or (n, 3)")
            points = points.reshape(1, 3)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError("points must have shape (3,) or (n, 3)")
        if n_max <= 0:
            raise ValueError("n_max must be positive")
        if len(points) == 0:
            return np.empty(0, dtype=float)
        distances = [
            proximity.signed_distance(self.trimesh_mesh, points[start : start + n_max])
            for start in range(0, len(points), n_max)
        ]
        return np.concatenate(distances)

    def _to_obj(self, global_id=0):
        """Build a Wavefront OBJ string for this fault surface.

        Category: writer
        Tags: dfn, fault, obj, export, mesh
        Usage: scripts need fault geometry as OBJ text before writing or combining surfaces.

        Returns:
            str: OBJ vertex and face records.
        """
        str_obj = ""
        for i, f in enumerate(self.meshio_mesh.points):
            str_obj += f"v {f[0]} {f[1]} {f[2]}\n"

        for i, f in enumerate(self.trimesh_mesh.faces):
            str_obj += "f "
            for j in range(3):
                str_obj += str(f[j] + global_id) + " "
            str_obj += "\n"
        return str_obj

    def to_obj(self, filename=None, global_id=1):
        """Export or return this fault surface as Wavefront OBJ.

        Category: writer
        Tags: dfn, fault, obj, export, geometry
        Usage: scripts need a visual-debug geometry file or OBJ string for a fault.

        Returns:
            str: OBJ text for the fault surface.
        """
        str_obj = self._to_obj(global_id=global_id)
        if filename is not None:
            with open(filename, 'w') as f:
                f.write(str_obj)
        return str_obj


    @property
    def points(self):
        """Return fault mesh vertex coordinates.

        Category: preprocessing
        Tags: dfn, fault, points, mesh, geometry
        Usage: scripts need raw fault vertices for geometry processing or export.

        Returns:
            numpy.ndarray: mesh point coordinates.
        """
        return self.meshio_mesh.points

    @property
    def cells(self):
        """Return fault mesh cell connectivity.

        Category: preprocessing
        Tags: dfn, fault, cells, mesh, connectivity
        Usage: scripts need triangle indices for fault geometry processing.

        Returns:
            numpy.ndarray: first mesh cell block connectivity.
        """
        return np.asarray(self.trimesh_mesh.faces)

    @property
    def num_points(self):
        """Return the number of fault mesh vertices.

        Category: preprocessing
        Tags: dfn, fault, points, count
        Usage: scripts need fault mesh size metadata.

        Returns:
            int: number of mesh points.
        """
        return self.meshio_mesh.points.shape[0]

    @property
    def num_cells(self):
        """Return the number of fault mesh cells.

        Category: preprocessing
        Tags: dfn, fault, cells, count
        Usage: scripts need fault surface triangle count metadata.

        Returns:
            int: number of cells in the first mesh cell block.
        """
        return len(self.trimesh_mesh.faces)

    @property
    def centroid(self):
        """Return the fault surface centroid.

        Category: preprocessing
        Tags: dfn, fault, centroid, geometry
        Usage: scripts need a representative fault location.

        Returns:
            numpy.ndarray: centroid coordinates.
        """
        return self.trimesh_mesh.centroid

    @property
    def size(self):
        """Return a characteristic size based on fault area.

        Category: preprocessing
        Tags: dfn, fault, size, area
        Usage: scripts need a scalar fault length scale for reporting or heuristics.

        Returns:
            float: square root of fault surface area.
        """
        return np.sqrt(self.trimesh_mesh.area)

    @property
    def normal_vector(self):
        """Return the average fault face normal vector.

        Category: preprocessing
        Tags: dfn, fault, normal, orientation
        Usage: scripts need the dominant orientation of a triangulated fault.

        Returns:
            numpy.ndarray: mean face-normal vector.
        """
        return np.mean(self.trimesh_mesh.face_normals, axis=0)

    def get_json(self):
        """Build a JSON-serializable fault metadata dictionary.

        Category: writer
        Tags: dfn, fault, json, serialize, properties
        Usage: scripts need to persist fault hydraulic properties and source filename.

        Returns:
            dict: serializable fault metadata.
        """
        self.filename: Path
        save_dict = {
            "aperture": self.aperture,
            "transmissivity": self.transmissivity,
            "porosity": self.porosity,
            "storativity": self.storativity,
            "effective_aperture": self.effective_aperture,
            "hydraulic_aperture": self.hydraulic_aperture,
            "hydraulic_conductivity": self.hydraulic_conductivity,
            "specific_storage": self.specific_storage,
            "filename": str(self.filename),
        }
        return save_dict

    @property
    def area(self):
        """Return the triangulated fault surface area.

        Category: preprocessing
        Tags: dfn, fault, area, geometry
        Usage: scripts need fault area for reporting, filtering, or upscaling calculations.

        Returns:
            float: fault surface area.
        """
        return self.trimesh_mesh.area

    def __str__(self):
        return f"Fault {self.local_id}"


