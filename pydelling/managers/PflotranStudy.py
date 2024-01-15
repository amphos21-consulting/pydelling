from .BaseStudy import BaseStudy
import logging
from typing import Union, List, Dict
import numpy as np

logger = logging.getLogger(__name__)


class PflotranStudy(BaseStudy):
    """This class extends the BaseStudy class to manage PFLOTRAN related simulations.
    """
    def __init__(self, input_file: str, *args, **kwargs):
        """This method initializes the class.
        """
        super().__init__(input_file, *args, **kwargs)
        self.regions_to_idx = {}
        self.datasets_to_idx = {}
        self._parse_blocks()

    def _parse_blocks(self):
        """
        Parse the file content and return a list of dictionaries and strings
        representing the structure of the file. Each block starts with a given name and ends with 'END' or '/'.
        Blocks can contain either other blocks (subblocks), data values, or comments.
        """
        # First we will find the blocks and their names
        # Each block starts with the format TAG or TAG tag_name and ends with END or /
        # I want to create a hierarchy of blocks,


    # Try parsing the file content again with the revised function

    def get_regions(self):
        """This method returns the regions of the simulation.
        """
        region_lines = self._find_tags('region')
        regions = []
        for line_idx in region_lines:
            line = self._get_line(line_idx)
            if self._get_parent_tag_name_(line_idx).lower() == 'region':
                regions.append(line.split()[1])
                self.regions_to_idx[line.split()[1]] = line_idx
        return regions

    def get_simulation_time(self, time_unit: str = 'y'):
        """This method returns the output time series of the simulation"""
        time_lines = self._get_line(self._find_tags('FINAL_TIME')[0])
        value = time_lines.split()[1]
        value_unit = time_lines.split()[2]
        return self.convert_time(value=value, initial_unit=value_unit, final_unit=time_unit)

    def get_checkpoint(self):
        """This method returns the checkpoint times of the simulation.
        """
        checkpoint_lines = self._find_tags('CHECKPOINT')
        if len(checkpoint_lines) == 0:
            return None
        checkpoint_line = checkpoint_lines[0]
        checkpoint_block = self._get_block_lines(checkpoint_line)
        for line in checkpoint_block:
            if 'times' in line.lower():
                return line
        return None

    def replace_simulation_time(self, new_time: float, time_unit: str = 'y'):
        """This method replaces the simulation time of the simulation.
        """
        time_lines = self._find_tags('FINAL_TIME')
        new_time = self.convert_time(value=new_time, initial_unit=time_unit, final_unit=time_unit)
        self._replace_line(line_index=time_lines[0], new_line=['FINAL_TIME', str(new_time), time_unit])

    def replace_parameter(self, label: str, new_value: float, inside: float, time_unit: str = 'y'):
        """This method replaces the value of a parameter.
        """
        if inside != 0:
            inside = inside
        else:
            inside = 0

        parameter_lines = self._find_tags(label[0])
        self._replace_line(line_index=parameter_lines[0] + inside, new_line=[label[1], str(new_value)])

    def replace_material_properties(self, new_perm: float, new_porosity: float, new_vertical_anisotropy: float, material_name: str = ''):
        """This method replaces the simulation time of the simulation.
        """
        material_lines = self._find_tags('MATERIAL_PROPERTY ' + material_name)
        self._replace_line(line_index=material_lines[0] + 2, new_line=['POROSITY', str(new_porosity)])
        self._replace_line(line_index=material_lines[0] + 8, new_line=['PERM_HORIZONTAL', str(new_perm)])
        self._replace_line(line_index=material_lines[0] + 9, new_line=['VERTICAL_ANISOTROPY_RATIO', str(new_vertical_anisotropy)])

    def get_region_file(self, region: str) -> Union[str, None]:
        """This method returns the file of the region.
        """
        self.get_regions()
        region_line = self.regions_to_idx[region]
        region_block = self._get_block_lines(region_line)
        for line in region_block:
            if 'file' in line.lower():
                return line.split()[1]
        return None

    def get_datasets(self) -> List[str]:
        """This method returns the datasets of the simulation.
        """
        datasets = []
        for line_idx in self._find_tags('DATASET'):
            line = self._get_line(line_idx)
            if line.split()[0].lower() == 'hdf5_dataset_name':
                continue
            if self._get_parent_tag_name_(line_idx).lower() == 'dataset':
                datasets.append(line.split()[1])
                self.datasets_to_idx[line.split()[1]] = line_idx
        return datasets

    def replace_region_file(self, region: str, new_file: str):
        """This method replaces the file of the region.
        """
        self.get_regions()
        old_file = self.get_region_file(region)
        region_line = self.regions_to_idx[region]
        region_block = self._get_block_lines(region_line)
        region_block_idx = self._get_block_line_idx(region_line)
        logger.info(f"Replacing region {region} file from '{old_file}' to '{new_file}'")
        for line_idx, line in zip(region_block_idx, region_block):
            if 'file' in line.lower():
                self._replace_line(line_index=line_idx, new_line=['FILE', new_file])

    def add_checkpoint(self, times: Union[float, List[float]], time_unit: str = 'y'):
        """This method adds a checkpoint to the simulation.
        """
        logger.info(f"Adding checkpoint at {times} {time_unit}")
        if isinstance(times, float) or isinstance(times, int):
            times = [times]
        times = [self.convert_time(value=time, initial_unit=time_unit, final_unit=time_unit) for time in times]
        times = [str(time) for time in times]
        # Check if the checkpoint tag is already in the input file
        if self.has_tag('CHECKPOINT'):
            checkpoint_line = self._find_tags('CHECKPOINT')[0]
            checkpoint_block = self._get_block_lines(checkpoint_line)
            checkpoint_block_idx = self._get_block_line_idx(checkpoint_line)
            for line_idx, line in zip(checkpoint_block_idx, checkpoint_block):
                if 'times' in line.lower():
                    self._replace_line(line_index=line_idx, new_line=['TIMES', time_unit, *times])
        else:
            # Find simulation block
            simulation_block_idx = self._get_block_line_idx(self._find_tags('SIMULATION')[0])
            # Find the last line of the simulation block
            last_line_idx = simulation_block_idx[-1]
            # Add the checkpoint block
            self._add_line(line_index=last_line_idx, new_line=['CHECKPOINT'])
            self._add_line(line_index=last_line_idx + 1, new_line=['TIMES', time_unit, *times])
            self._add_line(line_index=last_line_idx + 2, new_line=['FORMAT', 'HDF5'])
            self._add_line(line_index=last_line_idx + 3, new_line=['/'])

    def add_restart(self, filename: str):
        # Find simulation block
        simulation_block_idx = self._get_block_line_idx(self._find_tags('SIMULATION')[0])
        # Find the last line of the simulation block
        last_line_idx = simulation_block_idx[-1]
        # Add the checkpoint block
        self._add_line(line_index=last_line_idx, new_line=['RESTART'])
        self._add_line(line_index=last_line_idx + 1, new_line=['FILENAME', filename])
        self._add_line(line_index=last_line_idx + 2, new_line=['/'])

    def add_dataset(self, name: str, filename: str, hdf5_dataset_name: str):
        """This method adds a dataset to the simulation.
        """
        logger.info(f"Adding dataset {name} to the simulation")
        # Find simulation block
        if name in self.get_datasets():
            idx = self.datasets_to_idx[name]
            inside_block = self._get_block_line_idx(idx)
            for line_idx in inside_block:
                line = self._get_line(line_idx)
                if 'file' in line.lower():
                    self._replace_line(line_index=line_idx, new_line=['FILENAME', filename])
                if 'hdf5_dataset' in line.lower():
                    self._replace_line(line_index=line_idx, new_line=['HDF5_DATASET_NAME', hdf5_dataset_name])
        else:
            logger.warning(f"Dataset {name} not found in the simulation. Adding it.")
            subsurface_block_start = self.get_subsurface_idx()
            # Find the last line of the simulation block
            last_line_idx = subsurface_block_start + 2
            # Add the checkpoint block
            self._add_line(line_index=last_line_idx, new_line=['# Automatically added by pydelling'])
            self._add_line(line_index=last_line_idx + 1, new_line=['DATASET', name])
            self._add_line(line_index=last_line_idx + 2, new_line=['FILENAME', filename])
            self._add_line(line_index=last_line_idx + 3, new_line=['HDF5_DATASET_NAME', hdf5_dataset_name])
            self._add_line(line_index=last_line_idx + 4, new_line=['END'])

    def get_subsurface_idx(self) -> int:
        """This method returns the index of the subsurface tag.
        """
        subsurface_idx = self._find_tags('SUBSURFACE')
        for idx in subsurface_idx:
            if self._get_parent_tag_name_(idx) == 'SUBSURFACE':
                return idx

    def has_tag(self, tag: str):
        """This method returns True if the tag is in the input file.
        """
        return len(self._find_tags(tag)) > 0

    def _get_parent_tag_name_(self, line_index: int):
        """This method returns the parent tag of the line.
        """
        # Find the previous END tag
        has_end_tag = False
        temp_list = []
        original_line_index = line_index
        temp_list.append(self._get_line(line_index))
        while not has_end_tag:
            line = self._get_line(line_index)
            line_index -= 1
            if len(line.split()) == 0:
                continue
            if line[0] == '#':
                continue
            if 'subsurface' in line.lower():
                has_end_tag = True
            temp_list.append(line)
            if 'end' in line.lower().split():
                has_end_tag = True
            elif '/' in line.split():
                has_end_tag = True
        tag_name = temp_list[-2].split()[0]
        if self._get_line(original_line_index).split()[0].lower() == tag_name.lower():
            return None
        return temp_list[-2].split()[0]

    def _get_block_lines(self, line_index: int):
        """This method returns the lines of the block.
        """
        # Find the previous END tag
        has_end_tag = False
        temp_list = []
        temp_list.append(self._get_line(line_index))
        while not has_end_tag:
            line_index += 1
            line = self._get_line(line_index)
            if len(line.split()) == 0:
                continue
            if line[0] == '#':
                continue
            temp_list.append(line)
            if 'end' in line.lower():
                has_end_tag = True
        return temp_list

    def _get_block_line_idx(self, line_index: int):
        """This method returns the lines of the block.
        """
        # Find the previous END tag
        has_end_tag = False
        temp_list = []
        temp_list.append(line_index)
        while not has_end_tag:
            line_index += 1
            line = self._get_line(line_index)
            print(line)
            if len(line.split()) == 0:
                continue
            if line[0] == '#':
                continue
            temp_list.append(line_index)
            # Check 'end' is as its own word
            if 'end' in line.lower().split():
                print('here')
                print(self._get_parent_tag_name_(line_index))
                has_end_tag = True
        return temp_list

    def replace_maximum_timestep_values(self,
                                        final_timestep: float = 1,
                                        initial_timestep: float = 1E-8,
                                        timesteps_per_order_of_magnitude: int or list = 10,
                                        time_unit: str = 'y',
                                        initial_time: float = 0.0,
                                        ):
        """
        Replaces the maximum timestep values in a simulation's input file. This method adjusts the timestep settings based on
        the provided parameters, ensuring a gradual change in timestep sizes throughout the simulation.

        The method calculates the number of orders of magnitude difference between the initial and final timesteps.
        It then creates a series of timestep values, each incrementally larger than the previous, spaced evenly across
        these orders of magnitude.

        Args:
            final_timestep (float): The value of the final timestep in the simulation. Default is 1.
            initial_timestep (float): The value of the initial timestep. Default is 1E-8.
            timesteps_per_order_of_magnitude (int or list): The number of timesteps per order of magnitude. Can be an integer or a list specifying the number for each order. Default is 10.
            time_unit (str): The unit of time to be used for the timesteps (e.g., 'y' for years, 's' for seconds). Default is 'y'.
            initial_time (float): The starting time of the simulation. Default is 0.0.

        Returns:
            None

        Example:
            # Set the parameters for the timestep replacement
            final_timestep = 1
            initial_timestep = 1E-6
            timesteps_per_order_of_magnitude = 5
            time_unit = 'y'
            initial_time = 1.0

            # Replace the maximum timestep values
            simulation.replace_maximum_timestep_values(final_timestep,
                                                       initial_timestep,
                                                       timesteps_per_order_of_magnitude,
                                                       time_unit,
                                                       initial_time)
        """
        # Find the time block
        time_tags = self._find_tags('TIME')
        max_time_block_ids = []
        parent_tag_idx = None
        for idx  in time_tags:
            parent_tag = self._get_parent_tag_name_(idx)
            if parent_tag == None:
                parent_tag_idx = idx
            if parent_tag == 'TIME':
                content = self._get_line(idx)
                content_split = self._process_parameter_line(content)
                if content_split is not None:
                    if content_split[0] == 'MAXIMUM_TIMESTEP_SIZE':
                        max_time_block_ids.append(idx)
        # Delete the lines
        self._delete_lines(max_time_block_ids)

        # Add a random line after the time block
        assert parent_tag_idx is not None, "TIME block seems to be undefined"
        n_orders = int(np.log10(final_timestep / initial_timestep))
        lines_to_add = []
        for order in range(n_orders):
            cur_timestep = initial_timestep * 10 ** order / timesteps_per_order_of_magnitude
            cur_time = initial_time + initial_timestep * 10 ** order
            line = f"MAXIMUM_TIMESTEP_SIZE {cur_timestep} {time_unit} at {cur_time} {time_unit}"
            lines_to_add.append(line)
        self._add_lines(line_index=parent_tag_idx + 1, new_lines=lines_to_add)



    def _process_parameter_line(self, line: str):
        """This method processes a parameter line.
        """
        line = line.split()
        if line[0].startswith('#'):
            return None
        else:
            return [line[0], line[1:]]

    def _process_float(self, f: str):
        """This method processes a float.
        """
        try:
            return float(f)
        except ValueError:
            f = f.replace('d', 'e')
            f = f.replace('D', 'e')
            return float(f)


    # Class properties
    @property
    def final_time(self):
        """This method returns the final time of the simulation.
        """
        return self.get_simulation_time()

    @property
    def final_time_unit(self):
        """This method returns the final time unit of the simulation.
        """
        return self._get_line(self._find_tags('FINAL_TIME')[0]).split()[2]

    @property
    def idx_to_regions(self):
        """This method returns the regions of the simulation.
        """
        return {v: k for k, v in self.regions_to_idx.items()}



