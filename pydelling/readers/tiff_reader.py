"""
Module documentation.


"""

import rasterio

from pydelling.readers import BaseReader
from pydelling.readers.reader_utils import ImageOperations
import numpy as np
import rasterio as rio
import matplotlib.pyplot as plt


class TiffReader(BaseReader, ImageOperations):
    """Read a single-band TIFF raster with rasterio.

    Category: raster reader.
    Tags: tiff, raster, rasterio, image, bounds.
    Use when: an MCP agent needs to load TIFF raster values and spatial bounds
        through pydelling's reader interface.
    """

    def __init__(self, filename):
        """Load TIFF data and initialize the base reader around it.

        Category: raster reader.
        Tags: tiff, rasterio, image, initialization.
        Use when: constructing a TIFF-backed raster reader from a file path.
        Args:
            filename: TIFF file path.
        Side effects:
            Opens the raster, reads band 1 into ``self.data``, stores bounds,
            and displays a Matplotlib preview.
        """
        self.read_file(filename)

        super().__init__(filename,
                         read_data=False,
                         data=self.data,
                         )
        # plot numpy array
        print('here')
        fig, ax = plt.subplots()
        ax.imshow(self.data)
        plt.show()
        # Find bounds

    def read_file(self, filename):
        """Read raster data and bounds from a TIFF file.

        Category: raster reader.
        Tags: tiff, rasterio, bounds, band.
        Use when: loading the raw rasterio dataset and first data band.
        Args:
            filename: TIFF file path.
        Side effects:
            Sets ``raw_data``, ``bounds``, and ``data``.
        """
        self.raw_data = rasterio.open(filename)
        self.bounds = self.raw_data.bounds
        self.data = self.raw_data.read(1)

    def plot_image(self):
        """Display the loaded raster image.

        Category: raster reader.
        Tags: tiff, image, plot, matplotlib.
        Use when: visually inspecting the loaded TIFF data.
        Side effects:
            Calls the rasterio plot method and opens a Matplotlib image figure.
        """
        self.raw_data.plot()
        # plot numpy array
        print('here')
        fig, ax = plt.subplots()
        ax.imshow(self.data)
        plt.show()
