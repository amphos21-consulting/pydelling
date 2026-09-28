"""
PFLOTRAN study: a templated PFLOTRAN input deck with structure-aware editing.

Structure queries (regions, datasets, blocks, parent cards) go through
:class:`~pydelling.managers.pflotran_deck.PflotranDeck`, which parses ``raw_text`` into a
card/block tree. The card API (``get_card``, ``get_card_values``, ``set_card_values``,
``add_card``, ``remove_card``) edits lines selected by card path, e.g.::

    study.set_card_values('MATERIAL_PROPERTY soil', 'PERMEABILITY', 'PERM_ISO', values=1e-12)
"""

from .base_study import BaseStudy
from .pflotran_deck import Card, CardNotFound, LineNotFound, PflotranDeck
import logging
from typing import Union, List, Dict, Sequence

logger = logging.getLogger(__name__)

class PflotranStudy(BaseStudy):
    """Manage and edit PFLOTRAN input decks.

    Category: manager
    Tags: pflotran, study, input-file, simulation, editing
    Usage: scripts need to inspect or modify PFLOTRAN regions, datasets, timing, checkpoints, and material blocks.
    """
    # the parsed deck is rebuilt on demand, never copied
    _copy_skip_attrs = BaseStudy._copy_skip_attrs + ('_deck_cache',)

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
        self._deck_cache = None

    @property
    def deck(self) -> PflotranDeck:
        """Parsed card/block tree of the current ``raw_text`` (re-parsed after edits).

        Category: manager
        Tags: pflotran, parser, deck, blocks
        Usage: structure-aware queries on the input deck.

        Returns:
            PflotranDeck: parsed deck.
        """
        if self._deck_cache is None or self._deck_cache.text != self.raw_text:
            self._deck_cache = PflotranDeck(self.raw_text)
            for warning in self._deck_cache.warnings:
                logger.warning(f"{self.input_file_name}: {warning}")
        return self._deck_cache

    def get_card(self, *selectors: str) -> Card:
        """Return the card at a selector path, e.g. ``('MATERIAL_PROPERTY soil', 'POROSITY')``.

        Category: manager
        Tags: pflotran, card, lookup, parser
        Usage: reading or locating any card of the deck. Each selector is ``KEYWORD`` or
            ``KEYWORD name`` (case-insensitive) and matches at any depth below the previous one.

        Raises:
            CardNotFound: if a selector does not match.

        Returns:
            Card: the matched card (``card.line`` is its line index in ``raw_text``).
        """
        return self.deck.select(*selectors)

    def get_card_values(self, *selectors: str) -> List[str]:
        """Return the argument tokens of a card, e.g. ``['0.25']`` for ``POROSITY 0.25``.

        Category: manager
        Tags: pflotran, card, values, lookup
        Usage: reading a parameter value from the deck.

        Returns:
            list: argument tokens (comments removed).
        """
        return list(self.get_card(*selectors).args)

    def set_card_values(self, *selectors: str, values):
        """Replace the arguments of a card, keeping its keyword, indentation and comment.

        Category: manager
        Tags: pflotran, card, values, edit
        Usage: changing a parameter, e.g.
            ``set_card_values('MATERIAL_PROPERTY soil', 'POROSITY', values=0.3)`` or
            ``set_card_values('FINAL_TIME', values=[10, 'y'])``.

        Returns:
            None: mutates raw_text.
        """
        card = self.get_card(*selectors)
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            values = [values]
        line = self._get_line(card.line)
        indent = line[:len(line) - len(line.lstrip())]
        new_line = indent + ' '.join([card.keyword, *map(str, values)])
        comment = self._inline_comment(line)
        if comment:
            new_line += '  ' + comment
        self._replace_line(card.line, [new_line])

    def add_card(self, *selectors: str, line: str):
        """Append a line as the last entry of the selected block (before its terminator).

        Category: manager
        Tags: pflotran, card, insert, edit
        Usage: adding a card to a block, e.g.
            ``add_card('MATERIAL_PROPERTY soil', line='TORTUOSITY 0.5')``. The line is indented
            like the block's existing entries.

        Raises:
            CardNotFound: if the selector does not match; ValueError if it is not a block.

        Returns:
            None: mutates raw_text.
        """
        block = self.get_card(*selectors)
        if not block.is_block:
            raise ValueError(f"'{block.path}' is not a block")
        indent = block.children[0].indent if block.children else block.indent + 2
        self._add_line(block.end_line, [' ' * indent + line.strip()])

    def remove_card(self, *selectors: str):
        """Remove a card, including its whole block when it is one.

        Category: manager
        Tags: pflotran, card, delete, edit
        Usage: dropping an option or a block from the deck.

        Returns:
            None: mutates raw_text.
        """
        card = self.get_card(*selectors)
        self._delete_lines(list(range(card.line, card.last_line + 1)))

    @staticmethod
    def _inline_comment(line: str) -> str:
        """Return the ``#``/``!`` comment of a line (with its marker), or ''."""
        positions = [pos for pos in (line.find('#'), line.find('!')) if pos >= 0]
        return line[min(positions):].strip() if positions else ''

    def get_regions(self):
        """Return region names defined in the PFLOTRAN input deck.

        Category: manager
        Tags: pflotran, regions, input-file, lookup
        Usage: scripts need to inspect available REGION blocks or map region names to line indexes.

        Returns:
            list: names of REGION blocks (not REGION references inside couplers), in file order.
        """
        regions = []
        for card in self.deck.find_all('REGION', blocks_only=True):
            regions.append(card.name)
            self.regions_to_idx[card.name] = card.line
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

        Cards are located by keyword inside the block (not by fixed offsets), so the
        block's layout does not matter. ``new_perm`` replaces ``PERM_ISO`` and/or
        ``PERM_HORIZONTAL``; ``new_vertical_anisotropy`` replaces
        ``VERTICAL_ANISOTROPY_RATIO`` when given.

        Raises:
            LineNotFound: if the material block, its POROSITY line, a PERM_ISO/PERM_HORIZONTAL
                line, or (when requested) its VERTICAL_ANISOTROPY_RATIO line is missing.

        Returns:
            None: mutates the matching lines, keeping their indentation and comments.
        """
        selector = f'MATERIAL_PROPERTY {material_name}'.strip()
        material = self.deck.find(selector, blocks_only=True)
        if material is None:
            raise CardNotFound(f"No block '{selector}'")
        replacements = {'POROSITY': new_porosity, 'PERM_ISO': new_perm, 'PERM_HORIZONTAL': new_perm}
        if new_vertical_anisotropy is not None:
            replacements['VERTICAL_ANISOTROPY_RATIO'] = new_vertical_anisotropy
        targets = [card for card in material.iter() if card.key in replacements]
        replaced = {card.key for card in targets}
        missing = []
        if 'POROSITY' not in replaced:
            missing.append('POROSITY')
        if not replaced & {'PERM_ISO', 'PERM_HORIZONTAL'}:
            missing.append('PERM_ISO/PERM_HORIZONTAL')
        if new_vertical_anisotropy is not None and 'VERTICAL_ANISOTROPY_RATIO' not in replaced:
            missing.append('VERTICAL_ANISOTROPY_RATIO')
        if missing:
            raise LineNotFound(f"{selector} has no {', '.join(missing)} line")
        for card in targets:  # line numbers are unchanged by single-line replacements
            line = self._get_line(card.line)
            indent = line[:len(line) - len(line.lstrip())]
            new_line = f"{indent}{card.keyword} {replacements[card.key]}"
            comment = self._inline_comment(line)
            self._replace_line(card.line, [new_line + ('  ' + comment if comment else '')])

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

        Raises:
            KeyError: if there is no REGION block with that name.

        Returns:
            str | None: region file path token, or None when the region has no FILE card.
        """
        file_card = self._region_file_card(region)
        return file_card.name if file_card is not None else None

    def _region_file_card(self, region: str):
        block = self.deck.find(f'REGION {region}', blocks_only=True)
        if block is None:
            raise KeyError(region)
        return next((card for card in block.children if card.key == 'FILE'), None)

    def get_datasets(self) -> List[str]:
        """Return DATASET names defined in the input deck.

        Category: manager
        Tags: pflotran, dataset, hdf5, lookup
        Usage: scripts need to inspect or update referenced PFLOTRAN datasets.

        Returns:
            list: names of DATASET blocks, in file order.
        """
        datasets = []
        for card in self.deck.find_all('DATASET', blocks_only=True):
            datasets.append(card.name)
            self.datasets_to_idx[card.name] = card.line
        return datasets

    def replace_region_file(self, region: str, new_file: str):
        """Replace the FILE entry for a REGION block.

        Category: manager
        Tags: pflotran, region, file, edit
        Usage: scripts need to point a PFLOTRAN region to a new geometry file.

        Raises:
            KeyError: if there is no REGION block with that name.

        Returns:
            None: mutates the in-memory input text (no-op if the region has no FILE card).
        """
        file_card = self._region_file_card(region)
        if file_card is None:
            logger.warning(f"Region {region} has no FILE card; nothing replaced")
            return
        logger.info(f"Replacing region {region} file from '{file_card.name}' to '{new_file}'")
        self.set_card_values(f'REGION {region}', 'FILE', values=new_file)

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
            int | None: line index of the top-level SUBSURFACE card, or None.
        """
        for card in self.deck.root.children:
            if card.key == 'SUBSURFACE':
                return card.line
        return None

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
        """Return the top-level card keyword containing a line (looking through SUBSURFACE).

        Category: util
        Tags: pflotran, parent-tag, block, parser
        Usage: parsers need to classify matching tags by their enclosing block.

        Returns:
            str: keyword of the outermost enclosing card, as written in the deck.
        """
        card = self.deck.card_at(line_index)
        if card is None:
            return self._get_line(line_index).split()[0]
        return self.deck.top_level(card).keyword

    def _get_block_lines(self, line_index: int):
        """Return non-comment lines of the card starting at a line index (through its terminator).

        Category: util
        Tags: pflotran, block, lines, parser
        Usage: parsers need all lines in a PFLOTRAN input block.

        Returns:
            list: block lines from the start card through its END or '/'.
        """
        return [self._get_line(idx) for idx in self._get_block_line_idx(line_index)]

    def _get_block_line_idx(self, line_index: int):
        """Return non-comment line indexes of the card starting at a line index.

        Category: util
        Tags: pflotran, block, line-index, parser
        Usage: editing helpers need exact indexes for lines in a PFLOTRAN block.

        Blocks end at their matching terminator (``END`` or ``/``), so nested sub-blocks are
        included and never end the parent early. A card that is not a block returns only its
        own line.

        Returns:
            list: line indexes from the start card through its terminator.
        """
        deck = self.deck
        card = deck.card_at(line_index)
        if card is None or card.line != line_index:
            return [line_index]
        return deck.block_line_indexes(card)

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

