"""Card/block parser for PFLOTRAN input decks.

PFLOTRAN decks are sequences of *cards* (a keyword plus arguments per line). Some cards open a
block that is closed by ``END`` or ``/`` (``SUBSURFACE`` is closed by ``END_SUBSURFACE``). The
format does not mark which cards open blocks, so each terminator is matched to the innermost
*plausible* opener, in this order of evidence:

1. a known block keyword (``REGION``, ``MATERIAL_PROPERTY``, bare ``TYPE``…) whose contents are
   indented deeper than it, or that shares the terminator's indentation with all its contents
   (flush-left decks, reported in :attr:`PflotranDeck.warnings` because a reference card such
   as ``REGION all`` inside an unindented ``STRATA`` looks the same);
2. any card at the terminator's indentation whose contents are all indented deeper (named
   blocks such as a species inside ``ISOTHERM_REACTIONS``);
3. otherwise the latest card that has contents, recorded in :attr:`PflotranDeck.warnings`.

Comments (``#``/``!``) and ``SKIP`` … ``NOSKIP`` sections are ignored. The parser never
modifies text; :class:`PflotranStudy` uses it to locate lines and then edits ``raw_text``.

Example:
    ```python
    deck = PflotranDeck(text)
    deck.select('MATERIAL_PROPERTY soil', 'PERMEABILITY', 'PERM_ISO').args   # ['1.d-12']
    regions = deck.find_all('REGION', blocks_only=True)   # REGION blocks, not references
    ```
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LineNotFound(Exception):
    """Raised when a line, card or block cannot be found in an input deck."""


class CardNotFound(LineNotFound, KeyError):
    """Raised when a card selector does not match any card."""

    def __str__(self):
        return str(self.args[0]) if self.args else ''


KNOWN_BLOCKS = frozenset({
    # simulation
    'SIMULATION', 'PROCESS_MODELS', 'SUBSURFACE_FLOW', 'SUBSURFACE_TRANSPORT',
    'SUBSURFACE_GEOMECHANICS', 'NUCLEAR_WASTE_TRANSPORT', 'WIPP_FLOW', 'UFD_DECAY',
    'UFD_BIOSPHERE', 'CHECKPOINT', 'RESTART', 'OPTIONS',
    # discretisation & solvers
    'GRID', 'NUMERICAL_METHODS', 'TIMESTEPPER', 'NEWTON_SOLVER', 'LINEAR_SOLVER', 'TIME',
    # regions & materials
    'REGION', 'COORDINATES', 'MATERIAL_PROPERTY', 'PERMEABILITY', 'CHARACTERISTIC_CURVES',
    'SATURATION_FUNCTION', 'PERMEABILITY_FUNCTION', 'LIQUID_PERMEABILITY_FUNCTION',
    'GAS_PERMEABILITY_FUNCTION', 'SECONDARY_CONTINUUM', 'MULTIPLE_CONTINUUM', 'FLUID_PROPERTY',
    'EOS', 'DATASET', 'SPECIFIED_VELOCITY',
    # conditions & couplers
    'FLOW_CONDITION', 'TYPE', 'TRANSPORT_CONDITION', 'CONSTRAINT_LIST', 'CONSTRAINT',
    'CONCENTRATIONS', 'MINERALS', 'FREE_ION_GUESS', 'IMMOBILE', 'INITIAL_CONDITION',
    'BOUNDARY_CONDITION', 'SOURCE_SINK', 'STRATA', 'OBSERVATION', 'INTEGRAL_FLUX',
    # chemistry
    'CHEMISTRY', 'PRIMARY_SPECIES', 'SECONDARY_SPECIES', 'DECOUPLED_EQUILIBRIUM_REACTIONS',
    'GAS_SPECIES', 'PASSIVE_GAS_SPECIES', 'ACTIVE_GAS_SPECIES', 'MINERAL_KINETICS', 'SORPTION',
    'SURFACE_COMPLEXATION_RXN', 'ISOTHERM_REACTIONS', 'KD_REACTIONS', 'ION_EXCHANGE_RXN',
    'CATIONS', 'RADIOACTIVE_DECAY_REACTION', 'GENERAL_REACTION', 'MICROBIAL_REACTION',
    'IMMOBILE_SPECIES', 'IMMOBILE_DECAY_REACTION',
    # output
    'OUTPUT', 'SNAPSHOT_FILE', 'OBSERVATION_FILE', 'MASS_BALANCE_FILE', 'VARIABLES',
    'DEBUG',
})
# Keywords that open a block only when they have no arguments (``TYPE`` vs ``TYPE LINEAR``).
BARE_ONLY_BLOCKS = frozenset({'TYPE', 'TIME'})
TERMINATORS = frozenset({'END', '/'})


def strip_comment(line: str) -> str:
    """Return ``line`` without its ``#``/``!`` comment, stripped."""
    for marker in ('#', '!'):
        line = line.split(marker, 1)[0]
    return line.strip()


