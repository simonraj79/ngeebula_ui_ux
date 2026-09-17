"""Black-box acceptance checks derived from the published PS1 brief."""

from __future__ import annotations

import copy
import csv
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path

import pytest

from backend.ps1_data import load_instance
from backend.ps1_solver import solve
from backend.ps1_validator import validate_submission


ROOT = Path(__file__).parents[1]
INSTANCE = load_instance(ROOT / "data" / "ps1" / "01_data")
SAMPLE = ROOT / "data" / "ps1" / "03_submission_sample"


def _read(name: str) -> list[dict[str, str]]:
    with (SAMPLE / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def sample() -> dict:
    return {
        "scenario": "A",
        "schedule_access": _read("SCHEDULE_ACCESS.csv"),
        "schedule_occupancy": _read("SCHEDULE_OCCUPANCY.csv"),
        "results": _read("RESULTS.csv"),
    }


@pytest.fixture(scope="module")
def solved_a() -> dict:
    result = solve(INSTANCE, "A", time_limit_seconds=10)
    assert result["status"] == "success"
    return result


def _rules(report: dict) -> set[str]:
    return {item["rule"] for item in report["hard_violations"]}


def _move_activity_week(submission: dict, activity_id: str, old_week: int, new_week: int) -> None:
    for row in submission["schedule_access"]:
        if row["activity_id"] == activity_id and int(row["week"]) == old_week:
            row["week"] = str(new_week)
    for row in submission["schedule_occupancy"]:
        if row["activity_id"] == activity_id and int(row["week"]) == old_week:
            row["week"] = str(new_week)


def test_official_sample_passes_and_reproduces_reported_overrun(sample):
    report = validate_submission(INSTANCE, sample, "A")
    assert report["feasible"]
    assert report["hard_violations"] == []
    assert report["validator"]["complete"] is False
    assert report["validator"]["coverage"]["closure"] == "unverified"
    assert report["soft_scores"]["overrun_days_total"] == 28
    assert sum(int(row["overrun_days"]) for row in sample["results"]) == 28
    assert {row["activity_id"] for row in sample["schedule_access"]} == set(INSTANCE.activities_by_id)


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
def test_committed_release_csvs_and_report_witness_revalidate_completely(scenario):
    release = ROOT / "submissions" / "ps1"

    def read_csv(name: str) -> list[dict[str, str]]:
        with (release / scenario / name).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    saved_report = json.loads((release / "reports" / f"{scenario}.validation.json").read_text(encoding="utf-8"))
    submission = {
        "scenario": scenario,
        "schedule_access": read_csv("SCHEDULE_ACCESS.csv"),
        "schedule_occupancy": read_csv("SCHEDULE_OCCUPANCY.csv"),
        "results": read_csv("RESULTS.csv"),
        "physical_night_witness": saved_report["physical_night_witness"],
    }
    report = validate_submission(INSTANCE, submission, scenario)
    assert report["feasible"] is True
    assert report["complete"] is True
    assert report["hard_violations"] == []
    assert report["coverage"]["closure"] == "checked"
    assert {row["activity_id"] for row in submission["schedule_access"]} == set(INSTANCE.activities_by_id)
    for key in ("objective_score", "overrun_days_total", "excess_access_nights_total", "eclo_nights_total"):
        assert report["soft_scores"][key] == saved_report["metrics"][key]


def test_omitted_results_are_rejected(sample):
    sample.pop("results")
    assert not validate_submission(INSTANCE, sample, "A")["feasible"]


def test_malformed_or_incomplete_results_are_rejected(sample):
    sample["results"] = [{"scenario": "B", "contract_number": "C001", "overrun_days": "wrong"}]
    assert not validate_submission(INSTANCE, sample, "A")["feasible"]


def test_omitted_access_and_occupancy_fails_workload(sample):
    removed = sample["schedule_access"].pop(0)
    sample["schedule_occupancy"] = [
        row for row in sample["schedule_occupancy"]
        if not (row["activity_id"] == removed["activity_id"] and row["week"] == removed["week"])
    ]
    assert "workload" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_duplicate_sequence_and_second_access_same_week_are_rejected(sample):
    duplicate = copy.deepcopy(sample["schedule_access"][0])
    sample["schedule_access"].append(duplicate)
    rules = _rules(validate_submission(INSTANCE, sample, "A"))
    assert {"workload", "weekly_activity"} <= rules


def test_bogus_location_and_blank_group_are_rejected(sample):
    sample["schedule_occupancy"][0]["location_id"] = "SEC:BOGUS"
    sample["schedule_occupancy"][1]["co_share_group"] = ""
    rules = _rules(validate_submission(INSTANCE, sample, "A"))
    assert "schema" in rules
    assert "occupancy" in rules


def test_capacity_counts_distinct_possessions_not_activity_rows(sample):
    location, week = "PLAT:BET:S15:EB", "25"
    rows = [row for row in sample["schedule_occupancy"] if row["location_id"] == location and row["week"] == week]
    assert len({row["activity_id"] for row in rows}) > INSTANCE.capacity_for(location, int(week))
    for row in rows:
        row["co_share_group"] = f"separate-{row['activity_id']}"
    assert "capacity" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_pm_cannot_share_a_possession(sample):
    _move_activity_week(sample, "A075", 29, 2)
    for row in sample["schedule_occupancy"]:
        if row["activity_id"] == "A075":
            row["co_share_group"] = "b1"
    assert "mix" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_weekly_allocation_rejects_access_night_above_contract_cap(sample):
    sample["schedule_access"][0]["access_night"] = "99"
    assert "weekly_allocation" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_workfront_cap_rejects_third_activity_on_same_contract_night(sample):
    target = next(
        row for row in sample["schedule_access"]
        if INSTANCE.activities_by_id[row["activity_id"]].contract_number == "C001"
        and row["activity_id"] not in {"A001", "A007"}
    )
    old_week = int(target["week"])
    _move_activity_week(sample, target["activity_id"], old_week, 22)
    target["week"], target["access_night"] = "22", "3"
    assert "workfront" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_scenario_a_forbids_eclo(sample):
    sample["schedule_access"][0]["eclo"] = "1"
    assert "eclo" in _rules(validate_submission(INSTANCE, sample, "A"))


def test_scenario_c_requires_each_lines_eclo_within_two_week_span(sample):
    candidates = []
    for row in sample["schedule_access"]:
        line = INSTANCE.locations_by_id[INSTANCE.activities_by_id[row["activity_id"]].start_location_id].line_code
        if line == "ALP":
            candidates.append(row)
    first = min(candidates, key=lambda row: int(row["week"]))
    last = max(candidates, key=lambda row: int(row["week"]))
    first["eclo"] = last["eclo"] = "1"
    assert int(last["week"]) - int(first["week"]) > 1
    assert "eclo_continuity" in _rules(validate_submission(INSTANCE, sample, "C"))


def test_scenario_b_rejects_sample_contracts_finishing_after_planned_date(sample):
    rules = _rules(validate_submission(INSTANCE, sample, "B"))
    assert "planned_date" in rules


def test_documented_pc_and_c_mix_is_accepted_by_legal_mix_rule():
    from backend.ps1_validator import _legal_mix

    assert _legal_mix(["PC", "C", "C", "C"])
    assert _legal_mix(["C", "C", "C", "C"])
    assert not _legal_mix(["PC", "PC"])
    assert not _legal_mix(["PM", "C"])


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("schedule_access", "week", 1.5),
        ("schedule_access", "access_seq", True),
        ("schedule_occupancy", "week", 2.25),
        ("results", "overrun_days", 0.5),
    ],
)
def test_fractional_or_boolean_integer_fields_return_violations_not_exceptions(solved_a, section, field, value):
    mutated = copy.deepcopy(solved_a)
    mutated[section][0][field] = value
    report = validate_submission(INSTANCE, mutated, "A")
    assert not report["feasible"]
    assert _rules(report) & {"schema", "results"}


