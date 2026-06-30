"""
Class that contains functions to read a rasterized file in .asc format


"""

import logging

import numpy as np
from typing import Tuple, List, Union

from .base_reader import BaseReader
from skimage import measure
from scipy.spatial import ConvexHull
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class RasterFileReader(BaseReader):
    """Read, transform, sample, and export raster ASCII grid data.

    Category: reader
    Tags: raster, asc, grid, coordinates, interpolation
    Usage: scripts need raster values, coordinate grids, contours, or ASC/CSV exports.
    """
    def __init__(self,
                 filename=None,
                 header=False,
                 read_data=True,
                 **kwargs,):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            header (Any): Description.
            read_data (Any): Description.
            **kwargs (Any): Description.
        """
        super().__init__(filename=filename, header=header, read_data=read_data, **kwargs)

    def open_file(self, filename, n_header=6):
        """Open an ASC raster file and load its header and grid data.

        Category: reader
        Tags: raster, asc, open, header, grid
        Usage: scripts need to initialize RasterFileReader from an ASCII raster path.

        Returns:
            None: populates reader metadata and data arrays.
        """
        with open(filename, 'r') as opened_file:
            if self.header:
                opened_file.readline()  # For now, skips the header if it has
            self.read_file(opened_file, n_header)
        self.build_info()

    def read_file(self, opened_file, n_header=6):
        """Read ASC raster header, allocate arrays, and load grid values.

        Category: reader
        Tags: raster, asc, read, header, values
        Usage: an opened ASC file handle should be parsed into raster metadata and data.

        Returns:
            None: updates header metadata, coordinate meshes, and raster data.
        """
        self.read_header(opened_file, n_header=n_header)
        self.build_structure()
        self.read_data(opened_file)
        logger.info(f"Reading ASC raster file from {opened_file}")

    def read_header(self, opened_file, n_header=6):
        """Parse ASC raster header key-value metadata.

        Category: reader
        Tags: raster, asc, header, metadata, cellsize
        Usage: scripts need nrows, ncols, origin, spacing, and NODATA metadata from an ASC file.

        Returns:
            None: stores parsed header values in info["reader"].
        """
        flag_stop = False
        while not flag_stop:
            current_position = opened_file.tell()
            line = opened_file.readline().split()
            if len(line) != 2:
                opened_file.seek(current_position)
                flag_stop = True

            self.info["reader"][line[0]] = float(line[1])
        if 'cellsize' in self.info["reader"].keys():
            self.info["reader"]["dx"] = self.info["reader"]["cellsize"]
            self.info["reader"]["dy"] = self.info["reader"]["cellsize"]


    def read_data(self, opened_file):
        """Read raster grid values from the current file position.

        Category: reader
        Tags: raster, data, grid, values
        Usage: the ASC header has been parsed and the remaining lines contain numeric grid rows.

        Returns:
            None: fills the raster data array.
        """
        for id, line in enumerate(opened_file.readlines()):
            self.data[id] = np.array(line.split(), dtype=np.float32)

    def build_structure(self):
        """Build in-memory raster arrays and coordinate meshes from header metadata.

        Category: reader
        Tags: raster, grid, coordinates, mesh, metadata
        Usage: a raster header has been read and data arrays need consistent dimensions.

        Returns:
            None: initializes data, x_mesh, and y_mesh.
        """
        assert self.info is not {}
        self.xydata_computed = False
        self.data = np.zeros(shape=(int(self.reader_info["nrows"]), int(self.reader_info["ncols"])))

        if 'cellsize' in self.reader_info:
            x_range = np.arange(self.reader_info["xllcorner"], self.reader_info["xllcorner"] + self.reader_info["nrows"] * self.reader_info["cellsize"],
                                self.reader_info["cellsize"])
            y_range = np.arange(self.reader_info["yllcorner"], self.reader_info["yllcorner"] + self.reader_info["ncols"] * self.reader_info["cellsize"],
                                self.reader_info["cellsize"])
        else:
            x_range = np.arange(self.reader_info["xllcorner"], self.reader_info["xllcorner"] + self.reader_info["nrows"] * self.reader_info["dx"],
                                self.reader_info["dx"])
            y_range = np.arange(self.reader_info["yllcorner"], self.reader_info["yllcorner"] + self.reader_info["ncols"] * self.reader_info["dy"],
                                self.reader_info["dy"])
        self.x_mesh, self.y_mesh = np.meshgrid(x_range, y_range)
        self.y_mesh = np.flipud(self.y_mesh)  # To fit into the .asc format criteria

    def build_info(self):
        """Store basic reader metadata for this raster file.

        Category: reader
        Tags: raster, metadata, filename
        Usage: scripts need the source filename available in reader_info.

        Returns:
            None: updates info["reader"].
        """
        self.info["reader"]["filename"] = self.filename

    def add_z_info(self, z_coord):
        """Attach a fixed z coordinate to this raster layer.

        Category: reader
        Tags: raster, z, layer, coordinates
        Usage: exporting a 2D raster as x, y, z, value samples.

        Returns:
            None: stores z_coord on the reader.
        """
        self.z_coord = z_coord

    def get_data(self) -> np.ndarray:
        """Return raster data as coordinates plus values.

        Category: reader
        Tags: raster, data, coordinates, xyz, xy
        Usage: scripts need flattened raster samples for interpolation, export, or analysis.

        Returns:
            np.ndarray: columns of x, y, value or x, y, z, value.
        """
        # self.rebuild_x_y()
        if hasattr(self, "z_coord"):
            return self.get_xyz_data()
        else:
            return self.get_xy_data()

    def rebuild_x_y(self):
        """Rebuild coordinate meshes after raster spacing or origin changes.

        Category: reader
        Tags: raster, coordinates, mesh, rebuild
        Usage: downsampling, flipping, or metadata changes alter raster grid coordinates.

        Returns:
            None: updates x_mesh and y_mesh.
        """
        if 'cellsize' in self.info['reader']:
            x_range = np.arange(self.info['reader']["xllcorner"],
                                self.info['reader']["xllcorner"] + self.info['reader']["nrows"] * self.info['reader']["cellsize"],
                                self.info['reader']["cellsize"])
            y_range = np.arange(self.info['reader']["yllcorner"],
                                self.info['reader']["yllcorner"] + self.info['reader']["ncols"] * self.info['reader']["cellsize"],
                                self.info['reader']["cellsize"])
        else:
            x_range = np.arange(self.info['reader']["xllcorner"],
                                self.info['reader']["xllcorner"] + self.info['reader']["nrows"] * self.info['reader']["dx"],
                                self.info['reader']["dx"])
            y_range = np.arange(self.info['reader']["yllcorner"],
                                self.info['reader']["yllcorner"] + self.info['reader']["ncols"] * self.info['reader']["dy"],
                                self.info['reader']["dy"])
        self.x_mesh, self.y_mesh = np.meshgrid(x_range, y_range)
        self.y_mesh = np.flipud(self.y_mesh)  # To fit into the .asc format criteria


    def get_xy_data(self) -> np.ndarray:
        """Flatten raster cells into x, y, value rows.

        Category: reader
        Tags: raster, xy, flatten, coordinates, values
        Usage: exporting a 2D raster grid to point samples.

        Returns:
            np.ndarray: array with x, y, value columns.
        """
        ndata = int(self.info["reader"]["nrows"] * self.info["reader"]["ncols"])
        self.xydata = np.zeros(shape=(ndata, 3))
        rows_mesh_flatten = np.fliplr(self.x_mesh).T.flatten()
        cols_mesh_flatten = np.flipud(self.y_mesh).T.flatten()
        for id, data in enumerate(self.data.flatten()):
            self.xydata[id] = (cols_mesh_flatten[id], rows_mesh_flatten[id], data)
        self.xydata_computed = True
        return self.xydata

    def get_xyz_data(self) -> np.ndarray:
        """Flatten raster cells into x, y, z, value rows.

        Category: reader
        Tags: raster, xyz, flatten, coordinates, values
        Usage: exporting a raster layer at a fixed z coordinate.

        Returns:
            np.ndarray: array with x, y, z, value columns.
        """
        assert hasattr(self, "z_coord"), "The z-coordinate of this raster file is not given"
        ndata = int(self.info["reader"]["nrows"] * self.info["reader"]["ncols"])
        self.flatten_data = np.zeros(shape=(ndata, 4))
        rows_mesh_flatten = np.fliplr(self.x_mesh).T.flatten()
        cols_mesh_flatten = np.flipud(self.y_mesh).T.flatten()
        for id, data in enumerate(self.data.flatten()):
            self.flatten_data[id] = (cols_mesh_flatten[id], rows_mesh_flatten[id], self.z_coord, data)
        self.xydata_computed = True
        return self.flatten_data

    def to_csv(self, output_file, z_coord=None):
        """Write raster point samples to CSV.

        Category: writer
        Tags: raster, csv, export, coordinates, values
        Usage: scripts need x,y,value or x,y,z,value rows from an ASC raster.

        Returns:
            None: writes the CSV file.
        """

        xydata = self.get_xy_data()
        f = open(output_file, "w")
        if z_coord is not None:
            f.write(f"x,y,z,data\n")
        else:
            f.write(f"x,y,data\n")
        for data in xydata:
            if z_coord is not None:
                f.write(f"{data[0]},{data[1]},{z_coord},{data[2]}\n")
            else:
                f.write(f"{data[0]},{data[1]},{data[2]}\n")
        f.close()
        logger.info(f"The raster file points have been exported to the CSV file {output_file}")

    def to_wsv(self, output_file):
        """Write raster point samples as whitespace-separated values.

        Category: writer
        Tags: raster, wsv, export, coordinates, values
        Usage: scripts need plain whitespace-delimited x y value raster samples.

        Returns:
            None: writes the output file.
        """
        print(f"Starting dump into {output_file}")
        if not self.xydata_computed:
            xydata = self.dump_to_xydata()
        else:
            xydata = self.xydata
        f = open(output_file, "w")
        for data in xydata:
            f.write(f"{data[0]} {data[1]} {data[2]}\n")
        f.close()
        print(f"The data has been properly exported to the {output_file} file")

    def to_asc(self, output_file):
        """Write this raster back to ASC format.

        Category: writer
        Tags: raster, asc, export, header, grid
        Usage: scripts need an ASCII grid file after modifying or downsampling raster data.

        Returns:
            None: writes the ASC file.
        """
        logger.info(f"Starting dump into {output_file}")
        with open(output_file, 'w') as file:
            self.write_asc_header(file)
            self.write_asc_data(file)

    def write_asc_header(self, file):
        # assert isinstance(file, type(open)), "is not a correct file"
        # Write info in ASC format
        """Write ASC header metadata to an open file handle.

        Category: writer
        Tags: raster, asc, header, metadata
        Usage: scripts need to emit a valid ASC raster header before grid values.

        Returns:
            None: writes header lines to file.
        """
        file.write(f"ncols {self.info['reader']['ncols']}\n")
        file.write(f"nrows {self.info['reader']['nrows']}\n")
        if 'cellsize' in self.info:
            file.write(f"cellsize {self.info['reader']['cellsize']}\n")
        else:
            file.write(f"dx {self.info['reader']['dx']}\n")
            file.write(f"dy {self.info['reader']['dy']}\n")
        file.write(f"xllcorner {self.info['reader']['xllcorner']}\n")
        file.write(f"yllcorner {self.info['reader']['yllcorner']}\n")
        file.write(f"NODATA_value {self.info['reader']['NODATA_value']}\n")


    def write_asc_data(self, file):
        """Write raster grid values to an open ASC file handle.

        Category: writer
        Tags: raster, asc, data, grid, values
        Usage: scripts need to emit numeric raster rows after an ASC header.

        Returns:
            None: writes raster values to file.
        """
        np.savetxt(file, self.data)

    def downsample_data(self, slice_factor=2):
        """Downsample the raster by a constant row and column stride.

        Category: preprocessing
        Tags: raster, downsample, grid, spacing
        Usage: scripts need a coarser raster and updated grid spacing.

        Returns:
            None: mutates raster data, metadata, and coordinate meshes.
        """
        self.data = self.data[0::slice_factor, 0::slice_factor]
        self.info['reader']["nrows"] = self.data.shape[0]
        self.info['reader']["ncols"] = self.data.shape[1]
        if "cellsize" in self.info["reader"]:
            self.info['reader']["cellsize"] *= slice_factor
        else:
            self.info['reader']["dx"] *= slice_factor
            self.info['reader']["dy"] *= slice_factor
        self.rebuild_x_y()
        logger.info(f"Data has been downsampled by a factor of {slice_factor}")

    def get_value_from_coord(self, x: float, y: float) -> float:
        """Sample the nearest raster value at x and y coordinates.

        Category: reader
        Tags: raster, sample, coordinates, nearest, value
        Usage: scripts need a raster elevation or property value at one coordinate.

        Returns:
            float: nearest raster value.
        """
        # Define auxiliaty variables
        d_raster = self.reader_info["cellsize"]
        origin_x = self.reader_info["xllcorner"]
        origin_y = self.reader_info["yllcorner"]

        ix = int(np.floor((x - origin_x) / (1.001 * d_raster)))  # 1.001 value is used to avoid issues with
        # the floor function
        iy = int(np.floor((y - origin_y) / (1.001 * d_raster)))  # 1.001 value is used to avoid issues with
        # the floor function
        iy = int(self.reader_info["ncols"] - iy - 1)
        return self.data[iy, ix]

        # normalize the image
    def find_enclosing_polygon(self,
                               val,
                               plot_polygons=False,
                               export_polygons=True,
                               export_coordinates=True,
                               ):
        """Find convex polygons enclosing raster cells equal to a value.

        Category: preprocessing
        Tags: raster, polygons, contours, regions, coordinates
        Usage: scripts need polygon outlines for classified raster regions.

        Returns:
            list: polygons in raster coordinates or pixel coordinates.
        """
        import matplotlib.pyplot as plt
        self.data = self.data.astype(np.float32)
        binary_img = self.data.copy()
        binary_img[binary_img != val] = 0
        binary_img[binary_img == val] = 1
        norm_img = np.interp(binary_img, (binary_img.min(), binary_img.max()), (0, 255)).astype(np.uint8)

        labeled_img = measure.label(binary_img, connectivity=2)

        polygons = []

        # get properties of labeled regions
        region_props = measure.regionprops(labeled_img)

        for prop in region_props:
            # get coordinates of the polygon that encloses the region
            polygon = prop.coords
            # Find the convex hull of the polygon
            if len(polygon) > 3:
                hull = ConvexHull(polygon, qhull_options='QJ')
                polygon = polygon[hull.vertices]
                polygons.append(polygon)

        if plot_polygons:
            fig = self._plot_comparison_real_polygons(polygons)
            plt.show()

        if export_coordinates:
            polygon_coords = []
            for polygon in polygons:
                polygon_coords.append([])
                for coord in polygon:
                    polygon_coords[-1].append(self.get_coordinate_from_pixel(coord[1], coord[0]))
            return polygon_coords
        else:
            return polygons

    def _plot_comparison_real_polygons(self,
                                       polygons,
                                       background_data=None,
                                       palette='Oranges_r',
                                       preprocess_func: callable = None,
                                       timestamp: str = None,
                                       show_polygons=True,
                                       ):
        """
        _plot_comparison_real_polygons method.
        
        Args:
            polygons (Any): Description.
            background_data (Any): Description.
            palette (Any): Description.
            preprocess_func (callable): Description.
            timestamp (str): Description.
            show_polygons (Any): Description.
        """
        fig, ax = plt.subplots()
        plt_data = None
        if background_data is None:
            plt_data = self.data.copy()
        else:
            plt_data = background_data.copy()
        if preprocess_func is not None:
            plt_data = preprocess_func(plt_data)
        ax.imshow(plt_data, cmap=palette)
        if show_polygons:
            for polygon in polygons:
                ax.plot(polygon[:, 1], polygon[:, 0], '-r', linewidth=2)
                last_segment = np.array([[polygon[-1, 1], polygon[-1, 0]],
                                         [polygon[0, 1], polygon[0, 0]]])
                ax.plot(last_segment[:, 0], last_segment[:, 1], '-r', linewidth=2)
        if timestamp is not None:
            # Add a timestamp as a title
            ax.set_title(f'Time: {timestamp}')
        # Unite last polygon with first one
        return fig, ax

    def p2c(self, ix, iy):
        """Convert raster pixel indices to x and y coordinates.

        Category: reader
        Tags: raster, pixel, coordinates, conversion
        Usage: scripts need world coordinates for raster pixel indices.

        Returns:
            tuple: x and y coordinates.
        """
        x = self.reader_info["xllcorner"] + ix * self.reader_info["cellsize"]
        y = self.reader_info["yllcorner"] + iy * self.reader_info["cellsize"]
        return x, y

    def get_coordinate_from_pixel(self, ix, iy):
        """Convert raster pixel indices to x and y coordinates.

        Category: reader
        Tags: raster, pixel, coordinates, conversion
        Usage: scripts need coordinates for polygon vertices or raster indices.

        Returns:
            tuple: x and y coordinates.
        """
        x = self.reader_info["xllcorner"] + ix * self.reader_info["cellsize"]
        y = self.reader_info["yllcorner"] + iy * self.reader_info["cellsize"]
        return x, y

    def c2p(self, x, y):
        """Return the raster value for a coordinate lookup.

        Category: reader
        Tags: raster, coordinates, sample, value
        Usage: scripts need the value associated with an x,y coordinate.

        Returns:
            float: nearest raster value.
        """
        return self.get_value_from_coord(x, y)

    def flip_y(self):
        """Shift the raster origin by one grid height along y and rebuild coordinates.

        Category: preprocessing
        Tags: raster, flip, y, origin, coordinates
        Usage: adapting ASC raster orientation to another coordinate convention.

        Returns:
            None: updates y origin and coordinate mesh.
        """
        self.info['reader']["yllcorner"] = self.info['reader']["yllcorner"] + self.info['reader']["cellsize"] * self.info['reader']["nrows"]
        RasterFileReader.rebuild_x_y(self)

    def flip_x(self):
        """Shift the raster origin by one grid width along x and rebuild coordinates.

        Category: preprocessing
        Tags: raster, flip, x, origin, coordinates
        Usage: adapting ASC raster orientation to another coordinate convention.

        Returns:
            None: updates x origin and coordinate mesh.
        """
        self.info['reader']["xllcorner"] = self.info['reader']["xllcorner"] + self.info['reader']["cellsize"] * self.info['reader']["ncols"]
        RasterFileReader.rebuild_x_y(self)

    def get_plot_image(self, ax=None,
                       fig=None,
                       colorbar=True,
                       colorbar_label=None,
                       **kwargs):
        """Draw raster data on a matplotlib axes.

        Category: reader
        Tags: raster, plot, matplotlib, image, colorbar
        Usage: scripts need a reusable axes image for raster visualization.

        Returns:
            Any: matplotlib axes containing the raster image.
        """
        import matplotlib.pyplot as plt
        if ax is None:
            fig, ax = plt.subplots()
        ax.imshow(self.data, **kwargs)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        if colorbar:
            fig.colorbar(ax.get_images()[0], label=colorbar_label)
        return ax

    def plot(self, colorbar=True, colorbar_label=None, **kwargs):
        """Display the raster with matplotlib.

        Category: reader
        Tags: raster, plot, matplotlib, display
        Usage: scripts need an immediate visual inspection of raster values.

        Returns:
            None: shows a matplotlib plot.
        """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        self.get_plot_image(ax=ax,
                            fig=fig,
                            colorbar=colorbar,
                            colorbar_label=colorbar_label,
                            **kwargs)
        plt.show()

    def save_plot(self, output_file, colorbar=None, colorbar_label=None,**kwargs):
        """Save a raster plot image to disk.

        Category: writer
        Tags: raster, plot, image, export, matplotlib
        Usage: scripts need a PNG or other image artifact showing raster values.

        Returns:
            None: writes the plot image.
        """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        self.get_plot_image(ax=ax,
                            fig=fig,
                            colorbar=colorbar,
                            colorbar_label=colorbar_label,
                            **kwargs)
        plt.savefig(output_file)


    @property
    def nx(self) -> int:
        """Return the number of raster columns.

        Category: reader
        Tags: raster, columns, count, nx
        Usage: scripts need the x-direction grid size.

        Returns:
            int: number of columns.
        """
        return int(self.info['reader']["ncols"])

    @property
    def ny(self) -> int:
        """Return the number of raster rows.

        Category: reader
        Tags: raster, rows, count, ny
        Usage: scripts need the y-direction grid size.

        Returns:
            int: number of rows.
        """
        return int(self.info['reader']["nrows"])

    @property
    def nrows(self) -> int:
        """Return the number of raster rows.

        Category: reader
        Tags: raster, rows, count
        Usage: scripts need raster row count metadata.

        Returns:
            int: number of rows.
        """
        return int(self.info['reader']["nrows"])

    @property
    def ncols(self) -> int:
        """Return the number of raster columns.

        Category: reader
        Tags: raster, columns, count
        Usage: scripts need raster column count metadata.

        Returns:
            int: number of columns.
        """
        return int(self.info['reader']["ncols"])

    @property
    def dx(self):
        """Return raster spacing in the x direction.

        Category: reader
        Tags: raster, spacing, dx, cellsize
        Usage: scripts need horizontal grid spacing.

        Returns:
            float: x-direction cell spacing.
        """
        if 'dx' in self.info['reader']:
            return self.info['reader']['dx']
        else:
            return self.info['reader']["cellsize"]

    @property
    def dy(self):
        """Return raster spacing in the y direction.

        Category: reader
        Tags: raster, spacing, dy, cellsize
        Usage: scripts need vertical grid spacing.

        Returns:
            float: y-direction cell spacing.
        """
        if 'dy' in self.info['reader']:
            return self.info['reader']['dy']
        else:
            return self.info['reader']["cellsize"]

    # Read raster file from a .csv file
    @classmethod
    def from_xyz_csv(self, file_name, dims=None,):
        """Build a RasterFileReader from an x,y,value CSV file.

        Category: reader
        Tags: raster, csv, xyz, load, grid
        Usage: scripts need to reconstruct a raster grid from point-sample CSV data.

        Returns:
            RasterFileReader: raster reader initialized from CSV data.
        """
        data = np.loadtxt(file_name, delimiter=",", skiprows=1)
        if dims is None:
            dims = self._guess_raster_dimensions_from_data(data)
        else:
            assert dims[0] * dims[1] == data.shape[0], "The dimensions are not correct"
            dims = (dims[1], dims[0])

        info = {'reader': {}}
        info['reader']["ncols"] = dims[1]
        info['reader']["nrows"] = dims[0]
        info['reader']["xllcorner"] = data[:, 0].min()
        info['reader']["yllcorner"] = data[:, 1].min()
        info['reader']['dx'] = data[1, 0] - data[0, 0]
        info['reader']['dy'] = data[dims[1], 1] - data[0, 1]
        info['reader']['dx'] = info['reader']['dx']
        info['reader']['dy'] = - info['reader']['dy']
        info['reader']["NODATA_value"] = -9999
        return_raster = RasterFileReader(filename=file_name, data=data, info=info, read_data=False)
        return_raster.build_structure()
        return_raster.data = data[:, 2].reshape(dims[0], dims[1])
        return return_raster

    @staticmethod
    def _guess_raster_dimensions_from_data(data: np.ndarray) -> Tuple[int, int]:
        """
        This method guesses the raster dimensions from the data
        Args:
            data: array with the raster data

        Returns:
            Tuple with the number of rows and columns
        """
        if data.shape[0] == data.shape[1]:
            # Square raster
            return data.shape[0], data.shape[1]
        else:
            # Assume dimensions are ordered in x, y, target
            first_x_value = data[0, 0]
            first_y_value = data[0, 1]
            steps_with_same_x = 1
            steps_with_same_y = 1

            for idx in range(1, data.shape[0]):
                if data[idx, 0] == first_x_value:
                    steps_with_same_x += 1
                if data[idx, 1] == first_y_value:
                    steps_with_same_y += 1
            assert steps_with_same_x * steps_with_same_y == data.shape[0], f"Cant guess dimensions from data. Computed dimensions are {steps_with_same_x}x{steps_with_same_y}={steps_with_same_x * steps_with_same_y} and data has {data.shape[0]} elements"
            return steps_with_same_x, steps_with_same_y

    def get_data_from_coordinates(self, x, y) -> float:
        """Return the nearest raster data value at x and y coordinates.

        Category: reader
        Tags: raster, sample, coordinates, nearest, value
        Usage: scripts need to query raster values by real-world coordinates.

        Returns:
            float: nearest raster data value.
        """
        x_idx = np.argmin(np.abs(self.y - y))
        y_idx = np.argmin(np.abs(self.x - x))
        return self.data[self.nrows - x_idx - 1, y_idx]

    @property
    def x(self):
        """Return x coordinates for raster column centers.

        Category: reader
        Tags: raster, x, coordinates, columns
        Usage: scripts need the coordinate vector for raster columns.

        Returns:
            np.ndarray: x coordinate vector.
        """
        return self.info['reader']["xllcorner"] + np.arange(self.nx) * self.dx

    @property
    def y(self):
        """Return y coordinates for raster row centers.

        Category: reader
        Tags: raster, y, coordinates, rows
        Usage: scripts need the coordinate vector for raster rows.

        Returns:
            np.ndarray: y coordinate vector.
        """
        return self.info['reader']["yllcorner"] + np.arange(self.ny) * self.dy

    # Add difference of two raster files
    def __sub__(self, other):
        """
        __sub__ method.
        
        Args:
            other (Any): Description.
        """
        if isinstance(other, RasterFileReader):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data - other.data)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]
            return new_raster
        elif isinstance(other, (int, float)):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data - other)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]

            return new_raster
        else:
            raise ValueError("The other object is not a RasterFileReader or a number")

    # Add sum of two raster files
    def __add__(self, other):
        """
        __add__ method.
        
        Args:
            other (Any): Description.
        """
        if isinstance(other, RasterFileReader):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data + other.data)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]

            return new_raster
        elif isinstance(other, (int, float)):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data + other)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]

            return new_raster
        else:
            raise ValueError("The other object is not a RasterFileReader or a number")

    def __mul__(self, other):
        """
        __mul__ method.
        
        Args:
            other (Any): Description.
        """
        if isinstance(other, (int, float)):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data * other)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]
            return new_raster

        elif isinstance(other, RasterFileReader):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data * other.data)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]

            return new_raster

        else:
            raise ValueError("The other object is not a RasterFileReader or a number")

    def __truediv__(self, other):
        """
        __truediv__ method.
        
        Args:
            other (Any): Description.
        """
        if isinstance(other, (int, float)):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data / other)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]
            return new_raster

        elif isinstance(other, RasterFileReader):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data / other.data)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]

            return new_raster

        else:
            raise ValueError("The other object is not a RasterFileReader or a number")

    def __pow__(self, other):
        """
        __pow__ method.
        
        Args:
            other (Any): Description.
        """
        if isinstance(other, (int, float)):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data ** other)
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]
            return new_raster

        elif isinstance(other, RasterFileReader):
            new_raster = RasterFileReader(filename=self.filename, read_data=False, info=self.info, data=self.data ** other.data)
            new_raster.info = self.info
            for key in self.__dict__.keys():
                if key != "data" and key != "info":
                    new_raster.__dict__[key] = self.__dict__[key]


            return new_raster

        else:
            raise ValueError("The other object is not a RasterFileReader or a number")

    @property
    def reader_info(self):
        """Return parsed ASC raster header metadata.

        Category: reader
        Tags: raster, header, metadata, info
        Usage: scripts need nrows, ncols, origin, spacing, or NODATA metadata.

        Returns:
            dict: raster reader metadata.
        """
        return self.info['reader']
