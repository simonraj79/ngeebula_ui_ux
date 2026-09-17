"""Integration checks for the read-only planning showcase and its offline UI.

The comparison examples are intentionally synthetic.  These tests exercise the
HTTP and Streamlit boundaries so a visually convincing result cannot quietly
write live planning state, call Gemini, or overstate an incomplete plan.
"""
from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

from test_frontend import APP, button, metric_value, navigate, ui, visible_copy


ROOT = Path(__file__).resolve().parents[1]


SCENARIO_EXPECTATIONS = {
    "joint_planning": {
        "manual_proxy": ("incomplete", 1),
        "priority_first_fit": ("incomplete", 1),
        "cp_sat": ("complete", 2),
    },
    "straightforward": {
        "manual_proxy": ("complete", 2),
        "priority_first_fit": ("complete", 2),
        "cp_sat": ("complete", 2),
    },
    "no_capacity": {
        "manual_proxy": ("incomplete", 1),
        "priority_first_fit": ("incomplete", 1),
        "cp_sat": ("infeasible", 0),
    },
}


def api_state(api) -> dict:
    """Capture every public persisted collection touched by planning workflows."""
    return {
        "jobs": api.client.get("/jobs/").json(),
        "engineers": api.client.get("/engineers/").json(),
        "audit": api.client.get("/audit-logs/").json(),
    }


def roi_payload(*, baseline: str, setup: float = 1000, monthly: float = 100) -> dict:
    return {
        "planning_shifts_per_month": 10,
        "minutes_per_cycle": {
            "manual_proxy": 60,
            "priority_first_fit": 30,
            "cp_sat": 15,
        },
        "loaded_hourly_cost_sgd": 80,
        "initial_cost_sgd": {
            "manual_proxy": 0,
            "priority_first_fit": 0,
            "cp_sat": setup,
        },
        "monthly_operating_cost_sgd": {
            "manual_proxy": 0,
            "priority_first_fit": 0,
            "cp_sat": monthly,
        },
        "baseline_method": baseline,
    }


def test_showcase_endpoints_are_read_only_and_never_call_gemini(api, monkeypatch):
    def unexpected_gemini(*_args, **_kwargs):
        raise AssertionError("The synthetic showcase must not call Gemini")

    monkeypatch.setattr(api.main, "get_gemini_client", unexpected_gemini)
    before = api_state(api)

    for scenario, expected in SCENARIO_EXPECTATIONS.items():
        response = api.client.post("/schedule/compare", json={"scenario": scenario})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["scenario"] == scenario
        assert result["synthetic"] is True
        assert result["persisted"] is False
        assert result["can_apply"] is False
        methods = {row["method_id"]: row for row in result["methods"]}
        assert set(methods) == set(expected)
        for method, (status, scheduled) in expected.items():
            assert methods[method]["status"] == status
            assert methods[method]["metrics"]["scheduled_jobs"] == scheduled
            assert methods[method]["metrics"]["candidate_jobs"] == 2
        if scenario == "no_capacity":
            # A partial sequential result is not presented as a fully feasible plan.
            assert methods["cp_sat"]["metrics"]["on_time_jobs"] == 0
            assert len(methods["cp_sat"]["unscheduled"]) == 2

    for baseline in ("manual_proxy", "priority_first_fit"):
        response = api.client.post("/schedule/roi", json=roi_payload(baseline=baseline))
        assert response.status_code == 200, response.text
        assert response.json()["assumptions"]["baseline_method"] == baseline

    response = api.client.get("/schedule/readiness")
    assert response.status_code == 200, response.text
    assert api_state(api) == before


def test_roi_endpoint_exposes_zero_cost_and_negative_cases_without_inventing_roi(api):
    zero_cost = api.client.post(
        "/schedule/roi", json=roi_payload(baseline="manual_proxy", setup=0, monthly=0)
    )
    assert zero_cost.status_code == 200, zero_cost.text
    zero_joint = zero_cost.json()["calculated_outputs"]["cp_sat"]
    assert zero_joint["first_year_roi_percent"] is None
    assert "undefined" in zero_joint["roi_note"].casefold()

    negative_payload = roi_payload(baseline="priority_first_fit", setup=1000, monthly=100)
    negative_payload["planning_shifts_per_month"] = 0
    negative_payload["loaded_hourly_cost_sgd"] = 0
    negative = api.client.post("/schedule/roi", json=negative_payload)
    assert negative.status_code == 200, negative.text
    negative_joint = negative.json()["calculated_outputs"]["cp_sat"]
    assert negative_joint["first_year_net_benefit_sgd"] < 0
    assert negative_joint["first_year_roi_percent"] < 0
    assert negative_joint["payback_months"] is None


