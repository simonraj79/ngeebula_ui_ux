"""Operator journeys through actual Streamlit widgets and the actual FastAPI API.

Only the HTTP transport is bridged to TestClient. Workflow and persistence are real,
using the disposable database supplied by conftest, never the local running server.
"""
import ast
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
MAIN_PAGES = {"Cockpit", "1 · Requests", "2 · Plan & approve", "3 · Execution"}
UTILITY_LABELS = {"Audit log": "History"}
SGT = ZoneInfo("Asia/Singapore")


@pytest.fixture
def ui(api, monkeypatch):
    def transport(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return api.client.request(method, urlsplit(url).path, **kwargs)

    monkeypatch.setattr(requests, "request", transport)
    monkeypatch.syspath_prepend(str(APP.parent))
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()
    assert not app.exception
    return app


def button(app, label):
    matches = [widget for widget in app.button if widget.label == label]
    assert matches, (label, [widget.label for widget in app.button])
    return matches[0]


def navigate(app, page):
    if page in MAIN_PAGES:
        app.radio(key="main_navigation").set_value(page).run()
    else:
        button(app, UTILITY_LABELS.get(page, page)).click().run()
    assert app.session_state["page"] == page
    assert not app.exception


def metric_value(app, label):
    return next(item.value for item in app.metric if item.label == label)


def select_manual_location(app, track, line="North-South Line (NSL)"):
    app.radio(key="wizard_location_mode").set_value("Train / depot / other site").run()
    app.selectbox(key="wizard_line").select(line)
    app.text_input(key="wizard_track").set_value(track)


def visible_copy(app):
    values = []
    for collection_name in (
        "title",
        "header",
        "subheader",
        "caption",
        "markdown",
        "text",
        "info",
        "warning",
        "success",
        "error",
    ):
        values.extend(str(item.value) for item in getattr(app, collection_name, []))
    values.extend(str(item.label) for item in app.expander)
    values.extend(f"{item.label} {item.value}" for item in app.metric)
    return " ".join(values)


def job_dataframes(app):
    return [
        item.value
        for item in app.dataframe
        if isinstance(item.value, pd.DataFrame) and {"Job ID", "Job", "Assigned crew"} <= set(item.value.columns)
    ]


def create_api_job(api, *, name, priority, track="NS17 Track A", **overrides):
    deadline = api.main.solver.next_window()[1] + timedelta(hours=1)
    payload = {
        "name": name,
        "description": "Track maintenance required for worn track.",
        "line": "North South Line",
        "track": track,
        "deadline": deadline.isoformat(),
        "priority": priority,
        "duration_mins": 60,
        "required_skills": ["Track maintenance"],
        "engineers_needed": 2,
        "created_by": "Frontend test planner",
    }
    payload.update(overrides)
    response = api.client.post(
        "/jobs/parse-and-create",
        json=payload,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["job"]


def next_window_end_function():
    """Load the pure deadline helper without executing the Streamlit application."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "next_window_end"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"datetime": datetime, "timedelta": timedelta, "SGT": SGT}
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace["next_window_end"]


class UiGeminiClient:
    def __init__(self, *, text=None, error=None):
        self.text = text
        self.error = error
        self.models = self

    def generate_content(self, **_kwargs):
        if self.error:
            raise self.error
        return type("Response", (), {"text": self.text})()

    def close(self):
        return None


def configure_ui_gemini(api, monkeypatch, credential, model="gemini-3.8-flash"):
    configuration = api.main.gemini_config.GeminiConfiguration(
        credential=credential, model=model
    )
    monkeypatch.setattr(
        api.main.gemini_config,
        "resolve_configuration",
        lambda: configuration,
    )
    monkeypatch.setattr(api.main.gemini_config, "get_credential", lambda: credential)
    monkeypatch.setattr(api.main.gemini_config, "get_model_name", lambda: model)
    monkeypatch.setattr(
        api.main.gemini_config,
        "public_status",
        lambda: {"configured": True, "source": credential.source, "model": model},
    )


def create_request(ui, api, title="Track maintenance review", manual=False):
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    ui.button(key="wizard_other_asset").click().run()
    ui.text_area(key="wizard_description").set_value("Track maintenance required for worn track.")
    ui.text_input(key="wizard_title").set_value(title)
    ui.button(key="wizard_next_1").click().run()
    select_manual_location(ui, "NS17 Track A")
    ui.button(key="wizard_next_2").click().run()
    if manual:
        ui.selectbox(key="wizard_priority").select("Low")
        ui.radio(key="wizard_assignment_mode").set_value("Manual — choose engineers").run()
        assert not ui.multiselect(key="wizard_assigned_ids").disabled
        ui.multiselect(key="wizard_assigned_ids").set_value([101, 102])
    ui.button(key="wizard_create").click().run()
    assert not ui.exception
    jobs = api.client.get("/jobs/").json()
    assert len(jobs) == 1, [item.value for item in ui.error]
    button(ui, "Back to queue").click().run()
    return jobs[0]


def start_freeform_request(ui, description="Track maintenance required for worn track."):
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    ui.button(key="wizard_other_asset").click().run()
    ui.text_area(key="wizard_description").set_value(description)
    ui.button(key="wizard_next_1").click().run()


@pytest.mark.parametrize(
    ("clock", "expected_day_offset"),
    [
        ((0, 29), 0),
        ((0, 30), 0),
        ((0, 31), 1),
        ((2, 0), 1),
    ],
)
def test_wizard_default_deadline_uses_the_next_full_engineering_window(clock, expected_day_offset):
    helper = next_window_end_function()
    now = datetime(2026, 9, 17, *clock, tzinfo=SGT)

    deadline = helper(now)

    assert deadline == datetime(2026, 9, 17 + expected_day_offset, 5, 0, tzinfo=SGT)


def test_clementi_station_auto_selects_ewl_and_survives_back_before_create(ui, api):
    start_freeform_request(ui)
    assert ui.radio(key="wizard_location_mode").value == "Station / nearby track"
    ui.selectbox(key="wizard_station").select("Clementi").run()
    ui.text_input(key="wizard_location_detail").set_value("westbound platform end")
    assert "East-West Line (EWL)" in visible_copy(ui)
    ui.button(key="wizard_next_2").click().run()
    ui.button(key="wizard_back_3").click().run()

    assert ui.selectbox(key="wizard_station").value == "Clementi"
    assert ui.text_input(key="wizard_location_detail").value == "westbound platform end"
    assert ui.session_state["request_draft"]["station_line"] == "East-West Line (EWL)"
    ui.button(key="wizard_next_2").click().run()
    ui.button(key="wizard_create").click().run()

    assert not ui.exception
    jobs = api.client.get("/jobs/").json()
    assert len(jobs) == 1
    assert jobs[0]["line"] == "East-West Line (EWL)"
    assert jobs[0]["track"] == "EW23 Clementi · westbound platform end"
    assert jobs[0]["station_code"] == "EW23"
    assert jobs[0]["location_warning"] is None


def test_bishan_requires_line_and_switching_station_clears_dependent_values(ui):
    start_freeform_request(ui)
    ui.selectbox(key="wizard_station").select("Bishan").run()
    assert ui.selectbox(key="wizard_station_line").value is None
    ui.text_input(key="wizard_location_detail").set_value("north platform cabinet")
    ui.button(key="wizard_next_2").click().run()
    assert ui.error
    assert ui.session_state["wizard_step"] == 2
    assert ui.selectbox(key="wizard_station").value == "Bishan"
    assert ui.text_input(key="wizard_location_detail").value == "north platform cabinet"

    ui.selectbox(key="wizard_station_line").select("Circle Line (CCL)").run()
    ui.selectbox(key="wizard_station").select("Clementi").run()
    assert ui.session_state["request_draft"]["station_line"] == "East-West Line (EWL)"
    assert ui.text_input(key="wizard_location_detail").value == ""
    assert all(item.key != "wizard_station_line" for item in ui.selectbox)

    ui.selectbox(key="wizard_station").select("Bishan").run()
    assert ui.selectbox(key="wizard_station_line").value is None
    assert ui.text_input(key="wizard_location_detail").value == ""


def test_manual_train_location_uses_known_line_and_survives_back(ui, api):
    start_freeform_request(ui, "Inspect brake assembly on the identified train.")
    ui.radio(key="wizard_location_mode").set_value("Train / depot / other site").run()
    line_widget = ui.selectbox(key="wizard_line")
    assert set(line_widget.options) == {
        "North-South Line (NSL)",
        "East-West Line (EWL)",
        "Thomson-East Coast Line (TEL)",
        "Circle Line (CCL)",
    }
    line_widget.select("North-South Line (NSL)")
    ui.text_input(key="wizard_track").set_value("Train 512 car 3 · brake assembly")
    ui.button(key="wizard_next_2").click().run()
    ui.button(key="wizard_back_3").click().run()

    assert ui.radio(key="wizard_location_mode").value == "Train / depot / other site"
    assert ui.selectbox(key="wizard_line").value == "North-South Line (NSL)"
    assert ui.text_input(key="wizard_track").value == "Train 512 car 3 · brake assembly"
    ui.button(key="wizard_next_2").click().run()
    ui.button(key="wizard_create").click().run()

    assert not ui.exception
    job = api.client.get("/jobs/").json()[0]
    assert job["line"] == "North-South Line (NSL)"
    assert job["track"] == "Train 512 car 3 · brake assembly"
    assert job["station_code"] is None


def test_legacy_location_warning_requires_reasoned_correction_and_preserves_failed_draft(
    ui, api
):
    job = create_api_job(
        api, name="Legacy Clementi mismatch", priority="High", track="NS17 Track A"
    )
    job_id = job["job_id"]
    with api.database.SessionLocal() as session:
        record = session.get(api.database.RepairJob, job_id)
        record.track = "EW23 Clementi · westbound platform end"
        record.station_code = "EW23"
        session.commit()
    ui.run()
    navigate(ui, "1 · Requests")

    assert any("Location conflict" in warning.value and "Clementi" in warning.value for warning in ui.warning)
    assert ui.selectbox(key=f"location_edit_{job_id}_station").value == "Clementi"
    assert "East-West Line (EWL)" in visible_copy(ui)
    before = api.client.get("/jobs/").json()[0]
    ui.button(key=f"location_edit_{job_id}_save").click().run()

    assert ui.error
    assert "Enter a reason" in visible_copy(ui)
    assert ui.selectbox(key=f"location_edit_{job_id}_station").value == "Clementi"
    assert api.client.get("/jobs/").json()[0] == before
    reason = "Corrected the inherited NSL value after confirming Clementi with the field team."
    ui.text_area(key=f"location_edit_{job_id}_reason").set_value(reason)
    ui.button(key=f"location_edit_{job_id}_save").click().run()

    assert not ui.exception
    corrected = api.client.get("/jobs/").json()[0]
    assert corrected["line"] == "East-West Line (EWL)"
    assert corrected["track"] == "EW23 Clementi · westbound platform end"
    assert corrected["station_code"] == "EW23"
    assert corrected["location_warning"] is None
    audit = api.client.get("/audit-logs/").json()
    assert any(
        item["action"] == "Job overridden" and reason in item["details"]
        for item in audit
    )


def test_cockpit_prioritizes_attention_and_opens_the_correct_operator_action(ui, api):
    awaiting_approval = create_api_job(
        api, name="Scheduled plan", priority="Low", track="NS18 Track A"
    )
    schedule = api.client.post("/schedule/propose")
    assert schedule.status_code == 200, schedule.text
    planning = create_api_job(
        api, name="Awaiting plan", priority="Medium", track="NS19 Track A"
    )
    attention = create_api_job(
        api,
        name="Crew shortfall",
        priority="Urgent",
        track="NS20 Track A",
        engineers_needed=3,
    )

    ui.run()

    assert ui.session_state["page"] == "Cockpit"
    assert str(metric_value(ui, "Needs attention")) == "1"
    assert str(metric_value(ui, "Needs planning")) == "1"
    assert str(metric_value(ui, "Awaiting approval")) == "1"
    assert ui.selectbox(key="cockpit_next_job").value == attention["job_id"]
    assert button(ui, "Review request")
    queue = next(
        frame.value for frame in ui.dataframe
        if isinstance(frame.value, pd.DataFrame) and "Next action" in frame.value.columns
    )
    assert set(queue["Next action"]) == {"Review request", "Plan work", "Review approval"}
    assert f"#{awaiting_approval['job_id']}" in " ".join(queue["Request"])
    assert f"#{planning['job_id']}" in " ".join(queue["Request"])

    button(ui, "Review request").click().run()

    assert ui.session_state["page"] == "1 · Requests"
    assert ui.selectbox(key="request_review_job").value == attention["job_id"]
    assert not ui.exception


def test_cockpit_insertion_example_runs_both_read_only_solver_outcomes(ui, api):
    before_jobs = api.client.get("/jobs/").json()
    before_audit = api.client.get("/audit-logs/").json()

    ui.button(key="cockpit_example").click().run()
    assert ui.session_state["page"] == "Schedule example"
    assert "Nothing is saved to your live schedule" in visible_copy(ui)
    ui.button(key="demo_run").click().run()

    fits = ui.session_state["insertion_example_result"]
    assert fits["scenario"] == "fits" and fits["feasible"] is True
    assert any("repair fits" in item.value.casefold() for item in ui.success)
    assert ui.get("plotly_chart")
    assert api.client.get("/jobs/").json() == before_jobs
    assert api.client.get("/audit-logs/").json() == before_audit

    ui.radio(key="demo_scenario").set_value("no_capacity").run()
    ui.button(key="demo_run").click().run()

    no_capacity = ui.session_state["insertion_example_result"]
    assert no_capacity["scenario"] == "no_capacity"
    assert no_capacity["feasible"] is False and no_capacity["no_capacity"] is True
    assert any("no feasible slot" in item.value.casefold() for item in ui.warning)
    assert api.client.get("/jobs/").json() == before_jobs
    assert api.client.get("/audit-logs/").json() == before_audit
    assert not ui.exception


def test_wizard_keeps_all_three_steps_when_moving_back_and_forward(ui):
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    ui.button(key="wizard_other_asset").click().run()
    assert all(item.label != "Activity" for item in ui.selectbox)

    ui.text_area(key="wizard_description").set_value("Preserve a detailed rail defect description.")
    ui.text_input(key="wizard_title").set_value("Preserve wizard draft")
    ui.button(key="wizard_next_1").click().run()
    select_manual_location(ui, "NS17 northbound rail")
    ui.radio(key="wizard_deadline_choice").set_value("custom").run()
    custom_deadline = datetime.now(SGT) + timedelta(days=2)
    ui.date_input(key="wizard_deadline_date").set_value(custom_deadline.date())
    ui.time_input(key="wizard_deadline_time").set_value(custom_deadline.time().replace(second=0, microsecond=0, tzinfo=None))
    ui.button(key="wizard_next_2").click().run()

    ui.selectbox(key="wizard_priority").select("Low")
    ui.checkbox(key="wizard_manual_work").check().run()
    ui.number_input(key="wizard_duration").set_value(90)
    ui.multiselect(key="wizard_skills").set_value(["Track maintenance"])
    ui.number_input(key="wizard_engineers_needed").set_value(2)
    ui.radio(key="wizard_assignment_mode").set_value("Manual — choose engineers").run()
    ui.multiselect(key="wizard_assigned_ids").set_value([101, 102])
    ui.button(key="wizard_back_3").click().run()

    assert ui.session_state["wizard_step"] == 2
    assert ui.text_input(key="wizard_track").value == "NS17 northbound rail"
    assert ui.radio(key="wizard_deadline_choice").value == "custom"
    ui.button(key="wizard_back_2").click().run()
    assert ui.text_area(key="wizard_description").value == "Preserve a detailed rail defect description."
    assert ui.text_input(key="wizard_title").value == "Preserve wizard draft"

    ui.button(key="wizard_next_1").click().run()
    assert ui.text_input(key="wizard_track").value == "NS17 northbound rail"
    assert ui.radio(key="wizard_deadline_choice").value == "custom"
    ui.button(key="wizard_next_2").click().run()

    assert ui.selectbox(key="wizard_priority").value == "Low"
    assert ui.checkbox(key="wizard_manual_work").value is True
    assert ui.number_input(key="wizard_duration").value == 90
    assert ui.multiselect(key="wizard_skills").value == ["Track maintenance"]
    assert ui.number_input(key="wizard_engineers_needed").value == 2
    assert ui.radio(key="wizard_assignment_mode").value == "Manual — choose engineers"
    assert set(ui.multiselect(key="wizard_assigned_ids").value) == {101, 102}
    assert not ui.exception


def test_asset_selection_survives_back_navigation_and_creates_exact_catalog_pair(
    ui, api, monkeypatch
):
    monkeypatch.setattr(
        api.main,
        "MAINTENANCE_DB",
        {
            "maintenance_catalog": {
                "track_and_permanent_way": [
                    {
                        "activity": "Rail defect repair",
                        "type": "Corrective",
                        "required_skills": ["Track maintenance"],
                    },
                    {
                        "activity": "Rail replacement",
                        "type": "Corrective",
                        "required_skills": ["Track maintenance"],
                    },
                ]
            }
        },
    )
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Selected catalog assets must bypass Gemini")
        ),
    )
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    asset_keys = [
        "asset_train_doors",
        "asset_wheels_brakes",
        "asset_rails",
        "asset_points",
        "asset_signals",
        "asset_power",
        "asset_drainage_pumps",
        "asset_platform_doors",
    ]
    assert all(ui.button(key=key) for key in asset_keys)

    ui.button(key="asset_rails").click().run()
    assert ui.session_state["request_draft"]["asset_id"] == "rails"
    assert "Rail replacement" in visible_copy(ui)
    assert "Rail replacement" in ui.text_area(key="wizard_description").value
    ui.text_area(key="wizard_description").set_value(
        "Rail replacement at NS17 northbound. Confirmed damaged rail section."
    )
    ui.text_input(key="wizard_title").set_value("Replace damaged NS17 rail")
    ui.button(key="wizard_next_1").click().run()
    select_manual_location(ui, "NS17 northbound track")
    ui.button(key="wizard_back_2").click().run()

    assert ui.session_state["request_draft"]["asset_id"] == "rails"
    assert ui.text_area(key="wizard_description").value == (
        "Rail replacement at NS17 northbound. Confirmed damaged rail section."
    )
    assert "Rail replacement" in visible_copy(ui)
    ui.button(key="wizard_next_1").click().run()
    assert ui.text_input(key="wizard_track").value == "NS17 northbound track"
    ui.button(key="wizard_next_2").click().run()
    assert ui.session_state["request_draft"]["asset_id"] == "rails"
    ui.checkbox(key="wizard_manual_work").check().run()
    assert ui.multiselect(key="wizard_skills").disabled is True
    assert ui.multiselect(key="wizard_skills").value == ["Track maintenance"]
    ui.button(key="wizard_create").click().run()

    assert not ui.exception
    assert not ui.error, [item.value for item in ui.error]
    jobs = api.client.get("/jobs/").json()
    assert len(jobs) == 1
    assert jobs[0]["category"] == "track_and_permanent_way"
    assert jobs[0]["activity"] == "Rail replacement"
    assert jobs[0]["assessment_source"] == "catalog-selected"
    assert jobs[0]["required_skills"] == ["Track maintenance"]


def test_changing_asset_replaces_prior_manual_requirements_and_clears_crew(
    ui, api, monkeypatch
):
    monkeypatch.setattr(
        api.main,
        "MAINTENANCE_DB",
        {
            "maintenance_catalog": {
                "track_and_permanent_way": [
                    {
                        "activity": "Rail replacement",
                        "type": "Corrective",
                        "required_skills": ["Track maintenance"],
                    },
                    {
                        "activity": "Switch/point replacement",
                        "type": "Corrective",
                        "required_skills": ["Switch systems"],
                    },
                ]
            }
        },
    )
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    ui.button(key="asset_rails").click().run()
    ui.button(key="wizard_next_1").click().run()
    select_manual_location(ui, "NS17 northbound")
    ui.radio(key="wizard_deadline_choice").set_value("custom").run()
    retained_deadline = datetime.now(SGT) + timedelta(days=2)
    ui.date_input(key="wizard_deadline_date").set_value(retained_deadline.date())
    ui.time_input(key="wizard_deadline_time").set_value(
        retained_deadline.time().replace(second=0, microsecond=0, tzinfo=None)
    )
    ui.button(key="wizard_next_2").click().run()
    ui.selectbox(key="wizard_priority").select("Low")
    ui.checkbox(key="wizard_manual_work").check().run()
    assert ui.multiselect(key="wizard_skills").value == ["Track maintenance"]
    assert ui.multiselect(key="wizard_skills").disabled is True
    ui.radio(key="wizard_assignment_mode").set_value("Manual — choose engineers").run()
    ui.multiselect(key="wizard_assigned_ids").set_value([101, 102])
    ui.button(key="wizard_back_3").click().run()
    ui.button(key="wizard_back_2").click().run()
    ui.button(key="wizard_change_asset_button").click().run()

    ui.button(key="asset_points").click().run()

    draft = ui.session_state["request_draft"]
    assert draft["asset_id"] == "points"
    assert "manual_work" not in draft
    assert draft["skills"] == ["Switch systems"]
    assert "assigned_ids" not in draft
    ui.button(key="wizard_next_1").click().run()
    assert ui.text_input(key="wizard_track").value == "NS17 northbound"
    assert ui.radio(key="wizard_deadline_choice").value == "custom"
    assert ui.date_input(key="wizard_deadline_date").value == retained_deadline.date()
    ui.button(key="wizard_next_2").click().run()
    assert ui.selectbox(key="wizard_priority").value == "Low"
    assert ui.checkbox(key="wizard_manual_work").value is False
    assert ui.multiselect(key="wizard_skills").value == ["Switch systems"]
    assert ui.multiselect(key="wizard_skills").disabled is True
    assert ui.radio(key="wizard_assignment_mode").value.startswith("Automatic")
    assert ui.multiselect(key="wizard_assigned_ids").value == []


def test_operator_create_schedule_override_approve(ui, api):
    # Extra qualified engineers let the solver replace newly unavailable staff,
    # then let the planner make a distinct manual reassignment.
    with api.database.SessionLocal() as session:
        session.add_all([
            api.database.Engineer(
                id=105, name="Ella Relief Engineer", work_email="ella@example.test",
                is_available=True, years_of_experience=2,
                skills=[api.database.EngineerSkill(skill_name="Track maintenance")],
            ),
            api.database.Engineer(
                id=106, name="Faris Relief Engineer", work_email="faris@example.test",
                is_available=True, years_of_experience=1,
                skills=[api.database.EngineerSkill(skill_name="Track maintenance")],
            ),
        ])
        session.commit()
    job = create_request(ui, api)
    jid = job["job_id"]
    assert job["priority"] in ("Urgent", "High", "Medium", "Low")
    assert set(job["assigned_engineer_ids"]) == {101, 102}
    with api.database.SessionLocal() as session:
        session.get(api.database.Engineer, 102).is_available = False
        session.commit()

    navigate(ui, "2 · Plan & approve")
    button(ui, "Generate schedule").click().run()
    assert not ui.exception
    job = api.client.get("/jobs/").json()[0]
    assert job["scheduled_start"]
    assert set(job["assigned_engineer_ids"]) == {101, 105}
    assert ui.selectbox(key="plan_selected_job").value == jid
    assert set(ui.multiselect(key=f"plan_crew_{jid}").value) == {101, 105}
    assert metric_value(ui, "Priority") == job["priority"]
    assert all(name in visible_copy(ui) for name in job["assigned_engineers"])
    tables = job_dataframes(ui)
    assert tables and any(jid in frame["Job ID"].tolist() for frame in tables)
    prior_team = job["assigned_engineer_ids"]
    revised_team = [prior_team[0], 106]

    ui.checkbox(key=f"plan_priority_on_{jid}").check().run()
    ui.selectbox(key=f"plan_priority_{jid}").select("Low")
    ui.checkbox(key=f"plan_crew_on_{jid}").check().run()
    ui.multiselect(key=f"plan_crew_{jid}").set_value(revised_team)
    ui.checkbox(key=f"plan_start_on_{jid}").check().run()
    start = api.main.solver.next_window()[0] + timedelta(minutes=30)
    ui.date_input(key=f"plan_date_{jid}").set_value(start.date())
    ui.time_input(key=f"plan_time_{jid}").set_value(start.time().replace(tzinfo=None))
    ui.text_area(key=f"plan_reason_{jid}").set_value("Shift agreed with the inspection crew.")
    button(ui, "Save selected overrides").click().run()
    assert not ui.exception
    assert not ui.error, [item.value for item in ui.error]
    job = api.client.get("/jobs/").json()[0]
    assert job["priority"] == "Low"
    assert set(job["assigned_engineer_ids"]) == set(revised_team)
    assert set(job["assigned_engineer_ids"]) != set(prior_team)
    assert api.main.solver.as_utc(job["scheduled_start"]) == api.main.solver.as_utc(start)
    assert metric_value(ui, "Priority") == "Low"
    assert all(name in visible_copy(ui) for name in job["assigned_engineers"])
    assert set(ui.multiselect(key=f"plan_crew_{jid}").value) == set(revised_team)

    button(ui, "Record decision").click().run()
    assert not ui.exception
    assert api.client.get("/jobs/").json()[0]["is_approved"] is True
    for page in ("3 · Execution", "Alerts", "Audit log", "About"):
        navigate(ui, page)
        assert not ui.exception, page
        assert not ui.error, (page, [item.value for item in ui.error])


def test_manual_assignment_priority_and_confirmed_delete(ui, api):
    job = create_request(ui, api, manual=True)
    jid = job["job_id"]
    assert job["priority"] == "Low"
    assert set(job["assigned_engineer_ids"]) == {101, 102}
    assert button(ui, "Delete request").disabled
    ui.text_area(key=f"delete_reason_{jid}").set_value("Duplicate test request.")
    ui.checkbox(key=f"delete_confirm_{jid}").check().run()
    button(ui, "Delete request").click().run()
    assert not ui.exception
    assert api.client.get("/jobs/").json() == []
    audit = api.client.get("/audit-logs/").json()
    assert any("Duplicate test request." in entry["details"] for entry in audit)


def test_validation_keeps_request_fields(ui, api):
    navigate(ui, "1 · Requests")
    button(ui, "Add work").click().run()
    ui.button(key="wizard_other_asset").click().run()
    ui.text_area(key="wizard_description").set_value("Keep this detailed track repair description")
    ui.text_input(key="wizard_title").set_value("Keep this title")
    ui.button(key="wizard_next_1").click().run()
    select_manual_location(ui, "Keep NS17 northbound")
    ui.button(key="wizard_next_2").click().run()
    ui.selectbox(key="wizard_priority").select("Low")
    ui.radio(key="wizard_assignment_mode").set_value("Manual — choose engineers").run()
    ui.button(key="wizard_create").click().run()
    assert ui.error
    assert ui.session_state["request_draft"]["title"] == "Keep this title"
    assert ui.session_state["request_draft"]["track"] == "Keep NS17 northbound"
    assert ui.selectbox(key="wizard_priority").value == "Low"
    assert ui.radio(key="wizard_assignment_mode").value == "Manual — choose engineers"
    assert api.client.get("/jobs/").json() == []


def test_plan_filter_resets_stale_selection_without_changing_scheduler_scope(ui, api):
    low = create_api_job(api, name="Duplicate display name", priority="Low")
    urgent = create_api_job(api, name="Duplicate display name", priority="Urgent")
    navigate(ui, "2 · Plan & approve")
    ui.selectbox(key="plan_selected_job").select(low["job_id"]).run()
    assert ui.selectbox(key="plan_selected_job").value == low["job_id"]

    ui.selectbox(key="plan_filter_priority").select("Urgent").run()

    assert ui.selectbox(key="plan_selected_job").value == urgent["job_id"]
    assert "all eligible" in visible_copy(ui).casefold()
    filtered_tables = job_dataframes(ui)
    assert filtered_tables
    assert filtered_tables[-1]["Job ID"].tolist() == [urgent["job_id"]]

    button(ui, "Generate schedule").click().run()

    assert not ui.exception
    persisted = api.client.get("/jobs/").json()
    assert {job["job_id"] for job in persisted if job["scheduled_start"]} == {low["job_id"], urgent["job_id"]}
    assert ui.selectbox(key="plan_filter_priority").value == "Urgent"
    assert ui.selectbox(key="plan_selected_job").value == urgent["job_id"]
    chart = ui.get("plotly_chart")[0]
    spec = json.loads(chart.proto.spec)
    x_range = spec["layout"]["xaxis"]["range"]
    assert pd.Timestamp(x_range[0]).hour == 0 and pd.Timestamp(x_range[0]).minute == 30
    assert pd.Timestamp(x_range[1]).hour == 5 and pd.Timestamp(x_range[1]).minute == 0
    hover = " ".join(str(trace.get("hovertemplate", "")) for trace in spec["data"])
    assert all(label in hover for label in ("Start:", "End:", "Duration:"))
    plotted_names = [name for trace in spec["data"] for name in trace.get("text", [])]
    assert plotted_names.count("Duplicate display name") == 2
    category_rows = spec["layout"]["yaxis"].get("categoryarray", [])
    assert len(category_rows) == len(set(category_rows)) == 1


def test_active_job_hides_planning_mutations_and_exposes_valid_execution_states(ui, api):
    job = create_request(ui, api)
    jid = job["job_id"]
    navigate(ui, "2 · Plan & approve")
    button(ui, "Generate schedule").click().run()
    button(ui, "Record decision").click().run()
    navigate(ui, "3 · Execution")
    next(item for item in ui.selectbox if item.label == "Valid next action *").select("In progress")
    next(item for item in ui.text_area if item.label == "Field update reason *").set_value(
        "Field team accepted the protected worksite."
    )
    button(ui, "Record execution update").click().run()
    assert api.client.get("/jobs/").json()[0]["status"] == "In progress"

    navigate(ui, "1 · Requests")
    assert all(item.label != "Delete request" for item in ui.button)
    assert all(item.label != "Save selected overrides" for item in ui.button)
    assert "only while a job is not started" in visible_copy(ui).casefold()

    navigate(ui, "2 · Plan & approve")
    assert all(item.label != "Save selected overrides" for item in ui.button)
    assert all(item.label != "Record decision" for item in ui.button)
    page_copy = visible_copy(ui).casefold()
    assert "approval decisions are available only while a job is not started" in page_copy
    assert "overrides are available only while a job is not started" in page_copy


def test_ai_setup_does_not_offer_a_false_connection_test_without_a_key(ui):
    navigate(ui, "AI setup")

    assert "Gemini is not configured" in visible_copy(ui)
    assert ui.button(key="test_ai_connection").disabled is True
    assert "validated catalog assessment" not in " ".join(item.value for item in ui.success)


def test_utility_navigation_clears_main_selection_and_allows_reopening_same_page(ui):
    navigate(ui, "1 · Requests")

    navigate(ui, "AI setup")

    assert ui.session_state["main_navigation"] is None
    ui.radio(key="main_navigation").set_value("1 · Requests").run()
    assert ui.session_state["page"] == "1 · Requests"
    assert ui.radio(key="main_navigation").value == "1 · Requests"
    assert "Requests" in visible_copy(ui)
    assert not ui.exception


def test_ai_setup_shows_provider_failure_as_an_error_not_success(ui, api, monkeypatch):
    credential = api.main.gemini_config.GeminiCredential("ui-provider-key", "secure_store")
    configure_ui_gemini(api, monkeypatch, credential)
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda supplied=None: UiGeminiClient(error=RuntimeError("provider unavailable")),
    )
    navigate(ui, "AI setup")

    assert ui.button(key="test_ai_connection").disabled is False
    ui.button(key="test_ai_connection").click().run()

    assert ui.session_state["ai_last_test"]["ok"] is False
    assert ui.error
    assert "validated catalog assessment" not in " ".join(item.value for item in ui.success)


def test_ai_setup_turns_green_only_for_a_valid_complete_catalog_response(ui, api, monkeypatch):
    credential = api.main.gemini_config.GeminiCredential("ui-valid-key", "environment")
    provider_text = (
        '{"category":"track_and_permanent_way","activity":"Rail defect repair",'
        '"activity_type":"Corrective","required_skills":["Track maintenance"],'
        '"priority":"Medium","effort_level":3,"duration_mins":60,"engineers_needed":2}'
    )
    configure_ui_gemini(api, monkeypatch, credential)
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda supplied=None: UiGeminiClient(text=provider_text),
    )
    navigate(ui, "AI setup")
    ui.button(key="test_ai_connection").click().run()

    assert ui.session_state["ai_last_test"]["ok"] is True
    assert any("passed the production catalog validation" in item.value for item in ui.success)
    assert not ui.error


def test_about_works_without_backend(monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("About must not depend on HTTP requests")

    monkeypatch.syspath_prepend(str(APP.parent))
    monkeypatch.setattr(requests, "request", offline)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["page"] = "About"
    app.run()
    assert not app.exception
    copy = visible_copy(app)
    for phrase in (
        "1 · Create request",
        "2 · Review assessment",
        "3 · Generate plan",
        "4 · Override and approve",
        "5 · Track execution",
        "OR-Tools CP-SAT",
        "Why priority is weighted",
        "Rules, optional Gemini, and human approval",
        "Data used by this demonstration",
        "Expected value and evidence still needed",
        "Singapore rail-maintenance context",
        "training dataset",
        "The Straits Times",
        "CNA",
        "LTA, SMRT and SBS Transit",
        "Ministry of Transport",
    ):
        assert phrase in copy
