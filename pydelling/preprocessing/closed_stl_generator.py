"""
This class generates a closed STL from two regular raster files


"""

import numpy as np

from pydelling.readers import RasterFileReader
from stl import mesh
import logging
from pydelling.utils import create_results_folder

logger = logging.getLogger(__name__)

class ClosedStlGenerator(object):
    """Generate a closed STL volume from raster top and bottom surfaces.

    Category: preprocessing.
    Tags: stl, raster, surface, aperture, mesh-export.
    Use when: an MCP agent needs to turn regular raster surfaces into a closed
        triangulated STL shell for meshing or visualization.
    """

    def __init__(self, bottom_surface: RasterFileReader,
                 top_surface: RasterFileReader = None,
                 aperture: RasterFileReader = None,
    ):
        # Generate needed data
        """Configure raster surfaces used to build the closed STL.

        Category: preprocessing.
        Tags: stl, raster, top-surface, bottom-surface, aperture.
        Use when: preparing an STL shell from a bottom raster and either a top
            raster or an aperture raster.
        Args:
            bottom_surface: Raster defining the lower surface.
            top_surface: Raster defining the upper surface.
            aperture: Optional raster defining separation between surfaces.
        Raises:
            AssertionError: If no aperture can be derived.
        Side effects:
            Stores the surface rasters and initializes the STL mesh attribute.
        """
        self.bottom_surface = bottom_surface
        if top_surface is not None:
            self.top_surface = top_surface
        if aperture is not None:
            self.aperture = aperture
        else:
            self.aperture = top_surface - bottom_surface
        assert self.aperture is not None, "Aperture is not defined"
        self.stl_file: mesh.Mesh

    def run(self, output_filename: str = 'closed_stl.stl',
            export_faces=True,
            ):
        """Build and export the closed STL mesh.

        Category: preprocessing.
        Tags: stl, raster, triangulation, export.
        Use when: generating the complete STL shell and optional per-side STL
            files from the configured rasters.
        Args:
            output_filename: Name of the combined STL output file.
            export_faces: Whether to also write separate STL files for bottom,
                top, and side faces.
        Side effects:
            Builds ``self.stl_file`` and ``self.faces_stl`` then writes STL
            files through ``export_stl``.
        """
        logger.info(f'Generating closed STL based on bottom raster file: {self.bottom_surface.filename} and top raster file: {self.top_surface.filename}')
        # First, we need to generate the vertices
        vertices = []
        # Now, we need to generate the faces
        faces = []
        # First, we need to generate the faces for the bottom surface
        logger.info('Generating faces for the bottom surface')
        faces_dict = {
            'bottom': [],
            'top': [],
            'west': [],
            'east': [],
            'north': [],
            'south': [],
        }
        for row in range(self.bottom_surface.nrows - 1):
            for col in range(self.bottom_surface.ncols - 1):
                # Generate the face
                # Save the face vertices
                vertex_1 = [self.bottom_surface.x_mesh[row, col], self.bottom_surface.y_mesh[row, col], self.bottom_surface.data[row, col]]
                vertex_2 = [self.bottom_surface.x_mesh[row, col + 1], self.bottom_surface.y_mesh[row, col + 1], self.bottom_surface.data[row, col + 1]]
                vertex_3 = [self.bottom_surface.x_mesh[row + 1, col + 1], self.bottom_surface.y_mesh[row + 1, col + 1], self.bottom_surface.data[row + 1, col + 1]]
                face_vertices = [vertex_1, vertex_2, vertex_3]
                vertices.append(face_vertices)
                faces_dict['bottom'].append(face_vertices)

                # Save the face vertices
                vertex_1 = [self.bottom_surface.x_mesh[row, col], self.bottom_surface.y_mesh[row, col], self.bottom_surface.data[row, col]]
                vertex_2 = [self.bottom_surface.x_mesh[row + 1, col + 1], self.bottom_surface.y_mesh[row + 1, col + 1], self.bottom_surface.data[row + 1, col + 1]]
                vertex_3 = [self.bottom_surface.x_mesh[row + 1, col], self.bottom_surface.y_mesh[row + 1, col], self.bottom_surface.data[row + 1, col]]
                face_vertices = [vertex_1, vertex_2, vertex_3]
                vertices.append(face_vertices)
                faces_dict['bottom'].append(face_vertices)


        # Now, we need to generate the faces for the top surface
        logger.info('Generating faces for the top surface')
        for row in range(self.top_surface.nrows - 1):
            for col in range(self.top_surface.ncols - 1):
                # Generate the face
                # Save the face vertices
                vertex_1 = [self.top_surface.x_mesh[row, col], self.top_surface.y_mesh[row, col], self.top_surface.data[row, col]]
                vertex_2 = [self.top_surface.x_mesh[row, col + 1], self.top_surface.y_mesh[row, col + 1], self.top_surface.data[row, col + 1]]
                vertex_3 = [self.top_surface.x_mesh[row + 1, col + 1], self.top_surface.y_mesh[row + 1, col + 1], self.top_surface.data[row + 1, col + 1]]
                face_vertices = [vertex_1, vertex_2, vertex_3]
                vertices.append(face_vertices)
                faces_dict['top'].append(face_vertices)

                # Save the face vertices
                vertex_1 = [self.top_surface.x_mesh[row, col], self.top_surface.y_mesh[row, col], self.top_surface.data[row, col]]
                vertex_2 = [self.top_surface.x_mesh[row + 1, col + 1], self.top_surface.y_mesh[row + 1, col + 1], self.top_surface.data[row + 1, col + 1]]
                vertex_3 = [self.top_surface.x_mesh[row + 1, col], self.top_surface.y_mesh[row + 1, col], self.top_surface.data[row + 1, col]]
                face_vertices = [vertex_1, vertex_2, vertex_3]
                vertices.append(face_vertices)
                faces_dict['top'].append(face_vertices)

        # Now, we need to generate the four faces that connect the top and bottom surfaces
        # row = 0
        logger.info('Generating faces that connect the top and bottom surfaces')
        for col in range(self.top_surface.ncols - 1):
            # Generate the face
            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[0, col], self.top_surface.y_mesh[0, col], self.top_surface.data[0, col]]
            vertex_2 = [self.top_surface.x_mesh[0, col + 1], self.top_surface.y_mesh[0, col + 1], self.top_surface.data[0, col + 1]]
            vertex_3 = [self.bottom_surface.x_mesh[0, col + 1], self.bottom_surface.y_mesh[0, col + 1], self.bottom_surface.data[0, col + 1]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['north'].append(face_vertices)

            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[0, col], self.top_surface.y_mesh[0, col], self.top_surface.data[0, col]]
            vertex_2 = [self.bottom_surface.x_mesh[0, col + 1], self.bottom_surface.y_mesh[0, col + 1], self.bottom_surface.data[0, col + 1]]
            vertex_3 = [self.bottom_surface.x_mesh[0, col], self.bottom_surface.y_mesh[0, col], self.bottom_surface.data[0, col]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['north'].append(face_vertices)

        # row = nrows - 1
        for col in range(self.top_surface.ncols - 1):
            # Generate the face
            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[-1, col], self.top_surface.y_mesh[-1, col], self.top_surface.data[-1, col]]
            vertex_2 = [self.top_surface.x_mesh[-1, col + 1], self.top_surface.y_mesh[-1, col + 1], self.top_surface.data[-1, col + 1]]
            vertex_3 = [self.bottom_surface.x_mesh[-1, col + 1], self.bottom_surface.y_mesh[-1, col + 1], self.bottom_surface.data[-1, col + 1]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['south'].append(face_vertices)

            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[-1, col], self.top_surface.y_mesh[-1, col], self.top_surface.data[-1, col]]
            vertex_2 = [self.bottom_surface.x_mesh[-1, col + 1], self.bottom_surface.y_mesh[-1, col + 1], self.bottom_surface.data[-1, col + 1]]
            vertex_3 = [self.bottom_surface.x_mesh[-1, col], self.bottom_surface.y_mesh[-1, col], self.bottom_surface.data[-1, col]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['south'].append(face_vertices)

        # col = 0
        for row in range(self.top_surface.nrows - 1):
            # Generate the face
            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[row, 0], self.top_surface.y_mesh[row, 0], self.top_surface.data[row, 0]]
            vertex_2 = [self.top_surface.x_mesh[row + 1, 0], self.top_surface.y_mesh[row + 1, 0], self.top_surface.data[row + 1, 0]]
            vertex_3 = [self.bottom_surface.x_mesh[row + 1, 0], self.bottom_surface.y_mesh[row + 1, 0], self.bottom_surface.data[row + 1, 0]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['west'].append(face_vertices)

            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[row, 0], self.top_surface.y_mesh[row, 0], self.top_surface.data[row, 0]]
            vertex_2 = [self.bottom_surface.x_mesh[row + 1, 0], self.bottom_surface.y_mesh[row + 1, 0], self.bottom_surface.data[row + 1, 0]]
            vertex_3 = [self.bottom_surface.x_mesh[row, 0], self.bottom_surface.y_mesh[row, 0], self.bottom_surface.data[row, 0]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['west'].append(face_vertices)

        # col = ncols - 1
        for row in range(self.top_surface.nrows - 1):
            # Generate the face
            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[row, -1], self.top_surface.y_mesh[row, -1], self.top_surface.data[row, -1]]
            vertex_2 = [self.top_surface.x_mesh[row + 1, -1], self.top_surface.y_mesh[row + 1, -1], self.top_surface.data[row + 1, -1]]
            vertex_3 = [self.bottom_surface.x_mesh[row + 1, -1], self.bottom_surface.y_mesh[row + 1, -1], self.bottom_surface.data[row + 1, -1]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['east'].append(face_vertices)

            # Save the face vertices
            vertex_1 = [self.top_surface.x_mesh[row, -1], self.top_surface.y_mesh[row, -1], self.top_surface.data[row, -1]]
            vertex_2 = [self.bottom_surface.x_mesh[row + 1, -1], self.bottom_surface.y_mesh[row + 1, -1], self.bottom_surface.data[row + 1, -1]]
            vertex_3 = [self.bottom_surface.x_mesh[row, -1], self.bottom_surface.y_mesh[row, -1], self.bottom_surface.data[row, -1]]
            face_vertices = [vertex_1, vertex_2, vertex_3]
            vertices.append(face_vertices)
            faces_dict['east'].append(face_vertices)

        vertices = np.array(vertices)

        # Now we need to generate the mesh
        self.stl_file = mesh.Mesh(np.zeros(vertices.shape[0], dtype=mesh.Mesh.dtype))
        for i, f in enumerate(vertices):
            for j in range(3):
                self.stl_file.vectors[i][j] = f[j]

        # Create STL meshes for the faces
        self.faces_stl = {}
        for face in faces_dict:
            vertices = np.array(faces_dict[face])
            self.faces_stl[face] = mesh.Mesh(np.zeros(vertices.shape[0], dtype=mesh.Mesh.dtype))
            for i, f in enumerate(vertices):
                for j in range(3):
                    self.faces_stl[face].vectors[i][j] = f[j]

        self.export_stl(output_filename=output_filename, faces=export_faces)



    def export_stl(self, output_filename, faces=False):
        """Write the generated STL mesh to a results folder.

        Category: preprocessing.
        Tags: stl, export, results-folder.
        Use when: persisting a generated closed STL and optional individual face
            meshes.
        Args:
            output_filename: Combined STL output filename.
            faces: Whether to write the entries in ``self.faces_stl``.
        Side effects:
            Creates a results folder and writes one or more STL files.
        """
        from pathlib import Path
        results_folder = create_results_folder()
        output_filename = Path(output_filename)
        logger.info(f'Writing mesh to {output_filename}')
        self.stl_file.save(str(results_folder / output_filename))
        if faces:
            for face in self.faces_stl:
                face_filename = Path(f"{output_filename.stem}-{face}.stl")
                logger.info(f'Writing {face} face STL mesh to outputs folder')
                self.faces_stl[face].save(str(results_folder / face_filename))





    def plot_aperture(self):
        """Plot the aperture raster.

        Category: preprocessing.
        Tags: aperture, raster, plot.
        Use when: visually checking the surface separation before or after STL
            generation.
        Side effects:
            Delegates plotting to ``self.aperture.plot``.
        """
        self.aperture.plot(colorbar_label='Aperture')
