"""Base interfaces and helpers for file-based readers.


"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
import pydelling.utils.sub_fish_module as subfish


class BaseReader:
    """Provide the common interface for pydelling reader classes.

    Category: reader
    Tags: reader, file, data, csv, coordinates
    Usage: scripts need the base contract shared by concrete pydelling file readers.
    """

    data: np.ndarray  # Hint of self.data array
    info: dict
    raw_data: None

    def __init__(self, filename=None,
                 header=False,
                 read_data=True,
                 info=None,
                 data=None,
                 **kwargs,
                 ):
        """Set up reader metadata and optionally load data from disk.

        Category: reader
        Tags: reader, initialization, file, data
        Usage: constructing a pydelling reader from a file path or from data
            that has already been loaded by another workflow.
        Args:
            filename: Path to the source file. Stored as ``Path(filename)``.
            header: If truthy, ``open_file`` skips one leading line before
                reading data.
            read_data: If ``True``, load from ``filename`` immediately. If
                ``False``, assign ``data`` directly.
            info: Optional metadata retained for compatibility with older reader
                constructors.
            data: Preloaded data used when ``read_data`` is ``False``.
            **kwargs: Extra attributes copied onto the reader instance.
        Raises:
            AssertionError: If ``read_data`` is ``False`` and ``data`` is not
                provided.
        """
        self.filename = Path(filename)
        self.info = {"reader": {}}
        self.data = None
        self.header = header
        self.__dict__.update(kwargs)
        if read_data:
            self.open_file(filename, **kwargs)
        else:
            assert data is not None, "Error: data is None"
            # assert info is not None, "Error: info is None"
            self.data = data
            # self.info = info

    def read_file(self, opened_file):
        """Read data from an already opened file object.

        Category: reader
        Tags: reader, extension-point, file, data
        Usage: implementing a concrete reader subclass that must parse its
            specific file format.
        Args:
            opened_file: Open text file handle positioned at the data payload.
        Side effects:
            Concrete implementations are expected to populate ``self.data`` and
            related reader attributes.
        """
        pass

    def open_file(self, filename, **kwargs):
        """Open a file, optionally skip its header, read data, and build metadata.

        Category: reader
        Tags: reader, file, open, data, metadata
        Usage: a concrete reader should load data from disk using its read_file implementation.

        Returns:
            None: updates reader data and info.
        """
        with open(filename) as opened_file:
            if self.header:
                opened_file.readline()  # For now, skips the header if it has
            self.read_file(opened_file)
        self.build_info()

    def read_header(self, opened_file):
        """Read format-specific header metadata from an open file.

        Category: reader
        Tags: reader, extension-point, header, metadata
        Usage: implementing a reader whose file format has a reusable header
            section separate from the data payload.
        Args:
            opened_file: Open file handle positioned at the header.
        Side effects:
            Concrete implementations may populate ``self.info`` or other
            metadata attributes.
        """
        pass

    def get_data(self) -> np.ndarray:
        """Return data loaded by this reader.

        Category: reader
        Tags: reader, data, numpy, array
        Usage: scripts need the numeric payload from a pydelling reader.

        Returns:
            np.ndarray: loaded reader data.
        """
        return np.array(0)

    def build_info(self):
        """Build metadata describing the loaded reader data.

        Category: reader
        Tags: reader, metadata, info, extension-point
        Usage: a concrete reader has finished parsing and needs to expose
            shape, field, or source metadata through ``self.info``.
        Side effects:
            Replaces ``self.info`` with a metadata dictionary.
        """
        self.info = {}

    def global_coords_to_local(self, x_local_to_global, y_local_to_global):
        """Translate stored x/y coordinates from global to local space.

        Category: reader
        Tags: coordinates, transform, local, global
        Usage: loaded point data needs to be shifted into a model-local
            coordinate reference before interpolation or export.
        Args:
            x_local_to_global: X offset to subtract from the first data column.
            y_local_to_global: Y offset to subtract from the second data column.
        Raises:
            AssertionError: If ``self.data`` does not contain at least two
                coordinate columns.
        Side effects:
            Mutates the first two columns of ``self.data`` in place.
        """
        assert len(self.data.shape) >= 2 and self.data.shape[1] >= 2, "Error in data shape"
        self.data[:, 0] -= x_local_to_global
        self.data[:, 1] -= y_local_to_global

    def local_coords_to_global(self, x_local_to_global, y_local_to_global):
        """Translate stored x/y coordinates from local to global space.

        Category: reader
        Tags: coordinates, transform, local, global
        Usage: loaded point data needs to be shifted back to the global
            coordinate reference for export or comparison.
        Args:
            x_local_to_global: X offset to add to the first data column.
            y_local_to_global: Y offset to add to the second data column.
        Raises:
            AssertionError: If ``self.data`` does not contain at least two
                coordinate columns.
        Side effects:
            Mutates the first two columns of ``self.data`` in place.
        """
        assert len(self.data.shape) >= 2 and self.data.shape[1] >= 2, "Error in data shape"
        self.data[:, 0] += x_local_to_global
        self.data[:, 1] += y_local_to_global

    def dump_to_csv(self, output_file, delimiter=","):
        """Write reader data to a CSV file.

        Category: writer
        Tags: reader, writer, csv, export, data
        Usage: scripts need to export loaded reader data as delimited text.

        Returns:
            None: writes output_file.
        """
        print(f"Starting dump into {output_file}")
        np.savetxt(output_file, self.get_data(), delimiter=delimiter)
        print(f"The data has been properly exported to the {output_file} file")

    def create_postprocess_dict(self):
        """Create a local folder used to store postprocessing artifacts.

        Category: reader
        Tags: postprocess, folder, artifacts
        Usage: reader workflows need a predictable local directory for
            generated post-processing files.
        Side effects:
            Creates ``postprocess`` under the current working directory and
            stores the path in ``self.postprocessing_dict``.
        """
        self.postprocessing_dict = Path().cwd() / "postprocess"
        self.postprocessing_dict.mkdir(exist_ok=True)

    def generate_subfish_data(self, subfish_dict: dict, unit_factor=1/(365 * 24), unit_name='d') -> pd.DataFrame:
        """Generate SUBFISH results as a DataFrame from a parameter dictionary.

        Category: reader
        Tags: subfish, dataframe, transport, calculation
        Usage: scripts need tabular SUBFISH output from pydelling reader utilities.

        Returns:
            pd.DataFrame: time and result columns.
        """
        if not subfish_dict:
            raise AttributeError('Please, provide a suitable subfish dict object')
        tang_sol = subfish.calculate_tang(subfish_dict)
        tang_sol[0] *= unit_factor
        tang_sol_pd = pd.DataFrame({f'Time [{unit_name}]': tang_sol[0],
                                    'Result [M]': tang_sol[1]
                                    }
                                   )
        return tang_sol_pd

    @property
    def values(self):
        """Return the loaded data through the common values property.

        Category: reader
        Tags: reader, values, data, array
        Usage: scripts need reader data through a property-style accessor.

        Returns:
            Any: value returned by get_data.
        """
        return self.get_data() 