def test_readiness_reports_location_crew_and_deadline_blockers_without_solving(api, monkeypatch):
    def unexpected_solver(*_args, **_kwargs):
        raise AssertionError("Readiness is a preflight and must not run the solver")

    def unexpected_gemini(*_args, **_kwargs):
        raise AssertionError("Readiness must not call Gemini")

    window_start, window_end = api.main.solver.next_window()
    created = api.client.post(
        "/jobs/parse-and-create",
        json={
            "name": "Preflight blocker",
            "description": "Specialist work at a manual depot location.",
            "line": "North South Line",
            "track": "Manual depot bay",
            "deadline": (window_end + timedelta(hours=1)).isoformat(),
            "duration_mins": 60,
            "required_skills": ["Overhead power"],
            "engineers_needed": 2,
            "created_by": "Showcase test",
        },
    )
    assert created.status_code in (200, 201), created.text
    job_id = created.json()["job"]["job_id"]

    monkeypatch.setattr(api.main.solver, "solve_mrt_schedule", unexpected_solver)
    monkeypatch.setattr(api.main, "get_gemini_client", unexpected_gemini)

    # This represents a legacy bad row: Clementi is on EWL, not NSL.  The public
    # create and patch contracts reject it, while readiness must still diagnose it.
    with api.database.SessionLocal() as session:
        job = session.get(api.database.RepairJob, job_id)
        job.track = "Clementi"
        job.deadline = api.main.to_db(window_start + timedelta(minutes=30))
        session.commit()

    before = api_state(api)
    response = api.client.get("/schedule/readiness")
    assert response.status_code == 200, response.text
    result = response.json()
    check = next(row for row in result["checks"] if row["job_id"] == job_id)
    assert {issue["code"] for issue in check["issues"]} >= {"location", "crew", "deadline"}
    assert result["blocked_count"] == 1
    assert result["ready_for_solver"] is False
    assert "preliminary" in result["explanation"].casefold()
    assert api_state(api) == before


def test_catalog_uses_official_station_snapshot_without_mutating_its_sources(api, monkeypatch):
    full_stations = json.loads((ROOT / "backend" / "stations_db.json").read_text(encoding="utf-8"))
    reference = api.main.lta_reference.load_reference(ROOT / "backend" / "lta_station_reference.json")
    original_stations = copy.deepcopy(full_stations)
    original_reference = copy.deepcopy(reference)
    monkeypatch.setattr(api.main, "STATIONS_DB", full_stations)
    monkeypatch.setattr(api.main, "LTA_REFERENCE", reference)

    before = api_state(api)
    response = api.client.get("/catalog/")
    assert response.status_code == 200, response.text
    catalog = response.json()
    by_code = {row["code"]: row for row in catalog["stations"]}
    assert by_code["CE1"]["name"] == "Bayfront"
    assert by_code["CE1"]["old_name"] == "Promenade"
    assert by_code["CE1"]["reference_status"] == "corrected"
    assert by_code["DT4"]["name"] == "Hume"
    assert by_code["DT4"]["reference_status"] == "official"
    assert catalog["station_reference"]["publisher"] == "Land Transport Authority, Singapore"
    assert catalog["station_reference"]["retrieved_on"] == "2026-09-17"
    assert "Singapore Open Data Licence" in catalog["station_reference"]["notice"]

    def unexpected_gemini(*_args, **_kwargs):
        raise AssertionError("A station mismatch must be rejected before Gemini")

    monkeypatch.setattr(api.main, "get_gemini_client", unexpected_gemini)
    _, window_end = api.main.solver.next_window()
    rejected = api.client.post(
        "/jobs/parse-and-create",
        json={
            "name": "Conflicting station",
            "description": "The station code and station name disagree.",
            "line": "Circle Line",
            "track": "CE1 Promenade",
            "station_code": "CE1",
            "deadline": (window_end + timedelta(hours=1)).isoformat(),
            "created_by": "Showcase test",
        },
    )
    assert rejected.status_code == 400, rejected.text
    assert full_stations == original_stations
    assert reference == original_reference
    assert api_state(api) == before


