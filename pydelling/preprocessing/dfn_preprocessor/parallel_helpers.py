# parallel_helpers.py

import numpy as np
from pydelling.utils.geometry_utils import compute_polygon_area
import logging

# Initialize a logger
logger = logging.getLogger(__name__)

# Global variable for the mesh
global_mesh = None
global_eps = 1e-4  # Default epsilon value

def initializer(mesh, eps):
    """
    Initializer function for each worker process.
    Sets the global mesh and epsilon.
    """
    global global_mesh
    global global_eps
    global_mesh = mesh
    global_eps = eps
    logger.info('Worker process initialized with shared mesh.')

def process_fracture(fracture):
    """
    Processes a single fracture to find intersections with the global mesh.
    
    Parameters:
    - fracture (Fracture): The fracture to process.
    
    Returns:
    - dict: Intersection data for the fracture.
    """
    if global_mesh is None:
        raise ValueError("Global mesh is not initialized.")
    
    intersection_data = {
        'fracture_id': fracture.local_id,
        'intersections': [],  # List of intersection points
        'intersection_areas': {},  # element_id: intersection_area
        'associated_elements': {}  # element_id: {details}
    }
    
    # Get closest mesh elements within the fracture size distance
    kd_tree_filtered_elements = global_mesh.get_closest_mesh_elements(fracture.centroid, distance=fracture.size)
    
    for element in kd_tree_filtered_elements:
        absolute_distance = np.abs(fracture.distance_to_point(element.centroid))
        characteristic_length = np.power(element.volume, 1 / 3)
        if absolute_distance > 1.25 * characteristic_length:
            continue  # Filter out elements too far away
        
        intersection_points = element.intersect_with_fracture(fracture)
        
        if intersection_points:
            if intersection_data['intersections'] is not None:
                intersection_data['intersections'].append(intersection_points)
        
        if intersection_points:
            intersection_area = np.abs(compute_polygon_area(intersection_points))
            intersection_data['intersection_areas'][element.local_id] = intersection_area
            intersection_data['associated_elements'][element.local_id] = {
                'area': intersection_area,
                'volume': intersection_area * fracture.aperture,
                'fracture': fracture.local_id,
            }
    
    return intersection_data
