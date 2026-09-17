from __future__ import annotations

import datetime as dt
import json
from copy import deepcopy
from zoneinfo import ZoneInfo

import pytest


SGT = ZoneInfo("Asia/Singapore")
VALID_PRIORITIES = {"Urgent", "High", "Medium", "Low"}


def next_maintenance_window() -> tuple[dt.datetime, dt.datetime]:
    now = dt.datetime.now(SGT)
    start = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if start < now:
        start += dt.timedelta(days=1)
    return start, start + dt.timedelta(hours=4, minutes=30)


def create_payload(**overrides):
    _, window_end = next_maintenance_window()
    payload = {
        "name": "NS17 rail defect",
        "description": "Inspect and repair a reported rail defect near the platform.",
        "line": "North South Line",
        "track": "NS17 southbound",
        "deadline": (window_end + dt.timedelta(days=1)).isoformat(),
        "priority": "Urgent",
        "duration_mins": 60,
        "required_skills": ["Track maintenance"],
        "engineers_needed": 2,
        "created_by": "planner@example.test",
    }
    payload.update(overrides)
    return payload


def response_job(body):
    if isinstance(body, dict) and isinstance(body.get("job"), dict):
        return body["job"]
    return body


def jobs(client):
    response = client.get("/jobs/")
    assert response.status_code == 200, response.text
    body = response.json()
    if isinstance(body, dict):
        body = body.get("jobs", body.get("items"))
    assert isinstance(body, list), body
    return body


def audit_logs(client):
    response = client.get("/audit-logs/")
    assert response.status_code == 200, response.text
    body = response.json()
    if isinstance(body, dict):
        body = body.get("audit_logs", body.get("items"))
    assert isinstance(body, list), body
    return body


def assigned_ids(job):
    if "assigned_engineer_ids" in job:
        return job["assigned_engineer_ids"]
    values = job.get("assigned_engineers", [])
    return [value["id"] for value in values if isinstance(value, dict)]


def schedule_rows(body):
    if isinstance(body, list):
        return body
    if isinstance(body.get("schedule"), list):
        return body["schedule"]
    if isinstance(body.get("base_schedule"), list):
        return body["base_schedule"]
    options = body.get("options") or []
    return options[0]["schedule"] if options else []


