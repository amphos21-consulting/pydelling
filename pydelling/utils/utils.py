"""
Contains general purpose utility functions


"""
import os
from pathlib import Path

import numpy as np
import yaml

import pydelling.interpolation as interpolation
from pydelling.paraview_processor.filters import base_filter
import pydelling.readers as readers

try:
    from pydelling.paraview_processor.filters import plot_over_line_filter
except:
    from pydelling.paraview_processor.filters import base_filter
import pandas as pd
from box import Box

import logging
from typing import Union

logger = logging.getLogger(__name__)
import streamlit as st

from pydelling.utils.geometry import *
from pydelling.preprocessing.mesh_preprocessor.geometry.hexahedra_element import HexahedraElement

def interpolate_permeability_anisotropic(perm_filename, mesh_filename=None, mesh=None):
    perm = readers.centroid_reader(filename=perm_filename, header=True)
    if mesh is None:
        assert mesh_filename is not None, "A mesh file needs to be given under the mesh_filename tag"
        mesh = readers.centroid_reader(filename=mesh_filename, header=False)
    else:
        mesh = mesh
    interpolator = interpolation.sparse_data_interpolator(interpolation_data=perm.get_data(),
                                          mesh_data=mesh.get_data())
    interpolator.interpolate(method="nearest")
    if mesh is None:
        return interpolator, mesh
    else:
        return interpolator


def interpolate_centroid_to_structured_grid(centroid: np.ndarray,
                                            var: np.ndarray,
                                            automatic=True,
                                            n_x=100,
                                            n_y=100,
                                            origin_x=0.0,
                                            final_x=1.0,
                                            origin_y=0.0,
                                            final_y=1.0) -> np.ndarray:
    """Reads a set of 2D centroid points and interpolates them into a structured grid"""
    # Check that the centroid file is a 2D array
    assert centroid.shape[1] == 2, "The given centroid file is not a 2D array"
    _var = var
    _centroid = centroid
    _dx = abs(final_x - origin_x)/n_x
    _dy = abs(final_y - origin_y) / n_y
    linspace_x = np.linspace(origin_x, final_x, n_x)
    linspace_y = np.linspace(origin_y, final_y, n_y)
    # reshape private variable _var to shape [:, 1]
    if len(var.shape) == 1:
        _var = np.reshape(_var, (var.shape[0], 1))
    grid_x, grid_y = np.meshgrid(linspace_x, linspace_y)


def aperture_from_a_xy_point_old(dataset: base_filter, x_point, y_point, line_interpolator, variable=None, target_value=1.0, threshold=0.45, line_resolution=100):
    """
    This method computes the aperture at a given position in the XY plane.
    Args:
        x_point: X coordinate
        y_point: Y coordinate
        variable: The variable to consider that indicates the aperture
        target_value: Value of the variable when the fracture is open
        threshold: Value of the maximum variation from the target_value |line[variable] - target_value| < threshold is assumed
        line_resolution: Resolution of the line interpolation that is being used
    Returns:
        The value of the aperture at a given point
    """
    point_1 = [x_point, y_point, dataset.z_min]
    point_2 = [x_point, y_point, dataset.z_max]
    line_interpolator.set_points(point_1=point_1, point_2=point_2)
    line_interpolator.set_line_resolution(line_resolution)

    line_interpolation_point_data = line_interpolator.point_data
    dataset_mesh_points = dataset.mesh_points
    if variable:
        # If a target variable is defined,
        # print(abs(line_interpolation_point_data[variable] - target_value))
        line_interpolation = line_interpolation_point_data[abs(line_interpolation_point_data[variable] - target_value) < threshold]
        z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation.index]["z"]
        if len(z_points) > 0:
            # aperture = abs(z_points.max() - z_points.min())
            aperture = z_points.max()
        else:
            aperture = 0.0
        return aperture

    if not variable:
        # Calculate directly the aperture
        z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation_point_data.index]["z"]
        if len(z_points) > 0:
            aperture = abs(z_points.max() - z_points.min())
        else:
            aperture = 0.0
        return aperture

