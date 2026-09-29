"""The PFLOTRAN manager tutorials run end to end and write valid decks."""

import runpy
from pathlib import Path

import pytest

from pydelling.managers import PflotranDeck

TUTORIALS = Path(__file__).parents[3] / "code_snippets/managers/pflotran_manager"


@pytest.mark.parametrize(
    "script, studies",
    [("tutorial_01_edit_cards.py", 1), ("tutorial_02_samplers_and_sensitivity.py", 30)],
)
def test_tutorial_runs(script, studies, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(TUTORIALS / script), run_name="__main__")
    decks = sorted(tmp_path.glob("studies/**/column_template.in"))
    assert len(decks) == studies
    for deck in decks:
        text = deck.read_text()
        assert "<<" not in text
        assert PflotranDeck(text).warnings == []