def parse_instant(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"API timestamp is missing its timezone: {value}"
    return parsed


def create_job(client, **overrides):
    response = client.post("/jobs/parse-and-create", json=create_payload(**overrides))
    assert response.status_code in (200, 201), response.text
    body = response_job(response.json())
    assert body["job_id"]
    return body


def schedule_and_approve(client, **overrides):
    job = create_job(client, **overrides)
    proposal = client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    approval = client.post(
        f"/approval/{job['job_id']}",
        json={
            "approved": True,
            "approved_by": "manager@example.test",
            "reason": "Crew and possession confirmed for execution.",
        },
    )
    assert approval.status_code == 200, approval.text
    return response_job(approval.json())


class FakeGeminiClient:
    def __init__(self, *, text=None, error=None):
        self._text = text
        self._error = error
        self.models = self

    def generate_content(self, **_kwargs):
        if self._error:
            raise self._error
        return type("GeminiResponse", (), {"text": self._text})()


def test_catalog_roster_and_create_use_qualified_available_staff(api):
    catalog = api.client.get("/catalog/")
    assert catalog.status_code == 200, catalog.text
    assert "track_and_permanent_way" in str(catalog.json())

    roster = api.client.get("/engineers/")
    assert roster.status_code == 200, roster.text
    roster_body = roster.json()
    if isinstance(roster_body, dict):
        roster_body = roster_body.get("engineers", roster_body.get("items"))
    assert {engineer["id"] for engineer in roster_body} == {101, 102, 103, 104}

    job = create_job(api.client)
    assert job["priority"] == "Urgent"
    assert set(assigned_ids(job)) == {101, 102}
    names = job.get("assigned_engineers", [])
    if names and isinstance(names[0], dict):
        assert {item["name"] for item in names} == {
            "Aisha Track Lead",
            "Ben Track Engineer",
        }
    else:
        assert set(names) == {"Aisha Track Lead", "Ben Track Engineer"}

    persisted = jobs(api.client)
    assert len(persisted) == 1
    assert set(assigned_ids(persisted[0])) == {101, 102}
    assert persisted[0]["priority"] in VALID_PRIORITIES


def test_no_api_key_uses_deterministic_catalog_fallback(api, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert api.main.get_gemini_client() is None
    payload = create_payload()
    for optional in ("priority", "duration_mins", "required_skills", "engineers_needed"):
        payload.pop(optional)

    response = api.client.post("/jobs/parse-and-create", json=payload)

    assert response.status_code in (200, 201), response.text
    job = response_job(response.json())
    assert job["priority"] in VALID_PRIORITIES
    assert set(assigned_ids(job)) == {101, 102}


def test_valid_gemini_evaluation_is_used(api, monkeypatch):
    evaluation = {
        "category": "track_and_permanent_way",
        "activity": "Rail defect repair",
        "activity_type": "Corrective",
        "required_skills": ["Track maintenance"],
        "priority": "Low",
        "effort_level": 2,
        "duration_mins": 45,
        "engineers_needed": 2,
    }
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda: FakeGeminiClient(text=json.dumps(evaluation)),
    )
    payload = create_payload()
    for optional in ("priority", "duration_mins", "required_skills", "engineers_needed"):
        payload.pop(optional)

    response = api.client.post("/jobs/parse-and-create", json=payload)

    assert response.status_code in (200, 201), response.text
    job = response_job(response.json())
    assert job["assessment_source"] == "gemini-validated"
    assert job["required_skills"] == ["Track maintenance"]
    assert job["priority"] == "Low"
    assert job["duration_mins"] == 45
    assert set(assigned_ids(job)) == {101, 102}


@pytest.mark.parametrize(
    "fake_client",
    [
        FakeGeminiClient(error=RuntimeError("simulated provider outage")),
        FakeGeminiClient(text="not valid JSON"),
        FakeGeminiClient(text="[]"),
        FakeGeminiClient(text="{}"),
        FakeGeminiClient(text=json.dumps({"priority": "catastrophic"})),
        FakeGeminiClient(
            text=json.dumps(
                {
                    "matched_category": "track_and_permanent_way",
                    "activity_type": "Corrective",
                    "required_skills": ["Teleportation"],
                    "priority": "High",
                    "effort_level": 3,
                    "duration_mins": 60,
                    "engineers_needed": 2,
                }
            )
        ),
        FakeGeminiClient(
            text=json.dumps(
                {
                    "category": "track_and_permanent_way",
                    "activity": "Rail defect repair",
                    "activity_type": "Magic",
                    "required_skills": ["Track maintenance"],
                    "priority": "High",
                    "effort_level": 3,
                    "duration_mins": 60,
                    "engineers_needed": 2,
                }
            )
        ),
        FakeGeminiClient(
            text=json.dumps(
                {
                    "category": "track_and_permanent_way",
                    "activity": "Rail defect repair",
                    "activity_type": "Corrective",
                    "required_skills": ["Track maintenance"],
                    "priority": "High",
                    "effort_level": 0,
                    "duration_mins": 60,
                    "engineers_needed": 2,
                }
            )
        ),
        FakeGeminiClient(
            text=json.dumps(
                {
                    "category": "track_and_permanent_way",
                    "activity": "Rail defect repair",
                    "activity_type": "Corrective",
                    "required_skills": ["Track maintenance"],
                    "priority": "High",
                    "effort_level": 6,
                    "duration_mins": 60,
                    "engineers_needed": 2,
                }
            )
        ),
    ],
    ids=[
        "provider-error",
        "invalid-json",
        "array-output",
        "empty-dict",
        "invalid-schema",
        "unknown-skill",
        "invalid-activity-type",
        "effort-too-low",
        "effort-too-high",
    ],
)
def test_gemini_failure_or_invalid_output_falls_back_safely(api, monkeypatch, fake_client):
    monkeypatch.setattr(api.main, "get_gemini_client", lambda: fake_client)
    payload = create_payload()
    for optional in ("priority", "duration_mins", "required_skills", "engineers_needed"):
        payload.pop(optional)

    response = api.client.post("/jobs/parse-and-create", json=payload)

    assert response.status_code in (200, 201), response.text
    job = response_job(response.json())
    assert job["assessment_source"] == "rules"
    assert job["priority"] in VALID_PRIORITIES
    assert job["required_skills"] == ["Track maintenance"]
    assert job["duration_mins"] > 0
    assert set(assigned_ids(job)) == {101, 102}


@pytest.mark.parametrize("proposed_skills", [[], ["Track maintenance"]], ids=["empty", "partial"])
def test_gemini_cannot_remove_catalog_required_skills(api, monkeypatch, proposed_skills):
    monkeypatch.setattr(
        api.main,
        "MAINTENANCE_DB",
        {
            "maintenance_catalog": {
                "track_and_permanent_way": [
                    {
                        "activity": "Rail defect repair",
                        "type": "Corrective",
                        "required_skills": ["Track maintenance", "Rail safety"],
                    }
                ]
            }
        },
    )
    with api.database.SessionLocal() as session:
        for engineer_id in (101, 102):
            session.add(api.database.EngineerSkill(engineer_id=engineer_id, skill_name="Rail safety"))
        session.commit()
    suggestion = {
        "category": "track_and_permanent_way",
        "activity": "Rail defect repair",
        "activity_type": "Corrective",
        "required_skills": proposed_skills,
        "priority": "Low",
        "effort_level": 2,
        "duration_mins": 45,
        "engineers_needed": 2,
    }
    monkeypatch.setattr(
        api.main,
        "get_gemini_client",
        lambda: FakeGeminiClient(text=json.dumps(suggestion)),
    )
    payload = create_payload()
    for optional in ("priority", "duration_mins", "required_skills", "engineers_needed"):
        payload.pop(optional)

    response = api.client.post("/jobs/parse-and-create", json=payload)

    assert response.status_code in (200, 201), response.text
    job = response_job(response.json())
    assert job["assessment_source"] == "rules"
    assert set(job["required_skills"]) == {"Track maintenance", "Rail safety"}
    assert set(assigned_ids(job)) == {101, 102}


def test_full_create_plan_override_replan_approve_delete_keeps_audit(api):
    created = create_job(api.client)
    job_id = created["job_id"]

    planned = api.client.post("/schedule/propose")
    assert planned.status_code == 200, planned.text
    first_rows = schedule_rows(planned.json())
    assert [row["job_id"] for row in first_rows] == [job_id]

    window_start, _ = next_maintenance_window()
    manual_start = window_start + dt.timedelta(minutes=15)
    override = api.client.patch(
        f"/jobs/{job_id}",
        json={
            "updated_by": "control@example.test",
            "reason": "Possession starts after the inspection train clears.",
            "priority": "Low",
            "assigned_engineer_ids": [102, 101],
            "scheduled_start": manual_start.isoformat(),
        },
    )
    assert override.status_code == 200, override.text
    overridden = response_job(override.json())
    assert overridden["priority"] == "Low"
    assert set(assigned_ids(overridden)) == {101, 102}
    assert parse_instant(overridden["scheduled_start"]) == manual_start

    replanned = api.client.post("/schedule/propose")
    assert replanned.status_code == 200, replanned.text
    after_replan = next(item for item in jobs(api.client) if item["job_id"] == job_id)
    assert after_replan["priority"] == "Low"
    assert set(assigned_ids(after_replan)) == {101, 102}
    assert parse_instant(after_replan["scheduled_start"]) == manual_start

    approval = api.client.post(
        f"/approval/{job_id}",
        json={
            "approved": True,
            "approved_by": "manager@example.test",
            "reason": "Possession and crew confirmed.",
        },
    )
    assert approval.status_code == 200, approval.text

    deletion = api.client.request(
        "DELETE",
        f"/jobs/{job_id}",
        json={
            "deleted_by": "manager@example.test",
            "reason": "Work transferred to an emergency possession record.",
        },
    )
    assert deletion.status_code in (200, 204), deletion.text
    assert all(item["job_id"] != job_id for item in jobs(api.client))

    logs = audit_logs(api.client)
    serialized = " ".join(str(log).casefold() for log in logs)
    assert "control@example.test" in serialized
    assert "manager@example.test" in serialized
    assert "possession and crew confirmed" in serialized
    assert "work transferred to an emergency possession record" in serialized
    assert "delete" in serialized


def test_deleted_job_id_is_never_reused_and_audit_keeps_old_identity(api):
    first = create_job(api.client, name="Job whose ID must remain retired")
    first_id = first["job_id"]
    deletion = api.client.request(
        "DELETE",
        f"/jobs/{first_id}",
        json={
            "deleted_by": "manager@example.test",
            "reason": "Duplicate request; retain its identity in the audit trail.",
        },
    )
    assert deletion.status_code in (200, 204), deletion.text

    replacement = create_job(api.client, name="Later independent job")

    assert replacement["job_id"] > first_id
    deleted_log = next(
        log for log in audit_logs(api.client) if "delete" in log["action"].casefold()
    )
    details = json.loads(deleted_log["details"])
    assert details["job_id"] == first_id
    assert details["snapshot"]["job_id"] == first_id
    assert details["snapshot"]["name"] == "Job whose ID must remain retired"


@pytest.mark.parametrize(
    "change",
    [
        {"priority": "Critical"},
        {"assigned_engineer_ids": []},
        {"assigned_engineer_ids": [101, 999]},
        {"assigned_engineer_ids": [101, 101]},
        {"assigned_engineer_ids": [101, 103]},
        {"assigned_engineer_ids": [101, 104]},
        {"duration_mins": 0},
        {"required_skills": []},
        {"engineers_needed": 0},
        {"scheduled_start": "2026-09-18T00:45:00"},
        {"priority": None},
        {"assigned_engineer_ids": None},
        {"duration_mins": None},
        {"required_skills": None},
        {"engineers_needed": None},
        {"scheduled_start": None},
    ],
    ids=[
        "invalid-priority",
        "missing-crew",
        "unknown-engineer",
        "duplicate-engineer",
        "unavailable-engineer",
        "unqualified-engineer",
        "invalid-duration",
        "missing-skill",
        "invalid-headcount",
        "naive-start-time",
        "null-priority",
        "null-engineers",
        "null-duration",
        "null-skills",
        "null-headcount",
        "null-start-time",
    ],
)
def test_invalid_patch_is_atomic(api, change):
    job_id = create_job(api.client)["job_id"]
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))
    payload = {
        "updated_by": "control@example.test",
        "reason": "Atomic validation regression.",
        **change,
    }

    response = api.client.patch(f"/jobs/{job_id}", json=payload)

    assert 400 <= response.status_code < 500, response.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_insufficient_qualified_headcount_is_flagged_and_cannot_be_scheduled(api):
    response = api.client.post(
        "/jobs/parse-and-create",
        json=create_payload(engineers_needed=3),
    )
    assert response.status_code in (200, 201), response.text
    body = response.json()
    job = response_job(body)
    assert body["assignment_conflict"]
    assert job["engineers_needed"] == 3
    assert assigned_ids(job) == []
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    proposal = api.client.post("/schedule/propose")

    assert proposal.status_code == 409, proposal.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_explicit_qualified_team_clears_assignment_conflict(api):
    create = api.client.post(
        "/jobs/parse-and-create",
        json=create_payload(engineers_needed=3),
    )
    assert create.status_code in (200, 201), create.text
    conflicted = response_job(create.json())
    assert conflicted["assignment_conflict"]
    assert assigned_ids(conflicted) == []

    response = api.client.patch(
        f"/jobs/{conflicted['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Use the available two-person qualified repair method.",
            "engineers_needed": 2,
            "assigned_engineer_ids": [101, 102],
        },
    )

    assert response.status_code == 200, response.text
    repaired = response_job(response.json())
    assert repaired["assignment_conflict"] is None
    assert repaired["engineers_needed"] == 2
    assert set(assigned_ids(repaired)) == {101, 102}


