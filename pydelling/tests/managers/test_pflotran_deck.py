"""Tests for the PFLOTRAN card/block parser and the PflotranStudy card API."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydelling.managers import CardNotFound, LineNotFound, PflotranDeck, PflotranStudy
from pydelling.utils.configuration_utils import test_data_path

DECK = """\
# header comment with END and / inside
SIMULATION
  SIMULATION_TYPE SUBSURFACE
  PROCESS_MODELS
    SUBSURFACE_TRANSPORT transport
      MODE GIRT
      OPTIONS
      /
    /
  /
END

SUBSURFACE

CHEMISTRY
  PRIMARY_SPECIES
    Tracer_c
    Tracer_s
  /
  SORPTION
    ISOTHERM_REACTIONS
      Tracer_s
        TYPE LINEAR
        DISTRIBUTION_COEFFICIENT 1.d0 kg/m^3   # recommended value
      /
    /
  /
END

MATERIAL_PROPERTY soil
  ID 1
  POROSITY 0.25 ! porosity comment
  PERMEABILITY
    PERM_ISO 1.d-12
  /
END

FLOW_CONDITION hydrostatic
  TYPE
      PRESSURE hydrostatic
    /
  PRESSURE 101325.d0
END

CONSTRAINT inlet
  CONCENTRATIONS
    Tracer_c 1.0 T
/
END

SKIP
REGION skipped
END
NOSKIP

REGION all
  COORDINATES
    0.d0 0.d0 0.d0
    1.d0 1.d0 1.d0
  /
END

REGION inlet
  FILE ./inlet.ex
END

BOUNDARY_CONDITION west
  FLOW_CONDITION hydrostatic
  REGION inlet
END

STRATA
  REGION all
  MATERIAL soil
END

