"""Regression tests for study identity, copying, templating and block parsing."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydelling.managers import BaseCallback, BaseManager, BaseStudy, PflotranStudy
from pydelling.managers.base_study import MissingTemplateVariables
from pydelling.managers.pflotran_study import LineNotFound
from pydelling.utils.configuration_utils import test_data_path


def _write(folder: Path, name: str, text: str) -> Path:
    path = Path(folder) / name
    path.write_text(text)
    return path


class DummyManager(BaseManager):
    """Concrete manager that never launches a solver."""


DummyManager.__abstractmethods__ = frozenset()


class TestStudyIdentity(TestCase):
    def test_to_file_does_not_advance_study_counter(self):
        study = BaseStudy(str(test_data_path() / 'test_manager.in'))
        count_before = BaseStudy.count
        with TemporaryDirectory() as tmp:
            study.to_file(output_folder=Path(tmp) / 'case')
        self.assertEqual(BaseStudy.count, count_before)

    def test_manager_assigns_positional_idx(self):
        manager = DummyManager()
        studies = [PflotranStudy(str(test_data_path() / 'test_manager.in'), study_name=f's{i}')
                   for i in range(3)]
        for study in studies:
            manager.add_study(study)
        self.assertEqual([s.idx for s in studies], [0, 1, 2])

    def test_duplicate_study_name_raises(self):
        manager = DummyManager()
        manager.add_study(PflotranStudy(str(test_data_path() / 'test_manager.in'), study_name='same'))
        with self.assertRaises(ValueError):
            manager.add_study(PflotranStudy(str(test_data_path() / 'test_manager.in'), study_name='same'))

    def test_to_file_creates_nested_output_folder(self):
        study = BaseStudy(str(test_data_path() / 'test_manager.in'))
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'a' / 'b'
            study.to_file(output_folder=target)
            self.assertTrue((target / 'test_manager.in').exists())


class TestGenerateRunFiles(TestCase):
    def test_writes_one_folder_per_study_without_running(self):
        manager = DummyManager()
        base = PflotranStudy(str(test_data_path() / 'test_manager.in'))
        for i in range(3):
            manager.add_study(base.copy(study_name=f'case-{i}'))
        with TemporaryDirectory() as tmp:
            manager.generate_run_files(Path(tmp) / 'nested' / 'studies')
            written = sorted(p.parent.name for p in (Path(tmp) / 'nested' / 'studies').rglob('*.in'))
        self.assertEqual(written, ['case-0', 'case-1', 'case-2'])


class TestStudyCopy(TestCase):
    def test_copy_does_not_share_settings(self):
        with TemporaryDirectory() as tmp:
            template = _write(tmp, 'deck.in', 'POROSITY {{ phi }}\n')
            original = BaseStudy(str(template))
            original.replace_variable('phi', 0.1)
            clone = original.copy()
            clone.replace_variable('phi', 0.4)
            clone.add_input_file(template)
            self.assertEqual(original.jinja_settings['phi'], 0.1)
            self.assertEqual(original.aux_files, {})
            self.assertNotEqual(clone.name, original.name)

    def test_copy_accepts_name(self):
        study = BaseStudy(str(test_data_path() / 'test_manager.in'))
        self.assertEqual(study.copy(study_name='variant').name, 'variant')

    def test_copied_callbacks_bind_to_the_copy(self):
        BaseCallback.__abstractmethods__ = set()
        original = BaseStudy(str(test_data_path() / 'test_manager.in'))
        original.add_callback(BaseCallback, kind='pre')
        clone = original.copy()
        manager = DummyManager()
        clone.initialize_callbacks(manager)
        self.assertIs(clone.callbacks[0].study, clone)


class TestTemplating(TestCase):
    def test_missing_variable_raises_listing_all(self):
        with TemporaryDirectory() as tmp:
            study = BaseStudy(str(_write(tmp, 'deck.in', 'A {{ a }}\nB {{ b }}\nC {{ c }}\n')))
            study.replace_variable('a', 1)
            with self.assertRaises(MissingTemplateVariables) as ctx:
                study.render()
            self.assertEqual(ctx.exception.missing, ['b', 'c'])

    def test_render_kwargs_count_as_defined(self):
        with TemporaryDirectory() as tmp:
            study = BaseStudy(str(_write(tmp, 'deck.in', 'A {{ a }}\n')))
            self.assertEqual(study.render(a=2), 'A 2\n')

    def test_custom_delimiters(self):
        with TemporaryDirectory() as tmp:
            text = 'POROSITY <<PHI>>\n# {{ untouched }} and {# not a comment #}\n'
            study = BaseStudy(str(_write(tmp, 'deck.in', text)), variable_delimiters=('<<', '>>'))
            self.assertEqual(study.placeholders(), {'PHI'})
            study.set_variables(PHI=0.25)
            self.assertEqual(study.render(),
                             'POROSITY 0.25\n# {{ untouched }} and {# not a comment #}\n')

    def test_placeholders_and_missing(self):
        with TemporaryDirectory() as tmp:
            study = BaseStudy(str(_write(tmp, 'deck.in', '{{ x }} {{ y }}\n')))
            study.set_variables(x=1)
            self.assertEqual(study.placeholders(), {'x', 'y'})
            self.assertEqual(study.missing_variables(), ['y'])

    def test_non_strict_mode_keeps_legacy_behaviour(self):
        with TemporaryDirectory() as tmp:
            study = BaseStudy(str(_write(tmp, 'deck.in', 'A {{ a }}\n')), strict=False)
            self.assertEqual(study.render(), 'A \n')


BLOCK_DECK = """\
SUBSURFACE
MATERIAL_PROPERTY soil
  ID 1
  POROSITY 0.4   # recommended value
  PERMEABILITY
    PERM_ISO 1.d-12
  /
  # APPEND notes: end of comment
  TORTUOSITY 1.0
END
REGION all
  COORDINATES
    0. 0. 0.
    1. 1. 1.
  /
END
END_SUBSURFACE
"""


class TestBlockParsing(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.study = PflotranStudy(str(_write(self.tmp.name, 'deck.in', BLOCK_DECK)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_inline_comment_containing_end_does_not_close_block(self):
        start = self.study._find_tags('MATERIAL_PROPERTY')[0]
        block = self.study._get_block_lines(start)
        self.assertEqual(block[-1].strip(), 'END')
        self.assertTrue(any('TORTUOSITY' in line for line in block))

    def test_block_lines_and_indexes_agree(self):
        start = self.study._find_tags('MATERIAL_PROPERTY')[0]
        lines = self.study.raw_text.splitlines()
        self.assertEqual([lines[i] for i in self.study._get_block_line_idx(start)],
                         self.study._get_block_lines(start))

    def test_replace_material_properties_by_keyword(self):
        self.study.replace_material_properties(new_perm=2e-12, new_porosity=0.3,
                                               material_name='soil')
        text = self.study.raw_text
        self.assertIn('POROSITY 0.3', text)
        self.assertIn('TORTUOSITY 1.0', text)  # untouched
        self.assertIn('ID 1', text)
        self.assertIn('PERM_ISO 2e-12', text)

    def test_replace_material_properties_missing_line_raises(self):
        with self.assertRaises(LineNotFound):
            self.study.replace_material_properties(new_perm=2e-12, new_porosity=0.3,
                                                   new_vertical_anisotropy=0.1, material_name='soil')
        with self.assertRaises(LineNotFound):
            self.study.replace_material_properties(new_perm=2e-12, new_porosity=0.3,
                                                   material_name='rock')

    def test_regions_still_found(self):
        self.assertEqual(self.study.get_regions(), ['all'])