def test_requirement_change_recalculates_team_and_clears_assignment_conflict(api):
    create = api.client.post(
        "/jobs/parse-and-create",
        json=create_payload(required_skills=["Teleportation"]),
    )
    assert create.status_code in (200, 201), create.text
    conflicted = response_job(create.json())
    assert conflicted["assignment_conflict"]
    assert assigned_ids(conflicted) == []

    response = api.client.patch(
        f"/jobs/{conflicted['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Correct the mistakenly entered skill requirement.",
            "required_skills": ["Track maintenance"],
        },
    )

    assert response.status_code == 200, response.text
    repaired = response_job(response.json())
    assert repaired["assignment_conflict"] is None
    assert repaired["required_skills"] == ["Track maintenance"]
    assert set(assigned_ids(repaired)) == {101, 102}


def test_solver_prevents_track_and_staff_overlap_and_obeys_sgt_window(api):
    first = create_job(api.client, name="First rail repair")
    second = create_job(api.client, name="Second rail repair")

    response = api.client.post("/schedule/propose")
    assert response.status_code == 200, response.text
    rows = schedule_rows(response.json())
    assert {row["job_id"] for row in rows} == {first["job_id"], second["job_id"]}

    window_start, window_end = next_maintenance_window()
    intervals = []
    for row in rows:
        start = parse_instant(row["scheduled_start"]).astimezone(SGT)
        end = parse_instant(row["scheduled_end"]).astimezone(SGT)
        assert window_start <= start < end <= window_end
        assert end <= parse_instant(create_payload()["deadline"]).astimezone(SGT)
        intervals.append((start, end))
    intervals.sort()
    assert intervals[0][1] <= intervals[1][0]

    persisted = jobs(api.client)
    assert all(set(assigned_ids(job)) == {101, 102} for job in persisted)
    persisted_intervals = sorted(
        (parse_instant(job["scheduled_start"]), parse_instant(job["scheduled_end"]))
        for job in persisted
    )
    assert persisted_intervals[0][1] <= persisted_intervals[1][0]


