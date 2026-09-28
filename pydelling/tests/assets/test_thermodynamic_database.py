from pathlib import Path

from pydelling.assets.thermodynamic_database import (
    parse_thermodynamic_database,
    search_thermodynamic_database,
)


def test_parses_sections_reactions_and_recovers_after_bad_rows(tmp_path: Path):
    path = tmp_path / "thermo.dat"
    path.write_text(
        "\n".join(
            [
                "'temperature points' 2 0 25",
                "'H2O' 3.0 0.0 18.0153",
                "'null' 0 0 0",
                "'OH-' 2 -1 'H+' 1 'H2O' 14.0 13.9 3.5 -1 17.0 'ref one'",
                "'broken",
                "'null' 0",
                "'CO2(g)' 1 1 'CO2(aq)' 1.1 1.2 0 0 44",
                "'null' 0",
                "'Quartz' 22.6 1 1 'SiO2(aq)' -4.0 -3.9 60.08 'ref two'",
                "'null' 0",
                "'>SOH' 1 1 'H+' 2.0 2.1 0 0 0",
            ]
        )
    )

    database = parse_thermodynamic_database(path)

    assert database.temperatures == [0.0, 25.0]
    assert database.counts == {
        "primary_aqueous": 1,
        "secondary_aqueous": 1,
        "gases": 1,
        "minerals": 1,
        "surface_complexes": 1,
    }
    assert database.sections["secondary_aqueous"][0]["reaction"] == [
        {"coefficient": -1.0, "species": "H+"},
        {"coefficient": 1.0, "species": "H2O"},
    ]
    assert database.warnings

    result = search_thermodynamic_database(database, query="quartz", limit=10)
    assert result["total"] == 1
    assert result["items"][0]["reference"] == "ref two"
