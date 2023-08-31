from pathlib import Path

import pandas as pd
import numpy as np

from pydelling.estimators import BaseEstimator
from shapely.geometry import Point, Polygon
from typing import Union
from pathlib import Path
import logging
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


class PolygonZoneEstimator(BaseEstimator):
    """This class reads some polygon zone data and allows to classify a give point into one of the zones."""
    def __init__(self, zones_dict: dict[str, Union[str, Path]]):
        """
        Initializes the PolygonZoneEstimator class.
        Args:
            zones_dict: A dictionary with the name of the zone as key and the path to the polygon file as value.
        """
        super().__init__(file_path=None, zones_dict=zones_dict)
        # User the data keys alphabetically sorted
        self.data = {k: self.data[k] for k in sorted(self.data.keys())}
        self.zone_to_ids = {zone: i for i, zone in enumerate(self.data.keys())}
        self.ids_to_zone = {i: zone for i, zone in enumerate(self.data.keys())}
        logger.info(f"Initialized PolygonZoneEstimator with {len(self.data)} zones.")

    def read_data(self, file_path, zones_dict: dict[str, Union[str, Path]] = None):
        """Reads the data from the polygon files."""
        if zones_dict is None:
            logger.error("No valid {zone: polygon_file} dictionary was provided.")
            raise ValueError("No valid {zone: polygon_file} dictionary was provided.")
        # Read the data from the polygon files
        temp_data = {}
        for zone, polygon_file in zones_dict.items():
            if isinstance(polygon_file, str):
                temp_data[zone] = pd.read_csv(polygon_file)
                temp_data[zone].columns = ['x', 'y']
            elif isinstance(polygon_file, np.ndarray) or isinstance(polygon_file, list):
                temp_data[zone] = pd.DataFrame(polygon_file, columns=['x', 'y'])
            elif isinstance(polygon_file, Path):
                temp_data[zone] = pd.read_csv(polygon_file)
                temp_data[zone].columns = ['x', 'y']
            elif isinstance(polygon_file, pd.DataFrame):
                temp_data[zone] = polygon_file
            else:
                raise ValueError(f"Invalid zones_dict type: {type(polygon_file)}")
        return temp_data

    def process_data(self):
        """Processes the self.data variable."""
        # Convert the data to sympy polygons
        for zone, data in self.data.items():
            self.data[zone] = Polygon(data.values)

    def smooth_data(self, window_size=3, sigma=1):
        pass

    def plot_data(self, filename=None, *args, **kwargs):
        """PLots all the polygons"""
        import matplotlib.pyplot as plt
        for zone, data in self.data.items():
            data: Polygon
            vertices = data.exterior.coords.xy
            x = vertices[0]
            y = vertices[1]
            plt.plot(x, y, label=zone)
        plt.legend()
        if filename is not None:
            plt.savefig(filename)
        else:
            plt.show()

    def plot_data_plotly(self, filename=None) -> go.Figure:
        """Plots all the polygons using Plotly"""
        fig = go.Figure()
        from plotly.colors import qualitative
        idx = 0
        for zone, data in self.data.items():
            vertices = data.exterior.coords.xy
            x = vertices[0]
            y = vertices[1]
            x = [float(i) for i in x]
            y = [float(i) for i in y]
            x.append(x[0])
            y.append(y[0])
            # Generate a colorwheel
            color = qualitative.Plotly[idx]
            fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name=zone, line_color=color, showlegend=True, opacity=0.8))
            fig.add_trace(go.Scatter(x=x, y=y, fill='toself', fillcolor=color, opacity=0.2, line_color=color, showlegend=False))
            idx += 1

        if filename is not None:
            fig.write_image(filename)
        else:
            fig.show()

        return fig

    def point_in_zone(self, x, y):
        """Returns the zone in which the point (x, y) is located."""
        point = Point(x, y)
        for zone, polygon in self.data.items():
            polygon: Polygon
            if polygon.contains(point):
                return zone
        return None

    def point_in_zone_id(self, x, y):
        """Returns the zone id in which the point (x, y) is located."""
        zone = self.point_in_zone(x, y)
        if zone is None:
            biggest_zone_id = max(self.zone_to_ids.values())
            return biggest_zone_id + 1
        return self.zone_to_ids[zone]

    def predict(self, **kwargs):
        pass

    @property
    def zone_names(self):
        return list(self.original_data.keys())