def test_conflicting_manual_start_is_rejected_atomically(api):
    first = create_job(api.client, name="Committed rail repair")
    second = create_job(api.client, name="Repair that must not overlap")
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    first_job = next(item for item in jobs(api.client) if item["job_id"] == first["job_id"])
    second_job = next(item for item in jobs(api.client) if item["job_id"] == second["job_id"])
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    response = api.client.patch(
        f"/jobs/{second_job['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Regression: reject a conflicting track and crew commitment.",
            "assigned_engineer_ids": assigned_ids(first_job),
            "scheduled_start": first_job["scheduled_start"],
        },
    )

    assert response.status_code == 409, response.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


@pytest.mark.parametrize("line_alias", ["NS", "NSL", "North-South Line (NSL)"])
def test_line_alias_cannot_bypass_same_track_conflict(api, line_alias):
    with api.database.SessionLocal() as session:
        session.add_all(
            [
                api.database.Engineer(
                    id=105,
                    name="Evan Relief Engineer",
                    work_email="evan@example.test",
                    years_of_experience=4,
                    job_role="Engineer",
                    specialized_lines=json.dumps(["North South Line"]),
                    is_available=True,
                    skills=[api.database.EngineerSkill(skill_name="Track maintenance")],
                ),
                api.database.Engineer(
                    id=106,
                    name="Farah Relief Engineer",
                    work_email="farah@example.test",
                    years_of_experience=3,
                    job_role="Engineer",
                    specialized_lines=json.dumps(["North South Line"]),
                    is_available=True,
                    skills=[api.database.EngineerSkill(skill_name="Track maintenance")],
                ),
            ]
        )
        session.commit()
    committed = create_job(
        api.client,
        name="Canonical line repair",
        line="North South Line",
        assigned_engineer_ids=[101, 102],
    )
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    committed_job = next(job for job in jobs(api.client) if job["job_id"] == committed["job_id"])
    alternate = create_job(
        api.client,
        name=f"Alias repair {line_alias}",
        line=line_alias,
        assigned_engineer_ids=[105, 106],
    )
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    response = api.client.patch(
        f"/jobs/{alternate['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Regression attempt using a line alias.",
            "scheduled_start": committed_job["scheduled_start"],
        },
    )

    assert response.status_code == 409, response.text
    assert "track" in response.text.casefold()
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_replan_models_manual_time_and_crew_as_fixed_constraints(api):
    committed = create_job(api.client, name="Planner committed repair")
    window_start, _ = next_maintenance_window()
    committed_start = window_start + dt.timedelta(minutes=60)
    override = api.client.patch(
        f"/jobs/{committed['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Fixed possession and crew commitment.",
            "scheduled_start": committed_start.isoformat(),
            "assigned_engineer_ids": [101, 102],
        },
    )
    assert override.status_code == 200, override.text
    flexible = create_job(api.client, name="Flexible repair on the same track")

    response = api.client.post("/schedule/propose")

    assert response.status_code == 200, response.text
    stored = {job["job_id"]: job for job in jobs(api.client)}
    fixed = stored[committed["job_id"]]
    moved = stored[flexible["job_id"]]
    assert parse_instant(fixed["scheduled_start"]) == committed_start
    assert set(assigned_ids(fixed)) == {101, 102}
    fixed_interval = (
        parse_instant(fixed["scheduled_start"]),
        parse_instant(fixed["scheduled_end"]),
    )
    moved_interval = (
        parse_instant(moved["scheduled_start"]),
        parse_instant(moved["scheduled_end"]),
    )
    assert fixed_interval[1] <= moved_interval[0] or moved_interval[1] <= fixed_interval[0]
    assert set(assigned_ids(moved)) == {101, 102}


