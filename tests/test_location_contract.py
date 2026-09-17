"""Location integrity across catalog, creation, planning, and correction."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest


def location_payload(api, **overrides):
    payload = {
        "name": "Station rail repair",
        "description": "Repair a confirmed rail defect near the selected station.",
        "line": "North-South Line (NSL)",
        "track": "NS17 Bishan · northbound track",
        "station_code": "NS17",
        "deadline": (api.main.solver.next_window()[1] + timedelta(hours=1)).isoformat(),
        "catalog_category": "track_and_permanent_way",
        "catalog_activity": "Rail defect repair",
        "created_by": "Location integration test",
    }
    payload.update(overrides)
    return payload


def create_location_job(api, **overrides):
    response = api.client.post(
        "/jobs/parse-and-create", json=location_payload(api, **overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()["job"]


def saved_state(api):
    return {
        "jobs": api.client.get("/jobs/").json(),
        "audit": api.client.get("/audit-logs/").json(),
    }


def test_catalog_exposes_canonical_station_line_rows(api):
    response = api.client.get("/catalog/")

    assert response.status_code == 200, response.text
    stations = response.json()["stations"]
    assert {
        (row["name"], row["code"], row["line"], row["interchange"])
        for row in stations
    } >= {
        ("Clementi", "EW23", "East-West Line (EWL)", False),
        ("Bishan", "NS17", "North-South Line (NSL)", True),
        ("Bishan", "CC15", "Circle Line (CCL)", True),
        ("Woodlands", "NS9", "North-South Line (NSL)", True),
        ("Woodlands North", "TE1", "Thomson-East Coast Line (TEL)", False),
    }


@pytest.mark.parametrize(
    ("line", "track", "station_code", "interchange"),
    [
        ("East-West Line (EWL)", "EW23 Clementi · platform end", "EW23", False),
        ("North-South Line (NSL)", "NS17 Bishan · northbound", "NS17", True),
        ("Circle Line (CCL)", "CC15 Bishan · equipment cabinet", "CC15", True),
        ("Thomson-East Coast Line (TEL)", "TE1 Woodlands North", "TE1", False),
    ],
)
def test_station_location_persists_selected_serving_line(
    api, line, track, station_code, interchange
):
    job = create_location_job(
        api, line=line, track=track, station_code=station_code
    )

    assert job["line"] == line
    assert job["track"] == track
    assert job["station_code"] == station_code
    assert job["is_interchange"] is interchange
    assert job["location_warning"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"line": "North-South Line (NSL)", "track": "EW23 Clementi", "station_code": "EW23"},
        {"line": "North-South Line (NSL)", "track": "Clementi", "station_code": None},
        {"line": "North-South Line (NSL)", "track": "EW23 track", "station_code": None},
        {"line": "North-South Line (NSL)", "track": "Woodlands North", "station_code": None},
        {"line": "North-South Line (NSL)", "track": "Unknown worksite", "station_code": "ZZ99"},
        {"line": "North-South Line (NSL)", "track": "Clementi", "station_code": "NS17"},
    ],
    ids=[
        "explicit-clementi-code-on-nsl",
        "clementi-name-on-nsl",
        "clementi-code-in-track-on-nsl",
        "longest-name-woodlands-north-not-woodlands",
        "unknown-station-code",
        "station-code-disagrees-with-track-text",
    ],
)
def test_invalid_location_is_rejected_before_gemini_and_without_writes(
    api, monkeypatch, overrides
):
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Invalid location must be rejected before assessment")
        ),
    )
    before = saved_state(api)

    response = api.client.post(
        "/jobs/parse-and-create", json=location_payload(api, **overrides)
    )

    assert response.status_code == 400, response.text
    assert saved_state(api) == before


def test_unknown_train_or_depot_text_remains_a_valid_manual_location(api):
    job = create_location_job(
        api,
        line="North-South Line (NSL)",
        track="Train 512 car 3 · depot road 4 brake assembly",
        station_code=None,
    )

    assert job["station_code"] is None
    assert job["is_interchange"] is False
    assert job["location_warning"] is None


def test_legacy_location_warning_is_visible_and_blocks_planning_and_approval(api):
    job = create_location_job(api)
    job_id = job["job_id"]
    with api.database.SessionLocal() as session:
        record = session.get(api.database.RepairJob, job_id)
        record.track = "EW23 Clementi"
        record.station_code = "EW23"
        session.commit()

    exposed = api.client.get("/jobs/").json()[0]
    assert exposed["line"] == "North-South Line (NSL)"
    assert exposed["track"] == "EW23 Clementi"
    assert exposed["station_code"] == "EW23"
    assert exposed["location_warning"].startswith("Location conflict:")
    before = saved_state(api)

    proposal = api.client.post("/schedule/propose")
    approval = api.client.post(
        f"/approval/{job_id}",
        json={"approved": True, "approved_by": "Location reviewer"},
    )

    assert proposal.status_code == 409, proposal.text
    assert approval.status_code == 409, approval.text
    assert "Correct the line, track, or station code before planning" in proposal.text
    assert "Correct the line, track, or station code before planning" in approval.text
    assert saved_state(api) == before


def test_location_correction_recomputes_metadata_clears_plan_and_records_audit(api):
    job = create_location_job(api)
    job_id = job["job_id"]
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    approval = api.client.post(
        f"/approval/{job_id}",
        json={
            "approved": True,
            "approved_by": "Chief planner",
            "reason": "Original plan checked",
        },
    )
    assert approval.status_code == 200, approval.text
    planned = api.client.get("/jobs/").json()[0]
    assert planned["scheduled_start"] and planned["is_approved"] is True

    response = api.client.patch(
        f"/jobs/{job_id}",
        json={
            "updated_by": "Chief planner",
            "reason": "Crew confirmed the work is at Clementi, not Bishan.",
            "line": "East-West Line (EWL)",
            "track": "EW23 Clementi · westbound platform end",
            "station_code": "EW23",
        },
    )

    assert response.status_code == 200, response.text
    corrected = response.json()["job"]
    assert corrected["line"] == "East-West Line (EWL)"
    assert corrected["station_code"] == "EW23"
    assert corrected["is_interchange"] is False
    assert corrected["location_warning"] is None
    assert corrected["scheduled_start"] is None
    assert corrected["scheduled_end"] is None
    assert corrected["is_approved"] is False
    assert corrected["time_locked"] is False
    audit = api.client.get("/audit-logs/").json()
    entry = next(item for item in audit if item["action"] == "Job overridden")
    details = json.loads(entry["details"])
    assert details["reason"] == "Crew confirmed the work is at Clementi, not Bishan."
    assert details["location"] == {
        "line": "East-West Line (EWL)",
        "track": "EW23 Clementi · westbound platform end",
        "station_code": "EW23",
        "station_name": "Clementi",
    }
    assert details["before"]["scheduled_start"] is not None
    assert details["before"]["is_approved"] is True
    assert details["after"]["scheduled_start"] is None
    assert details["after"]["is_approved"] is False


def test_invalid_location_correction_is_atomic(api):
    job = create_location_job(api)
    before = saved_state(api)

    response = api.client.patch(
        f"/jobs/{job['job_id']}",
        json={
            "updated_by": "Chief planner",
            "reason": "Incorrect attempted correction",
            "line": "North-South Line (NSL)",
            "track": "EW23 Clementi",
            "station_code": "EW23",
        },
    )

    assert response.status_code == 400, response.text
    assert saved_state(api) == before
