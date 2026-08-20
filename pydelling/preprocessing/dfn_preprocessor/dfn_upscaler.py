"""
Module documentation.


"""

import logging
import pathlib
from multiprocessing import Pool, cpu_count
from .parallel_helpers import initializer, process_fracture
from typing import TYPE_CHECKING, Union, Any

import dill
import numpy as np
import math
from tqdm import tqdm

import pydelling.preprocessing.mesh_preprocessor.geometry as geometry
import pydelling.preprocessing.mesh_preprocessor.geometry.base_element
# Import needed for type hints in method signatures
if TYPE_CHECKING:
    from pydelling.preprocessing.dfn_preprocessor.fracture import Fracture
    from pydelling.preprocessing.dfn_preprocessor.fault import Fault
    from pydelling.preprocessing.dfn_preprocessor import DfnPreprocessor
from pydelling.preprocessing.mesh_preprocessor import MeshPreprocessor
from pydelling.preprocessing.mesh_preprocessor.array_mesh import ArrayMesh
from pydelling.utils.geometry_utils import compute_polygon_area

logger = logging.getLogger(__name__)




class DfnUpscaler:
    """Upscale DFN fractures and faults onto an unstructured mesh.

    Category: preprocessing
    Tags: dfn, upscaling, mesh, porosity, permeability, storativity
    Usage: scripts need mesh cell properties derived from fracture and fault intersections.
    """
    def __init__(self, dfn,
                 mesh: MeshPreprocessor,
                 parallel=False,
                 save_intersections=False,
                 load_faults:Union[str, pathlib.Path]=None,
                 loading=False,
                 nearest=None,
                 check_nodes=True,
                 ):
        """
        __init__ method.
        
        Args:
            dfn (Any): Description.
            mesh (MeshPreprocessor): Description.
            parallel (Any): Description.
            save_intersections (Any): Description.
            load_faults (Union[str, pathlib.Path]): Description.
            loading (Any): Description.
            nearest (Any): Description.
            check_nodes (Any): Description.
        """
        self.eps = 1E-4
        self.dfn = dfn
        self.mesh: MeshPreprocessor = mesh
        logger.info('The DFN and mesh objects have been set properly')
        self.all_intersected_points = []
        self.save_intersections = save_intersections
        self.load_faults = load_faults

        self.target_num = 15
        self.cur_num = 0
        self.add_to_class('nearest', nearest, default=None)
        self.add_to_class('check_nodes', check_nodes, default=False)

        self.surface_intersections = None
        self.intersection_index = None
        self.upscaling_result = None
        self.default_workers = cpu_count() if parallel is True else int(parallel) if isinstance(parallel, int) and parallel > 0 else 1

    def upscale(
        self,
        *,
        matrix_porosity,
        matrix_intrinsic_permeability,
        matrix_specific_storage=0.0,
        density=997.16,
        dynamic_viscosity=8.9e-4,
        gravity=9.80665,
        chunk_size=50_000,
        workers=None,
        keep_intersections="auto",
        group_contributions=True,
        engine="auto",
        hydraulic_aperture_ratio=1.0,
        combination_mode="volume_weighted",
    ):
        """Upscale object- or array-backed DFNs with a unit-explicit result.

        This is the unit-explicit API. The historical
        :meth:`upscale_mesh_permeability` method is retained for object-backed
        fracture networks and returns hydraulic conductivity despite its name.
        ``engine='auto'`` selects the indexed array engine for bulk work.
        """

        from .surface_upscaler import IntersectionIndex, intersect_surface_with_mesh, upscale_surface_dfn

        if engine not in ("auto", "indexed", "legacy"):
            raise ValueError("engine must be 'auto', 'indexed', or 'legacy'")
        if engine == "legacy":
            if combination_mode != "volume_weighted":
                raise ValueError(
                    "engine='legacy' only supports combination_mode='volume_weighted'"
                )
            return self._upscale_legacy_result(
                matrix_porosity=matrix_porosity,
                matrix_intrinsic_permeability=matrix_intrinsic_permeability,
                matrix_specific_storage=matrix_specific_storage,
                density=density,
                dynamic_viscosity=dynamic_viscosity,
                gravity=gravity,
            )
        workers = self.default_workers if workers is None else int(workers)
        if workers < 1:
            raise ValueError("workers must be at least one")
        array_mesh = self.mesh if isinstance(self.mesh, ArrayMesh) else self.mesh.to_array_mesh()
        def align(values):
            if not isinstance(values, dict):
                return values
            return np.asarray([values[int(cell_id)] for cell_id in array_mesh.cell_ids])
        matrix_porosity = align(matrix_porosity)
        matrix_intrinsic_permeability = align(matrix_intrinsic_permeability)
        matrix_specific_storage = align(matrix_specific_storage)
        if hasattr(self.dfn, "to_surface_dfn"):
            surface = self.dfn.to_surface_dfn(
                density=density,
                dynamic_viscosity=dynamic_viscosity,
                gravity=gravity,
                hydraulic_aperture_ratio=hydraulic_aperture_ratio,
            )
        else:
            raise TypeError("dfn must provide to_surface_dfn()")
        object_backed = bool(getattr(self.dfn, "dfn", [])) or bool(getattr(self.dfn, "faults", []))
        if keep_intersections not in (True, False, "auto"):
            raise ValueError("keep_intersections must be True, False, or 'auto'")
        retain = object_backed if keep_intersections == "auto" else bool(keep_intersections)
        intersections = None
        if retain:
            intersections = intersect_surface_with_mesh(
                surface,
                array_mesh,
                chunk_size=chunk_size,
                workers=workers,
            )
        result = upscale_surface_dfn(
            surface,
            array_mesh,
            matrix_porosity=matrix_porosity,
            matrix_intrinsic_permeability=matrix_intrinsic_permeability,
            matrix_specific_storage=matrix_specific_storage,
            density=density,
            dynamic_viscosity=dynamic_viscosity,
            gravity=gravity,
            intersections=intersections,
            chunk_size=chunk_size,
            workers=workers,
            group_contributions=group_contributions,
            combination_mode=combination_mode,
        )
        self.surface_intersections = intersections
        self.intersection_index = None if intersections is None else IntersectionIndex(surface, array_mesh, intersections)
        result.metadata["intersection_engine"] = "indexed"
        result.metadata["intersections_retained"] = intersections is not None
        self.upscaling_result = result
        return result

    def prepare_intersections(self, *, engine="auto", chunk_size=50_000, workers=None,
                              density=997.16, dynamic_viscosity=8.9e-4, gravity=9.80665,
                              hydraulic_aperture_ratio=1.0):
        """Prepare intersections explicitly without running property upscaling."""

        if engine not in ("auto", "indexed", "legacy"):
            raise ValueError("engine must be 'auto', 'indexed', or 'legacy'")
        if engine == "legacy":
            if isinstance(self.mesh, ArrayMesh):
                raise TypeError("legacy intersections require MeshPreprocessor")
            self._clear_legacy_associations()
            self._intersect_dfn_with_mesh(parallel=False)
            return None
        from .surface_upscaler import IntersectionIndex, intersect_surface_with_mesh
        array_mesh = self.mesh if isinstance(self.mesh, ArrayMesh) else self.mesh.to_array_mesh()
        surface = self.dfn.to_surface_dfn(
            density=density, dynamic_viscosity=dynamic_viscosity, gravity=gravity,
            hydraulic_aperture_ratio=hydraulic_aperture_ratio,
        )
        table = intersect_surface_with_mesh(
            surface, array_mesh, chunk_size=chunk_size,
            workers=self.default_workers if workers is None else workers,
        )
        self.surface_intersections = table
        self.intersection_index = IntersectionIndex(surface, array_mesh, table)
        return self.intersection_index

    def intersections_for(self, obj):
        """Return retained compact intersections for a fracture, fault, or mesh element."""

        if self.intersection_index is None:
            raise RuntimeError("no compact intersections retained; call prepare_intersections() or upscale(..., keep_intersections=True)")
        if hasattr(obj, "meshio_mesh"):
            return self.intersection_index.for_fault(obj)
        if hasattr(obj, "side_points"):
            return self.intersection_index.for_fracture(obj)
        return self.intersection_index.for_cell(obj)

    def materialize_legacy_intersections(self, *, fractures=None, faults=None, cells=None):
        """Populate legacy dictionaries only for explicitly selected objects."""

        if self.intersection_index is None or isinstance(self.mesh, ArrayMesh):
            raise RuntimeError("materialization requires retained intersections and MeshPreprocessor")
        if fractures is None and faults is None and cells is None:
            raise ValueError("select fractures, faults, or cells to materialize")
        fracture_items = self.dfn.dfn if fractures is None and cells is not None else (fractures or [])
        fault_items = self.dfn.faults if faults is None and cells is not None else (faults or [])
        cell_ids = None if cells is None else {int(getattr(cell, "local_id", cell)) for cell in cells}
        elements = {int(element.local_id): element for element in self.mesh.elements}
        for fracture in fracture_items:
            if not hasattr(fracture, "local_id"):
                fracture = self.dfn.dfn[int(fracture)]
            view = self.intersection_index.for_fracture(fracture)
            aggregate = {}
            for cell_id, area, volume in zip(view.cell_ids, view.areas, view.pore_volumes):
                if cell_ids is not None and int(cell_id) not in cell_ids:
                    continue
                current = aggregate.setdefault(int(cell_id), [0.0, 0.0])
                current[0] += float(area)
                current[1] += float(volume)
            for cell_id, (area, volume) in aggregate.items():
                element = elements[int(cell_id)]
                fracture.intersection_dictionary[int(cell_id)] = area
                element.associated_fractures[int(fracture.local_id)] = {
                    "area": area, "volume": volume, "fracture": int(fracture.local_id)
                }
        for fault in fault_items:
            if not hasattr(fault, "local_id"):
                fault = self.dfn.faults[int(fault)]
            view = self.intersection_index.for_fault(fault)
            aggregate = {}
            for cell_id, area, volume in zip(view.cell_ids, view.areas, view.pore_volumes):
                if cell_ids is not None and int(cell_id) not in cell_ids:
                    continue
                current = aggregate.setdefault(int(cell_id), [0.0, 0.0])
                current[0] += float(area)
                current[1] += float(volume)
            for cell_id, (area, volume) in aggregate.items():
                element = elements[int(cell_id)]
                element.associated_faults[int(fault.local_id)] = {"area": area, "volume": volume}
                if element not in fault.associated_elements:
                    fault.associated_elements.append(element)

    def upscale_hydraulic_conductivity(self, **kwargs):
        """Run compact upscaling and return the combined conductivity tensor in m/s."""

        return self.upscale(**kwargs).hydraulic_conductivity

    def upscale_intrinsic_permeability(self, **kwargs):
        """Run compact upscaling and return the combined permeability tensor in m²."""

        return self.upscale(**kwargs).intrinsic_permeability



    def _intersect_dfn_with_mesh(self, parallel=False):
        """
        Runs the DfnUpscaler with optional parallel processing.
        
        Args:
            parallel (Any): Description.
        """
        logger.info('Upscaling the DFN to the mesh')
        self.mesh.find_intersection_stats = {
            'intersection_points': {},
            'total_intersections': 0
        }
        self.all_intersected_points = []

        if parallel:
            logger.info('Computing intersections in parallel')
            num_workers = cpu_count()  # Use the number of CPU cores available
            with Pool(processes=num_workers, initializer=initializer, initargs=(self.mesh, self.eps)) as pool:
                # Use tqdm to monitor progress
                results = list(tqdm(pool.imap(process_fracture, self.dfn), total=len(self.dfn), desc='Intersecting fractures with mesh'))
        else:
            logger.info('Computing intersections serially')
            results = []
            for fracture in tqdm(self.dfn, desc='Intersecting fractures with mesh', total=len(self.dfn)):
                result = self.find_intersection_points_between_fracture_and_mesh(fracture)
                results.append(result)

        # Aggregate results
        for data in results:
            fracture_id = data['fracture_id']
            fracture = self.dfn[fracture_id]
            
            # Update intersection_dictionary
            fracture.intersection_dictionary.update(data['intersection_areas'])
            
            # Update associated fractures in mesh elements
            for element_id, assoc_data in data['associated_elements'].items():
                element = self.mesh.elements[element_id]
                element.associated_fractures[fracture_id] = assoc_data
                
                # Update intersection statistics
                n_intersections = len(data['intersections']) if data['intersections'] else 0
                if n_intersections not in self.mesh.find_intersection_stats['intersection_points']:
                    self.mesh.find_intersection_stats['intersection_points'][n_intersections] = 0
                self.mesh.find_intersection_stats['intersection_points'][n_intersections] += 1
                self.mesh.find_intersection_stats['total_intersections'] += n_intersections
            
            # Save intersections if required
            if self.save_intersections:
                self.all_intersected_points.append(data['intersections'])

        # Proceed with fault cell assignments
        if not self.load_faults:
            self.find_fault_cells(save_fault_cells=False, nearest=self.nearest, check_nodes=self.check_nodes)
        else:
            logger.info(f'Loading fault assignment information from {self.load_faults}')
            with open(self.load_faults, 'rb') as f:
                fault_info = dill.load(f)
                for element in self.mesh.elements:
                    element.associated_faults = fault_info.get(element.local_id, {})

        # Save intersections to CSV if required
        if self.save_intersections:
            import csv
            with open('intersections.csv', 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['x', 'y', 'z', 'value'])
                local_id = 0
                for intersection_group in self.all_intersected_points:
                    for intersection in intersection_group:
                        for point in intersection:
                            writer.writerow([point.x, point.y, point.z, local_id])
                    local_id += 1

    def find_intersection_points_between_fracture_and_mesh(self, fracture: 'Fracture'):
        """Compute one fracture's intersections with nearby mesh elements.

        Category: preprocessing
        Tags: dfn, fracture, mesh, intersection, area
        Usage: scripts need per-cell fracture intersection areas and associated mesh elements.

        Returns:
            dict: fracture id, intersection points, areas, and associated element metadata.
        """
        
        intersection_data = {
            'fracture_id': fracture.local_id,
            'intersections': [],  # List of intersection points
            'intersection_areas': {},  # element_id: intersection_area
            'associated_elements': {}  # element_id: {details}
        }
        
        kd_tree_filtered_elements = self.mesh.get_closest_mesh_elements(fracture.centroid, distance=fracture.size)
        
        for element in kd_tree_filtered_elements:
            absolute_distance = np.abs(fracture.distance_to_point(element.centroid))
            characteristic_length = np.power(element.volume, 1 / 3)
            if absolute_distance > 1.25 * characteristic_length:
                continue  # Filter out elements too far away
            
            intersection_points = element.intersect_with_fracture(fracture)
            
            if intersection_points:
                if intersection_data['intersections'] is not None:
                    intersection_data['intersections'].append(intersection_points)
            
            intersection_area = np.abs(compute_polygon_area(intersection_points))
            intersection_data['intersection_areas'][element.local_id] = intersection_area
            
            if intersection_points:
                intersection_data['associated_elements'][element.local_id] = {
                    'area': intersection_area,
                    'volume': intersection_area * fracture.aperture,
                    'fracture': fracture.local_id,
                }
        
        return intersection_data

    def find_fault_cells(self, save_fault_cells=True,
                         nearest=None,
                         check_nodes=False,
                         ):
        """Associate mesh elements with nearby fault surfaces.

        Category: preprocessing
        Tags: dfn, faults, mesh, cells, distance
        Usage: scripts need fault-affected cells before upscaling porosity, storativity, or permeability.

        Returns:
            None: updates element associated_faults and optionally writes fault_cells.pkl.
        """
        logger.info('Finding fault cells')
        fault_cells = {}
        for fault in tqdm(self.dfn.faults, desc='Finding distances to faults'):
            fault: Fault
            # Re-running association must be idempotent.
            fault.associated_elements = []
            # Iterate over each triangle individually and find close mesh elements
            triangle_centers = fault.trimesh_mesh.triangles_center
            triangle_areas = fault.trimesh_mesh.area_faces
            characteristic_distance = fault.effective_aperture if fault.effective_aperture is not None else fault.aperture
            logger.info(f'Processing fault {fault.local_id} containing {len(triangle_centers)} triangles')
            close_triangles = []
            for triangle_center in triangle_centers:
                if not nearest:
                    kd_tree_filtered_elements = self.mesh.get_closest_mesh_elements(triangle_center, distance=characteristic_distance)
                    if len(kd_tree_filtered_elements) == 0:
                        continue
                else:
                    nearest: int
                    assert type(nearest) == int, 'nearest must be an integer'
                    kd_tree_filtered_elements = self.mesh.get_closest_n_mesh_elements(triangle_center, n=nearest)
                close_triangles.append(kd_tree_filtered_elements)
            close_triangles = [item for sublist in close_triangles for item in sublist]
            # Filter out duplicates
            temp_dict = {triangle.local_id: triangle for triangle in close_triangles}
            close_triangles = list(temp_dict.values())

            kd_tree_centroids = np.array([elem.centroid for elem in close_triangles])
            # Add element nodes


            logger.info(f'Found {len(kd_tree_centroids)} close elements, computing distances to mesh.')
            distances = fault.distance(kd_tree_centroids)

            for element, distance in zip(close_triangles, distances):
                distance = np.abs(distance)
                if not nearest:
                    if distance < fault.aperture / 2:
                        element.associated_faults[fault.local_id] = {
                            'distance': distance,
                        }
                        fault.associated_elements.append(element)

                else:
                    element.associated_faults[fault.local_id] = {
                        'distance': distance if distance > self.eps else self.eps,
                    }
                    fault.associated_elements.append(element)

            # Check node distances
            if check_nodes:
                logger.info('Checking node distances')
                number_of_nodes = []
                all_nodes = []
                for element in close_triangles:
                    element: pydelling.preprocessing.mesh_preprocessor.geometry.base_element
                    nodes = element.coords
                    number_of_nodes.append(len(nodes))
                    all_nodes += [node for node in nodes]
                # all_nodes = np.array(all_nodes).reshape(-1, 3)
                distances = fault.distance(np.array(all_nodes))
                reconstructed_distances = []
                cum_idx = 0
                for n_node in number_of_nodes:
                    reconstructed_distances.append(distances[cum_idx:cum_idx + n_node])
                    cum_idx += n_node

                for element_id, element in enumerate(close_triangles):
                    element: pydelling.preprocessing.mesh_preprocessor.geometry.base_element
                    distances = reconstructed_distances[element_id]
                    for distance in distances:
                        if distance < fault.aperture / 2:
                            element.associated_faults[fault.local_id] = {
                                'distance': distance if distance > self.eps else self.eps,
                            }
                            fault.associated_elements.append(element)
                            break

            fault.associated_elements = list(
                {element.local_id: element for element in fault.associated_elements}.values()
            )

        if save_fault_cells:
            import dill
            for element in self.mesh.elements:
                fault_cells[element.local_id] = element.associated_faults
            with open('fault_cells.pkl', 'wb') as f:
                dill.dump(fault_cells, f)




    def _compute_fracture_volume_in_elements(self):
        # Compute volume of fractures in each element.
        # self.elements.total_fracture_volume = np.zeros([len(elements)])
        for elem in tqdm(self.mesh.elements, desc="Computing fracture volume fractions"):
            elem.total_fracture_volume = 0.0
            for fracture in elem.associated_fractures:
                fracture_dict = elem.associated_fractures[fracture]
                # Attribute of the element: portion of element occupied by fractures.
                elem.total_fracture_volume += fracture_dict['volume']

    def _legacy_upscale_mesh_porosity(self,
                              matrix_porosity=None,
                              intensity_correction_factor=1.0,
                              existing_fractures_fraction=1.0,
                              truncate_to_min_percentile=5,
                              truncate_to_max_percentile=95,
                              truncate=True,
                              ):
        # Compute upscaled porosity for each element.
        """Compute upscaled mesh porosity from fracture volumes and faults.

        Category: preprocessing
        Tags: dfn, upscaling, porosity, mesh, fractures, faults
        Usage: scripts need per-cell porosity values derived from DFN intersections.

        Returns:
            dict: element ids mapped to upscaled porosity values.
        """
        matrix_porosity = 0.0 if matrix_porosity is None else matrix_porosity
        self._compute_fracture_volume_in_elements()
        upscaled_porosity = {}
        for elem in tqdm(self.mesh.elements, desc="Upscaling porosity"):
            element_volume = elem.volume
            local_matrix_porosity = (
                matrix_porosity.get(elem.local_id, 0.0)
                if isinstance(matrix_porosity, dict)
                else np.asarray(matrix_porosity)[elem.local_id]
                if np.asarray(matrix_porosity).ndim
                else float(matrix_porosity)
            )
            upscaled_porosity[elem.local_id] = (elem.total_fracture_volume / element_volume) + local_matrix_porosity * (1 - (elem.total_fracture_volume / element_volume))
            upscaled_porosity[elem.local_id] = np.abs(upscaled_porosity[elem.local_id]) * intensity_correction_factor * (1 / existing_fractures_fraction)

        for fault in self.dfn.faults:
            for element in fault.associated_elements:
                if fault.porosity is not None:
                    current = upscaled_porosity[element.local_id]
                    upscaled_porosity[element.local_id] = current + fault.porosity * (1.0 - current)

        #Post-processing: Truncate values to P5 and P95.
        if truncate:
            resulting_porosity = [upscaled_porosity[local_id] for local_id in upscaled_porosity]
            finite = np.asarray(resulting_porosity, dtype=float)
            finite = finite[np.isfinite(finite)]
            positive = finite[finite > 0]
            minimum_porosity = float(np.percentile(positive, truncate_to_min_percentile)) if len(positive) else 0.0

            # Truncate to max
            maximum_porosity = float(np.percentile(finite, truncate_to_max_percentile)) if len(finite) else 0.0

            for elem in tqdm(self.mesh.elements, desc="Truncating porosity values to P1 and P99"):

                if math.isnan(upscaled_porosity[elem.local_id]):
                    upscaled_porosity[elem.local_id] = minimum_porosity
                elif upscaled_porosity[elem.local_id] > maximum_porosity:
                    upscaled_porosity[elem.local_id] = maximum_porosity
                elif upscaled_porosity[elem.local_id] <= 0.0:
                    upscaled_porosity[elem.local_id] = minimum_porosity
                else:
                    continue

        vtk_porosity = np.zeros(len(self.mesh.elements), dtype=float)
        for local_id in upscaled_porosity:
            vtk_porosity[local_id] = upscaled_porosity[local_id]

        refactored_porosity = self.mesh.refactor_array_by_element_type(vtk_porosity)

        self.mesh.cell_data['upscaled_porosity'] = refactored_porosity
        self.upscaled_porosity = upscaled_porosity

        return upscaled_porosity

    def _legacy_upscale_mesh_storativity(self,
                                 matrix_storativity=None,
                                 truncate_to_min_percentile=5,
                                 truncate_to_max_percentile=95,
                                 truncate=True,
                                 ):

        """Compute upscaled mesh storativity from intersecting fractures and faults.

        Category: preprocessing
        Tags: dfn, upscaling, storativity, mesh, fractures, faults
        Usage: scripts need per-cell storativity values derived from DFN intersections.

        Returns:
            dict: element ids mapped to upscaled storativity values.
        """
        upscaled_storativity = {}

        def local_matrix_value(element_id):
            if matrix_storativity is None:
                return 0.0
            if isinstance(matrix_storativity, dict):
                return float(matrix_storativity[element_id])
            values = np.asarray(matrix_storativity, dtype=float)
            return float(values[element_id]) if values.ndim else float(values)

        for elem in tqdm(self.mesh.elements, desc="Upscaling fractures storativity"):
            matrix_value = local_matrix_value(elem.local_id)
            element_volume = elem.volume
            fracture_fraction = 0.0
            fracture_storage = 0.0
            for frac_name in elem.associated_fractures:
                frac_dict = elem.associated_fractures[frac_name]
                frac = frac_dict['fracture']
                frac_volume_in_element = frac_dict['volume'] / element_volume
                fracture_fraction += frac_volume_in_element
                fracture_storage += self.dfn[frac].storativity * frac_volume_in_element
            fracture_fraction = min(max(fracture_fraction, 0.0), 1.0)
            upscaled_storativity[elem.local_id] = (
                fracture_storage + matrix_value * (1.0 - fracture_fraction)
            )


        for fault in self.dfn.faults:
            for element in fault.associated_elements:
                if fault.storativity is not None:
                    upscaled_storativity[element.local_id] = max(
                        upscaled_storativity[element.local_id], float(fault.storativity)
                    )


        #Post-processing: Truncate values to P5 and P95.
        if truncate:
            resulting_storativity = np.asarray(list(upscaled_storativity.values()), dtype=float)
            finite = resulting_storativity[np.isfinite(resulting_storativity)]
            positive = finite[finite > 0]
            minimum_storativity = (
                float(np.percentile(positive, truncate_to_min_percentile))
                if len(positive)
                else 0.0
            )
            maximum_storativity = (
                float(np.percentile(finite, truncate_to_max_percentile))
                if len(finite)
                else 0.0
            )

            for elem in tqdm(self.mesh.elements, desc="Truncating porosity values to P1 and P99"):
                if math.isnan(upscaled_storativity[elem.local_id]):
                  upscaled_storativity[elem.local_id] = minimum_storativity
                elif upscaled_storativity[elem.local_id] > maximum_storativity:
                    upscaled_storativity[elem.local_id] = maximum_storativity
                elif upscaled_storativity[elem.local_id] <= minimum_storativity:
                    upscaled_storativity[elem.local_id] = minimum_storativity
                else:
                    continue

        vtk_storativity = np.zeros(len(self.mesh.elements), dtype=float)
        for local_id in upscaled_storativity:
            vtk_storativity[local_id] = upscaled_storativity[local_id]

        self.mesh.cell_data['upscaled_storativity'] = self.mesh.refactor_array_by_element_type(vtk_storativity)
        self.upscaled_storativity = upscaled_storativity

        return upscaled_storativity

    def export_fault_distances(self):
        """Attach accumulated fault-distance values as mesh cell data.

        Category: preprocessing
        Tags: dfn, faults, distance, mesh, cell-data
        Usage: scripts need fault distance fields available in VTK or meshio output.

        Returns:
            None: stores distance values in mesh.cell_data and distance.
        """
        distance = {}

        for elem in tqdm(self.mesh.elements, desc="Computing distances"):
            distance[elem.local_id] = 0
            for fault in elem.associated_faults:
                fault_dict = elem.associated_faults[fault]
                distance[elem.local_id] += fault_dict['distance'] if 'distance' in fault_dict else 0

        vtk_distance = np.asarray(self.mesh.elements)
        for local_id in distance:
            vtk_distance[local_id] = distance[local_id]

        self.mesh.cell_data['distance'] =  self.mesh.refactor_array_by_element_type(vtk_distance)
        self.distance = distance

    def export_fracture_property(self, property='area'):
        """Aggregate one fracture intersection property onto mesh cells.

        Category: preprocessing
        Tags: dfn, fractures, property, mesh, cell-data
        Usage: scripts need per-cell totals such as fracture area or volume exported as cell data.

        Returns:
            None: stores the aggregated property in mesh.cell_data.
        """
        property_dict = {}
        for elem in tqdm(self.mesh.elements, desc="Computing fracture properties"):
            property_dict[elem.local_id] = 0
            # print(elem.associated_fractures)
            for fracture in elem.associated_fractures:
                fracture_dict = elem.associated_fractures[fracture]
                property_dict[elem.local_id] += fracture_dict[property]

        vtk_property = np.asarray(self.mesh.elements)
        for local_id in property_dict:
            vtk_property[local_id] = property_dict[local_id]

        self.mesh.cell_data[property] = [vtk_property.tolist()]
        self.property_dict = property_dict

    def _legacy_upscale_mesh_permeability(self,
                                  matrix_permeability=None,
                                  rho=1000,
                                  g=9.8,
                                  mu=8.9e-4,
                                  mode='full_tensor',
                                  truncate_to_min_percentile=5,
                                  truncate_to_max_percentile=95,
                                  truncate=True,
                                  ):

        """Compute upscaled permeability tensors from fractures, faults, and matrix values.

        Category: preprocessing
        Tags: dfn, upscaling, permeability, tensor, mesh, vtk
        Usage: scripts need Kxx, Kyy, Kzz, Kxy, Kxz, and Kyz cell data for a fractured mesh.

        Returns:
            dict: element ids mapped to 3x3 upscaled permeability tensors.
        """
        self._compute_fracture_volume_in_elements()
        if matrix_permeability is None:
            matrix_permeability_tensor = {
                elem.local_id: np.zeros((3, 3), dtype=float) for elem in self.mesh.elements
            }
        elif isinstance(matrix_permeability, dict):
            matrix_permeability_tensor = {}
            for elem in self.mesh.elements:
                value = np.asarray(matrix_permeability[elem.local_id], dtype=float)
                matrix_permeability_tensor[elem.local_id] = self._as_legacy_tensor(value)
        else:
            value = np.asarray(matrix_permeability, dtype=float)
            n_elements = len(self.mesh.elements)
            if value.ndim == 1 and value.shape != (n_elements,):
                raise ValueError("matrix_permeability vector must have one value per element")
            if value.ndim == 3 and value.shape != (n_elements, 3, 3):
                raise ValueError("matrix_permeability tensor field must have shape (n, 3, 3)")
            if value.ndim not in (0, 1, 2, 3):
                raise ValueError("unsupported matrix_permeability shape")
            matrix_permeability_tensor = {}
            for elem in self.mesh.elements:
                current = value[elem.local_id] if value.ndim in (1, 3) else value
                matrix_permeability_tensor[elem.local_id] = self._as_legacy_tensor(current)

        # Check correct size of matrix_permeability.
        # matrix_permeability_tensor = np.zeros(len(self.elements))
        #
        # if len(matrix_permeability) != len(self.elements):
        #     print("Incorrect size for matrix permeability. Size of variable doesn't match number of elements in the mesh.")
        #     break
        # else:
        #     for elem in tqdm(self.elements, desc="Check size of matrix permeability input"):
        #         if len(matrix_permeability[elem]) == 3:
        #             if np.shape(matrix_permeability[elem]) == (3,3):
        #                 print("Matrix Permeability Tensor (3,3) for Anisotropic case.")
        #                 continue
        #             else:
        #                 print("Matrix Permeability Tensor must be an np.array([3,3]) for Anisotropic case.")
        #         elif len(matrix_permeability[elem]) == 1:
        #             print("Matrix Permeability for Isotropic case.")
        #             matrix_permeability_tensor[elem] = np.zeros([3,3])
        #             matrix_permeability_tensor[elem][0,0] = matrix_permeability[elem]
        #             continue
        #         else:
        #             print("Incorrect Matrix Permeability Tensor. Must be an np.array([3,3]) for use in Anisotropic case or a single float/int for use in Isotropic case.")
        #             continue

        # UPSCALED PERMEABILITY
        fracture_hk = {}
        fault_hk = {}
        upscaled_hk = {}

        # For each fracture, compute permeability tensor,
        # and add it to the elements intersected by the fracture.
        for elem in tqdm(self.mesh.elements, desc="Upscaling fractures permeability"):
            element_volume = elem.volume
            element_porosity = elem.total_fracture_volume / elem.volume
            fracture_hk[elem.local_id] = np.zeros([3, 3])
            upscaled_hk[elem.local_id] = np.zeros([3, 3])
            fault_hk[elem.local_id] = np.zeros([3, 3])

            for frac_name in elem.associated_fractures:
                frac_dict = elem.associated_fractures[frac_name]
                frac = frac_dict['fracture']
                # n1 = math.cos(frac.dip * (math.pi / 180)) * math.sin(frac.dip_dir * (math.pi / 180))
                # n2 = math.cos(frac.dip * (math.pi / 180)) * math.cos(frac.dip_dir * (math.pi / 180))
                # n3 = -1 * math.sin(frac.dip * (math.pi / 180))
                n1 = self.dfn[frac].unit_normal_vector[0]
                n2 = self.dfn[frac].unit_normal_vector[1]
                n3 = self.dfn[frac].unit_normal_vector[2]
                #frac.hk = ((frac.aperture ** 2) * rho * g) / (12 * mu)
                self.dfn[frac].hk = self.dfn[frac].transmissivity / self.dfn[frac].aperture
                #self.dfn[frac].hk = (5.932E-8 * (np.log10(self.dfn[frac].size / 2.0)) ** 2) / self.dfn[frac].aperture

                if mode == 'isotropy':
                    # Add fracture permeability, weighted by the area that the fracture occupies in the element.
                    fracture_hk[elem.local_id][0, 0] += self.dfn[frac].hk * (frac_dict['volume'] / element_volume)  # Kxx

                else:  # 'anisotropy' in 'mode':
                    perm_tensor = np.zeros([3, 3])
                    # for i in range(1, 4):
                    #    for j in range(1, 4):
                    # Compute tensor
                    perm_tensor[0, 0] = self.dfn[frac].hk * ((n2 ** 2) + (n3 ** 2))
                    perm_tensor[0, 1] = self.dfn[frac].hk * (-1) * n1 * n2
                    perm_tensor[0, 2] = self.dfn[frac].hk * (-1) * n1 * n3
                    perm_tensor[1, 1] = self.dfn[frac].hk * ((n3 ** 2) + (n1 ** 2))
                    perm_tensor[1, 2] = self.dfn[frac].hk * (-1) * n2 * n3
                    perm_tensor[2, 2] = self.dfn[frac].hk * ((n1 ** 2) + (n2 ** 2))

                    if mode == 'anisotropy_principals':
                        eigen_perm_tensor = np.diag(np.linalg.eig(perm_tensor)[0])
                        perm_tensor = eigen_perm_tensor

                    frac_volume_in_element = frac_dict['volume'] / element_volume
                    # Add fracture permeability, weighted by the area that the fracture occupies in the element.
                    fracture_hk[elem.local_id][0, 0] += (perm_tensor[0, 0] * frac_volume_in_element)
                    fracture_hk[elem.local_id][0, 1] += (perm_tensor[0, 1] * frac_volume_in_element)
                    fracture_hk[elem.local_id][0, 2] += (perm_tensor[0, 2] * frac_volume_in_element)
                    fracture_hk[elem.local_id][1, 0] += (perm_tensor[0, 1] * frac_volume_in_element)
                    fracture_hk[elem.local_id][1, 1] += (perm_tensor[1, 1] * frac_volume_in_element)
                    fracture_hk[elem.local_id][1, 2] += (perm_tensor[1, 2] * frac_volume_in_element)
                    fracture_hk[elem.local_id][2, 0] += (perm_tensor[0, 2] * frac_volume_in_element)
                    fracture_hk[elem.local_id][2, 1] += (perm_tensor[1, 2] * frac_volume_in_element)
                    fracture_hk[elem.local_id][2, 2] += (perm_tensor[2, 2] * frac_volume_in_element)

            # Sum permeability contribution from fractures and from matrix.

            upscaled_hk[elem.local_id] = fracture_hk[elem.local_id] + matrix_permeability_tensor[elem.local_id] * (
                    1 - element_porosity)

            if len(elem.associated_faults) > 0:
                for fault_name in elem.associated_faults:
                    fault = self.dfn.faults[fault_name]
                    # n1 = math.cos(frac.dip * (math.pi / 180)) * math.sin(frac.dip_dir * (math.pi / 180))
                    # n2 = math.cos(frac.dip * (math.pi / 180)) * math.cos(frac.dip_dir * (math.pi / 180))
                    # n3 = -1 * math.sin(frac.dip * (math.pi / 180))
                    # n1 = fault.unit_normal_vector[0]
                    # n2 = fault.unit_normal_vector[1]
                    # n3 = fault.unit_normal_vector[2]
                    # frac.hk = ((frac.aperture ** 2) * rho * g) / (12 * mu)
                    effective_aperture = fault.effective_aperture if fault.effective_aperture is not None else fault.aperture
                    fault.hk = fault.transmissivity / effective_aperture

                    if mode == 'isotropy':
                        # Add fault permeability.
                        fault_hk[elem.local_id][0, 0] += fault.hk

                    else:
                        normal = np.asarray(fault.normal_vector, dtype=float)
                        norm = np.linalg.norm(normal)
                        if norm == 0:
                            raise ValueError(f"fault {fault.local_id} has no valid normal")
                        normal /= norm
                        fault_hk[elem.local_id] += fault.hk * (
                            np.eye(3) - np.outer(normal, normal)
                        )

                #
                # else:  # 'anisotropy' in 'mode':
                #     perm_tensor = np.zeros([3, 3])
                #     # for i in range(1, 4):
                #     #    for j in range(1, 4):
                #     # Compute tensor
                #     perm_tensor[0, 0] = fault.hk * ((n2 ** 2) + (n3 ** 2))
                #     perm_tensor[0, 1] = fault.hk * (-1) * n1 * n2
                #     perm_tensor[0, 2] = fault.hk * (-1) * n1 * n3
                #     perm_tensor[1, 1] = fault.hk * ((n3 ** 2) + (n1 ** 2))
                #     perm_tensor[1, 2] = fault.hk * (-1) * n2 * n3
                #     perm_tensor[2, 2] = fault.hk * ((n1 ** 2) + (n2 ** 2))
                #
                #     if 'mode' == 'anisotropy_principals':
                #         eigen_perm_tensor = np.diag(np.linalg.eig(perm_tensor)[0])
                #         perm_tensor = eigen_perm_tensor
                #
                #     # Add fault permeability. Element porosity equals to 1 when intersected by faults.
                #     fault_hk[elem.local_id][0, 0] += perm_tensor[0, 0]
                #     fault_hk[elem.local_id][0, 1] += perm_tensor[0, 1]
                #     fault_hk[elem.local_id][0, 2] += perm_tensor[0, 1]
                #     fault_hk[elem.local_id][1, 0] += perm_tensor[0, 1]
                #     fault_hk[elem.local_id][1, 1] += perm_tensor[1, 1]
                #     fault_hk[elem.local_id][1, 2] += perm_tensor[1, 2]
                #     fault_hk[elem.local_id][2, 0] += perm_tensor[0, 1]
                #     fault_hk[elem.local_id][2, 1] += perm_tensor[1, 2]
                #     fault_hk[elem.local_id][2, 2] += perm_tensor[2, 2]

            # Sum permeability contribution from faults.
            upscaled_hk[elem.local_id] = upscaled_hk[elem.local_id] + fault_hk[elem.local_id]

        #Post-processing: Truncate values in each direction.
        if truncate:
            for i, j in ((0, 0), (1, 1), (2, 2)):
                    resulting_hk = np.asarray([upscaled_hk[local_id][i, j] for local_id in upscaled_hk], dtype=float)
                    finite_hk = resulting_hk[np.isfinite(resulting_hk)]
                    positive_hk = finite_hk[finite_hk > 0]
                    minimum_hk = float(np.percentile(positive_hk, truncate_to_min_percentile)) if len(positive_hk) else 0.0
                    maximum_hk = float(np.percentile(finite_hk, truncate_to_max_percentile)) if len(finite_hk) else 0.0

                    for elem in tqdm(self.mesh.elements, desc="Truncating permeability values"):
                        if math.isnan(upscaled_hk[elem.local_id][i,j]):
                            upscaled_hk[elem.local_id][i,j] = minimum_hk
                        elif upscaled_hk[elem.local_id][i,j] > maximum_hk:
                            upscaled_hk[elem.local_id][i,j] = maximum_hk
                        elif upscaled_hk[elem.local_id][i,j] <= minimum_hk:
                            upscaled_hk[elem.local_id][i,j] = minimum_hk
                        else:
                            continue

        # Export values to VTK
        vtk_kxx = np.zeros(len(self.mesh.elements), dtype=float)
        vtk_kyy = np.zeros(len(self.mesh.elements), dtype=float)
        vtk_kzz = np.zeros(len(self.mesh.elements), dtype=float)
        vtk_kxy = np.zeros(len(self.mesh.elements), dtype=float)
        vtk_kxz = np.zeros(len(self.mesh.elements), dtype=float)
        vtk_kyz = np.zeros(len(self.mesh.elements), dtype=float)
        for local_id in upscaled_hk:
            vtk_kxx[local_id] = upscaled_hk[local_id][0, 0]
            vtk_kyy[local_id] = upscaled_hk[local_id][1, 1]
            vtk_kzz[local_id] = upscaled_hk[local_id][2, 2]
            vtk_kxy[local_id] = upscaled_hk[local_id][0, 1]
            vtk_kxz[local_id] = upscaled_hk[local_id][0, 2]
            vtk_kyz[local_id] = upscaled_hk[local_id][1, 2]

        self.mesh.cell_data['Kxx'] = self.mesh.refactor_array_by_element_type(vtk_kxx)
        self.mesh.cell_data['Kyy'] = self.mesh.refactor_array_by_element_type(vtk_kyy)
        self.mesh.cell_data['Kzz'] = self.mesh.refactor_array_by_element_type(vtk_kzz)
        self.mesh.cell_data['Kxy'] = self.mesh.refactor_array_by_element_type(vtk_kxy)
        self.mesh.cell_data['Kxz'] = self.mesh.refactor_array_by_element_type(vtk_kxz)
        self.mesh.cell_data['Kyz'] = self.mesh.refactor_array_by_element_type(vtk_kyz)

        self.upscaled_permeability = upscaled_hk

        return upscaled_hk

    @staticmethod
    def _as_legacy_tensor(value):
        """Normalize one historical matrix property to a 3x3 tensor."""

        value = np.asarray(value, dtype=float)
        if value.ndim == 0:
            return np.eye(3) * float(value)
        if value.shape != (3, 3):
            raise ValueError("matrix permeability values must be scalar or 3x3 tensors")
        return value.copy()

    def _clear_legacy_associations(self):
        for fracture in getattr(self.dfn, "dfn", []):
            fracture.intersection_dictionary = {}
        for fault in getattr(self.dfn, "faults", []):
            fault.associated_elements = []
        for element in self.mesh.elements:
            element.associated_fractures = {}
            element.associated_faults = {}

    def _upscale_legacy_result(self, *, matrix_porosity, matrix_intrinsic_permeability,
                               matrix_specific_storage, density, dynamic_viscosity, gravity):
        """Build a unified result from the historical object intersection engine."""

        if isinstance(self.mesh, ArrayMesh):
            raise TypeError("engine='legacy' requires MeshPreprocessor")
        from .surface_upscaler import UpscalingResult, _scalar_field, _tensor_field

        self._clear_legacy_associations()
        self._intersect_dfn_with_mesh(parallel=False)
        array_mesh = self.mesh.to_array_mesh(use_cache=False)
        ids = array_mesh.cell_ids
        n = array_mesh.n_cells
        matrix_phi = _scalar_field(matrix_porosity, n, "matrix_porosity")
        matrix_storage = _scalar_field(matrix_specific_storage, n, "matrix_specific_storage")
        matrix_k = _tensor_field(matrix_intrinsic_permeability, n, "matrix_intrinsic_permeability")
        conversion = density * gravity / dynamic_viscosity
        phi_dict = self._legacy_upscale_mesh_porosity(
            matrix_porosity={int(cell_id): matrix_phi[row] for row, cell_id in enumerate(ids)}, truncate=False
        )
        storage_dict = self._legacy_upscale_mesh_storativity(
            matrix_storativity={int(cell_id): matrix_storage[row] for row, cell_id in enumerate(ids)}, truncate=False
        )
        conductivity_dict = self._legacy_upscale_mesh_permeability(
            matrix_permeability={int(cell_id): matrix_k[row] * conversion for row, cell_id in enumerate(ids)},
            rho=density, g=gravity, mu=dynamic_viscosity, truncate=False,
        )
        porosity = np.asarray([phi_dict[int(cell_id)] for cell_id in ids], dtype=float)
        storage = np.asarray([storage_dict[int(cell_id)] for cell_id in ids], dtype=float)
        conductivity = np.asarray([conductivity_dict[int(cell_id)] for cell_id in ids], dtype=float)
        area = np.zeros(n, dtype=float)
        pore_volume = np.zeros(n, dtype=float)
        count = np.zeros(n, dtype=np.int64)
        for row, element in enumerate(self.mesh.elements):
            for association in element.associated_fractures.values():
                area[row] += association["area"]
                pore_volume[row] += association["volume"]
                count[row] += 1
        dfn_phi = pore_volume / array_mesh.volumes
        matrix_K = matrix_k * conversion
        dfn_K = conductivity - matrix_K * (1.0 - dfn_phi)[:, None, None]
        dfn_storage = storage - matrix_storage * (1.0 - dfn_phi)
        result = UpscalingResult(
            mesh=array_mesh,
            matrix_porosity=matrix_phi,
            dfn_porosity=dfn_phi,
            porosity=porosity,
            matrix_specific_storage=matrix_storage,
            dfn_specific_storage=dfn_storage,
            specific_storage=storage,
            matrix_hydraulic_conductivity=matrix_K,
            dfn_hydraulic_conductivity=dfn_K,
            hydraulic_conductivity=conductivity,
            matrix_intrinsic_permeability=matrix_k,
            dfn_intrinsic_permeability=dfn_K / conversion,
            intrinsic_permeability=conductivity / conversion,
            fracture_area=area,
            fracture_pore_volume=pore_volume,
            fracture_element_count=count,
            metadata={
                "density_kg_m3": density,
                "dynamic_viscosity_pa_s": dynamic_viscosity,
                "gravity_m_s2": gravity,
                "intersection_engine": "legacy",
                "intersections_retained": True,
            },
        )
        self.upscaling_result = result
        return result

    @staticmethod
    def _safe_percentile_clip(values, low, high, *, positive=False):
        result = np.asarray(values, dtype=float).copy()
        finite = result[np.isfinite(result)]
        reference = finite[finite > 0] if positive else finite
        if not len(reference):
            result[~np.isfinite(result)] = 0.0
            return result
        lower = float(np.percentile(reference, low))
        upper = float(np.percentile(finite, high))
        result[~np.isfinite(result)] = lower
        return np.clip(result, lower, upper)

    def _store_scalar_legacy_field(self, name, cell_ids, values):
        if isinstance(self.mesh, ArrayMesh):
            self.mesh.cell_data[name] = np.asarray(values, dtype=float)
            return
        maximum = max((int(value) for value in cell_ids), default=-1)
        storage = np.zeros(maximum + 1, dtype=float)
        storage[np.asarray(cell_ids, dtype=np.int64)] = values
        self.mesh.cell_data[name] = self.mesh.refactor_array_by_element_type(storage)

    def upscale_mesh_porosity(self, matrix_porosity=None, intensity_correction_factor=1.0,
                              existing_fractures_fraction=1.0, truncate_to_min_percentile=5,
                              truncate_to_max_percentile=95, truncate=True, *, engine="auto",
                              workers=1, chunk_size=50_000):
        if engine == "legacy":
            return self._legacy_upscale_mesh_porosity(
                matrix_porosity=matrix_porosity,
                intensity_correction_factor=intensity_correction_factor,
                existing_fractures_fraction=existing_fractures_fraction,
                truncate_to_min_percentile=truncate_to_min_percentile,
                truncate_to_max_percentile=truncate_to_max_percentile,
                truncate=truncate,
            )
        matrix_porosity = 0.0 if matrix_porosity is None else matrix_porosity
        result = self.upscale(
            matrix_porosity=matrix_porosity, matrix_intrinsic_permeability=0.0,
            matrix_specific_storage=0.0, engine=engine, workers=workers, chunk_size=chunk_size,
        )
        values = result.porosity * float(intensity_correction_factor) / float(existing_fractures_fraction)
        if truncate:
            values = self._safe_percentile_clip(
                values, truncate_to_min_percentile, truncate_to_max_percentile, positive=True
            )
        output = {int(cell_id): float(values[row]) for row, cell_id in enumerate(result.mesh.cell_ids)}
        self._store_scalar_legacy_field("upscaled_porosity", result.mesh.cell_ids, values)
        self.upscaled_porosity = output
        return output

    def upscale_mesh_storativity(self, matrix_storativity=None, truncate_to_min_percentile=5,
                                 truncate_to_max_percentile=95, truncate=True, *, engine="auto",
                                 workers=1, chunk_size=50_000):
        if engine == "legacy":
            return self._legacy_upscale_mesh_storativity(
                matrix_storativity=matrix_storativity,
                truncate_to_min_percentile=truncate_to_min_percentile,
                truncate_to_max_percentile=truncate_to_max_percentile,
                truncate=truncate,
            )
        matrix_storativity = 0.0 if matrix_storativity is None else matrix_storativity
        result = self.upscale(
            matrix_porosity=0.0, matrix_intrinsic_permeability=0.0,
            matrix_specific_storage=matrix_storativity, engine=engine,
            workers=workers, chunk_size=chunk_size,
        )
        values = result.specific_storage
        if truncate:
            values = self._safe_percentile_clip(
                values, truncate_to_min_percentile, truncate_to_max_percentile, positive=True
            )
        output = {int(cell_id): float(values[row]) for row, cell_id in enumerate(result.mesh.cell_ids)}
        self._store_scalar_legacy_field("upscaled_storativity", result.mesh.cell_ids, values)
        self.upscaled_storativity = output
        return output

    def upscale_mesh_permeability(self, matrix_permeability=None, rho=1000, g=9.8, mu=8.9e-4,
                                  mode="full_tensor", truncate_to_min_percentile=5,
                                  truncate_to_max_percentile=95, truncate=True, *, engine="auto",
                                  workers=1, chunk_size=50_000):
        """Historical wrapper returning hydraulic conductivity despite its name."""

        if engine == "legacy":
            return self._legacy_upscale_mesh_permeability(
                matrix_permeability=matrix_permeability, rho=rho, g=g, mu=mu, mode=mode,
                truncate_to_min_percentile=truncate_to_min_percentile,
                truncate_to_max_percentile=truncate_to_max_percentile, truncate=truncate,
            )
        matrix_conductivity = 0.0 if matrix_permeability is None else matrix_permeability
        conversion = float(rho) * float(g) / float(mu)
        if isinstance(matrix_conductivity, dict):
            intrinsic = {
                key: np.asarray(value, dtype=float) / conversion
                for key, value in matrix_conductivity.items()
            }
        else:
            intrinsic = np.asarray(matrix_conductivity, dtype=float) / conversion
        result = self.upscale(
            matrix_porosity=0.0,
            matrix_intrinsic_permeability=intrinsic,
            density=rho, dynamic_viscosity=mu, gravity=g, engine=engine,
            workers=workers, chunk_size=chunk_size,
        )
        values = result.hydraulic_conductivity.copy()
        if mode == "isotropy":
            isotropic = np.trace(values, axis1=1, axis2=2) / 3.0
            values[:] = 0.0
            values[:, range(3), range(3)] = isotropic[:, None]
        elif mode == "anisotropy_principals":
            eigenvalues = np.linalg.eigvalsh(values)
            values[:] = 0.0
            values[:, range(3), range(3)] = eigenvalues
        elif mode not in ("full_tensor", "anisotropy"):
            raise ValueError("mode must be full_tensor, anisotropy, anisotropy_principals, or isotropy")
        if truncate:
            for i in range(3):
                values[:, i, i] = self._safe_percentile_clip(
                    values[:, i, i], truncate_to_min_percentile, truncate_to_max_percentile, positive=True
                )
        output = {int(cell_id): values[row].copy() for row, cell_id in enumerate(result.mesh.cell_ids)}
        maximum = max(map(int, result.mesh.cell_ids))
        for label, i, j in (("Kxx",0,0),("Kyy",1,1),("Kzz",2,2),("Kxy",0,1),("Kxz",0,2),("Kyz",1,2)):
            if isinstance(self.mesh, ArrayMesh):
                self.mesh.cell_data[label] = values[:, i, j].copy()
            else:
                storage = np.zeros(maximum + 1, dtype=float)
                storage[result.mesh.cell_ids] = values[:, i, j]
                self.mesh.cell_data[label] = self.mesh.refactor_array_by_element_type(storage)
        self.upscaled_permeability = output
        return output

    def to_vtk(self, filename):
        """Export the mesh and any upscaled cell variables to VTK.

        Category: writer
        Tags: dfn, upscaling, vtk, mesh, export
        Usage: scripts need a VTK visualization file containing upscaled DFN properties.

        Returns:
            None: writes the VTK file.
        """
        self.mesh.to_vtk(filename)

    def porosity_to_csv(self, filename='./porosity.csv'):
        """Export upscaled porosity values with element centroids to CSV.

        Category: writer
        Tags: dfn, porosity, csv, centroids, export
        Usage: scripts need tabular x,y,z,porosity values for analysis or reporting.

        Returns:
            None: writes the CSV file.
        """
        import csv
        logger.info(f"Exporting porosity to {filename}")
        with open(filename, 'w') as csvfile:
            writer = csv.writer(csvfile)
            for element_id in self.upscaled_porosity:
                centroid = self.mesh.elements[element_id].centroid
                porosity = self.upscaled_porosity[element_id]
                writer.writerow([centroid[0], centroid[1], centroid[2], porosity])

    def plot_porosity_histogram(self, filename='upscaled_porosity_histogram.png'):
        """Build a histogram of upscaled porosity values.

        Category: preprocessing
        Tags: dfn, porosity, histogram, plot, statistics
        Usage: scripts need to inspect the distribution of upscaled porosity.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting upscaled porosity histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([self.upscaled_porosity[element_id] for element_id in self.upscaled_porosity], bins=100)
        return fig, ax

    def plot_hkx_histogram(self, filename='upscaled_hkx_histogram.png'):
        """Build a histogram of upscaled Kxx permeability values.

        Category: preprocessing
        Tags: dfn, permeability, histogram, Kxx, plot
        Usage: scripts need to inspect the distribution of upscaled x-direction permeability.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting upscaled hkx histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([self.upscaled_permeability[element_id][0, 0] for element_id in self.upscaled_permeability], bins=100)
        return fig, ax

    def plot_storativity_histogram(self, filename='upscaled_storativity_histogram.png'):
        """Build a histogram of upscaled storativity values.

        Category: preprocessing
        Tags: dfn, storativity, histogram, plot, statistics
        Usage: scripts need to inspect the distribution of upscaled storativity.

        Returns:
            tuple: matplotlib figure and axes.
        """
        logger.info(f'Plotting upscaled storativity histogram to {filename}')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plt.hist([self.upscaled_storativity[element_id] for element_id in self.upscaled_storativity], bins=100)
        return fig, ax

    def export_intersection_stats(self, filename='intersection_stats.txt'):
        # Export the run_stats dictionary to file
        """Export mesh fracture-intersection statistics to JSON.

        Category: writer
        Tags: dfn, intersection, stats, json, diagnostics
        Usage: scripts need diagnostics after DFN-mesh intersection.

        Returns:
            None: writes run_stats.json.
        """
        assert self.mesh.is_intersected, 'The mesh has not been intersected yet.'
        import json
        with open('run_stats.json', 'w') as fp:
            json.dump(self.mesh.find_intersection_stats, fp)

    def save(self, filename='upscaled_model.json'):
        """Serialize this upscaler object with jsonpickle.

        Category: writer
        Tags: dfn, upscaler, save, serialize, jsonpickle
        Usage: scripts need to persist the full upscaling object state.

        Returns:
            None: writes the serialized file.
        """
        logger.info(f'Saving a copy of the class to {filename}')
        # Create saving dictionary
        saving_dict = {}
        saving_dict['mesh'] = self.mesh.get_json()
        import jsonpickle
        with open(filename, 'w') as f:
            jsonpickle.encode(self, f)


    def to_json(self, filename='upscaler.json'):
        """Write mesh and DFN state to a JSON upscaler file.

        Category: writer
        Tags: dfn, upscaler, json, serialize, mesh
        Usage: scripts need a portable JSON snapshot of the upscaling inputs.

        Returns:
            None: writes the JSON file.
        """
        logger.info(f'Saving a copy of the class to {filename}')
        # Create saving dictionary
        saving_dict = {}
        saving_dict['mesh'] = self.mesh.get_json()
        saving_dict['dfn'] = self.dfn.get_json()
        intersected_points = []
        # for point_group in self.all_intersected_points:
        #     intersected_points.append([])
        #     for point in point_group:
        #         intersected_points[-1].append(point.get_json())
        # saving_dict['all_intersected_points'] = intersected_points
        import json
        with open(filename, 'w') as f:
            json.dump(saving_dict, f)

    @classmethod
    def from_json(cls, filename):
        """Load a DfnUpscaler from a JSON upscaler file.

        Category: preprocessing
        Tags: dfn, upscaler, json, load, serialize
        Usage: scripts need to restore mesh and DFN state for continued upscaling work.

        Returns:
            DfnUpscaler: restored upscaler instance.
        """
        logger.info(f'Loading the upscaling class from {filename}')
        import json
        with open(filename, 'rb') as f:
            load_dict = json.load(f)
            mesh = MeshPreprocessor.from_dict(load_dict['mesh'])
            dfn = DfnPreprocessor.from_dict(load_dict['dfn'])
            loaded_class = cls(mesh=mesh, dfn=dfn, loading=True)
            # loaded_class.all_intersected_points = load_dict['all_intersected_points']
            return loaded_class

    def add_to_class(self, key, value, default=None):
        """Set an attribute and log non-default configuration.

        Category: util
        Tags: dfn, upscaler, configuration, attribute
        Usage: scripts or initialization need to attach optional runtime settings.

        Returns:
            None: sets the attribute on this object.
        """
        setattr(self, key, value)
        if value != default:
            logger.info(f'Added {key} = {value} to the class')





        