def test_readiness_pass_does_not_claim_joint_feasibility(api):
    window_start, _ = api.main.solver.next_window()
    for number, track in enumerate(("Manual bay A", "Manual bay B"), start=1):
        response = api.client.post(
            "/jobs/parse-and-create",
            json={
                "name": f"Individually feasible work {number}",
                "description": "Both qualified engineers are needed for the whole deadline window.",
                "line": "North South Line",
                "track": track,
                "deadline": (window_start + timedelta(minutes=60)).isoformat(),
                "duration_mins": 60,
                "required_skills": ["Track maintenance"],
                "engineers_needed": 2,
                "created_by": "Showcase test",
            },
        )
        assert response.status_code in (200, 201), response.text

    readiness = api.client.get("/schedule/readiness")
    assert readiness.status_code == 200, readiness.text
    preliminary = readiness.json()
    assert preliminary["candidate_count"] == 2
    assert preliminary["blocked_count"] == 0
    assert preliminary["ready_for_solver"] is True
    assert "only generating a proposal" in preliminary["explanation"].casefold()

    before = api_state(api)
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 409, proposal.text
    assert api_state(api) == before


@pytest.mark.parametrize(
    "change",
    [
        {"minutes_per_cycle": {"manual_proxy": 1.0, "priority_first_fit": 1.0}},
        {
            "minutes_per_cycle": {
                "manual_proxy": 1.0,
                "priority_first_fit": 1.0,
                "cp_sat": 1.0,
                "invented": 1.0,
            }
        },
        {"minutes_per_cycle": {"manual_proxy": 1.0, "priority_first_fit": 1.0, "cp_sat": True}},
        {"minutes_per_cycle": {"manual_proxy": 1.0, "priority_first_fit": 1.0, "cp_sat": 100000001.0}},
        {
            "initial_cost_sgd": {
                "manual_proxy": 0.0,
                "priority_first_fit": 0.0,
                "cp_sat": 0.0,
                "invented": 0.0,
            }
        },
    ],
)
def test_roi_endpoint_rejects_incomplete_unknown_boolean_and_out_of_bounds_values(api, change):
    payload = roi_payload(baseline="manual_proxy")
    payload.update(change)
    before = api_state(api)
    response = api.client.post("/schedule/roi", json=payload)
    assert response.status_code == 422, response.text
    assert api_state(api) == before


def test_compare_page_runs_all_scenarios_and_hides_a_stale_result(ui):
    navigate(ui, "Compare approaches")
    expected_metrics = {
        "joint_planning": ("1 / 2", "1 / 2", "2 / 2"),
        "straightforward": ("2 / 2", "2 / 2", "2 / 2"),
        "no_capacity": ("1 / 2", "1 / 2", "0 / 2"),
    }
    labels = ("Requested slots", "First available slot", "Joint planning")
    for scenario, values in expected_metrics.items():
        ui.selectbox(key="compare_scenario").select(scenario).run()
        ui.button(key="compare_run").click().run()
        assert not ui.exception
        assert tuple(metric_value(ui, label) for label in labels) == values

    # Changing the input invalidates the displayed result until the user reruns.
    ui.selectbox(key="compare_scenario").select("joint_planning").run()
    assert not ui.metric
    copy = visible_copy(ui)
    assert "Run a comparison to reveal the outcomes" in copy
    assert "No complete plan fits these inputs" not in copy


