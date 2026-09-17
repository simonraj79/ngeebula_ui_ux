from __future__ import annotations

import math
from datetime import datetime

import pytest

from backend.planning_comparison import calculate_roi, run_planning_comparison


def methods(result):
    return {row["method_id"]: row for row in result["methods"]}


@pytest.mark.parametrize("scenario", ["joint_planning", "straightforward", "no_capacity"])
def test_comparison_is_read_only_explicit_and_uses_one_fair_input(scenario):
    result = run_planning_comparison(scenario)
    assert result["synthetic"] is True
    assert result["persisted"] is False
    assert result["can_apply"] is False
    assert len(result["commitments"]) == 1
    assert {row["metrics"]["candidate_jobs"] for row in result["methods"]} == {len(result["candidates"])}
    assert {row["metrics"]["fixed_commitments_preserved"] for row in result["methods"]} == {1}
    for method in result["methods"]:
        assert method["metrics"]["scheduled_jobs"] + method["metrics"]["unscheduled_jobs"] == len(result["candidates"])
        assert {str(row["job_id"]) for row in method["schedule"]}.isdisjoint(
            {str(row["job_id"]) for row in method["unscheduled"]}
        )
    assert result["roi"]["status"] == "assumptions_required"
    assert "safety" in result["roi"]["unmonetized"]
    for method in result["methods"]:
        for row in method["schedule"]:
            row_start = datetime.fromisoformat(row["scheduled_start"])
            row_end = datetime.fromisoformat(row["scheduled_end"])
            for fixed in result["commitments"]:
                fixed_start = datetime.fromisoformat(fixed["scheduled_start"])
                fixed_end = datetime.fromisoformat(fixed["scheduled_end"])
                if row_start < fixed_end and fixed_start < row_end:
                    assert not (
                        (row["line"], row["track"]) == (fixed["line"], fixed["track"])
                        or set(row["assigned_engineer_ids"]) & set(fixed["assigned_engineer_ids"])
                    )


def test_joint_planning_scenario_shows_greedy_limit_and_complete_cp_sat_plan():
    result = run_planning_comparison("joint_planning")
    by_method = methods(result)
    assert by_method["manual_proxy"]["metrics"]["scheduled_jobs"] == 1
    assert by_method["priority_first_fit"]["metrics"]["scheduled_jobs"] == 1
    assert by_method["cp_sat"]["metrics"]["scheduled_jobs"] == 2
    assert by_method["cp_sat"]["metrics"]["on_time_jobs"] == 2
    assert by_method["manual_proxy"]["status"] == "incomplete"
    assert by_method["priority_first_fit"]["status"] == "incomplete"
    assert by_method["cp_sat"]["status"] == "complete"
    assert by_method["cp_sat"]["solver_status"] in {"OPTIMAL", "FEASIBLE"}
    assert by_method["cp_sat"]["wall_time_ms"] >= 0
    teams = {row["job_id"]: row["assigned_engineer_ids"] for row in by_method["cp_sat"]["schedule"]}
    assert teams["flexible-1"] == [8102]
    assert teams["specialist-1"] == [8101]


def test_straightforward_scenario_shows_heuristic_can_match_joint_planning():
    by_method = methods(run_planning_comparison("straightforward"))
    assert {row["metrics"]["scheduled_jobs"] for row in by_method.values()} == {2}
    assert {row["metrics"]["on_time_jobs"] for row in by_method.values()} == {2}
    assert {row["status"] for row in by_method.values()} == {"complete"}


def test_no_capacity_preserves_all_or_none_solver_policy_and_exposes_partial_proxies():
    by_method = methods(run_planning_comparison("no_capacity"))
    assert by_method["manual_proxy"]["metrics"]["scheduled_jobs"] == 1
    assert by_method["priority_first_fit"]["metrics"]["scheduled_jobs"] == 1
    assert by_method["cp_sat"]["metrics"]["scheduled_jobs"] == 0
    assert by_method["cp_sat"]["status"] == "infeasible"
    assert by_method["cp_sat"]["solver_status"] == "INFEASIBLE"
    assert len(by_method["cp_sat"]["unscheduled"]) == 2
    assert all("all-or-none" in row["reason"] for row in by_method["cp_sat"]["unscheduled"])


