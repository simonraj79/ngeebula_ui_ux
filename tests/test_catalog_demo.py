"""Operator-selected catalog and read-only insertion demonstration journeys."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def create_payload(api, **overrides):
    payload = {
        "name": "Selected rail defect repair",
        "description": "Repair the confirmed rail defect at the selected asset.",
        "line": "North South Line",
        "track": "NS17 Track A",
        "deadline": (api.main.solver.next_window()[1] + timedelta(hours=1)).isoformat(),
        "created_by": "Catalog integration test",
    }
    payload.update(overrides)
    return payload


def persisted_state(api):
    return {
        "jobs": api.client.get("/jobs/").json(),
        "audit": api.client.get("/audit-logs/").json(),
    }


def test_explicit_catalog_pair_bypasses_gemini_and_anchors_domain_fields(
    api, monkeypatch
):
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("An explicit catalog selection must not invoke Gemini")
        ),
    )
    response = api.client.post(
        "/jobs/parse-and-create",
        json=create_payload(
            api,
            catalog_category="track_and_permanent_way",
            catalog_activity="Rail defect repair",
            priority="Low",
            duration_mins=45,
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    job = body["job"]
    assert job["category"] == "track_and_permanent_way"
    assert job["activity"] == "Rail defect repair"
    assert job["activity_type"] == "Corrective"
    assert job["required_skills"] == ["Track maintenance"]
    assert job["assessment_source"] == "catalog-selected"
    assert job["priority"] == "Low"
    assert job["duration_mins"] == 45
    assert body["assessment"]["matched_category"] == job["category"]
    assert body["assessment"]["matched_activity"] == job["activity"]
    assert body["assessment"]["assessment_source"] == "catalog-selected"
    persisted = api.client.get("/jobs/").json()
    assert len(persisted) == 1
    assert persisted[0]["activity"] == "Rail defect repair"
    assert persisted[0]["priority"] == "Low"
    assert persisted[0]["duration_mins"] == 45


@pytest.mark.parametrize(
    "catalog_fields",
    [
        {"catalog_category": "track_and_permanent_way"},
        {"catalog_activity": "Rail defect repair"},
        {
            "catalog_category": "track_and_permanent_way",
            "catalog_activity": "Nonexistent repair",
        },
        {
            "catalog_category": "track_and_permanent_way",
            "catalog_activity": "rail defect repair",
        },
        {
            "catalog_category": "track_and_permanent_way",
            "catalog_activity": "Rail defect repair",
            "required_skills": ["Signalling"],
        },
    ],
    ids=[
        "category-only",
        "activity-only",
        "unknown-pair",
        "wrong-case-is-not-exact",
        "skills-cannot-contradict-selection",
    ],
)
def test_invalid_or_partial_catalog_selection_is_transactional(api, catalog_fields):
    before = persisted_state(api)

    response = api.client.post(
        "/jobs/parse-and-create", json=create_payload(api, **catalog_fields)
    )

    assert response.status_code in {400, 422}, response.text
    assert persisted_state(api) == before


def test_insertion_demo_uses_real_solver_preserves_baseline_and_never_persists(
    api, monkeypatch
):
    original_solver = api.main.solver.solve_mrt_schedule
    solver_calls = []

    def observed_solver(*args, **kwargs):
        solver_calls.append((args, kwargs))
        return original_solver(*args, **kwargs)

    monkeypatch.setattr(api.main.solver, "solve_mrt_schedule", observed_solver)
    before = persisted_state(api)

    fits_response = api.client.post(
        "/schedule/insertion-demo", json={"scenario": "fits"}
    )
    no_capacity_response = api.client.post(
        "/schedule/insertion-demo", json={"scenario": "no_capacity"}
    )

    assert fits_response.status_code == 200, fits_response.text
    assert no_capacity_response.status_code == 200, no_capacity_response.text
    fits = fits_response.json()
    no_capacity = no_capacity_response.json()
    assert len(solver_calls) == 2
    assert fits["synthetic"] is no_capacity["synthetic"] is True
    assert fits["persisted"] is no_capacity["persisted"] is False
    assert fits["can_apply"] is no_capacity["can_apply"] is False
    assert fits["scenario"] == "fits"
    assert fits["status"] == "success"
    assert fits["feasible"] is True and fits["no_capacity"] is False
    assert no_capacity["scenario"] == "no_capacity"
    assert no_capacity["status"] == "infeasible"
    assert no_capacity["feasible"] is False and no_capacity["no_capacity"] is True
    assert fits["baseline"] == no_capacity["baseline"]
    assert len(fits["baseline"]) == 3
    assert fits["proposed"][:3] == fits["baseline"]
    assert len(fits["proposed"]) == 4
    assert no_capacity["proposed"] == no_capacity["baseline"]
    assert fits["added_request"]["scheduled_start"] is not None
    assert fits["added_request"]["scheduled_end"] is not None
    assert no_capacity["added_request"]["scheduled_start"] is None
    assert no_capacity["added_request"]["scheduled_end"] is None
    assert fits["added_request"]["engineers_needed"] == 2
    assert no_capacity["added_request"]["engineers_needed"] == 2
    for field in ("name", "track", "duration_mins", "required_skills", "activity"):
        assert fits["added_request"][field] == no_capacity["added_request"][field]
    assert fits["added_request"]["deadline"] != no_capacity["added_request"]["deadline"]
    assert "no 45-minute interval" in no_capacity["explanation"]
    assert no_capacity["solver_status"]

    baseline_crew = set(fits["baseline"][0]["assigned_engineer_ids"])
    for row in fits["baseline"]:
        assert row["is_approved"] is True
        assert row["time_locked"] is True
        assert row["assignment_locked"] is True
        assert len(row["assigned_engineer_ids"]) == row["engineers_needed"]
        assert len(set(row["assigned_engineer_ids"])) == row["engineers_needed"]
        assert set(row["assigned_engineer_ids"]) == baseline_crew
    for index, left in enumerate(fits["proposed"]):
        left_start = datetime.fromisoformat(left["scheduled_start"])
        left_end = datetime.fromisoformat(left["scheduled_end"])
        assert left_start < left_end
        assert len(left["assigned_engineer_ids"]) == left["engineers_needed"]
        for right in fits["proposed"][index + 1 :]:
            right_start = datetime.fromisoformat(right["scheduled_start"])
            right_end = datetime.fromisoformat(right["scheduled_end"])
            if left_start < right_end and right_start < left_end:
                assert not (
                    set(left["assigned_engineer_ids"])
                    & set(right["assigned_engineer_ids"])
                )
    assert persisted_state(api) == before
