from pathlib import Path

import pytest

from backend.ps1_data import PS1DataError, load_ps1_instance


DATA = Path(__file__).parents[1] / "data" / "ps1" / "01_data"


def test_loads_pinned_public_instance_and_indexes_relations():
    instance = load_ps1_instance(DATA)
    assert (len(instance.lines), len(instance.stations), len(instance.sectors)) == (2, 20, 18)
    assert (len(instance.location_supply), len(instance.projects), len(instance.activities)) == (76, 14, 54)
    assert instance.horizon_weeks == 30
    assert instance.week_for_date(instance.activities_by_id["A002"].planned_start_date) == 1
    assert instance.projects_by_contract["C014"].access_type == "PM"


def test_span_contains_inclusive_sectors_and_platforms():
    instance = load_ps1_instance(DATA)
    assert instance.activity_span_ids("A001") == (
        "SEC:BET:S15_S16:EB",
        "SEC:BET:S16_S17:EB",
        "PLAT:BET:S15:EB",
        "PLAT:BET:S16:EB",
        "PLAT:BET:S17:EB",
    )


def test_live_closure_mirrors_bounds_and_crosses_lines_at_interchange():
    instance = load_ps1_instance(DATA)
    live_interchange = next(
        a for a in instance.activities
        if instance.projects_by_contract[a.contract_number].nature_of_activity == "Live"
        and "H01_H02" in a.start_location_id + a.end_location_id
    )
    footprint = set(instance.closure_footprint(live_interchange.activity_id))
    assert "SEC:ALP:H01_H02:EB" in footprint
    assert "SEC:ALP:H01_H02:WB" in footprint
    assert "SEC:BET:H01_H02:EB" in footprint
    assert "SEC:BET:H01_H02:WB" in footprint


def test_rejects_wrong_schema(tmp_path):
    for source in DATA.glob("*.csv"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / "01_LINES.csv").write_text("bad,column\nALP,Alpha\n", encoding="utf-8")
    with pytest.raises(PS1DataError, match="schema does not match"):
        load_ps1_instance(tmp_path)


def test_accepts_upload_mapping_and_serializes_public_data():
    upload = {path.name: path.read_bytes() for path in DATA.glob("*.csv")}
    instance = load_ps1_instance(upload)
    public = instance.to_public_dict()
    assert public["horizon_start"] == "2027-01-04"
    assert public["activities"][0]["total_accesses"] == "2"


def test_capacity_overrides_are_run_local_and_week_specific():
    instance = load_ps1_instance(DATA)
    location_id = instance.location_supply[0].location_id
    changed = instance.with_capacity_overrides([{"location_id": location_id, "week": 3, "capacity": 1}])
    assert changed.capacity_for(location_id, 3) == 1
    assert changed.capacity_for(location_id, 4) == instance.locations_by_id[location_id].supply_capacity
    assert instance.capacity_overrides == {}
    with pytest.raises(PS1DataError, match="outside the horizon"):
        instance.with_capacity_overrides([{"location_id": location_id, "week": 31, "capacity": 1}])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_rejects_nonfinite_activity_workload(value):
    upload = {path.name: path.read_text(encoding="utf-8-sig") for path in DATA.glob("*.csv")}
    upload["08_ACTIVITY_DETAILS.csv"] = upload["08_ACTIVITY_DETAILS.csv"].replace(",2,2027-05-24,", f",{value},2027-05-24,", 1)
    with pytest.raises(PS1DataError, match="finite positive"):
        load_ps1_instance(upload)


def test_rejects_extra_csv_values_even_when_header_is_exact():
    upload = {path.name: path.read_text(encoding="utf-8-sig") for path in DATA.glob("*.csv")}
    lines = upload["01_LINES.csv"].splitlines()
    lines[1] += ",unexpected"
    upload["01_LINES.csv"] = "\n".join(lines) + "\n"
    with pytest.raises(PS1DataError, match="extra or missing columns"):
        load_ps1_instance(upload)
