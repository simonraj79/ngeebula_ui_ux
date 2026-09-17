"""Independent PS1 schedule validator.

This module implements the public written rules.  The organisers' ``trackaccess``
validator is not present in the public problem-statement repository, so a pass
here must never be represented as an official-validator pass.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable


SCENARIOS = {"A", "B", "C"}
CONTRACT_WEIGHTS = {1: Decimal("100"), 2: Decimal("10"), 3: Decimal("1")}
ACTIVITY_NUDGES = {1: Decimal("0.3"), 2: Decimal("0.2"), 3: Decimal("0")}


def _rows(submission: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = submission.get(name)
        if value is not None:
            if isinstance(value, dict):
                return [value]
            if isinstance(value, (str, bytes)):
                return [{}]
            try:
                return list(value)
            except TypeError:
                return [{}]
    return []


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    try:
        return vars(row)
    except TypeError:
        return {}


def _integer(value: Any, *, minimum: int = 0) -> int:
    """Parse a schema integer without silently truncating floats or booleans."""
    if isinstance(value, bool):
        raise ValueError("Boolean is not an integer field")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value == value.strip() and value.lstrip("-").isdigit():
        parsed = int(value)
    else:
        raise ValueError("integer field required")
    if parsed < minimum:
        raise ValueError("integer field below minimum")
    return parsed


def _span(instance: Any, activity_id: str) -> tuple[str, ...]:
    return tuple(instance.activity_span_ids(activity_id))


def _closure(instance: Any, activity_id: str) -> tuple[str, ...]:
    return tuple(instance.closure_footprint(activity_id))


def _project(instance: Any, contract_number: str) -> Any:
    return instance.projects_by_contract[contract_number]


def _activity(instance: Any, activity_id: str) -> Any:
    return instance.activities_by_id[activity_id]


def _week_for_date(instance: Any, value: Any) -> int:
    if hasattr(instance, "week_for_date"):
        return int(instance.week_for_date(value))
    return ((value - instance.horizon_start).days // 7) + 1


def _location_supply(instance: Any, location_id: str) -> int:
    if hasattr(instance, "capacity_for"):
        # Callers that need week-specific capacity use the dedicated helper
        # below.  This fallback retains compatibility with compact fixtures.
        return int(instance.capacity_for(location_id, 1))
    row = instance.locations_by_id[location_id]
    return int(row.supply_capacity if hasattr(row, "supply_capacity") else row["supply_capacity"])


def _capacity_for(instance: Any, location_id: str, week: int) -> int:
    if hasattr(instance, "capacity_for") and 1 <= week <= instance.horizon_weeks:
        return int(instance.capacity_for(location_id, week))
    row = instance.locations_by_id[location_id]
    return int(row.supply_capacity if hasattr(row, "supply_capacity") else row["supply_capacity"])


def _line_for_location(location_id: str) -> str:
    parts = location_id.split(":")
    return parts[1] if len(parts) > 2 else ""


def _legal_mix(access_types: Iterable[str]) -> bool:
    values = list(access_types)
    pm, pc, co = values.count("PM"), values.count("PC"), values.count("C")
    if pm:
        return len(values) == 1 and pm == 1
    return (pc == 1 and co <= 3 and len(values) == pc + co) or (pc == 0 and 1 <= co <= 4)


def validate_submission(instance: Any, submission: dict[str, Any], scenario: str | None = None) -> dict[str, Any]:
    """Validate normalized output dictionaries against the published PS1 rules."""
    scenario = str(scenario or submission.get("scenario", "A")).upper()
    if scenario not in SCENARIOS:
        raise ValueError("scenario must be A, B, or C")
    access = _rows(submission, "schedule_access", "SCHEDULE_ACCESS")
    occupancy = _rows(submission, "schedule_occupancy", "SCHEDULE_OCCUPANCY")
    violations: list[dict[str, str]] = []

    def violation(rule: str, detail: str) -> None:
        violations.append({"rule": rule, "severity": "hard", "detail": detail})

    access_by_activity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    access_by_activity_week: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    valid_access: list[dict[str, Any]] = []
    for raw in access:
        row = _as_dict(raw)
        aid = str(row.get("activity_id", ""))
        if aid not in instance.activities_by_id:
            violation("schema", f"unknown activity_id {aid!r} in SCHEDULE_ACCESS")
            continue
        try:
            normalized = row | {
                "activity_id": aid,
                "access_seq": _integer(row["access_seq"], minimum=1),
                "week": _integer(row["week"], minimum=1),
                "eclo": _integer(row["eclo"]),
                "access_night": _integer(row["access_night"], minimum=1),
            }
        except (KeyError, TypeError, ValueError):
            violation("schema", f"invalid access row for {aid}")
            continue
        if normalized["eclo"] not in (0, 1):
            violation("schema", f"invalid access values for {aid}")
            continue
        valid_access.append(normalized)
        access_by_activity[aid].append(normalized)
        access_by_activity_week[(aid, normalized["week"])].append(normalized)

    for (aid, week), rows in access_by_activity_week.items():
        if len(rows) > 1:
            violation("weekly_activity", f"{aid} has more than one access in week {week}")

    for aid, activity in instance.activities_by_id.items():
        rows = sorted(access_by_activity.get(aid, []), key=lambda row: row["access_seq"])
        if [row["access_seq"] for row in rows] != list(range(1, len(rows) + 1)):
            violation("workload", f"{aid} access_seq is not contiguous from 1")
        delivered = sum((Decimal("1.5") if row["eclo"] else Decimal("1")) for row in rows)
        required = Decimal(str(activity.total_accesses))
        if delivered < required:
            violation("workload", f"{aid} delivers {delivered} of {required} required accesses")
        earliest = _week_for_date(instance, activity.planned_start_date)
        for row in rows:
            if row["week"] < earliest:
                violation("planned_start", f"{aid} scheduled in week {row['week']} before week {earliest}")
            if scenario == "A" and row["eclo"]:
                violation("eclo", f"{aid} uses ECLO in Scenario A")

    occupancy_by_key: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    occupancy_by_activity_week: dict[tuple[str, int], set[str]] = defaultdict(set)
    occupancy_count: dict[tuple[str, int, str], int] = defaultdict(int)
    valid_occupancy: list[dict[str, Any]] = []
    for raw in occupancy:
        row = _as_dict(raw)
        aid = str(row.get("activity_id", ""))
        location = str(row.get("location_id", ""))
        raw_group = row.get("co_share_group", "")
        group = raw_group.strip() if isinstance(raw_group, str) else ""
        try:
            week = _integer(row["week"], minimum=1)
        except (KeyError, TypeError, ValueError):
            violation("schema", f"invalid occupancy week for {aid!r}")
            continue
        if aid not in instance.activities_by_id or location not in instance.locations_by_id or not group:
            violation("schema", f"invalid occupancy row for {aid!r} at {location!r}")
            continue
        normalized = row | {"activity_id": aid, "location_id": location, "week": week, "co_share_group": group}
        valid_occupancy.append(normalized)
        occupancy_by_key[(location, week, group)].append(normalized)
        occupancy_by_activity_week[(aid, week)].add(location)
        occupancy_count[(aid, week, location)] += 1

    for (aid, week, location), count in occupancy_count.items():
        if count != 1:
            violation("occupancy", f"{aid} week {week} must have exactly one row for {location}")

    for (aid, week), rows in access_by_activity_week.items():
        expected = set(_span(instance, aid))
        actual = occupancy_by_activity_week.get((aid, week), set())
        if actual != expected:
            missing, extra = sorted(expected - actual), sorted(actual - expected)
            violation("occupancy", f"{aid} week {week} footprint mismatch; missing={missing}, extra={extra}")
    for aid, week in occupancy_by_activity_week:
        if (aid, week) not in access_by_activity_week:
            violation("occupancy", f"{aid} has occupancy in week {week} without an access row")

    for (location, week, group), rows in occupancy_by_key.items():
        aids = {str(row["activity_id"]) for row in rows}
        types = [_project(instance, _activity(instance, aid).contract_number).access_type for aid in aids]
        if not _legal_mix(types):
            violation("mix", f"illegal possession mix at {location}, week {week}, group {group}: {types}")

    witness_supplied = submission.get("physical_night_witness") is not None
    witness = _rows(submission, "physical_night_witness") if witness_supplied else None
    buffer_coverage = "unverified"
    if witness is not None:
        seen_witness = set()
        witness_night: dict[tuple[str, int], int] = {}
        possession_members: dict[tuple[int, int], list[str]] = defaultdict(list)
        buffer_coverage = "checked"
        for placement in witness:
            try:
                aid = str(placement["activity_id"])
                week = _integer(placement["week"], minimum=1)
                night = _integer(placement["physical_night"], minimum=1)
            except (KeyError, TypeError, ValueError):
                violation("witness", "malformed possession witness")
                buffer_coverage = "invalid"
                continue
            if aid not in instance.activities_by_id or (aid, week) not in access_by_activity_week:
                violation("witness", f"invalid or duplicate witness placement for {aid} week {week}")
                buffer_coverage = "invalid"
                continue
            if (aid, week) in seen_witness:
                violation("witness", f"invalid or duplicate witness placement for {aid} week {week}")
                buffer_coverage = "invalid"
                continue
            seen_witness.add((aid, week))
            witness_night[(aid, week)] = night
            possession_members[(week, night)].append(aid)

        group_to_nights: dict[tuple[str, int, str], set[int]] = defaultdict(set)
        night_to_groups: dict[tuple[str, int, int], set[str]] = defaultdict(set)
        for row in valid_occupancy:
            key = (row["activity_id"], row["week"])
            if key not in witness_night:
                continue
            night = witness_night[key]
            group_to_nights[(row["location_id"], row["week"], row["co_share_group"])].add(night)
            night_to_groups[(row["location_id"], row["week"], night)].add(row["co_share_group"])
        if any(len(nights) != 1 for nights in group_to_nights.values()) or any(
            len(groups) != 1 for groups in night_to_groups.values()
        ):
            violation("witness", "location-local co_share_group and physical night mapping is inconsistent")
            buffer_coverage = "invalid"

        local_to_physical: dict[tuple[str, str, int, int], set[int]] = defaultdict(set)
        physical_to_local: dict[tuple[str, str, int, int], set[int]] = defaultdict(set)
        for row in valid_access:
            key = (row["activity_id"], row["week"])
            if key not in witness_night:
                continue
            activity = _activity(instance, row["activity_id"])
            physical = witness_night[key]
            prefix = (activity.contract_number, activity.activity_type, row["week"])
            local_to_physical[prefix + (row["access_night"],)].add(physical)
            physical_to_local[prefix + (physical,)].add(row["access_night"])
        if any(len(nights) != 1 for nights in local_to_physical.values()) or any(
            len(nights) != 1 for nights in physical_to_local.values()
        ):
            violation("witness", "contract/type access_night and physical night mapping is inconsistent")
            buffer_coverage = "invalid"
        for (week, night), aids in possession_members.items():
            for index, aid in enumerate(aids):
                for other in aids[index + 1:]:
                    span, other_span = set(_span(instance, aid)), set(_span(instance, other))
                    shared = span & other_span
                    types = [_project(instance, _activity(instance, value).contract_number).access_type
                             for value in (aid, other)]
                    # Co-sharing is proven from the exported location-local rows:
                    # both activities must use the same group at every location
                    # they jointly occupy, and their access types must be legal.
                    same_local_group = bool(shared) and all(
                        len({row["co_share_group"] for row in valid_occupancy
                             if row["activity_id"] in {aid, other}
                             and row["week"] == week
                             and row["location_id"] == location}) == 1
                        for location in shared
                    )
                    conflicts = set(_closure(instance, aid)) & set(_closure(instance, other))
                    # A legal possession mix exempts only the locations that
                    # the pair actually occupies together.  Buffer-only
                    # intersections elsewhere still conflict.
                    if same_local_group and _legal_mix(types):
                        conflicts -= shared
                    if conflicts:
                        violation("closure", f"week {week}, possession {night}: {aid} conflicts with {other}")
        if seen_witness != set(access_by_activity_week):
            violation("witness", "possession witness does not cover every activity-week access")
            buffer_coverage = "invalid"

    groups_per_location_week: dict[tuple[str, int], set[str]] = defaultdict(set)
    for location, week, group in occupancy_by_key:
        groups_per_location_week[(location, week)].add(group)
    excess_total = 0
    capacity_hotspots = []
    for (location, week), groups in groups_per_location_week.items():
        supply = _capacity_for(instance, location, week)
        excess = max(0, len(groups) - supply)
        excess_total += excess
        if len(groups) >= supply:
            capacity_hotspots.append({"location_id": location, "week": week, "used": len(groups), "supply": supply})
        allowed = 0 if scenario == "A" else 1 if scenario == "C" else None
        if allowed is not None and excess > allowed:
            violation("capacity", f"{location} week {week} uses {len(groups)} possession nights; supply {supply}, allowance {allowed}")

    # The published occupancy schema assigns co_share_group independently per
    # location; the official sample legitimately changes b1/b2/b4 along one
    # activity span.  It therefore does not expose a global physical night with
    # which to reconstruct pairwise buffer collisions.  We validate footprints,
    # local legal mixes and all capacity accounting here, while the solver uses
    # closure_footprint conservatively during construction.  Do not invent a
    # global-night interpretation that rejects the organisers' sample.

    contract_type_week_nights: dict[tuple[str, str, int], set[int]] = defaultdict(set)
    contract_type_week_night_activities: dict[tuple[str, str, int, int], set[str]] = defaultdict(set)
    for row in valid_access:
        activity = _activity(instance, row["activity_id"])
        key = (activity.contract_number, activity.activity_type, row["week"])
        contract_type_week_nights[key].add(row["access_night"])
        contract_type_week_night_activities[key + (row["access_night"],)].add(row["activity_id"])
    for key, nights in contract_type_week_nights.items():
        project = _project(instance, key[0])
        if len(nights) > project.number_of_maximum_access_per_week or max(nights) > project.number_of_maximum_access_per_week:
            violation("weekly_allocation", f"{key} uses access nights {sorted(nights)} above cap {project.number_of_maximum_access_per_week}")
    for key, aids in contract_type_week_night_activities.items():
        project = _project(instance, key[0])
        if len(aids) > project.number_of_workfronts:
            violation("workfront", f"{key} has {len(aids)} activities; cap {project.number_of_workfronts}")

    eclo_by_line: dict[str, list[int]] = defaultdict(list)
    if scenario == "C":
        for row in valid_access:
            if not row["eclo"]:
                continue
            lines = {_line_for_location(location) for location in _closure(instance, row["activity_id"])}
            for line in lines - {""}:
                eclo_by_line[line].append(row["week"])
        for line, weeks in eclo_by_line.items():
            if max(weeks) - min(weeks) + 1 > 2:
                violation("eclo_continuity", f"{line} ECLO weeks {sorted(set(weeks))} exceed one two-week span")

    completion_week = {aid: max((row["week"] for row in rows), default=0) for aid, rows in access_by_activity.items()}
    contract_completion = {}
    overrun_total = 0
    contracts_overrunning = 0
    priority_overrun = {"1": 0, "2": 0, "3": 0}
    weighted_overrun = Decimal("0")
    for contract, project in instance.projects_by_contract.items():
        activities = [a for a in instance.activities_by_id.values() if a.contract_number == contract]
        week = max((completion_week.get(a.activity_id, 0) for a in activities), default=0)
        completion_date = instance.horizon_start + timedelta(days=max(0, week * 7 - 1))
        days = max(0, (completion_date - project.planned_completion_date).days)
        contract_completion[contract] = (completion_date, days)
        overrun_total += days
        contracts_overrunning += int(days > 0)
        priority_overrun[str(project.contract_priority)] += days
        if scenario == "B" and days:
            violation("planned_date", f"{contract} completes {days} days after planned completion")
        for activity in activities:
            activity_week = completion_week.get(activity.activity_id, 0)
            activity_date = instance.horizon_start + timedelta(days=max(0, activity_week * 7 - 1))
            activity_days = max(0, (activity_date - project.planned_completion_date).days)
            weighted_overrun += CONTRACT_WEIGHTS[project.contract_priority] * (
                Decimal("1") + ACTIVITY_NUDGES[activity.activity_priority]
            ) * activity_days

    supplied_results = _rows(submission, "results", "RESULTS")
    if not supplied_results:
        violation("results", "RESULTS must contain exactly one row per contract")
    else:
        seen_contracts = set()
        for raw in supplied_results:
            row = _as_dict(raw)
            contract = str(row.get("contract_number", ""))
            row_scenario = str(row.get("scenario", "")).upper()
            if row_scenario != scenario:
                violation("results", f"RESULTS mixes or mislabels scenario {row_scenario!r}; expected {scenario}")
            if contract not in contract_completion or contract in seen_contracts:
                violation("results", f"RESULTS has unknown or duplicate contract {contract!r}")
                continue
            seen_contracts.add(contract)
            expected_date, expected_days = contract_completion[contract]
            try:
                actual_date = date.fromisoformat(str(row["simulated_completion_date"]))
                actual_days = _integer(row["overrun_days"])
            except (KeyError, TypeError, ValueError):
                violation("results", f"RESULTS has malformed completion values for {contract}")
                continue
            if actual_days < 0 or (actual_date, actual_days) != (expected_date, expected_days):
                violation("results", f"RESULTS completion for {contract} does not match scheduled accesses")
        missing_contracts = set(contract_completion) - seen_contracts
        if missing_contracts:
            violation("results", f"RESULTS omits contracts {sorted(missing_contracts)}")

    eclo_total = sum(row["eclo"] for row in valid_access)
    objective = (Decimal("0") if scenario == "B" else weighted_overrun) + (
        Decimal("0") if scenario == "A" else Decimal(7 * excess_total + 5 * eclo_total)
    )
    soft_scores = {
        "scenario": scenario,
        "overrun_days_total": overrun_total,
        "contracts_overrunning": contracts_overrunning,
        "excess_access_nights_total": excess_total,
        "eclo_nights_total": eclo_total,
        "priority_overrun": priority_overrun,
        "priority_weighted_score": float(weighted_overrun),
    }
    if not violations:
        soft_scores.update(objective_score=float(objective),
                           formula_version="public-brief-2026-09-17-independent")
    complete = not violations and buffer_coverage == "checked"
    coverage = {"closure": buffer_coverage, "structural": "checked", "objectives": "checked"}
    return {
        "scenario": scenario,
        "feasible": not violations,
        "complete": complete,
        "coverage": coverage,
        "validator": {"name": "ngeebula-independent-ps1", "official": False,
                      "complete": complete,
                      "coverage": coverage,
                      "note": "Official trackaccess validator was not published; arbitrary CSV group IDs leave buffers partial unless a solver possession witness is supplied."},
        "hard_violations": violations,
        "soft_scores": soft_scores,
        "detail": {"capacity_hotspots": capacity_hotspots,
                   "nights_scheduled": len(valid_access), "eclo_nights": eclo_total},
        "contract_completion": {
            contract: {"simulated_completion_date": value[0].isoformat(), "overrun_days": value[1]}
            for contract, value in contract_completion.items()
        },
    }


validate = validate_submission