END_SUBSURFACE
"""


class TestPflotranDeck(TestCase):
    def setUp(self):
        self.deck = PflotranDeck(DECK)

    def test_no_warnings(self):
        self.assertEqual(self.deck.warnings, [])

    def test_top_level(self):
        self.assertEqual([c.keyword for c in self.deck.root.children], ['SIMULATION', 'SUBSURFACE'])
        subsurface = self.deck.root.children[1]
        self.assertTrue(subsurface.is_block)
        self.assertEqual([c.keyword for c in subsurface.children],
                         ['CHEMISTRY', 'MATERIAL_PROPERTY', 'FLOW_CONDITION', 'CONSTRAINT', 'REGION',
                          'REGION', 'BOUNDARY_CONDITION', 'STRATA'])

    def test_nested_slash_blocks(self):
        process_models = self.deck.select('SIMULATION', 'PROCESS_MODELS')
        transport = process_models.children[0]
        self.assertEqual(transport.keyword, 'SUBSURFACE_TRANSPORT')
        self.assertEqual([c.keyword for c in transport.children], ['MODE', 'OPTIONS'])
        self.assertTrue(self.deck.select('OPTIONS').is_block)  # empty block
        self.assertEqual(self.deck.select('SIMULATION').children[-1], process_models)

    def test_named_species_block(self):
        species = self.deck.select('ISOTHERM_REACTIONS', 'Tracer_s')
        self.assertTrue(species.is_block)
        self.assertEqual([c.key for c in species.children], ['TYPE', 'DISTRIBUTION_COEFFICIENT'])
        self.assertFalse(species.children[0].is_block)  # TYPE LINEAR is a card, not a block

    def test_misaligned_terminators(self):
        type_block = self.deck.select('FLOW_CONDITION hydrostatic', 'TYPE')
        self.assertTrue(type_block.is_block)
        self.assertEqual(self.deck.select('FLOW_CONDITION hydrostatic').children[-1].key, 'PRESSURE')
        concentrations = self.deck.select('CONSTRAINT inlet', 'CONCENTRATIONS')
        self.assertTrue(concentrations.is_block)
        self.assertTrue(self.deck.select('CONSTRAINT inlet').is_block)

    def test_region_blocks_vs_references(self):
        self.assertEqual([c.name for c in self.deck.find_all('REGION', blocks_only=True)], ['all', 'inlet'])
        self.assertEqual(len(self.deck.find_all('REGION')), 4)  # + references in BC and STRATA

    def test_skip_sections_ignored(self):
        self.assertIsNone(self.deck.find('REGION skipped'))

    def test_comments_ignored(self):
        dc = self.deck.select('DISTRIBUTION_COEFFICIENT')
        self.assertEqual(dc.args, ['1.d0', 'kg/m^3'])
        self.assertEqual(self.deck.select('MATERIAL_PROPERTY soil', 'POROSITY').args, ['0.25'])

    def test_select_errors(self):
        with self.assertRaises(CardNotFound):
            self.deck.select('MATERIAL_PROPERTY rock')
        with self.assertRaises(LineNotFound):  # CardNotFound is a LineNotFound
            self.deck.select('MATERIAL_PROPERTY soil', 'TORTUOSITY')

    def test_paths_and_lookup(self):
        perm = self.deck.select('MATERIAL_PROPERTY soil', 'PERM_ISO')
        self.assertEqual(perm.path, 'SUBSURFACE/MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO 1.d-12')
        self.assertIs(self.deck.card_at(perm.line), perm)
        coordinates = self.deck.select('REGION all', 'COORDINATES')
        self.assertIs(self.deck.card_at(coordinates.end_line), coordinates)  # terminator line
        self.assertIs(self.deck.card_at(coordinates.line + 1).parent, coordinates)  # data row
        self.assertEqual(self.deck.top_level(perm).keyword, 'MATERIAL_PROPERTY')

    def test_flush_left_deck_uses_keywords_and_warns(self):
        deck = PflotranDeck("REGION all\nCOORDINATES\n0 0 0\n1 1 1\n/\nEND\n")
        self.assertEqual([c.keyword for c in deck.root.children], ['REGION'])
        self.assertTrue(deck.select('REGION all', 'COORDINATES').is_block)
        self.assertEqual(len(deck.warnings), 2)  # both matches relied on keywords only

    def test_flush_left_reference_cards_are_ambiguous(self):
        # Without indentation "REGION all" inside STRATA looks like a REGION block: the parser
        # cannot tell, so it must say so instead of failing silently.
        deck = PflotranDeck("STRATA\nREGION all\nMATERIAL soil\nEND\n")
        self.assertTrue(deck.warnings)

    def test_unmatched_terminator_warns(self):
        deck = PflotranDeck("FINAL_TIME 1 y\n/\n")
        self.assertEqual(len(deck.warnings), 1)

    def test_packaged_decks_parse_cleanly(self):
        for name in ('test_manager.in', 'test_pflotran_manager_nocheckpoint.in'):
            deck = PflotranDeck((test_data_path() / name).read_text())
            self.assertEqual(deck.warnings, [], name)
            self.assertEqual([c.key for c in deck.root.children], ['SIMULATION', 'SUBSURFACE'], name)


class TestPflotranStudyCardApi(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        path = Path(self.tmp.name) / 'deck.in'
        path.write_text(DECK)
        self.study = PflotranStudy(str(path))

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_and_set_values_keep_indent_and_comment(self):
        self.assertEqual(self.study.get_card_values('MATERIAL_PROPERTY soil', 'POROSITY'), ['0.25'])
        self.study.set_card_values('MATERIAL_PROPERTY soil', 'POROSITY', values=0.3)
        self.assertIn('  POROSITY 0.3  ! porosity comment', self.study.raw_text.splitlines())
        self.study.set_card_values('DISTRIBUTION_COEFFICIENT', values=[2.5, 'kg/m^3'])
        self.assertEqual(self.study.get_card_values('Tracer_s', 'DISTRIBUTION_COEFFICIENT'),
                         ['2.5', 'kg/m^3'])

    def test_set_values_with_template_placeholder(self):
        self.study.set_card_values('MATERIAL_PROPERTY soil', 'PERM_ISO', values='{{ perm }}')
        self.study.set_variables(perm=5e-13)
        self.assertIn('PERM_ISO 5e-13', self.study.render())

    def test_add_card(self):
        self.study.add_card('MATERIAL_PROPERTY soil', line='TORTUOSITY 0.5')
        material = self.study.get_card('MATERIAL_PROPERTY soil')
        self.assertEqual(material.children[-1].keyword, 'TORTUOSITY')
        self.assertEqual(self.study._get_line(material.children[-1].line), '  TORTUOSITY 0.5')
        with self.assertRaises(ValueError):
            self.study.add_card('MATERIAL_PROPERTY soil', 'ID', line='X 1')

    def test_remove_card_block(self):
        self.study.remove_card('MATERIAL_PROPERTY soil', 'PERMEABILITY')
        self.assertNotIn('PERM_ISO', self.study.raw_text)
        self.assertEqual([c.key for c in self.study.get_card('MATERIAL_PROPERTY soil').children],
                         ['ID', 'POROSITY'])
        self.assertEqual(self.study.deck.warnings, [])

    def test_deck_reparsed_after_edits(self):
        before = self.study.deck
        self.study.set_card_values('MATERIAL_PROPERTY soil', 'ID', values=2)
        self.assertIsNot(self.study.deck, before)
        self.assertEqual(self.study.get_card_values('MATERIAL_PROPERTY soil', 'ID'), ['2'])

    def test_legacy_helpers_use_parser(self):
        self.assertEqual(self.study.get_regions(), ['all', 'inlet'])
        self.assertEqual(self.study.get_region_file('inlet'), './inlet.ex')
        self.assertIsNone(self.study.get_region_file('all'))
        self.study.replace_region_file('inlet', './new.ex')
        self.assertEqual(self.study.get_region_file('inlet'), './new.ex')
        with self.assertRaises(KeyError):
            self.study.get_region_file('missing')
        subsurface = self.study.get_subsurface_idx()
        self.assertEqual(self.study._get_line(subsurface), 'SUBSURFACE')
        coordinates_line = self.study.get_card('REGION all', 'COORDINATES').line
        self.assertEqual(self.study._get_parent_tag_name(coordinates_line), 'REGION')
        sim_idx = self.study._get_block_line_idx(self.study.get_card('SIMULATION').line)
        self.assertEqual(self.study._get_line(sim_idx[-1]), 'END')

    def test_copy_does_not_share_parsed_deck(self):
        clone = self.study.copy()
        clone.set_card_values('MATERIAL_PROPERTY soil', 'POROSITY', values=0.1)
        self.assertEqual(self.study.get_card_values('MATERIAL_PROPERTY soil', 'POROSITY'), ['0.25'])
