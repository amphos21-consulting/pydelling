"""Post-processing callbacks: registration, execution, specs and validation."""

from pathlib import Path

import pandas as pd
import pytest

from pydelling.managers import PflotranStudy
from pydelling.managers.postprocess import (
    FunctionCallback,
    PostprocessCallback,
    processed_intact,
    run_postprocess,
    validate_postprocess,
)


class Constant(PostprocessCallback):
    """Returns a fixed table; fails when ``fail`` is set."""

    def __init__(self, value: float = 1.0, name: str = "constant", fail: bool = False) -> None:
        self.value = value
        self.name = name
        self.fail = fail

    def options(self) -> dict:
        return {"value": self.value, "name": self.name, "fail": self.fail}

    def validate(self, study: PflotranStudy) -> None:
        if self.value < 0:
            raise ValueError("value must be positive")

    def process(self, workdir: Path, study: PflotranStudy) -> pd.DataFrame:
        if self.fail:
            raise RuntimeError("broken")
        return pd.DataFrame({"study": [study.name], "value": [self.value]})


def table(workdir: Path, study: PflotranStudy) -> pd.DataFrame:
    return pd.DataFrame({"files": [len(list(Path(workdir).glob("*.h5")))]})


@pytest.fixture
def study(tmp_path: Path) -> PflotranStudy:
    deck = tmp_path / "deck.in"
    deck.write_text("SUBSURFACE\nEND_SUBSURFACE\n")
    return PflotranStudy(str(deck), study_name="a")


def test_callbacks_are_registered_once_per_name(study):
    study.add_postprocess(Constant(), Constant(name="other"))
    assert [c.name for c in study.postprocess] == ["constant", "other"]
    with pytest.raises(ValueError, match="already has a postprocess callback named 'constant'"):
        study.add_postprocess(Constant())


def test_copies_get_their_own_callbacks(study):
    study.add_postprocess(Constant(2.0))
    copy = study.copy(study_name="b")
    copy.postprocess[0].value = 3.0
    assert study.postprocess[0].value == 2.0


def test_run_writes_one_table_per_callback_and_keeps_going(study, tmp_path):
    study.add_postprocess(Constant(fail=True, name="broken"), Constant(5.0))
    records = run_postprocess(study, tmp_path)
    assert records["broken"]["state"] == "failed"
    assert records["broken"]["error"] == "RuntimeError: broken"
    good = records["constant"]
    assert good["state"] == "completed" and good["rows"] == 1
    assert good["file"] == "processed/constant.parquet"
    assert pd.read_parquet(tmp_path / good["file"]).value.tolist() == [5.0]
    assert not processed_intact(study, tmp_path, records)


def test_processed_files_must_match_their_records(study, tmp_path):
    study.add_postprocess(Constant())
    records = run_postprocess(study, tmp_path)
    assert processed_intact(study, tmp_path, records)
    pd.DataFrame({"value": [9.0]}).to_parquet(tmp_path / "processed/constant.parquet", index=False)
    assert not processed_intact(study, tmp_path, records)
    assert not processed_intact(study, tmp_path, None)
    assert processed_intact(PflotranStudy(str(study.input_file)), tmp_path, None)


def test_a_callback_must_return_a_table(study, tmp_path):
    study.add_postprocess(FunctionCallback(lambda workdir, s: [1, 2], name="bad"))
    record = run_postprocess(study, tmp_path)["bad"]
    assert record["state"] == "failed"
    assert "must return a pandas DataFrame" in record["error"]


def test_specs_rebuild_the_callbacks():
    callback = Constant(4.0, name="four")
    spec = callback.spec()
    assert spec == {
        "type": f"{__name__}:Constant",
        "options": {"value": 4.0, "name": "four", "fail": False},
    }
    rebuilt = PostprocessCallback.from_spec(spec)
    assert isinstance(rebuilt, Constant) and rebuilt.value == 4.0
    function = FunctionCallback(table, name="count")
    assert function.spec()["options"] == {"function": f"{__name__}:table", "name": "count"}
    assert PostprocessCallback.from_spec(function.spec()).function is table


def test_function_callbacks_run_where_the_study_ran(study, tmp_path):
    (tmp_path / "out.h5").write_text("")
    study.add_postprocess(FunctionCallback(table, name="count"))
    run_postprocess(study, tmp_path)
    assert pd.read_parquet(tmp_path / "processed/count.parquet").files.tolist() == [1]


def test_validation_names_the_study_and_the_callback(study):
    study.add_postprocess(Constant(-1.0))
    with pytest.raises(ValueError, match="a: constant: value must be positive"):
        validate_postprocess([study])


def test_names_must_be_safe_file_stems(study):
    with pytest.raises(ValueError, match="safe name"):
        study.add_postprocess(Constant(name="../x"))