def test_duplicate_occupancy_row_is_rejected(solved_a):
    mutated = copy.deepcopy(solved_a)
    mutated["schedule_occupancy"].append(copy.deepcopy(mutated["schedule_occupancy"][0]))
    assert "occupancy" in _rules(validate_submission(INSTANCE, mutated, "A"))


@pytest.mark.parametrize("bad_witness", [5, "bad", [{"activity_id": "UNKNOWN", "week": 1, "physical_night": 1}]])
def test_malformed_or_unknown_witness_returns_report_not_exception(solved_a, bad_witness):
    mutated = copy.deepcopy(solved_a)
    mutated["physical_night_witness"] = bad_witness
    report = validate_submission(INSTANCE, mutated, "A")
    assert "witness" in _rules(report)
    assert report["coverage"]["closure"] == "invalid"


def test_local_group_must_map_to_one_physical_night(solved_a):
    mutated = copy.deepcopy(solved_a)
    by_group = defaultdict(set)
    for row in mutated["schedule_occupancy"]:
        by_group[(row["location_id"], row["week"], row["co_share_group"])].add(row["activity_id"])
    location_group, aids = next((key, aids) for key, aids in by_group.items() if len(aids) > 1)
    aid = sorted(aids)[0]
    week = location_group[1]
    placement = next(row for row in mutated["physical_night_witness"] if row["activity_id"] == aid and row["week"] == week)
    placement["physical_night"] += 100
    report = validate_submission(INSTANCE, mutated, "A")
    assert "witness" in _rules(report)
    assert report["coverage"]["closure"] == "invalid"