def test_solver_can_atomically_swap_two_existing_candidate_times(api, monkeypatch):
    first = create_job(api.client, name="First swappable repair")
    second = create_job(api.client, name="Second swappable repair")
    initial = api.client.post("/schedule/propose")
    assert initial.status_code == 200, initial.text
    stored = {job["job_id"]: job for job in jobs(api.client)}
    first_old, second_old = stored[first["job_id"]], stored[second["job_id"]]
    assert first_old["scheduled_start"] != second_old["scheduled_start"]
    window_start, _ = next_maintenance_window()

    def minute(value):
        return int((parse_instant(value) - window_start.astimezone(dt.timezone.utc)).total_seconds() / 60)

    def swap_solver(_jobs, _engineers, *args, **kwargs):
        rows = []
        for source, target in ((first_old, second_old), (second_old, first_old)):
            start = parse_instant(target["scheduled_start"])
            end = start + dt.timedelta(minutes=source["duration_mins"])
            rows.append(
                {
                    "id": source["job_id"],
                    "job_id": source["job_id"],
                    "name": source["name"],
                    "line": source["line"],
                    "track": source["track"],
                    "priority": source["priority"],
                    "scheduled_start": start.isoformat(),
                    "scheduled_end": end.isoformat(),
                    "scheduled_start_min": minute(start.isoformat()),
                    "scheduled_end_min": minute(end.isoformat()),
                    "assigned_engineers": [101, 102],
                }
            )
        return {
            "status": "success",
            "schedule": rows,
            "conflicts": [],
            "warnings": [],
            "solver_status": "OPTIMAL",
            "ai_explanation": "Deterministic valid swap.",
        }

    monkeypatch.setattr(api.main.solver, "solve_mrt_schedule", swap_solver)
    response = api.client.post("/schedule/propose")

    assert response.status_code == 200, response.text
    swapped = {job["job_id"]: job for job in jobs(api.client)}
    assert parse_instant(swapped[first["job_id"]]["scheduled_start"]) == parse_instant(second_old["scheduled_start"])
    assert parse_instant(swapped[second["job_id"]]["scheduled_start"]) == parse_instant(first_old["scheduled_start"])