def split_path(path: str) -> List[str]:
    """Split a card path ``'GRID/BOUNDS'`` into selectors ``['GRID', 'BOUNDS']``."""
    selectors = [part.strip() for part in path.split('/') if part.strip()]
    if not selectors:
        raise ValueError(f"Empty card path: {path!r}")
    return selectors


def _indent(line: str) -> int:
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


@dataclass(eq=False)
class Card:
    """One card of a deck. A card with ``end_line`` set is a block."""
    keyword: str
    args: List[str]
    line: int
    indent: int
    end_line: Optional[int] = None
    children: List['Card'] = field(default_factory=list)
    parent: Optional['Card'] = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """Upper-case keyword, for comparisons."""
        return self.keyword.upper()

    @property
    def name(self) -> Optional[str]:
        """First argument (the block name for ``REGION all``, ``MATERIAL_PROPERTY soil``…)."""
        return self.args[0] if self.args else None

    @property
    def is_block(self) -> bool:
        return self.end_line is not None

    @property
    def last_line(self) -> int:
        """Index of the terminator for a block, of the card line otherwise."""
        return self.end_line if self.end_line is not None else self.line

    @property
    def path(self) -> str:
        """Human-readable location, e.g. ``SUBSURFACE/MATERIAL_PROPERTY soil/PERMEABILITY``."""
        parts = []
        card = self
        while card is not None and card.parent is not None:
            parts.append(' '.join([card.keyword] + card.args[:1]))
            card = card.parent
        return '/'.join(reversed(parts))

    def iter(self) -> Iterator['Card']:
        """Depth-first iteration over all descendants."""
        for child in self.children:
            yield child
            yield from child.iter()

    def matches(self, selector: str) -> bool:
        """Whether this card matches ``'KEYWORD'`` or ``'KEYWORD name'`` (case-insensitive)."""
        parts = selector.split()
        if not parts or parts[0].upper() != self.key:
            return False
        return len(parts) == 1 or (self.name is not None and self.name.lower() == parts[1].lower())

    def find_all(self, selector: str = None, blocks_only: bool = False) -> List['Card']:
        """All descendants matching ``selector`` (all descendants if None), in file order."""
        return [card for card in self.iter()
                if (selector is None or card.matches(selector)) and (card.is_block or not blocks_only)]

    def find(self, selector: str, blocks_only: bool = False) -> Optional['Card']:
        """First descendant matching ``selector``, or None."""
        found = self.find_all(selector, blocks_only=blocks_only)
        return found[0] if found else None

    def select(self, *selectors: str) -> 'Card':
        """Follow ``selectors`` as a descendant path and return the card; raise if missing.

        Each selector matches at any depth below the previous match, e.g.
        ``select('MATERIAL_PROPERTY soil', 'PERM_ISO')``. All selectors but the last only
        match blocks, since the path has to descend into them.
        """
        card = self
        for depth, selector in enumerate(selectors):
            found = card.find(selector, blocks_only=depth < len(selectors) - 1)
            if found is None:
                where = ' > '.join(selectors[:depth]) or 'deck'
                raise CardNotFound(f"No card '{selector}' in {where}")
            card = found
        return card

    def __repr__(self):
        kind = f"block {self.line}-{self.end_line}" if self.is_block else f"line {self.line}"
        return f"Card({' '.join([self.keyword] + self.args)!r}, {kind})"


