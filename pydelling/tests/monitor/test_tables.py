"""Downloaded CSV tables: listing, paging, filtering and path confinement."""

import pandas as pd
import pytest

from pydelling.monitor.service import NotFound, RunsService
from pydelling.monitor.tables import MAX_PAGE, list_tables, read_table, resolve_table


@pytest.fixture
def run_folder(tmp_path):
    folder = tmp_path / "run"
    (folder / "postprocess").mkdir(parents=True)
    (folder / "s1" / "processed").mkdir(parents=True)
    (folder / "s1" / "attempts" / "0001" / "processed").mkdir(parents=True)
    (folder / "prepared" / "s1").mkdir(parents=True)
    (folder / "manifest.csv").write_text('study_id,K,note\ns1,1e-4,ok\ns2,2.5,"a, b"\n')
    rows = "".join(f"s{i % 3},{i},{i * 0.5}\n" for i in range(250))
    (folder / "profiles.csv").write_text("study_id,x_m,value\n" + rows)
    (folder / "postprocess" / "extractions.csv").write_text("a\n1\n")
    (folder / "s1/processed/extractions.csv").write_text("a\n1\n")
    (folder / "s1/attempts/0001/processed/extractions.csv").write_text("a\n1\n")
    (folder / "prepared/s1/inputs.csv").write_text("a\n1\n")
    (folder / "summary.json").write_text("{}")
    frame = pd.DataFrame(
        {
            "study_id": [f"s{i % 3}" for i in range(250)],
            "x_m": [float(i) for i in range(250)],
            "n": list(range(250)),
            "note": [None if i % 2 else "ok" for i in range(250)],
        }
    )
    frame.to_parquet(folder / "postprocess" / "extractions.parquet", index=False, row_group_size=60)
    (folder / "old.bin").write_bytes(b"PAR1")
    return folder


def test_list_tables_finds_csvs_and_skips_attempt_copies(run_folder):
    listed = list_tables(run_folder)
    assert [t["path"] for t in listed] == [
        "manifest.csv",
        "profiles.csv",
        "postprocess/extractions.csv",
        "postprocess/extractions.parquet",
    ]
    assert all(t["size"] > 0 for t in listed)
    assert list_tables(run_folder / "missing") == []


def test_read_table_pages_and_counts_rows(run_folder):
    first = read_table(run_folder, "profiles.csv", limit=100)
    assert first["columns"] == ["study_id", "x_m", "value"]
    assert first["total"] == 250 and len(first["rows"]) == 100
    assert first["rows"][0] == ["s0", "0", "0.0"]
    last = read_table(run_folder, "profiles.csv", offset=200, limit=100)
    assert len(last["rows"]) == 50 and last["rows"][-1] == ["s0", "249", "124.5"]
    assert read_table(run_folder, "profiles.csv", limit=10**6)["limit"] == MAX_PAGE
    assert read_table(run_folder, "profiles.csv", offset=-5)["offset"] == 0


def test_parquet_tables_page_across_row_groups(run_folder):
    path = "postprocess/extractions.parquet"
    first = read_table(run_folder, path, limit=10)
    assert first["columns"] == ["study_id", "x_m", "n", "note"]
    assert first["total"] == 250 and first["rows"][0] == ["s0", "0.0", "0", "ok"]
    assert first["rows"][1] == ["s1", "1.0", "1", ""], "missing values are empty text"
    across = read_table(run_folder, path, offset=55, limit=10)  # spans groups of 60 rows
    assert [r[2] for r in across["rows"]] == [str(i) for i in range(55, 65)]
    tail = read_table(run_folder, path, offset=240, limit=100)
    assert len(tail["rows"]) == 10 and tail["rows"][-1][2] == "249"
    assert read_table(run_folder, path, offset=999)["rows"] == []


def test_parquet_tables_filter_rows_by_text(run_folder):
    path = "postprocess/extractions.parquet"
    hits = read_table(run_folder, path, query="S2", limit=5)
    assert hits["total"] == 83 and all(r[0] == "s2" for r in hits["rows"])
    assert read_table(run_folder, path, query="249")["total"] == 1


def test_read_table_keeps_quoted_cells_and_empty_values(run_folder):
    table = read_table(run_folder, "manifest.csv")
    assert table["rows"] == [["s1", "1e-4", "ok"], ["s2", "2.5", "a, b"]]


def test_read_table_filters_rows_by_text(run_folder):
    hits = read_table(run_folder, "profiles.csv", query="S1", limit=10)
    assert hits["total"] == 83 and all(r[0] == "s1" for r in hits["rows"])
    second = read_table(run_folder, "profiles.csv", query="s1", offset=80, limit=10)
    assert len(second["rows"]) == 3
    assert read_table(run_folder, "profiles.csv", query="zzz")["rows"] == []


def test_row_count_follows_the_file(run_folder):
    assert read_table(run_folder, "manifest.csv")["total"] == 2
    with (run_folder / "manifest.csv").open("a") as stream:
        stream.write("s3,3,x\n")
    assert read_table(run_folder, "manifest.csv")["total"] == 3


@pytest.mark.parametrize(
    "path",
    [
        "../run/manifest.csv",
        "/etc/passwd",
        "summary.json",
        "old.parquet",
        "missing.csv",
        "",
        "a\\b.csv",
    ],
)
def test_only_csv_files_inside_the_run_are_served(run_folder, path):
    with pytest.raises(ValueError):
        resolve_table(run_folder, path)


def test_symlinked_tables_are_refused(run_folder, tmp_path):
    outside = tmp_path / "secret.csv"
    outside.write_text("a\n1\n")
    (run_folder / "link.csv").symlink_to(outside)
    with pytest.raises(ValueError):
        read_table(run_folder, "link.csv")
    assert "link.csv" not in [t["path"] for t in list_tables(run_folder)]


def test_service_serves_tables_of_a_downloaded_run(project, registry, run_folder):
    run_id = registry.ensure_run("macario", "/r/campaigns/x", name="x", status="completed")
    service = RunsService(project, registry)
    assert service.tables(run_id) == {"tables": []}, "nothing downloaded yet"
    with pytest.raises(NotFound):
        service.table(run_id, "manifest.csv")
    registry.update_run(run_id, local_folder=str(run_folder))
    assert service.tables(run_id)["tables"][0]["path"] == "manifest.csv"
    assert service.table(run_id, "profiles.csv", offset=100, limit=5)["rows"][0][1] == "100"
    with pytest.raises(ValueError):
        service.table(run_id, "../../etc/passwd")