def test_duration_override_updates_end_time_and_reason_audit(api):
    job = create_job(api.client)
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    before = jobs(api.client)[0]

    response = api.client.patch(
        f"/jobs/{job['job_id']}",
        json={
            "updated_by": "control@example.test",
            "reason": "Inspection proved the repair scope is smaller.",
            "duration_mins": 30,
        },
    )

    assert response.status_code == 200, response.text
    updated = response_job(response.json())
    start = parse_instant(before["scheduled_start"])
    assert updated["duration_mins"] == 30
    assert parse_instant(updated["scheduled_start"]) == start
    assert parse_instant(updated["scheduled_end"]) == start + dt.timedelta(minutes=30)
    assert updated["is_approved"] is False
    assert "inspection proved the repair scope is smaller" in str(audit_logs(api.client)).casefold()


def test_impossible_deadline_is_rejected_without_partial_schedule(api):
    window_start, _ = next_maintenance_window()
    response = api.client.post(
        "/jobs/parse-and-create",
        json=create_payload(
            duration_mins=60,
            deadline=(window_start + dt.timedelta(minutes=30)).isoformat(),
        ),
    )
    if 400 <= response.status_code < 500:
        assert jobs(api.client) == []
        return

    assert response.status_code in (200, 201), response.text
    before = deepcopy(jobs(api.client))
    proposal = api.client.post("/schedule/propose")
    assert 400 <= proposal.status_code < 500, proposal.text
    assert jobs(api.client) == before
    assert all(job.get("scheduled_start") is None for job in jobs(api.client))


