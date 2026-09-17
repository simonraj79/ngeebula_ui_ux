import json
from pathlib import Path

import pytest

from scripts.import_lta_stations import build_reference, normalize_station_rows
from backend.lta_reference import enrich_station_catalog, reference_attribution


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "backend" / "lta_station_reference.json"
CURRENT_PATH = ROOT / "backend" / "stations_db.json"


def _reference():
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def test_committed_reference_has_pinned_official_provenance_and_expected_schema():
    reference = _reference()
    provenance = reference["provenance"]

    assert reference["schema_version"] == 1
    assert provenance["publisher"] == "Land Transport Authority, Singapore"
    assert provenance["retrieved_on"] == "2026-09-17"
    assert provenance["station_source"]["url"].startswith("https://datamall.lta.gov.sg/")
    assert provenance["line_source"]["url"].startswith("https://datamall.lta.gov.sg/")
    assert len(provenance["station_source"]["sha256"]) == 64
    assert len(provenance["line_source"]["sha256"]) == 64
    assert reference["summary"]["station_code_count"] == 213
    assert reference["summary"]["line_catalog_row_count"] == 12


def test_station_records_are_unique_and_retain_published_line_membership():
    stations = _reference()["stations"]
    by_code = {row["station_code"]: row for row in stations}

    assert len(by_code) == len(stations)
    assert by_code["EW23"]["station_name"] == "Clementi"
    assert by_code["EW23"]["published_line_name"] == "East-West Line"
    assert by_code["NS24"]["station_name"] == "Dhoby Ghaut"
    assert by_code["NE6"]["station_name"] == "Dhoby Ghaut"
    assert by_code["CC1"]["station_name"] == "Dhoby Ghaut"
    assert "interchange" not in by_code["NS24"]


def test_current_unverified_reference_differences_remain_visible_for_review():
    official = {(row["station_code"], row["station_name"]) for row in _reference()["stations"]}
    current_data = json.loads(CURRENT_PATH.read_text(encoding="utf-8"))
    current = {
        (row["code"], row["name"])
        for system in current_data.values()
        for rows in system.values()
        for row in rows
    }

    assert official - current == {("CE1", "Bayfront"), ("DT4", "Hume")}
    assert current - official == {
        ("CC30", "Keppel"),
        ("CC31", "Cantonment"),
        ("CC32", "Prince Edward Road"),
        ("CC33", "Marina Bay"),
        ("CC34", "Bayfront"),
        ("CE1", "Promenade"),
        ("DT36", "Xilin"),
        ("DT37", "Sungei Bedok"),
        ("TE30", "Bedok South"),
        ("TE31", "Sungei Bedok"),
    }


def test_normalizer_rejects_duplicate_or_invalid_codes():
    row = {
        "stn_code": "EW23",
        "mrt_station_english": "Clementi",
        "mrt_station_chinese": "金文泰",
        "mrt_line_english": "East-West Line",
        "mrt_line_chinese": "东西线",
    }
    with pytest.raises(ValueError, match="Duplicate station code"):
        normalize_station_rows([row, row])
    with pytest.raises(ValueError, match="Invalid LTA station code"):
        normalize_station_rows([{**row, "stn_code": "EW-23"}])


def test_builder_keeps_duplicate_line_codes_as_distinct_published_rows():
    station_rows = [
        {
            "stn_code": "EW23",
            "mrt_station_english": "Clementi",
            "mrt_station_chinese": "金文泰",
            "mrt_line_english": "East-West Line",
            "mrt_line_chinese": "东西线",
        }
    ]
    line_rows = [
        {
            "MRT/LRT Line": "EWL",
            "MRT/LRT Description": description,
            "MRT/LRT Direction": "",
            "Shuttle Direction": "",
        }
        for description in ("Changi Extension", "East-West Line")
    ]
    result = build_reference(
        station_rows,
        line_rows,
        retrieved_on="2026-09-17",
        station_sha256="a" * 64,
        line_sha256="b" * 64,
    )

    assert [row["published_description"] for row in result["line_catalog"]] == [
        "Changi Extension",
        "East-West Line",
    ]


