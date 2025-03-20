import numpy as np

from pydelling.readers import RasterFileReader
from stl import mesh
import logging
from pydelling.utils import create_results_folder

logger = logging.getLogger(__name__)

class ClosedStlGenerator(object):
    """This class generates a closed STL from two regular raster files"""
    def __init__(self, bottom_surface: RasterFileReader,
                 top_surface: RasterFileReader = None,
                 aperture: RasterFileReader = None,
    ):
        # Generate needed data
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
        """This method runs the closed STL generator"""
        logger.info(f'Generating closed STL based on bottom raster file: {self.bottom_surface.filename} and top raster file: {self.top_surface.filename}') 