def test_active_job_cannot_be_deleted_and_failed_delete_is_atomic(api):
    job_id = schedule_and_approve(api.client)["job_id"]
    active = api.client.patch(
        f"/checklist/{job_id}",
        json={"status": "In progress", "updated_by": "controller@example.test"},
    )
    assert active.status_code == 200, active.text
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    deletion = api.client.request(
        "DELETE",
        f"/jobs/{job_id}",
        json={"deleted_by": "controller@example.test", "reason": "Invalid active delete."},
    )
    assert deletion.status_code == 409, deletion.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


@pytest.mark.parametrize("status", ["In progress", "Done"])
def test_unscheduled_unapproved_job_cannot_enter_execution_states_atomically(api, status):
    job_id = create_job(api.client)["job_id"]
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    response = api.client.patch(
        f"/checklist/{job_id}",
        json={"status": status, "updated_by": "controller@example.test"},
    )

    assert response.status_code == 409, response.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_scheduled_but_unapproved_job_cannot_start_atomically(api):
    job_id = create_job(api.client)["job_id"]
    proposal = api.client.post("/schedule/propose")
    assert proposal.status_code == 200, proposal.text
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    response = api.client.patch(
        f"/checklist/{job_id}",
        json={"status": "In progress", "updated_by": "controller@example.test"},
    )

    assert response.status_code == 409, response.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_active_job_cannot_be_reapproved_or_rejected_atomically(api):
    job_id = schedule_and_approve(api.client)["job_id"]
    active = api.client.patch(
        f"/checklist/{job_id}",
        json={"status": "In progress", "updated_by": "controller@example.test"},
    )
    assert active.status_code == 200, active.text
    before_jobs = deepcopy(jobs(api.client))
    before_logs = deepcopy(audit_logs(api.client))

    response = api.client.post(
        f"/approval/{job_id}",
        json={
            "approved": False,
            "approved_by": "manager@example.test",
            "reason": "This attempted state change must be rejected.",
        },
    )

    assert response.status_code == 409, response.text
    assert jobs(api.client) == before_jobs
    assert audit_logs(api.client) == before_logs