def test_enrichment_marks_matches_preserves_local_only_and_corrects_conflicts():
    reference = {
        **_reference(),
        "stations": [
            {
                "station_code": "EW23",
                "station_name": "Clementi",
                "published_line_name": "East-West Line",
            },
            {
                "station_code": "CE1",
                "station_name": "Bayfront",
                "published_line_name": "Circle Line Extension",
            },
            {
                "station_code": "DT4",
                "station_name": "Hume",
                "published_line_name": "Downtown Line",
            },
        ],
    }
    local = [
        {"code": "EW23", "name": "clementi", "line": "East-West Line (EWL)"},
        {"code": "CE1", "name": "Promenade", "line": "Circle Line (CCL)"},
        {"code": "CC30", "name": "Keppel", "line": "Circle Line (CCL)"},
    ]

    result = enrich_station_catalog(local, reference)
    by_code = {row["code"]: row for row in result["stations"]}

    assert by_code["EW23"]["reference_status"] == "matched"
    assert by_code["EW23"]["name"] == "clementi"
    assert by_code["CC30"]["reference_status"] == "unverified"
    assert by_code["CC30"]["name"] == "Keppel"
    assert by_code["CE1"]["reference_status"] == "corrected"
    assert by_code["CE1"]["name"] == "Bayfront"
    assert by_code["CE1"]["old_name"] == "Promenade"
    assert "conflicts" in by_code["CE1"]["reference_warning"]
    assert by_code["DT4"] == {
        "code": "DT4",
        "name": "Hume",
        "line": "Downtown Line (DTL)",
        "interchange": False,
        "reference_status": "official",
    }
    assert local[1]["name"] == "Promenade"


def test_enrichment_normalizes_interchange_from_shared_station_name():
    reference = {
        **_reference(),
        "stations": [
            {
                "station_code": "NS24",
                "station_name": "Dhoby Ghaut",
                "published_line_name": "North-South Line",
            },
            {
                "station_code": "NE6",
                "station_name": "Dhoby Ghaut",
                "published_line_name": "North East Line",
            },
        ],
    }
    result = enrich_station_catalog([], reference)
    assert all(row["interchange"] is True for row in result["stations"])


def test_enrichment_corrects_a_published_code_on_the_wrong_local_line():
    reference = {
        **_reference(),
        "stations": [
            {
                "station_code": "EW23",
                "station_name": "Clementi",
                "published_line_name": "East-West Line",
            }
        ],
    }
    result = enrich_station_catalog(
        [{"code": "EW23", "name": "Clementi", "line": "North-South Line (NSL)"}],
        reference,
    )
    station = result["stations"][0]
    assert station["reference_status"] == "corrected"
    assert station["old_line"] == "North-South Line (NSL)"
    assert station["line"] == "East-West Line (EWL)"


def test_missing_reference_falls_back_without_changing_local_values(tmp_path):
    local = [{"code": "EW23", "name": "Clementi", "line": "East-West Line (EWL)"}]
    result = enrich_station_catalog(local, reference_path=tmp_path / "missing.json")

    assert result["stations"] == [{**local[0], "reference_status": "unverified"}]
    assert result["provenance"]["available"] is False
    assert "unavailable" in result["provenance"]["warning"]


def test_enrichment_and_attribution_are_offline(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: pytest.fail("network access is forbidden"),
    )
    reference = _reference()
    result = enrich_station_catalog([], reference)
    attribution = reference_attribution(reference)

    assert len(result["stations"]) == 213
    assert attribution["publisher"] == "Land Transport Authority, Singapore"
    assert attribution["retrieved_on"] == "2026-09-17"
    assert attribution["dataset_url"].startswith("https://datamall.lta.gov.sg/")
    assert attribution["licence_url"] in attribution["notice"]
