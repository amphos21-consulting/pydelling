import rasterio

from pydelling.readers import BaseReader
from pydelling.readers.reader_utils import ImageOperations
import numpy as np
import rasterio as rio
import matplotlib.pyplot as plt


class TiffReader(BaseReader, ImageOperations):
    def __init__(self, filename):
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
        self.raw_data = rasterio.open(filename)
        self.bounds = self.raw_data.bounds
        self.data = self.raw_data.read(1)

    def plot_image(self):
        self.raw_data.plot()
        # plot numpy array
        print('here')
        fig, ax = plt.subplots()
        ax.imshow(self.data)
        plt.show()