def test_savings_page_supports_both_baselines_and_handles_nonpositive_returns(ui):
    navigate(ui, "Compare approaches")
    ui.radio(key="comparison_view").set_value("Estimated savings").run()
    assert "versus requested slots" in visible_copy(ui).casefold()
    requested_slots_benefit = metric_value(ui, "First-year net benefit")

    ui.radio(key="roi_baseline").set_value("priority_first_fit").run()
    assert ui.radio(key="roi_baseline").value == "priority_first_fit"
    assert metric_value(ui, "First-year net benefit") != requested_slots_benefit

    ui.number_input(key="roi_shifts").set_value(0)
    ui.number_input(key="roi_rate").set_value(0.0)
    ui.number_input(key="roi_initial").set_value(3000.0)
    ui.number_input(key="roi_monthly").set_value(100.0).run()
    copy = visible_copy(ui)
    assert "do not recover the extra cost" in copy
    assert "Illustrative result versus" not in copy
    assert float(metric_value(ui, "First-year net benefit").replace("S$", "").replace(",", "")) < 0

    ui.number_input(key="roi_initial").set_value(0.0)
    ui.number_input(key="roi_monthly").set_value(0.0).run()
    assert metric_value(ui, "First-year ROI") == "Not defined"
    assert "undefined" in visible_copy(ui).casefold()


def test_savings_assumptions_survive_leaving_the_view(ui, caplog, recwarn):
    navigate(ui, "Compare approaches")
    ui.radio(key="comparison_view").set_value("Estimated savings").run()
    caplog.clear()

    ui.radio(key="roi_baseline").set_value("priority_first_fit")
    ui.number_input(key="roi_shifts").set_value(18)
    ui.number_input(key="roi_rate").set_value(75.0)
    ui.number_input(key="roi_minutes_manual_proxy").set_value(70.0)
    ui.number_input(key="roi_minutes_priority_first_fit").set_value(40.0)
    ui.number_input(key="roi_minutes_cp_sat").set_value(12.0)
    ui.number_input(key="roi_initial").set_value(0.0)
    ui.number_input(key="roi_monthly").set_value(0.0).run()

    first_result = metric_value(ui, "First-year net benefit")
    assert metric_value(ui, "First-year ROI") == "Not defined"
    assert metric_value(ui, "Estimated payback") == "No setup premium"
    assert ui.session_state["roi_input_draft"] == {
        "roi_baseline": "priority_first_fit",
        "roi_shifts": 18,
        "roi_rate": 75.0,
        "roi_initial": 0.0,
        "roi_monthly": 0.0,
        "roi_minutes_manual_proxy": 70.0,
        "roi_minutes_priority_first_fit": 40.0,
        "roi_minutes_cp_sat": 12.0,
    }

    ui.radio(key="comparison_view").set_value("Data & evidence").run()
    assert "Where the information comes from" in visible_copy(ui)
    ui.radio(key="comparison_view").set_value("Estimated savings").run()

    assert ui.radio(key="roi_baseline").value == "priority_first_fit"
    assert ui.number_input(key="roi_shifts").value == 18
    assert ui.number_input(key="roi_rate").value == 75.0
    assert ui.number_input(key="roi_minutes_manual_proxy").value == 70.0
    assert ui.number_input(key="roi_minutes_priority_first_fit").value == 40.0
    assert ui.number_input(key="roi_minutes_cp_sat").value == 12.0
    assert ui.number_input(key="roi_initial").value == 0.0
    assert ui.number_input(key="roi_monthly").value == 0.0
    assert metric_value(ui, "First-year net benefit") == first_result
    assert metric_value(ui, "Estimated payback") == "No setup premium"

    emitted = " ".join([caplog.text, *(str(item.message) for item in recwarn)]).casefold()
    assert not ("session state" in emitted and "default value" in emitted)


@pytest.mark.parametrize(
    ("page", "select_view", "search", "phrases"),
    [
        (
            "Glossary",
            None,
            "satisfiability",
            ("CP-SAT · Solver", "mathematical optimisation", "1 of 20 terms"),
        ),
        (
            "Compare approaches",
            "Data & evidence",
            None,
            ("Where the information comes from", "Official sources reviewed", "Needed from the operator"),
        ),
    ],
)
def test_reference_views_work_offline(monkeypatch, page, select_view, search, phrases):
    def offline(*_args, **_kwargs):
        raise AssertionError("Reference views must not depend on backend or network calls")

    monkeypatch.syspath_prepend(str(APP.parent))
    monkeypatch.setattr(requests, "request", offline)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["page"] = page
    app.run()
    if select_view:
        app.radio(key="comparison_view").set_value(select_view).run()
    if search:
        app.text_input(key="glossary_search").set_value(search).run()
    assert not app.exception
    copy = visible_copy(app)
    for phrase in phrases:
        assert phrase in copy
