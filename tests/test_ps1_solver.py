from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from backend.ps1_data import load_instance
from backend.ps1_solver import solve
from backend.ps1_validator import validate_submission


ROOT = Path(__file__).resolve().parents[1]
INSTANCE_DIR = ROOT / "data" / "ps1" / "01_data"
SAMPLE_DIR = ROOT / "data" / "ps1" / "03_submission_sample"


@pytest.fixture(scope="module")
def ps1_instance():
    return load_instance(INSTANCE_DIR)


def csv_rows(name: str) -> list[dict[str, str]]:
    with (SAMPLE_DIR / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_independent_validator_accepts_organiser_sample(ps1_instance):
    report = validate_submission(ps1_instance, {
        "scenario": "A",
        "schedule_access": csv_rows("SCHEDULE_ACCESS.csv"),
        "schedule_occupancy": csv_rows("SCHEDULE_OCCUPANCY.csv"),
        "results": csv_rows("RESULTS.csv"),
    })
    assert report["feasible"] is True
    assert report["hard_violations"] == []
    assert report["validator"]["official"] is False
    assert report["soft_scores"]["overrun_days_total"] == 28


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
def test_solver_returns_complete_locally_valid_schedule(ps1_instance, scenario):
    result = solve(ps1_instance, scenario=scenario, time_limit_seconds=20)
    assert result["status"] == "success", result.get("explanation")
    assert result["feasible"] is True
    assert result["violations"] == []
    assert {row["activity_id"] for row in result["schedule_access"]} == set(ps1_instance.activities_by_id)
    delivered = {}
    for row in result["schedule_access"]:
        delivered[row["activity_id"]] = delivered.get(row["activity_id"], Decimal("0")) + (
            Decimal("1.5") if row["eclo"] else Decimal("1")
        )
    assert all(delivered[aid] >= activity.total_accesses
               for aid, activity in ps1_instance.activities_by_id.items())
    report = validate_submission(ps1_instance, result, scenario)
    assert report["feasible"] is True, report["hard_violations"]
    assert len(result["results"]) == len(ps1_instance.projects_by_contract)
    if scenario == "A":
        assert not any(row["eclo"] for row in result["schedule_access"])
        assert result["metrics"]["excess_access_nights_total"] == 0
    if scenario == "B":
        assert result["metrics"]["overrun_days_total"] == 0
        assert result["metrics"]["objective_score"] < 897
        assert result["metrics"]["eclo_nights_total"] < 115


def test_workload_omission_is_a_hard_failure(ps1_instance):
    access = csv_rows("SCHEDULE_ACCESS.csv")
    occupancy = csv_rows("SCHEDULE_OCCUPANCY.csv")
    access = [row for row in access if row["activity_id"] != "A001"]
    occupancy = [row for row in occupancy if row["activity_id"] != "A001"]
    report = validate_submission(ps1_instance, {
        "scenario": "A", "schedule_access": access, "schedule_occupancy": occupancy,
        "results": csv_rows("RESULTS.csv"),
    })
    assert report["feasible"] is False
    assert any(item["rule"] == "workload" and "A001" in item["detail"]
               for item in report["hard_violations"])


def test_scenario_a_rejects_eclo_and_capacity_excess(ps1_instance):
    access = csv_rows("SCHEDULE_ACCESS.csv")
    occupancy = csv_rows("SCHEDULE_OCCUPANCY.csv")
    access[0] = access[0] | {"eclo": "1"}
    target = occupancy[0]
    occupancy.append(target | {"activity_id": target["activity_id"], "co_share_group": "extra-a"})
    occupancy.append(target | {"activity_id": target["activity_id"], "co_share_group": "extra-b"})
    report = validate_submission(ps1_instance, {
        "scenario": "A", "schedule_access": access, "schedule_occupancy": occupancy,
        "results": csv_rows("RESULTS.csv"),
    })
    rules = {item["rule"] for item in report["hard_violations"]}
    assert "eclo" in rules
    assert "capacity" in rules


@pytest.mark.parametrize("mutation", ["missing", "wrong", "mixed", "malformed"])
def test_results_must_match_schedule_exactly(ps1_instance, mutation):
    results = csv_rows("RESULTS.csv")
    if mutation == "missing":
        results = results[:-1]
    elif mutation == "wrong":
        results[0] = results[0] | {"overrun_days": "99"}
    elif mutation == "mixed":
        results[0] = results[0] | {"scenario": "B"}
    else:
        results[0] = results[0] | {"simulated_completion_date": "not-a-date"}
    report = validate_submission(ps1_instance, {
        "scenario": "A",
        "schedule_access": csv_rows("SCHEDULE_ACCESS.csv"),
        "schedule_occupancy": csv_rows("SCHEDULE_OCCUPANCY.csv"),
        "results": results,
    })
    assert report["feasible"] is False
    assert any(item["rule"] == "results" for item in report["hard_violations"])
    assert "objective_score" not in report["soft_scores"]
    assert "formula_version" not in report["soft_scores"]


def test_week_specific_capacity_override_changes_solver_input(ps1_instance):
    location = ps1_instance.activity_span_ids("A048")[0]
    week = ps1_instance.week_for_date(ps1_instance.activities_by_id["A048"].planned_start_date)
    changed = ps1_instance.with_capacity_overrides({(location, week): 0})
    assert ps1_instance.capacity_for(location, week) > 0
    assert changed.capacity_for(location, week) == 0
    result = solve(changed, scenario="A", time_limit_seconds=20)
    assert result["status"] == "success"
    a048_weeks = {row["week"] for row in result["schedule_access"] if row["activity_id"] == "A048"}
    assert week not in a048_weeks


def test_baseline_reports_churn_without_claiming_minimality(ps1_instance):
    first = solve(ps1_instance, scenario="A", time_limit_seconds=20)
    repeated = solve(ps1_instance, scenario="A", time_limit_seconds=20, baseline=first)
    assert repeated["status"] == "success"
    assert repeated["metrics"]["baseline_accesses_compared"] == len(first["schedule_access"])
    assert repeated["metrics"]["moved_activity_week_accesses"] == 0


def test_scenario_c_includes_strict_supply_candidate_and_avoids_dominated_result(ps1_instance):
    scenario_a = solve(ps1_instance, scenario="A", time_limit_seconds=20)
    result = solve(ps1_instance, scenario="C", time_limit_seconds=20)
    assert result["status"] == "success"
    assert result["selection"]["global_optimality_proven"] is False
    assert result["metrics"]["objective_score"] <= scenario_a["metrics"]["objective_score"]


def test_consist_buffer_only_overlap_is_separated_and_rejected(ps1_instance):
    result = solve(ps1_instance, scenario="A", time_limit_seconds=20)
    witness = {(row["activity_id"], row["week"]): row["physical_night"]
               for row in result["physical_night_witness"]}
    rows = result["schedule_access"]
    pair = None
    for index, left in enumerate(rows):
        left_project = ps1_instance.projects_by_contract[
            ps1_instance.activities_by_id[left["activity_id"]].contract_number]
        if left_project.nature_of_activity != "Non-live (Consist)":
            continue
        for right in rows[index + 1:]:
            right_project = ps1_instance.projects_by_contract[
                ps1_instance.activities_by_id[right["activity_id"]].contract_number]
            if (right["week"] != left["week"] or right["activity_id"] == left["activity_id"]
                    or right_project.nature_of_activity != "Non-live (Consist)"):
                continue
            left_span = set(ps1_instance.activity_span_ids(left["activity_id"]))
            right_span = set(ps1_instance.activity_span_ids(right["activity_id"]))
            closure_overlap = (set(ps1_instance.closure_footprint(left["activity_id"]))
                               & set(ps1_instance.closure_footprint(right["activity_id"])))
            if not left_span & right_span and closure_overlap:
                pair = left, right
                break
        if pair:
            break
    assert pair is not None, "published workload should contain a buffer-only Consist collision"
    left, right = pair
    assert witness[(left["activity_id"], left["week"])] != witness[(right["activity_id"], right["week"])]

    forced_night = witness[(left["activity_id"], left["week"])]
    mutated = result | {"physical_night_witness": [
        row | {"physical_night": forced_night}
        if row["activity_id"] == right["activity_id"] and row["week"] == right["week"] else row
        for row in result["physical_night_witness"]
    ]}
    report = validate_submission(ps1_instance, mutated, "A")
    assert report["feasible"] is False
    assert any(item["rule"] == "closure" for item in report["hard_violations"])


def test_post_horizon_capacity_assumption_is_explicit(ps1_instance):
    result = solve(ps1_instance, scenario="A", time_limit_seconds=20)
    assert any(item["code"] == "extending_flat_nominal_assumption"
               for item in result["explanations"])


def test_timeout_or_impossible_construction_is_unresolved_not_infeasible(ps1_instance):
    location = ps1_instance.activity_span_ids("A075")[0]
    overrides = {(location, week): 0 for week in range(1, ps1_instance.horizon_weeks + 1)}
    changed = ps1_instance.with_capacity_overrides(overrides)
    result = solve(changed, scenario="A", time_limit_seconds=20,
                   disruptions={"location_supply": {location: 0}})
    assert result["status"] == "unresolved"
    assert result["feasible"] is False
    assert result["schedule_access"] == []
    assert "No placement found" in result["explanation"]