def test_delay_transition_persists_reason_revised_duration_and_requires_reapproval(api):
    job_id = schedule_and_approve(api.client)["job_id"]
    active = api.client.patch(
        f"/checklist/{job_id}",
        json={"status": "In progress", "updated_by": "controller@example.test"},
    )
    assert active.status_code == 200, active.text
    active_job = next(job for job in jobs(api.client) if job["job_id"] == job_id)
    start = parse_instant(active_job["scheduled_start"])

    delayed = api.client.patch(
        f"/checklist/{job_id}",
        json={
            "status": "Delay",
            "updated_by": "controller@example.test",
            "reason": "Unexpected fastener corrosion requires more preparation.",
            "updated_repair_time_mins": 90,
        },
    )

    assert delayed.status_code == 200, delayed.text
    stored = next(job for job in jobs(api.client) if job["job_id"] == job_id)
    assert stored["status"] == "Delay"
    assert stored["is_approved"] is False
    assert stored["duration_mins"] == 90
    assert parse_instant(stored["scheduled_end"]) == start + dt.timedelta(minutes=90)
    serialized = str(audit_logs(api.client)).casefold()
    assert "unexpected fastener corrosion requires more preparation" in serialized


def test_alerts_handle_sqlite_naive_datetimes_as_utc(api):
    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)
    job_id = create_job(api.client, deadline=deadline.isoformat())["job_id"]

    response = api.client.get("/alerts/")

    assert response.status_code == 200, response.text
    assert any(alert["job_id"] == job_id for alert in response.json())


def test_schedule_endpoint_consumes_solver_result_dict_and_persists_assignments(api, monkeypatch):
    job_id = create_job(api.client)["job_id"]
    window_start, _ = next_maintenance_window()
    start = window_start + dt.timedelta(minutes=30)
    end = start + dt.timedelta(minutes=60)

    def deterministic_solver(jobs_arg, engineers_arg, *args, **kwargs):
        assert jobs_arg[0]["id"] == job_id
        assert {engineer["id"] for engineer in engineers_arg} == {101, 102, 103, 104}
        return {
            "status": "success",
            "schedule": [
                {
                    "id": job_id,
                    "job_id": job_id,
                    "name": "NS17 rail defect",
                    "line": "North South Line",
                    "track": "NS17 southbound",
                    "priority": "Urgent",
                    "scheduled_start": start.isoformat(),
                    "scheduled_end": end.isoformat(),
                    "scheduled_start_min": 30,
                    "scheduled_end_min": 90,
                    "assigned_engineers": [101, 102],
                }
            ],
            "conflicts": [],
            "warnings": [],
            "ai_explanation": "Deterministic integration fixture.",
        }

    monkeypatch.setattr(api.main.solver, "solve_mrt_schedule", deterministic_solver)
    response = api.client.post("/schedule/propose")

    assert response.status_code == 200, response.text
    rows = schedule_rows(response.json())
    assert len(rows) == 1 and rows[0]["job_id"] == job_id
    stored = jobs(api.client)[0]
    assert parse_instant(stored["scheduled_start"]) == start
    assert parse_instant(stored["scheduled_end"]) == end
    assert set(assigned_ids(stored)) == {101, 102}