def test_roi_keeps_assumptions_separate_and_only_values_planning_effort():
    result = calculate_roi(
        planning_shifts_per_month=10,
        minutes_per_cycle={"manual_proxy": 60, "priority_first_fit": 30, "cp_sat": 15},
        loaded_hourly_cost_sgd=80,
        initial_cost_sgd={"cp_sat": 1000},
        monthly_operating_cost_sgd={"cp_sat": 100},
    )
    assert result["assumptions"]["minutes_per_cycle"]["cp_sat"] == 15
    assert result["calculated_outputs"]["manual_proxy"]["annual_planning_hours"] == 120
    assert result["calculated_outputs"]["cp_sat"]["annual_planning_hours"] == 30
    assert result["calculated_outputs"]["cp_sat"]["planning_labour_savings_vs_baseline_sgd"] == 7200
    assert result["calculated_outputs"]["cp_sat"]["first_year_net_benefit_sgd"] == 5000
    assert result["calculated_outputs"]["cp_sat"]["first_year_roi_percent"] == 500
    assert "safety" in result["unmonetized"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"planning_shifts_per_month": -1, "minutes_per_cycle": {"manual_proxy": 1}},
        {"planning_shifts_per_month": math.inf, "minutes_per_cycle": {"manual_proxy": 1}},
        {"planning_shifts_per_month": 1, "minutes_per_cycle": {}},
        {"planning_shifts_per_month": 1, "minutes_per_cycle": {"manual_proxy": float("nan")}},
        {"planning_shifts_per_month": 1, "minutes_per_cycle": {"cp_sat": 1}, "baseline_method": "manual_proxy"},
        {"planning_shifts_per_month": 1, "minutes_per_cycle": {"manual_proxy": 1}, "loaded_hourly_cost_sgd": -2},
        {"planning_shifts_per_month": 1, "minutes_per_cycle": {"manual_proxy": 1}, "initial_cost_sgd": {"unknown": 2}},
    ],
)
def test_roi_rejects_invalid_or_ambiguous_inputs(kwargs):
    with pytest.raises(ValueError):
        calculate_roi(**kwargs)


def test_unknown_comparison_scenario_is_rejected():
    with pytest.raises(ValueError, match="scenario"):
        run_planning_comparison("invented")


def test_zero_initial_cost_leaves_roi_percentage_undefined():
    result = calculate_roi(
        planning_shifts_per_month=1,
        minutes_per_cycle={"manual_proxy": 30, "cp_sat": 10},
        loaded_hourly_cost_sgd=60,
        initial_cost_sgd={"cp_sat": 0},
    )
    cp_sat = result["calculated_outputs"]["cp_sat"]
    assert cp_sat["first_year_roi_percent"] is None
    assert "undefined" in cp_sat["roi_note"]


def test_negative_annual_benefit_is_not_clamped_and_has_no_payback():
    result = calculate_roi(
        planning_shifts_per_month=0.5,
        minutes_per_cycle={"manual_proxy": 10.5, "cp_sat": 10.0},
        loaded_hourly_cost_sgd=1.0,
        initial_cost_sgd={"cp_sat": 100},
        monthly_operating_cost_sgd={"cp_sat": 20},
    )
    cp_sat = result["calculated_outputs"]["cp_sat"]
    assert cp_sat["annual_net_benefit_sgd"] < 0
    assert cp_sat["first_year_roi_percent"] < 0
    assert cp_sat["payback_months"] is None


@pytest.mark.parametrize(
    ("solver_result", "expected_status"),
    [
        ({"status": "unknown", "schedule": [], "ai_explanation": "timed out"}, "unknown"),
        ({"status": "error", "schedule": [], "ai_explanation": "invalid"}, "error"),
    ],
)
def test_solver_unknown_or_error_is_not_mislabeled_as_infeasible(monkeypatch, solver_result, expected_status):
    monkeypatch.setattr(
        "backend.planning_comparison.solver.solve_mrt_schedule",
        lambda *_args, **_kwargs: solver_result,
    )
    cp_sat = methods(run_planning_comparison("joint_planning"))["cp_sat"]
    assert cp_sat["status"] == expected_status
    assert cp_sat["status"] != "infeasible"


def test_zero_acceptance_sequential_result_is_incomplete_not_infeasibility_proof(monkeypatch):
    monkeypatch.setattr(
        "backend.planning_comparison._manual_proxy",
        lambda candidates, _engineers, _commitments: (
            [], [{"job_id": row["id"], "reason": "proxy skipped"} for row in candidates]
        ),
    )
    manual = methods(run_planning_comparison("straightforward"))["manual_proxy"]
    assert manual["status"] == "incomplete"