def aperture_from_a_xy_point(dataset: base_filter, x_point, y_point, line_interpolator, variable=None, target_value=1.0, threshold=0.45, line_resolution=100, method='explicit'):
    """
    This method computes the aperture at a given position in the XY plane.
    Args:
        x_point: X coordinate
        y_point: Y coordinate
        variable: The variable to consider that indicates the aperture
        target_value: Value of the variable when the fracture is open
        threshold: Value of the maximum variation from the target_value |line[variable] - target_value| < threshold is assumed
        line_resolution: Resolution of the line interpolation that is being used
        method: Method to use to calculate the aperture. It can be 'explicit' or 'implicit'
    Returns:
        The value of the aperture at a given point
    """
    point_1 = [x_point, y_point, dataset.z_min]
    point_2 = [x_point, y_point, dataset.z_max]
    line_interpolator.set_points(point_1=point_1, point_2=point_2)
    line_interpolator.set_line_resolution(line_resolution)
    line_interpolator_resolution = (dataset.z_max - dataset.z_min) / line_resolution


    line_interpolation_point_data = line_interpolator.point_data
    dataset_mesh_points = dataset.mesh_points
    if variable:
        # If a target variable is defined,
        # print(abs(line_interpolation_point_data[variable] - target_value))
        # line_interpolation = line_interpolation_point_data[abs(line_interpolation_point_data[variable] - target_value) < threshold]
        # z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation.index]["z"]
        if method == 'explicit':
            line_interpolation = line_interpolation_point_data[abs(line_interpolation_point_data[variable] - target_value) < threshold]
            z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation.index]["z"]
            aperture = len(z_points) * line_interpolator_resolution
            return aperture
        elif method == 'implicit':
            eps_field = (line_interpolation_point_data[variable] - line_interpolation_point_data[variable].min())
            eps_field = eps_field / eps_field.max()
            aperture = (eps_field * line_interpolator_resolution).sum()
            return aperture

    if not variable:
        # Calculate directly the aperture
        z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation_point_data.index]["z"]
        if len(z_points) > 0:
            aperture = abs(z_points.max() - z_points.min())
        else:
            aperture = 0.0
        return aperture


def get_root_path() -> Path:
    """Returns path to the root of the project"""
    return Path(__file__).parent


def get_config_path() -> Path:
    """Returns path to the root of the project"""
    return Path(__file__).parent / "config"


def test_data_path() -> Path:
    """Returns path to the root of the project"""
    return Path(__file__).parent.parent / "tests/test_data"

def runtime_path():
    return Path(os.getcwd())


def read_local_config():
    def read_config(config_file: Path = "./config.yaml"):
        """
        Reads the configuration file
        :param config_file:
        :return:
        """
        with open(config_file) as file:
            context = yaml.load(file, Loader=yaml.FullLoader)
        return Box(context, default_box=True)

    _config_file = list(
        Path(os.getcwd()).glob("**/*config.yml") and Path(os.getcwd()).glob("**/*config.yaml") and Path().cwd().glob(
            "*config*.yml") and Path().cwd().glob(
            "*config*.yaml"))
    _config_file = _config_file if _config_file else list(Path(__file__).parent.glob("config.yml"))
    assert len(_config_file) == 1, "Please provide a configuration file that has a '*config.yaml' name structure"
    config = read_config(config_file=_config_file[0])
    return config