def test_contract_local_access_night_must_map_consistently_to_physical_night(solved_a):
    mutated = copy.deepcopy(solved_a)
    witness = {(row["activity_id"], row["week"]): row for row in mutated["physical_night_witness"]}
    by_local_night = defaultdict(list)
    for row in mutated["schedule_access"]:
        activity = INSTANCE.activities_by_id[row["activity_id"]]
        by_local_night[(activity.contract_number, activity.activity_type, row["week"], row["access_night"])].append(row)
    _, rows = next((key, rows) for key, rows in by_local_night.items() if len(rows) > 1)
    target = rows[0]
    witness[(target["activity_id"], target["week"])]["physical_night"] += 100
    report = validate_submission(INSTANCE, mutated, "A")
    assert "witness" in _rules(report)
    assert report["coverage"]["closure"] == "invalid"


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
def test_solver_returns_complete_independently_validated_scenario(scenario):
    solved = solve(INSTANCE, scenario, time_limit_seconds=10)
    assert solved["status"] == "success"
    assert solved["feasible"] is True
    report = validate_submission(INSTANCE, solved, scenario)
    assert report["feasible"], report["hard_violations"]
    assert report["validator"]["complete"] is True
    assert report["validator"]["coverage"]["closure"] == "checked"
    rows_by_activity = {}
    for row in solved["schedule_access"]:
        rows_by_activity.setdefault(row["activity_id"], []).append(row)
    assert set(rows_by_activity) == set(INSTANCE.activities_by_id)
    for activity_id, activity in INSTANCE.activities_by_id.items():
        delivered = sum(1.5 if row["eclo"] else 1 for row in rows_by_activity[activity_id])
        assert delivered >= float(activity.total_accesses)

    # The solver has a global physical-night witness that the public CSV schema
    # lacks. Co-sharing waives a closure only at an actually shared span
    # location; it must not erase buffer collisions elsewhere along the pair.
    possessions = defaultdict(list)
    for row in solved["physical_night_witness"]:
        possessions[(row["week"], row["physical_night"])].append(row["activity_id"])
    for (week, night), activity_ids in possessions.items():
        for left, right in combinations(activity_ids, 2):
            left_span, right_span = set(INSTANCE.activity_span_ids(left)), set(INSTANCE.activity_span_ids(right))
            left_project = INSTANCE.projects_by_contract[INSTANCE.activities_by_id[left].contract_number]
            right_project = INSTANCE.projects_by_contract[INSTANCE.activities_by_id[right].contract_number]
            shared = left_span & right_span
            mix = [left_project.access_type, right_project.access_type]
            co_share_legal = "PM" not in mix and not (mix.count("PC") > 1)
            waived = shared if co_share_legal else set()
            collision = (
                (set(INSTANCE.closure_footprint(left)) & right_span)
                | (set(INSTANCE.closure_footprint(right)) & left_span)
            ) - waived
            assert not collision, (
                f"scenario {scenario}, week {week}, night {night}: "
                f"{left}/{right} collide at {sorted(collision)}"
            )