class PflotranDeck:
    """Parsed view of a PFLOTRAN input deck (see module docstring for the matching rules)."""

    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.root = Card(keyword='', args=[], line=-1, indent=-1, end_line=len(self.lines))
        self.cards: List[Card] = []
        self.warnings: List[str] = []
        self._parse()

    # ------------------------------------------------------------------ parsing
    def _parse(self):
        pending: List[Card] = []  # cards not yet enclosed by a closed block, in file order
        skipping = False
        for idx, raw in enumerate(self.lines):
            tokens = strip_comment(raw).split()
            if not tokens:
                continue
            key = tokens[0].upper()
            if key == 'NOSKIP':
                skipping = False
                continue
            if skipping:
                continue
            if key == 'SKIP':
                skipping = True
                continue
            if key in TERMINATORS or key == 'END_SUBSURFACE':
                self._close(pending, idx, _indent(raw), subsurface=key == 'END_SUBSURFACE')
                continue
            card = Card(keyword=tokens[0], args=tokens[1:], line=idx, indent=_indent(raw))
            self.cards.append(card)
            pending.append(card)
        for card in pending:
            if not card.is_block and card.key == 'SUBSURFACE':
                self.warnings.append(f"line {card.line + 1}: SUBSURFACE without END_SUBSURFACE")
            card.parent = self.root
        self.root.children = pending

    def _close(self, pending: List[Card], idx: int, indent: int, subsurface: bool):
        opener_pos = self._choose_opener(pending, indent, subsurface)
        if opener_pos is None:
            self.warnings.append(f"line {idx + 1}: terminator without an open block")
            return
        opener = pending[opener_pos]
        opener.children = pending[opener_pos + 1:]
        for child in opener.children:
            child.parent = opener
        opener.end_line = idx
        del pending[opener_pos + 1:]

    def _choose_opener(self, pending: List[Card], indent: int, subsurface: bool) -> Optional[int]:
        if subsurface:
            for pos in range(len(pending) - 1, -1, -1):
                if pending[pos].key == 'SUBSURFACE' and not pending[pos].is_block:
                    return pos
            return None
        fallback = None
        for pos in range(len(pending) - 1, -1, -1):
            card = pending[pos]
            if card.is_block or card.key == 'SUBSURFACE':
                continue
            contents = pending[pos + 1:]
            if not contents:
                # empty block, e.g. "OPTIONS" directly followed by "/" at the same indentation
                if self._is_known_block(card) and card.indent == indent:
                    return pos
                continue
            deeper = all(child.indent > card.indent for child in contents)
            if self._is_known_block(card):
                if deeper:
                    return pos
                if card.indent == indent and all(child.indent == indent for child in contents):
                    self.warnings.append(
                        f"line {card.line + 1}: '{card.keyword}' block matched by keyword only "
                        f"(no indentation); check the structure if this is a reference card")
                    return pos
            elif card.indent == indent and deeper:
                return pos
            if fallback is None:
                fallback = pos
        if fallback is not None:
            card = pending[fallback]
            self.warnings.append(f"line {card.line + 1}: guessed '{card.keyword}' as the block "
                                 f"closed by the terminator (no known keyword/indentation match)")
        return fallback

    @staticmethod
    def _is_known_block(card: Card) -> bool:
        if card.key not in KNOWN_BLOCKS:
            return False
        return not (card.key in BARE_ONLY_BLOCKS and card.args)

    # ------------------------------------------------------------------ queries
    def find_all(self, selector: str = None, blocks_only: bool = False) -> List[Card]:
        """All cards matching ``selector`` anywhere in the deck, in file order."""
        return self.root.find_all(selector, blocks_only=blocks_only)

    def find(self, selector: str, blocks_only: bool = False) -> Optional[Card]:
        """First card matching ``selector`` anywhere in the deck, or None."""
        return self.root.find(selector, blocks_only=blocks_only)

    def select(self, *selectors: str) -> Card:
        """Follow a descendant path of selectors; raise :class:`CardNotFound` if missing."""
        return self.root.select(*selectors)

    def top_level_cards(self) -> List[Card]:
        """Cards at the top of the deck, looking through ``SUBSURFACE`` (``GRID``, ``TIME``…)."""
        cards = []
        for card in self.root.children:
            if card.key == 'SUBSURFACE' and card.is_block:
                cards.extend(card.children)
            else:
                cards.append(card)
        return cards

    def resolve(self, path: str) -> Tuple[Optional[Card], List[Card]]:
        """Resolve a card path like ``'MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO'``.

        The first selector matches a top-level card (see :meth:`top_level_cards`), each later
        selector a direct child of the previous block, so ``'OUTPUT/TIMES'`` is never
        ``CHEMISTRY/OUTPUT``. Returns ``(parent, matches)``: the block holding the last
        selector (None at the top level) and every card it matches, possibly none.

        Raises:
            CardNotFound: if a block along the path is missing or ambiguous.
        """
        selectors = split_path(path)
        parent, candidates = None, self.top_level_cards()
        for depth, selector in enumerate(selectors):
            matches = [card for card in candidates if card.matches(selector)]
            if depth == len(selectors) - 1:
                return parent, matches
            blocks = [card for card in matches if card.is_block]
            where = '/'.join(selectors[:depth + 1])
            if not blocks:
                raise CardNotFound(self.not_found_message(where))
            if len(blocks) > 1:
                names = ', '.join(self.path_of(block) for block in blocks)
                raise CardNotFound(f"'{where}' matches {len(blocks)} blocks ({names}); "
                                   f"name the one you mean")
            parent, candidates = blocks[0], blocks[0].children

    def not_found_message(self, path: str) -> str:
        """Error text for a missing path, listing where its last keyword does exist."""
        last = split_path(path)[-1]
        found = [self.path_of(card) for card in self.find_all(last)]
        hint = f"; found at: {', '.join(found)}" if found else ''
        return f"No card '{path}'{hint}"

    def path_of(self, card: Card) -> str:
        """Card path of ``card`` as accepted by :meth:`resolve` (blocks include their name)."""
        parts = []
        while card is not None and card is not self.root:
            if not (card.key == 'SUBSURFACE' and card.parent is self.root):
                parts.append(card.keyword + (f' {card.name}' if card.is_block and card.name else ''))
            card = card.parent
        return '/'.join(reversed(parts))

    def card_at(self, line_index: int) -> Optional[Card]:
        """The card on ``line_index``, else the innermost block spanning it, else None."""
        best = None
        for card in self.cards:
            if card.line == line_index:
                return card
            if card.is_block and card.line < line_index <= card.end_line:
                if best is None or card.line > best.line:
                    best = card
        return best

    def top_level(self, card: Card) -> Card:
        """The outermost ancestor of ``card`` below the root, looking through ``SUBSURFACE``."""
        while card.parent is not None and card.parent is not self.root \
                and not (card.parent.key == 'SUBSURFACE' and card.parent.parent is self.root):
            card = card.parent
        return card

    def block_line_indexes(self, card: Card) -> List[int]:
        """Non-blank, non-comment line indexes from the card line through its terminator."""
        return [idx for idx in range(card.line, card.last_line + 1)
                if strip_comment(self.lines[idx])]

    def __repr__(self):
        return f"PflotranDeck({len(self.cards)} cards, {len(self.root.children)} top-level)"