def sample_values_from_dict(input_dict: dict, n: int, write_to_file: bool = True, return_generator: bool = False) -> list:
    """
    This method reads a dictionary and generates n samples from them based on the
    following criteria.

    The structure of the dictionary should be as follows:

    name_of_dict:
        material_name_i:
            type: type of the desired distribution
            option_keys: these keys depend on the chosen distribution type
        material_name_i:

    Type of implemented distributions:
        constant[value]: sets a constant value for the variable
        log_normal[mean, std]: generates a log-normal distribution based on the mean, std values
        specified in natural scale.

    Args:
        input_dict: dictionary to extract the samples from.
        n: integer specifying the number of generated samples.
        write_to_file: optional argument that writes a csv file with the generated cases. Defaults to True.
        return_generator: if True, returns the sampled data as a generator.
    Returns:
        A dictionary containing the sampled results
    """
    class BaseDistribution:
        """Base sampler used by ``sample_values_from_dict``.

        Category: utilities.
        Tags: sampling, distribution, sensitivity-analysis.
        Use when: to understand the local sampler contract
            used to generate sensitivity-analysis cases.
        """

        def __init__(self):
            pass
        def run(self) -> float:
            """Generate one sampled value.

            Category: utilities.
            Tags: sampling, distribution, extension-point.
            Use when: implementing a local sampler used by
                ``sample_values_from_dict``.
            Returns:
                float: Sampled value.
            """

    class ConstantDistribution(BaseDistribution):
        """Sampler that always returns one constant value.

        Category: utilities.
        Tags: sampling, constant, sensitivity-analysis.
        Use when: a sensitivity-analysis material should keep the same value in
            every generated case.
        """

        def __init__(self, value):
            """Store the constant sampled value.

            Category: utilities.
            Tags: sampling, constant, initialization.
            Use when: creating a deterministic sampler.
            Args:
                value: Value returned by every call to ``run``.
            """
            super().__init__()
            self.value = value

        def run(self):
            """Return the configured constant value.

            Category: utilities.
            Tags: sampling, constant.
            Use when: generating one deterministic sample.
            Returns:
                Any: The configured value.
            """
            return self.value

    class NormalDistribution(BaseDistribution):
        """Sampler for normal or log-normal random values.

        Category: utilities.
        Tags: sampling, normal, lognormal, sensitivity-analysis.
        Use when: sensitivity-analysis cases need random values from a normal or
            log-normal distribution.
        """

        def __init__(self, mean, std, log=False):
            """Configure the normal or log-normal sampler.

            Category: utilities.
            Tags: sampling, normal, lognormal, initialization.
            Use when: creating a stochastic sampler from mean and standard
                deviation parameters.
            Args:
                mean: Distribution mean.
                std: Distribution standard deviation.
                log: If ``True``, sample from a log-normal distribution.
            """
            super().__init__()
            self.mean = float(mean)
            self.std = float(std)
            self.log = log

        def run(self):
            """Generate one normal or log-normal random value.

            Category: utilities.
            Tags: sampling, normal, lognormal.
            Use when: generating one stochastic sensitivity-analysis value.
            Returns:
                float: Random sample.
            """
            if not self.log:
                return np.random.normal(self.mean, self.std)
            else:
                return np.random.lognormal(self.mean, self.std)

    # Process each material and create sample generators
    generator_dict = {}
    for material in input_dict:
        material_dict = input_dict[material]
        if material_dict['type'] == 'constant':
            generator_dict[material] = ConstantDistribution(value=material_dict['value'])
        elif material_dict['type'] == 'normal':
            generator_dict[material] = NormalDistribution(mean=material_dict['mean'],
                                                          std=material_dict['std'],
                                                          )
        elif material_dict['type'] == 'log-normal' or material_dict['type'] == 'log_normal':
            generator_dict[material] = NormalDistribution(mean=material_dict['mean'],
                                                          std=material_dict['std'],
                                                          log=True,
                                                          )
        elif material_dict['type'] == 'log_normal-two_values':
            y_min_log = np.log(float(material_dict['y_min']))
            y_max_log = np.log(float(material_dict['y_max']))
            mean = (y_min_log + y_max_log) / 2.0
            std = (mean - y_min_log) / 2.0

            generator_dict[material] = NormalDistribution(mean=mean,
                                                          std=std,
                                                          log=True,
                                                          )

    final_list = []
    for sample_id in range(n):
        current_case = {}
        for generator in generator_dict:
            current_case[generator] = generator_dict[generator].run()
        final_list.append(current_case)
    if write_to_file:
        df_test = pd.DataFrame(final_list)
        df_test.to_csv('SA_cases.csv', index=False)
    if return_generator:
        return generator_dict
    return final_list

# Create a cache decorator

