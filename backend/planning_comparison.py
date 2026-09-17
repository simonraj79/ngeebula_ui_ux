"""Deterministic, read-only comparisons of three planning approaches.

The scenarios in this module are synthetic teaching examples.  They do not
read or write the application database and they do not estimate operational
safety, reliability, or real staff performance.
"""

from __future__ import annotations

import datetime as dt
import math
import time
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional

try:
    from . import solver
except ImportError:  # pragma: no cover - supports direct backend imports
    import solver


UTC = dt.timezone.utc
SGT = dt.timezone(dt.timedelta(hours=8))
PRIORITY_ORDER = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}


def _instant(value: Any) -> dt.datetime:
    return solver.as_utc(value)


def _overlaps(start: dt.datetime, end: dt.datetime, other_start: Any, other_end: Any) -> bool:
    return start < _instant(other_end) and _instant(other_start) < end


def _qualified(engineer: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    known = {str(skill).strip().casefold() for skill in engineer.get("skills", [])}
    needed = {str(skill).strip().casefold() for skill in job.get("required_skills", [])}
    return bool(engineer.get("is_available")) and needed <= known


def _candidate_row(job: Mapping[str, Any], start: dt.datetime, engineer_ids: Iterable[Any]) -> Dict[str, Any]:
    duration = int(job["duration_mins"])
    end = start + dt.timedelta(minutes=duration)
    return {
        "job_id": job["id"],
        "name": job["name"],
        "line": job["line"],
        "track": job["track"],
        "priority": job["priority"],
        "deadline": _instant(job["deadline"]).isoformat(),
        "duration_mins": duration,
        "scheduled_start": start.isoformat(),
        "scheduled_end": end.isoformat(),
        "assigned_engineer_ids": list(engineer_ids),
        "on_time": end <= _instant(job["deadline"]),
    }


def _can_place(
    job: Mapping[str, Any],
    start: dt.datetime,
    engineer_ids: Iterable[Any],
    scheduled: List[Mapping[str, Any]],
    commitments: List[Mapping[str, Any]],
) -> bool:
    end = start + dt.timedelta(minutes=int(job["duration_mins"]))
    if end > _instant(job["deadline"]):
        return False
    ids = {str(value) for value in engineer_ids}
    for other in [*commitments, *scheduled]:
        if not _overlaps(start, end, other["scheduled_start"], other["scheduled_end"]):
            continue
        same_location = (
            str(job["line"]).casefold() == str(other["line"]).casefold()
            and str(job["track"]).casefold() == str(other["track"]).casefold()
        )
        other_ids = {str(value) for value in other.get("assigned_engineer_ids", [])}
        if same_location or ids & other_ids:
            return False
    return True


def _available_team(
    job: Mapping[str, Any],
    start: dt.datetime,
    scheduled: List[Mapping[str, Any]],
    commitments: List[Mapping[str, Any]],
    engineers: List[Mapping[str, Any]],
) -> Optional[List[Any]]:
    eligible = sorted(
        (engineer for engineer in engineers if _qualified(engineer, job)),
        key=lambda engineer: str(engineer["id"]),
    )
    needed = int(job["engineers_needed"])
    # Try combinations rather than taking a busy first engineer and giving up.
    from itertools import combinations

    for team in combinations(eligible, needed):
        ids = [engineer["id"] for engineer in team]
        if _can_place(job, start, ids, scheduled, commitments):
            return ids
    return None


def _manual_proxy(
    candidates: List[Mapping[str, Any]],
    engineers: List[Mapping[str, Any]],
    commitments: List[Mapping[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep requested slots in worksheet order; never search another time."""
    scheduled: List[Dict[str, Any]] = []
    unscheduled: List[Dict[str, Any]] = []
    for job in candidates:
        start = _instant(job["scheduled_start"])
        team = _available_team(job, start, scheduled, commitments, engineers)
        if team is None:
            unscheduled.append({
                "job_id": job["id"],
                "reason": "The requested slot has a location, deadline, or qualified-crew conflict; this proxy does not search alternatives.",
            })
        else:
            scheduled.append(_candidate_row(job, start, team))
    return scheduled, unscheduled


def _priority_first_fit(
    candidates: List[Mapping[str, Any]],
    engineers: List[Mapping[str, Any]],
    commitments: List[Mapping[str, Any]],
    window_start: dt.datetime,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    scheduled: List[Dict[str, Any]] = []
    unscheduled: List[Dict[str, Any]] = []
    ordered = sorted(
        candidates,
        key=lambda job: (PRIORITY_ORDER[job["priority"]], _instant(job["deadline"]), str(job["id"])),
    )
    for job in ordered:
        latest_start = _instant(job["deadline"]) - dt.timedelta(minutes=int(job["duration_mins"]))
        minute = window_start
        placed = False
        while minute <= latest_start:
            team = _available_team(job, minute, scheduled, commitments, engineers)
            if team is not None:
                scheduled.append(_candidate_row(job, minute, team))
                placed = True
                break
            minute += dt.timedelta(minutes=1)
        if not placed:
            unscheduled.append({
                "job_id": job["id"],
                "reason": "No first-fit slot with enough qualified free crew was found before the deadline.",
            })
    scheduled.sort(key=lambda row: (row["scheduled_start"], str(row["job_id"])))
    return scheduled, unscheduled


def _metrics(candidates: List[Mapping[str, Any]], schedule: List[Mapping[str, Any]], commitments: List[Mapping[str, Any]]) -> Dict[str, int]:
    scheduled_ids = {str(row["job_id"]) for row in schedule}
    preserved = 0
    for commitment in commitments:
        conflict = False
        commitment_ids = {str(value) for value in commitment.get("assigned_engineer_ids", [])}
        for row in schedule:
            if not _overlaps(_instant(row["scheduled_start"]), _instant(row["scheduled_end"]), commitment["scheduled_start"], commitment["scheduled_end"]):
                continue
            same_location = (
                str(row["line"]).casefold() == str(commitment["line"]).casefold()
                and str(row["track"]).casefold() == str(commitment["track"]).casefold()
            )
            row_ids = {str(value) for value in row.get("assigned_engineer_ids", [])}
            if same_location or row_ids & commitment_ids:
                conflict = True
                break
        preserved += int(not conflict)
    return {
        "candidate_jobs": len(candidates),
        "scheduled_jobs": len(scheduled_ids),
        "on_time_jobs": sum(bool(row.get("on_time")) for row in schedule),
        "unscheduled_jobs": len(candidates) - len(scheduled_ids),
        "fixed_commitments_preserved": preserved,
    }


def _method_result(
    method_id: str,
    name: str,
    description: str,
    candidates: List[Mapping[str, Any]],
    commitments: List[Mapping[str, Any]],
    schedule: List[Dict[str, Any]],
    unscheduled: List[Dict[str, Any]],
    *,
    solver_status: Optional[str] = None,
    wall_time_ms: Optional[float] = None,
    status_override: Optional[str] = None,
) -> Dict[str, Any]:
    metrics = _metrics(candidates, schedule, commitments)
    status = status_override or ("complete" if metrics["unscheduled_jobs"] == 0 else "incomplete")
    result: Dict[str, Any] = {
        "method_id": method_id,
        "method_name": name,
        "method_description": description,
        "status": status,
        "schedule": schedule,
        "unscheduled": unscheduled,
        "metrics": metrics,
    }
    if solver_status is not None:
        result["solver_status"] = solver_status
    if wall_time_ms is not None:
        result["wall_time_ms"] = round(wall_time_ms, 3)
    return result


def _scenario(name: str) -> Dict[str, Any]:
    if name not in {"joint_planning", "straightforward", "no_capacity"}:
        raise ValueError("scenario must be joint_planning, straightforward, or no_capacity")
    start = dt.datetime(2026, 10, 1, 0, 30, tzinfo=SGT).astimezone(UTC)
    end = start + dt.timedelta(hours=4, minutes=30)
    engineers = [
        {"id": 8101, "name": "Synthetic multi-skill engineer", "skills": ["Mechanical", "Signalling"], "is_available": True},
        {"id": 8102, "name": "Synthetic mechanical engineer", "skills": ["Mechanical"], "is_available": True},
    ]
    commitments = [{
        "job_id": "fixed-1", "name": "Approved preventive inspection",
        "line": "North-South Line (NSL)", "track": "Synthetic bay C",
        "scheduled_start": (start + dt.timedelta(minutes=210)).isoformat(),
        "scheduled_end": (start + dt.timedelta(minutes=240)).isoformat(),
        "assigned_engineer_ids": [8101], "is_approved": True, "time_locked": True,
    }]

    def job(job_id: str, name_: str, track: str, offset: int, duration: int, deadline: int, skills: List[str], priority: str) -> Dict[str, Any]:
        return {
            "id": job_id, "name": name_, "line": "North-South Line (NSL)", "track": track,
            "scheduled_start": start + dt.timedelta(minutes=offset),
            "duration_mins": duration, "deadline": start + dt.timedelta(minutes=deadline),
            "required_skills": skills, "engineers_needed": 1, "priority": priority,
            "status": "Not started", "is_approved": False, "time_locked": False,
            "assignment_locked": False, "assigned_engineer_ids": [],
        }

    if name == "joint_planning":
        candidates = [
            job("flexible-1", "Mechanical door adjustment", "Synthetic bay A", 0, 90, 150, ["Mechanical"], "Urgent"),
            job("specialist-1", "Signal equipment correction", "Synthetic bay B", 30, 60, 90, ["Signalling"], "High"),
        ]
    elif name == "straightforward":
        candidates = [
            job("simple-1", "Mechanical door adjustment", "Synthetic bay A", 0, 45, 90, ["Mechanical"], "High"),
            job("simple-2", "Signal equipment correction", "Synthetic bay B", 90, 45, 180, ["Signalling"], "Medium"),
        ]
    else:
        candidates = [
            job("blocked-1", "Long mechanical correction", "Synthetic bay A", 0, 180, 180, ["Mechanical"], "Urgent"),
            job("blocked-2", "Deadline-bound signal correction", "Synthetic bay B", 0, 120, 120, ["Signalling"], "High"),
        ]
        # Both jobs need engineer 8101 for overlapping full deadline windows.
        candidates[0]["required_skills"] = ["Mechanical", "Signalling"]
    return {"window_start": start, "window_end": end, "engineers": engineers, "commitments": commitments, "candidates": candidates}


def run_planning_comparison(scenario: str = "joint_planning") -> Dict[str, Any]:
    """Run the three methods against one identical synthetic input set."""
    data = _scenario(scenario)
    candidates = data["candidates"]
    engineers = data["engineers"]
    commitments = data["commitments"]
    start, end = data["window_start"], data["window_end"]

    manual_schedule, manual_unscheduled = _manual_proxy(candidates, engineers, commitments)
    heuristic_schedule, heuristic_unscheduled = _priority_first_fit(candidates, engineers, commitments, start)

    solver_commitments = [{
        "line": row["line"], "track": row["track"],
        "scheduled_start": row["scheduled_start"], "scheduled_end": row["scheduled_end"],
        "assigned_engineer_ids": row["assigned_engineer_ids"],
    } for row in commitments]
    tick = time.perf_counter()
    solved = solver.solve_mrt_schedule(
        deepcopy(candidates), deepcopy(engineers), window_start=start, window_end=end,
        commitments=solver_commitments,
    )
    elapsed_ms = (time.perf_counter() - tick) * 1000
    cp_schedule: List[Dict[str, Any]] = []
    if solved.get("status") == "success":
        by_id = {str(job["id"]): job for job in candidates}
        for row in solved.get("schedule", []):
            source = by_id[str(row["job_id"])]
            cp_schedule.append(_candidate_row(source, _instant(row["scheduled_start"]), row.get("assigned_engineers") or []))
    scheduled_ids = {str(row["job_id"]) for row in cp_schedule}
    cp_unscheduled = [{
        "job_id": job["id"],
        "reason": ("The all-or-none CP-SAT plan is infeasible with every candidate included; no candidate was silently dropped."
                   if solved.get("status") == "infeasible" else "The solver did not return this candidate in a complete plan."),
    } for job in candidates if str(job["id"]) not in scheduled_ids]

    methods = [
        _method_result("manual_proxy", "Keep requested slots", "Manual worksheet proxy: process input order, keep each requested start, and do not search another time. This is a reproducible rule, not a benchmark of people.", candidates, commitments, manual_schedule, manual_unscheduled),
        _method_result("priority_first_fit", "Priority then first fit", "Sort by priority and deadline, then take the first minute and qualified free crew that fits. Earlier choices are not reconsidered.", candidates, commitments, heuristic_schedule, heuristic_unscheduled),
        _method_result(
            "cp_sat", "Joint constraint planning",
            "Run the existing OR-Tools CP-SAT planner on every candidate together. The live all-or-none policy never silently drops a job.",
            candidates, commitments, cp_schedule, cp_unscheduled,
            solver_status=solved.get("solver_status") or str(solved.get("status", "unknown")).upper(),
            wall_time_ms=elapsed_ms,
            status_override=(
                "complete" if solved.get("status") == "success" and len(cp_schedule) == len(candidates)
                else "infeasible" if solved.get("status") == "infeasible"
                else "unknown" if solved.get("status") == "unknown"
                else "error"
            ),
        ),
    ]
    measured = {method["method_id"]: deepcopy(method["metrics"]) for method in methods}
    measured["cp_sat"]["solver_wall_time_ms"] = methods[2]["wall_time_ms"]
    return {
        "synthetic": True, "persisted": False, "can_apply": False,
        "scenario": scenario,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "comparison_basis": "Same synthetic fixed commitments, candidate jobs, deadlines, locations, and crew for every method.",
        "scenario_explanation": {
            "joint_planning": "The flexible job can use either engineer, but the signalling job needs the multi-skill engineer. Sequential rules commit that specialist too early; joint planning sees both needs together.",
            "straightforward": "The requested jobs do not compete for the same time and specialist, so the simpler rules match joint planning.",
            "no_capacity": "Both deadline windows require the only signalling-qualified engineer. No method can fit every candidate, and CP-SAT returns no partial plan under the live all-or-none policy.",
        }[scenario],
        "commitments": deepcopy(commitments),
        "engineers": deepcopy(engineers),
        "candidates": [{**deepcopy(job), "scheduled_start": _instant(job["scheduled_start"]).isoformat(), "deadline": _instant(job["deadline"]).isoformat()} for job in candidates],
        "methods": methods,
        "measured_synthetic_outputs": measured,
        "roi": {
            "status": "assumptions_required",
            "message": "No money or staff-performance claim is inferred from this synthetic run. Supply planning-frequency, time, and optional labour-cost assumptions to calculate_roi.",
            "unmonetized": ["safety", "reliability", "service availability", "maintenance quality"],
        },
    }


def _finite_nonnegative(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


def calculate_roi(
    *,
    planning_shifts_per_month: float,
    minutes_per_cycle: Mapping[str, float],
    loaded_hourly_cost_sgd: Optional[float] = None,
    initial_cost_sgd: Optional[Mapping[str, float]] = None,
    monthly_operating_cost_sgd: Optional[Mapping[str, float]] = None,
    baseline_method: str = "manual_proxy",
) -> Dict[str, Any]:
    """Calculate an assumption-led planning-effort comparison.

    Scheduling outcomes from ``run_planning_comparison`` are deliberately not
    extrapolated into money.  Only the caller's explicit time and cost inputs
    participate in these formulas.
    """
    shifts = _finite_nonnegative("planning_shifts_per_month", planning_shifts_per_month)
    if not isinstance(minutes_per_cycle, Mapping) or not minutes_per_cycle:
        raise ValueError("minutes_per_cycle must contain at least one method")
    minutes = {str(key): _finite_nonnegative(f"minutes_per_cycle[{key}]", value) for key, value in minutes_per_cycle.items()}
    if baseline_method not in minutes:
        raise ValueError("baseline_method must appear in minutes_per_cycle")
    rate = None if loaded_hourly_cost_sgd is None else _finite_nonnegative("loaded_hourly_cost_sgd", loaded_hourly_cost_sgd)
    initial = {str(key): _finite_nonnegative(f"initial_cost_sgd[{key}]", value) for key, value in (initial_cost_sgd or {}).items()}
    monthly = {str(key): _finite_nonnegative(f"monthly_operating_cost_sgd[{key}]", value) for key, value in (monthly_operating_cost_sgd or {}).items()}
    unknown = (set(initial) | set(monthly)) - set(minutes)
    if unknown:
        raise ValueError("cost assumptions contain an unknown method")

    annual_hours = {key: shifts * 12 * value / 60 for key, value in minutes.items()}
    baseline_hours = annual_hours[baseline_method]
    baseline_initial = initial.get(baseline_method, 0.0)
    baseline_monthly = monthly.get(baseline_method, 0.0)
    outputs: Dict[str, Any] = {}
    for key in minutes:
        row: Dict[str, Any] = {
            "annual_planning_hours": annual_hours[key],
            "hours_saved_vs_baseline": baseline_hours - annual_hours[key],
        }
        if rate is not None:
            annual_labour = annual_hours[key] * rate
            baseline_labour = baseline_hours * rate
            annual_operating = monthly.get(key, 0.0) * 12
            incremental_initial = initial.get(key, 0.0) - baseline_initial
            incremental_annual_operating = (monthly.get(key, 0.0) - baseline_monthly) * 12
            annual_net = baseline_labour - annual_labour - incremental_annual_operating
            row.update({
                "annual_planning_labour_cost_sgd": annual_labour,
                "planning_labour_savings_vs_baseline_sgd": baseline_labour - annual_labour,
                "initial_cost_sgd": initial.get(key, 0.0),
                "annual_operating_cost_sgd": annual_operating,
                "incremental_initial_cost_sgd": incremental_initial,
                "incremental_annual_operating_cost_sgd": incremental_annual_operating,
                "annual_net_benefit_sgd": annual_net,
                "first_year_net_benefit_sgd": annual_net - incremental_initial,
            })
            if incremental_initial > 0:
                row["first_year_roi_percent"] = ((annual_net - incremental_initial) / incremental_initial) * 100
            else:
                row["first_year_roi_percent"] = None
                row["roi_note"] = "ROI percentage is undefined when incremental initial cost is zero or negative. Review net benefit instead."
            row["payback_months"] = (
                incremental_initial / (annual_net / 12)
                if incremental_initial > 0 and annual_net > 0 else None
            )
        outputs[key] = row
    return {
        "assumptions": {
            "planning_shifts_per_month": shifts,
            "minutes_per_cycle": minutes,
            "loaded_hourly_cost_sgd": rate,
            "initial_cost_sgd": initial,
            "monthly_operating_cost_sgd": monthly,
            "baseline_method": baseline_method,
        },
        "calculated_outputs": outputs,
        "scope": "Planning effort and caller-supplied labour cost only.",
        "unmonetized": ["safety", "reliability", "service availability", "maintenance quality"],
    }
