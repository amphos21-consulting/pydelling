"""
Module documentation.


"""

from .base_study import BaseStudy
import logging
from typing import Union, List, Dict

logger = logging.getLogger(__name__)

class LineNotFound(Exception):
    """Raised when a requested PFLOTRAN input-deck line cannot be found.

    Category: PFLOTRAN study.
    Tags: pflotran, input-file, exception, lookup.
    Usage: to identify errors from PFLOTRAN input-deck
        editing operations.
    """

    pass

class PflotranStudy(BaseStudy):
    """Manage and edit PFLOTRAN input decks.

    Category: manager
    Tags: pflotran, study, input-file, simulation, editing
    Usage: scripts need to inspect or modify PFLOTRAN regions, datasets, timing, checkpoints, and material blocks.
    """
    def __init__(self, input_file: str, *args, **kwargs):
        """Initialize a PFLOTRAN study from an input file.

        Category: manager
        Tags: pflotran, study, input-file, parser
        Usage: scripts need an editable representation of a PFLOTRAN input deck.

        Returns:
            None: initializes BaseStudy state and PFLOTRAN index maps.
        """
        super().__init__(input_file, *args, **kwargs)
        self.regions_to_idx = {}
        self.datasets_to_idx = {}

    def get_regions(self):
        """Return region names defined in the PFLOTRAN input deck.

        Category: manager
        Tags: pflotran, regions, input-file, lookup
        Usage: scripts need to inspect available REGION blocks or map region names to line indexes.

        Returns:
            list: region names found in top-level REGION blocks.
        """
        region_lines = self._find_tags('region')
        regions = []
        for line_idx in region_lines:
            line = self._get_line(line_idx)
            if self._get_parent_tag_name(line_idx).lower() == 'region':
                regions.append(line.split()[1])
                self.regions_to_idx[line.split()[1]] = line_idx
        return regions

    def get_simulation_time(self, time_unit: str = 'y'):
        """Return the simulation final time in the requested unit.

        Category: manager
        Tags: pflotran, simulation-time, final-time, units
        Usage: scripts need to inspect PFLOTRAN FINAL_TIME as a numeric value.

        Returns:
            float: final simulation time converted to time_unit.
        """
        time_lines = self._get_line(self._find_tags('FINAL_TIME')[0])
        value = time_lines.split()[1]
        value_unit = time_lines.split()[2]
        return self.convert_time(value=value, initial_unit=value_unit, final_unit=time_unit)

    def get_checkpoint(self):
        """Return the checkpoint TIMES line if present.

        Category: manager
        Tags: pflotran, checkpoint, restart, simulation
        Usage: scripts need to inspect whether checkpoint output is configured.

        Returns:
            str | None: checkpoint times line, or None when no checkpoint is configured.
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
        """Replace the PFLOTRAN FINAL_TIME line.

        Category: manager
        Tags: pflotran, simulation-time, final-time, edit
        Usage: scripts need to change the total runtime of a PFLOTRAN simulation.

        Returns:
            None: mutates the in-memory input text.
        """
        time_lines = self._find_tags('FINAL_TIME')
        new_time = self.convert_time(value=new_time, initial_unit=time_unit, final_unit=time_unit)
        self._replace_line(line_index=time_lines[0], new_line=['FINAL_TIME', str(new_time), time_unit])

    def replace_parameter(self, label: str, new_value: float, inside: float, time_unit: str = 'y'):
        """Replace a parameter line relative to a matching tag.

        Category: manager
        Tags: pflotran, parameter, edit, input-file
        Usage: scripts need to modify a PFLOTRAN parameter located near a known tag.

        Returns:
            None: mutates the in-memory input text.
        """
        if inside != 0:
            inside = inside
        else:
            inside = 0

        parameter_lines = self._find_tags(label[0])
        self._replace_line(line_index=parameter_lines[0] + inside, new_line=[label[1], str(new_value)])

    def replace_material_properties(self, new_perm: float, new_porosity: float, new_vertical_anisotropy: float = None, material_name: str = ''):
        """Replace porosity and permeability values in a MATERIAL_PROPERTY block.

        Category: manager
        Tags: pflotran, material, porosity, permeability, edit
        Usage: scripts need to update material hydraulic properties before running PFLOTRAN.

        Lines are located by keyword inside the block (not by fixed offsets), so the
        block's layout does not matter. ``new_perm`` replaces ``PERM_ISO`` and/or
        ``PERM_HORIZONTAL``; ``new_vertical_anisotropy`` replaces
        ``VERTICAL_ANISOTROPY_RATIO`` when given.

        Raises:
            LineNotFound: if the material block, its POROSITY line, a PERM_ISO/PERM_HORIZONTAL
                line, or (when requested) its VERTICAL_ANISOTROPY_RATIO line is missing.

        Returns:
            None: mutates the matching lines, keeping their indentation.
        """
        start = self._find_material_property(material_name)
        replacements = {'porosity': new_porosity, 'perm_iso': new_perm, 'perm_horizontal': new_perm}
        if new_vertical_anisotropy is not None:
            replacements['vertical_anisotropy_ratio'] = new_vertical_anisotropy
        replaced = set()
        for line_idx in self._get_block_line_idx(start)[1:]:
            line = self._get_line(line_idx)
            tokens = self._strip_comment(line).split()
            key = tokens[0].lower() if tokens else None
            if key in replacements:
                indent = line[:len(line) - len(line.lstrip())]
                self._replace_line(line_idx, [indent + tokens[0], str(replacements[key])])
                replaced.add(key)
        missing = []
        if 'porosity' not in replaced:
            missing.append('POROSITY')
        if not replaced & {'perm_iso', 'perm_horizontal'}:
            missing.append('PERM_ISO/PERM_HORIZONTAL')
        if new_vertical_anisotropy is not None and 'vertical_anisotropy_ratio' not in replaced:
            missing.append('VERTICAL_ANISOTROPY_RATIO')
        if missing:
            raise LineNotFound(f"MATERIAL_PROPERTY {material_name or '(first)'} has no {', '.join(missing)} line")

    def _find_material_property(self, material_name: str = '') -> int:
        """Return the line index of ``MATERIAL_PROPERTY <material_name>`` (first one if no name)."""
        for line_idx, line in enumerate(self.raw_text.splitlines()):
            tokens = self._strip_comment(line).split()
            if not tokens or tokens[0].lower() != 'material_property':
                continue
            if not material_name or (len(tokens) > 1 and tokens[1].lower() == material_name.lower()):
                return line_idx
        raise LineNotFound(f"MATERIAL_PROPERTY {material_name} not found")

    def get_line_after_finding(self, given_lines: list, file_lines: list) -> int:
        """Find the line index reached after matching an ordered sequence.

        Category: util
        Tags: pflotran, text, search, line-index
        Usage: scripts need to locate nested PFLOTRAN text by matching several line prefixes in order.

        Returns:
            int: index of the line matching the last requested prefix.
        """
        given_line_i = 0
        for line_i, line in enumerate(file_lines):
            if line.lstrip().startswith(given_lines[given_line_i].lstrip()):
                given_line_i += 1
                if given_line_i==len(given_lines):
                    # All lines have been found
                    return line_i

        message = "Sequence of lines not found: "
        for gl in given_lines:
            message += '"' + gl + '"' + " / "

        message = message [:-3] # Remove last slash
            
        raise LineNotFound(message)

    def replace_after_finding(self, prev_lines: list, new_line: str, offset: int=0):
        """Replace a line after finding an ordered sequence of line prefixes.

        Category: manager
        Tags: pflotran, text, replace, line-edit
        Usage: scripts need robust edits in PFLOTRAN blocks identified by ordered context lines.

        Returns:
            None: updates raw_text with the replacement line.
        """
        file_lines = self.raw_text.splitlines()

        sought_line = self.get_line_after_finding(prev_lines, file_lines)
        file_lines[sought_line+offset] = new_line

        self.raw_text = '\n'.join(file_lines)

    def add_after_finding(self, prev_lines: list, new_line: str, offset: int=0):
        """Insert a line after finding an ordered sequence of line prefixes.

        Category: manager
        Tags: pflotran, text, insert, line-edit
        Usage: scripts need to add PFLOTRAN lines relative to nested block context.

        Returns:
            None: updates raw_text with the inserted line.
        """
        file_lines = self.raw_text.splitlines()

        sought_line = self.get_line_after_finding(prev_lines, file_lines)
        file_lines.insert(sought_line+offset+1, new_line)

        self.raw_text = '\n'.join(file_lines)

    def remove_after_finding(self, prev_lines: list, offset: int=0):
        """Remove a line after finding an ordered sequence of line prefixes.

        Category: manager
        Tags: pflotran, text, remove, line-edit
        Usage: scripts need to delete PFLOTRAN lines relative to nested block context.

        Returns:
            None: updates raw_text after removing the targeted line.
        """
        file_lines = self.raw_text.splitlines()

        sought_line = self.get_line_after_finding(prev_lines, file_lines)
        file_lines.pop(sought_line+offset)

        self.raw_text = '\n'.join(file_lines)

    def get_region_file(self, region: str) -> Union[str, None]:
        """Return the FILE value for a REGION block.

        Category: manager
        Tags: pflotran, region, file, lookup
        Usage: scripts need to resolve the geometry file referenced by a PFLOTRAN region.

        Returns:
            str | None: region file path token, or None when not found.
        """
        self.get_regions()
        region_line = self.regions_to_idx[region]
        region_block = self._get_block_lines(region_line)
        for line in region_block:
            if 'file' in line.lower():
                return line.split()[1]
        return None

    def get_datasets(self) -> List[str]:
        """Return DATASET names defined in the input deck.

        Category: manager
        Tags: pflotran, dataset, hdf5, lookup
        Usage: scripts need to inspect or update referenced PFLOTRAN datasets.

        Returns:
            list: dataset names found in top-level DATASET blocks.
        """
        datasets = []
        for line_idx in self._find_tags('DATASET'):
            line = self._get_line(line_idx)
            if line.split()[0].lower() == 'hdf5_dataset_name':
                continue
            if self._get_parent_tag_name(line_idx).lower() == 'dataset':
                datasets.append(line.split()[1])
                self.datasets_to_idx[line.split()[1]] = line_idx
        return datasets

    def replace_region_file(self, region: str, new_file: str):
        """Replace the FILE entry for a REGION block.

        Category: manager
        Tags: pflotran, region, file, edit
        Usage: scripts need to point a PFLOTRAN region to a new geometry file.

        Returns:
            None: mutates the in-memory input text.
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
        """Add or update CHECKPOINT output times.

        Category: manager
        Tags: pflotran, checkpoint, hdf5, restart, edit
        Usage: scripts need PFLOTRAN checkpoint files at selected simulation times.

        Returns:
            None: adds or updates the CHECKPOINT block.
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
        """Add a RESTART block to the SIMULATION section.

        Category: manager
        Tags: pflotran, restart, simulation, edit
        Usage: scripts need a PFLOTRAN simulation to restart from an existing checkpoint file.

        Returns:
            None: inserts a RESTART block.
        """
        simulation_block_idx = self._get_block_line_idx(self._find_tags('SIMULATION')[0])
        # Find the last line of the simulation block
        last_line_idx = simulation_block_idx[-1]
        # Add the checkpoint block
        self._add_line(line_index=last_line_idx, new_line=['RESTART'])
        self._add_line(line_index=last_line_idx + 1, new_line=['FILENAME', filename])
        self._add_line(line_index=last_line_idx + 2, new_line=['/'])

    def add_dataset(self, name: str, filename: str, hdf5_dataset_name: str):
        """Add or update a PFLOTRAN DATASET block.

        Category: manager
        Tags: pflotran, dataset, hdf5, edit
        Usage: scripts need to connect PFLOTRAN inputs to an HDF5 dataset path and dataset name.

        Returns:
            None: adds a DATASET block or updates its filename and HDF5 dataset name.
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
        """Return the line index of the top-level SUBSURFACE tag.

        Category: manager
        Tags: pflotran, subsurface, line-index, lookup
        Usage: scripts need an insertion point for subsurface dataset edits.

        Returns:
            int: line index of the top-level SUBSURFACE block.
        """
        subsurface_idx = self._find_tags('SUBSURFACE')
        for idx in subsurface_idx:
            if self._get_parent_tag_name(idx) == 'SUBSURFACE':
                return idx

    def has_tag(self, tag: str):
        """Check whether a tag appears in the input deck.

        Category: manager
        Tags: pflotran, tag, lookup, input-file
        Usage: scripts need to branch depending on whether a PFLOTRAN block exists.

        Returns:
            bool: True when at least one matching tag is found.
        """
        return len(self._find_tags(tag)) > 0

    def _get_parent_tag_name(self, line_index: int):
        """Return the parent block tag name for a line index.

        Category: util
        Tags: pflotran, block, parent, line-index
        Usage: parsing needs to distinguish top-level tags from nested tag references.

        Returns:
            str: parent tag name.
        """
        # Walk back to the END closing the previous block (or the SUBSURFACE card / file start);
        # the parent tag is the first card after it.
        temp_list = [self._get_line(line_index)]
        while line_index >= 0:
            line = self._get_line(line_index)
            line_index -= 1
            tokens = self._strip_comment(line).split()
            if not tokens:
                continue
            temp_list.append(line)
            if tokens[0].lower() in ('end', 'end_subsurface', 'subsurface'):
                break
        return temp_list[-2].split()[0] if len(temp_list) > 1 else temp_list[0].split()[0]

    def _get_block_lines(self, line_index: int):
        """Return non-comment lines in the block starting at a line index.

        Category: util
        Tags: pflotran, block, lines, parser
        Usage: scripts need the text content of a PFLOTRAN block.

        Returns:
            list: block lines from the start tag through END.
        """
        return [self._get_line(idx) for idx in self._get_block_line_idx(line_index)]

    def _get_block_line_idx(self, line_index: int):
        """Return line indexes in the block starting at a line index.

        Category: util
        Tags: pflotran, block, line-index, parser
        Usage: scripts need editable line indexes inside a PFLOTRAN block.

        Returns:
            list: line indexes from the start tag through END.
        """
        # Nested sub-blocks closed with '/' are included; the block ends at the first END card.
        n_lines = len(self.raw_text.splitlines())
        temp_list = [line_index]
        while line_index + 1 < n_lines:
            line_index += 1
            tokens = self._strip_comment(self._get_line(line_index)).split()
            if not tokens:
                continue
            temp_list.append(line_index)
            if tokens[0].lower() == 'end':
                break
        return temp_list

    @staticmethod
    def _strip_comment(line: str) -> str:
        """Return ``line`` without its ``#`` comment (PFLOTRAN uses ``#`` and ``!``)."""
        for marker in ('#', '!'):
            line = line.split(marker, 1)[0]
        return line.strip()

    # Class properties
    @property
    def final_time(self):
        """Return the simulation final time in years.

        Category: manager
        Tags: pflotran, final-time, simulation-time
        Usage: callers need property-style access to final simulation time.

        Returns:
            float: final simulation time in years.
        """
        return self.get_simulation_time()

    @property
    def final_time_unit(self):
        """Return the unit token used by FINAL_TIME.

        Category: manager
        Tags: pflotran, final-time, units
        Usage: scripts need the original time unit from the input deck.

        Returns:
            str: FINAL_TIME unit token.
        """
        return self._get_line(self._find_tags('FINAL_TIME')[0]).split()[2]

    @property
    def idx_to_regions(self):
        """Return the inverse region line-index lookup.

        Category: manager
        Tags: pflotran, regions, line-index, lookup
        Usage: scripts need to map stored region indexes back to region names.

        Returns:
            dict: line indexes mapped to region names.
        """
        return {v: k for k, v in self.regions_to_idx.items()}