# Generate a pyvista component from streamlit
def plot_pyvista(_plot_method,
                 data=None,
                 filename=None,
                 border=True,
                 width=None,
                 height=None,
                 **kwargs):
    plot_method = _plot_method
    import pickle
    import inspect
    import subprocess
    import streamlit as st
    from pathlib import Path
    import textwrap
    import streamlit.components.v1 as components
    if data is not None:
        # Save the data to a temporal file
        with open('temp_data.pkl', 'wb') as file:
            pickle.dump(data, file)
    filename = Path(filename)
    filename = filename.with_suffix('.html')
    filename = str(filename)
    temp_file_path = './temp_method.py'
    temp_data_path = './temp_data.pkl'

    def execute_method_in_file(method):
        # Extract the source code of the method
        source_code = inspect.getsource(method)
        # Add necessary imports to the source code
        full_code = "import pyvista as pv\n"
        full_code += "import pickle\n"
        if data is not None:
            full_code += f"with open('temp_data.pkl', 'rb') as file:\n"
            full_code += "    data = pickle.load(file)\n"
        full_code += textwrap.dedent(source_code)
        # Add a line in the source code idented
        # full_code += "\t"
        if data is None:
            full_code += f"{method.__name__}('{filename}')"
        else:
            full_code += f"{method.__name__}('{filename}', data)"

        # Write the source code to a temporary file
        with open(temp_file_path, 'w') as file:
            file.write(full_code)

        # Execute the temporary file in a subprocess
        execution_result = subprocess.run(["uv", "run", temp_file_path], capture_output=True, text=True)

        # Return the execution result
        return execution_result.stderr, execution_result.returncode

    stderr, return_code = execute_method_in_file(plot_method)
    if not return_code:
        subprocess.run(["rm", temp_file_path])
        if data is not None:
            subprocess.run(["rm", temp_data_path])
        HtmlFile = open(f"{filename}", 'r', encoding='utf-8')
        source_code = HtmlFile.read()
        with st.container(border=border):
            component_dict = dict()
            if width is not None:
                component_dict['width'] = width
            if height is not None:
                component_dict['height'] = height
            components.html(source_code, **component_dict)
    else:
        logger.error(f"An error occurred while executing the method {plot_method.__name__}")
        print(stderr)

def find_intersection_points_with_bounding_box(element: Union[Line, Plane],
                                               min_x: float,
                                               max_x: float,
                                               min_y: float,
                                               max_y: float,
                                               min_z: float,
                                               max_z: float,
                                               ):
    """Finds the intersection points of a line or plane with a bounding box"""
    assert isinstance(element, (Line, Plane)), "Element must be a Line or a Plane"
    # Compute intersection points
    edges = [
        [(min_x, min_y, min_z), (max_x, min_y, min_z)],
        [(min_x, max_y, min_z), (max_x, max_y, min_z)],
        [(min_x, min_y, max_z), (max_x, min_y, max_z)],
        [(min_x, max_y, max_z), (max_x, max_y, max_z)],
        [(min_x, min_y, min_z), (min_x, max_y, min_z)],
        [(max_x, min_y, min_z), (max_x, max_y, min_z)],
        [(min_x, min_y, max_z), (min_x, max_y, max_z)],
        [(max_x, min_y, max_z), (max_x, max_y, max_z)],
        [(min_x, min_y, min_z), (min_x, min_y, max_z)],
        [(max_x, min_y, min_z), (max_x, min_y, max_z)],
        [(min_x, max_y, min_z), (min_x, max_y, max_z)],
        [(max_x, max_y, min_z), (max_x, max_y, max_z)]
    ]
    # Order the points counter-clockwise


    bbox = HexahedraElement(
        node_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        node_coords=[
            [min_x, min_y, min_z],
            [max_x, min_y, min_z],
            [max_x, max_y, min_z],
            [min_x, max_y, min_z],
            [min_x, min_y, max_z],
            [max_x, min_y, max_z],
            [max_x, max_y, max_z],
            [min_x, max_y, max_z]
        ],
    )
    # bbox.plot_normal_vectors()

    intersection_points = []
    for edge in edges:
        intersection = element.intersect(Line(Point(edge[0]), Point(edge[1])))
        if bbox.contains(intersection):
            intersection_points.append(intersection)
    # Order the intersection points counter-clockwise

    def calculate_centroid(points):
        sum_x, sum_y, sum_z = 0, 0, 0
        for point in points:
            sum_x += point[0]
            sum_y += point[1]
            sum_z += point[2]
        n = len(points)
        return (sum_x / n, sum_y / n, sum_z / n)

    # Function to calculate the normal vector of the plane formed by the points
    def normal_vector(points):
        # Assuming all points are coplanar and using the first three points to define the plane
        v1 = np.array(points[1]) - np.array(points[0])
        v2 = np.array(points[2]) - np.array(points[0])
        return np.cross(v1, v2)

    # Function to sort points clockwise
    def sort_points_clockwise(points, centroid, normal):
        if not points:
            # If the list is empty, there's nothing to sort.
            return

        # Define a reference vector for the plane
        ref_vector = np.array(points[0]) - np.array(centroid)
        ref_vector -= np.dot(ref_vector, normal) * normal  # Project onto the plane

        def angle_from_centroid(point):
            v = np.array(point) - np.array(centroid)
            v -= np.dot(v, normal) * normal  # Project v onto the plane
            # Calculate angle using the cross product and dot product
            cross_product = np.cross(ref_vector, v)
            dot_product = np.dot(ref_vector, v)
            angle = np.arctan2(np.linalg.norm(cross_product), dot_product)
            # Determine the direction of the angle based on the sign of the dot product with the normal
            if np.dot(normal, cross_product) < 0:
                angle = 2 * np.pi - angle
            return angle

        # Sort points based on the computed angles
        points.sort(key=angle_from_centroid, reverse=True)  # Use reverse=True for clockwise

    # Example usage, assuming intersection_points, centroid, and normal have been defined:
    if intersection_points:  # Ensure there are points to sort
        centroid = calculate_centroid(intersection_points)
        normal = normal_vector(intersection_points)
        sort_points_clockwise(intersection_points, centroid, normal)
    else:
        print("No intersection points found.")
    return intersection_points


