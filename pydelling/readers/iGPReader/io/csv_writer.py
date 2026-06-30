import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydelling.readers.iGPReader.io.igp_reader import iGPReader
from pydelling.readers.iGPReader.utils.geometry_utils import *


class CsvWriter:
    """CSV export mixin for iGP cell centroids and connection geometry.

    Category: iGP export.
    Tags: igp, csv, cells, connections, centroids.
    Use when: to identify the CSV export helpers available on
        iGP reader/writer objects.
    """

    def write_csv_cells(self):
        """Write element centroid coordinates and volumes to CSV.

        Category: iGP export.
        Tags: igp, csv, cells, centroids, volume.
        Use when: exporting a compact table of mesh cell centers and volumes.
        Side effects:
            Writes ``<project_name>_cell.csv`` either in the current directory or
            under the configured output folder.
        """
        if not self.output_folder:
            file_csv = open(f"{self.project_name}_cell.csv", "w")
        else:
            file_csv = open(Path.cwd() / f"output/{self.project_name}_cell.csv", "w")
        file_csv.write("X,Y,Z,V\n")
        for element in self.elements:
            file_csv.write(f"{element.centroid[0]},{element.centroid[1]},{element.centroid[2]},{element.volume}\n")
        file_csv.close()

    def write_csv_connection(self):
        """Write connection centroid coordinates and face areas to CSV.

        Category: iGP export.
        Tags: igp, csv, connections, face-area, centroids.
        Use when: exporting cell-to-cell connection geometry for diagnostics or
            downstream processing.
        Side effects:
            Writes ``<project_name>_connections.csv`` using connection face
            intersections and areas.
        """
        if self.output_folder is None:
            file_csv = open(f"{self.project_name}_connections.csv", "w")
        else:
            file_csv = open(os.path.join(self.output_folder, f"{self.project_name}_connections.csv"), "w")
        file_csv.write("X,Y,Z,A\n")
        for element in self.connections:
            prime_element = element[0]
            for connected_element in element[1]:
                face_id = element[1][connected_element]
                face_obj = self.elements[prime_element].faces[face_id]
                face_nodes = face_obj.coords
                # Compute line-face intersection
                line_points = np.array([self.elements[prime_element].centroid_coords,
                                        self.elements[connected_element].centroid_coords])
                intersection_point = line_plane_intersection(line_points=line_points,
                                                                      plane_points=face_nodes)
                # compute connection centroid and area
                conn_area = face_obj.area
                conn_centroid = face_obj.centroid
                # export_file.write(f"{prime_element + 1} {connected_element + 1} {conn_centroid[0]:1.4e} {conn_centroid[1]:1.4e} {conn_centroid[2]:1.4e} {conn_area:1.4e}\n")
                file_csv.write(f"{intersection_point[0]},{intersection_point[1]},{intersection_point[2]},{conn_area}\n")
        file_csv.close()