def order_points_clockwise(points):
    """
    Orders a set of points in a clockwise manner
    Args:
        points: list of points to order
    Returns:
        A list of points ordered clockwise
    """
    def calculate_centroid(points):
        sum_x, sum_y, sum_z = 0, 0, 0
        for point in points:
            sum_x += point[0]
            sum_y += point[1]
            sum_z += point[2]
        n = len(points) # n
        
        return (sum_x / n, sum_y / n, sum_z / n)

    # Function to calculate the normal vector of the plane formed by the points
    def normal_vector(points):
        # Assuming all points are coplanar and using the first three points to define the plane
        v1 = np.array(points[1]) - np.array(points[0])
        v2 = np.array(points[2]) - np.array(points[0])
        return np.cross(v1, v2)

    # Function to sort points clockwise
    def sort_points_clockwise(points, centroid, normal):
        if not points:
            # If the list is empty, there's nothing to sort.
            return

        # Define a reference vector for the plane
        ref_vector = np.array(points[0]) - np.array(centroid)
        ref_vector -= np.dot(ref_vector, normal) * normal  # Project onto the plane

        def angle_from_centroid(point):
            v = np.array(point) - np.array(centroid)
            v -= np.dot(v, normal) * normal  # Project v onto the plane
            # Calculate angle using the cross product and dot product
            cross_product = np.cross(ref_vector, v)
            dot_product = np.dot(ref_vector, v)
            angle = np.arctan2(np.linalg.norm(cross_product), dot_product)
            # Determine the direction of the angle based on the sign of the dot product with the normal
            if np.dot(normal, cross_product) < 0:
                angle = 2 * np.pi - angle
            return angle

        # Sort points based on the computed angles
        points.sort(key=angle_from_centroid, reverse=True)  # Use reverse=True for clockwise

    # Example usage, assuming intersection_points, centroid, and normal have been defined:
    centroid = calculate_centroid(points)
    normal = normal_vector(points)
    sort_points_clockwise(points, centroid, normal)
    return points

def compute_area_of_polygon(points):
    """
    This method computes the area of a polygon given a set of points
    Args:
        points: list of points that define the polygon
    Returns:
        The area of the polygon
    """
    # order points
    points = order_points_clockwise(points)
    n = len(points)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    area = abs(area) / 2.0
    return area

