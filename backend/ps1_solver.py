"""Construct complete PS1 track-access schedules from normalized instances.

The construction heuristic is deliberately validator-led: it never returns a
partial schedule as feasible.  It packs compatible possessions first, then
opens additional possession nights subject to each scenario's supply policy.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
import time
from typing import Any

try:
    from .ps1_validator import validate_submission
except ImportError:  # pragma: no cover - direct module execution
    from ps1_validator import validate_submission


def _week_for_date(instance: Any, value: Any) -> int:
    if hasattr(instance, "week_for_date"):
        return max(1, int(instance.week_for_date(value)))
    return max(1, ((value - instance.horizon_start).days // 7) + 1)


def _span(instance: Any, aid: str) -> set[str]:
    return set(instance.activity_span_ids(aid))


def _closure(instance: Any, aid: str) -> set[str]:
    return set(instance.closure_footprint(aid))


def _legal_mix(types: list[str]) -> bool:
    pm, pc, co = types.count("PM"), types.count("PC"), types.count("C")
    if pm:
        return len(types) == 1 and pm == 1
    return (pc == 1 and co <= 3 and len(types) == pc + co) or (pc == 0 and 1 <= co <= 4)


def _capacity(instance: Any, location: str, disruptions: dict[str, Any] | None, week: int) -> int:
    if hasattr(instance, "capacity_for") and 1 <= week <= instance.horizon_weeks:
        base = int(instance.capacity_for(location, week))
    else:
        row = instance.locations_by_id[location]
        base = int(row.supply_capacity if hasattr(row, "supply_capacity") else row["supply_capacity"])
    if not disruptions:
        return base
    reductions = disruptions.get("location_supply", disruptions.get("supply", {}))
    for key in ((location, week), f"{location}|{week}", location):
        if key in reductions:
            value = reductions[key]
            if isinstance(value, dict):
                value = value.get(str(week), value.get(week, base))
            return max(0, int(value))
    return base


def _preferred_rows(baseline: dict[str, Any] | None) -> dict[tuple[str, int], tuple[int, int]]:
    result = {}
    if not baseline:
        return result
    rows = baseline.get("schedule_access", baseline.get("SCHEDULE_ACCESS", []))
    for row in rows:
        try:
            result[(str(row["activity_id"]), int(row["access_seq"]))] = (
                int(row["week"]), int(row["access_night"])
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


class _Builder:
    def __init__(self, instance: Any, scenario: str, deadline: float,
                 baseline: dict[str, Any] | None, disruptions: dict[str, Any] | None,
                 order_mode: str = "scenario", strict_supply: bool = False):
        self.instance, self.scenario, self.deadline = instance, scenario, deadline
        self.disruptions = disruptions
        self.order_mode = order_mode
        self.strict_supply = strict_supply
        self.preferred = _preferred_rows(baseline)
        self.access: list[dict[str, Any]] = []
        self.occupancy: list[dict[str, Any]] = []
        self.group_members: dict[tuple[int, int], set[str]] = defaultdict(set)
        self.location_groups: dict[tuple[str, int], set[int]] = defaultdict(set)
        self.location_group_members: dict[tuple[str, int, int], set[str]] = defaultdict(set)
        self.contract_night_map: dict[tuple[str, str, int], dict[int, int]] = defaultdict(dict)
        self.workfronts: dict[tuple[str, str, int, int], set[str]] = defaultdict(set)
        self.eclo_weeks: dict[str, list[int]] = defaultdict(list)

    def project(self, aid: str) -> Any:
        return self.instance.projects_by_contract[self.instance.activities_by_id[aid].contract_number]

    def _candidate_nights(self, aid: str, seq: int, week: int) -> list[int]:
        preferred = self.preferred.get((aid, seq))
        existing = sorted({night for candidate_week, night in self.group_members if candidate_week == week})
        values = []
        if preferred and preferred[0] == week:
            # Baseline access_night is contract-local, but using it as an early
            # global-night hint reduces churn without making it authoritative.
            values.append(preferred[1])
        values.extend(existing)
        values.extend(range(1, 13))
        return list(dict.fromkeys(values))

    def can_place(self, aid: str, week: int, night: int, eclo: int) -> bool:
        if time.monotonic() >= self.deadline:
            raise TimeoutError
        activity, project = self.instance.activities_by_id[aid], self.project(aid)
        key = (activity.contract_number, activity.activity_type, week)
        night_map = self.contract_night_map[key]
        if night not in night_map and len(night_map) >= project.number_of_maximum_access_per_week:
            return False
        if len(self.workfronts[key + (night,)]) >= project.number_of_workfronts:
            return False
        if eclo and self.scenario == "A":
            return False
        if eclo and self.scenario == "C":
            lines = {location.split(":")[1] for location in _closure(self.instance, aid)}
            for line in lines:
                weeks = self.eclo_weeks[line] + [week]
                if max(weeks) - min(weeks) + 1 > 2:
                    return False

        span, closure = _span(self.instance, aid), _closure(self.instance, aid)
        for location in span:
            members = self.location_group_members[(location, week, night)]
            types = [self.project(member).access_type for member in members] + [project.access_type]
            if members and not _legal_mix(types):
                return False
            groups = self.location_groups[(location, week)]
            if night not in groups:
                supply = _capacity(self.instance, location, self.disruptions, week)
                allowance = (0 if self.strict_supply or self.scenario == "A"
                             else 1 if self.scenario == "C" else 12)
                if len(groups) >= supply + allowance:
                    return False
        for other in self.group_members[(week, night)]:
            other_span = _span(self.instance, other)
            shared = span & other_span
            legal_shared = shared and all(_legal_mix([
                self.project(member).access_type
                for member in self.location_group_members[(location, week, night)] | {aid}
            ]) for location in shared)
            conflicts = closure & _closure(self.instance, other)
            if legal_shared:
                conflicts -= shared
            if conflicts:
                return False
        return True

    def place(self, aid: str, seq: int, week: int, night: int, eclo: int) -> None:
        activity, project = self.instance.activities_by_id[aid], self.project(aid)
        key = (activity.contract_number, activity.activity_type, week)
        night_map = self.contract_night_map[key]
        if night not in night_map:
            night_map[night] = len(night_map) + 1
        local_night = night_map[night]
        self.workfronts[key + (night,)].add(aid)
        self.group_members[(week, night)].add(aid)
        if eclo:
            for line in {location.split(":")[1] for location in _closure(self.instance, aid)}:
                self.eclo_weeks[line].append(week)
        group = f"w{week:03d}-n{night:02d}"
        self.access.append({"activity_id": aid, "access_seq": seq, "week": week,
                            "eclo": eclo, "access_night": local_night})
        for location in sorted(_span(self.instance, aid)):
            self.location_groups[(location, week)].add(night)
            self.location_group_members[(location, week, night)].add(aid)
            self.occupancy.append({"activity_id": aid, "week": week,
                                   "location_id": location, "co_share_group": group})

    def build(self, eclo_count_by_activity: dict[str, int]) -> tuple[bool, str | None]:
        def order(activity: Any) -> tuple:
            project = self.instance.projects_by_contract[activity.contract_number]
            if self.order_mode == "deadline" or (self.order_mode == "scenario" and self.scenario == "B"):
                return (project.planned_completion_date, project.contract_priority,
                        activity.activity_priority, activity.planned_start_date,
                        -Decimal(str(activity.total_accesses)), activity.activity_id)
            return (project.contract_priority, activity.activity_priority,
                    project.planned_completion_date, activity.planned_start_date,
                    -Decimal(str(activity.total_accesses)), activity.activity_id)

        activities = sorted(self.instance.activities_by_id.values(), key=order)
        for activity in activities:
            aid = activity.activity_id
            project = self.project(aid)
            required = Decimal(str(activity.total_accesses))
            eclo_count = min(eclo_count_by_activity.get(aid, 0), int(required.to_integral_value(rounding=ROUND_CEILING)))
            while True:
                access_count = int((required - Decimal("0.5") * eclo_count).to_integral_value(rounding=ROUND_CEILING))
                if eclo_count <= access_count:
                    break
                eclo_count = access_count
            earliest = _week_for_date(self.instance, activity.planned_start_date)
            if self.scenario == "B":
                latest = _week_for_date(self.instance, project.planned_completion_date)
            else:
                latest = max(self.instance.horizon_weeks, earliest) + 52
            previous_week = earliest - 1
            for seq in range(1, access_count + 1):
                eclo = int(seq > access_count - eclo_count)
                preferred = self.preferred.get((aid, seq))
                weeks = list(range(previous_week + 1, latest + 1))
                if preferred and preferred[0] in weeks:
                    weeks.remove(preferred[0]); weeks.insert(0, preferred[0])
                placed = False
                for week in weeks:
                    for night in self._candidate_nights(aid, seq, week):
                        if self.can_place(aid, week, night, eclo):
                            self.place(aid, seq, week, night, eclo)
                            previous_week, placed = week, True
                            break
                    if placed:
                        break
                if not placed:
                    return False, f"No placement found for {aid} access {seq} in weeks {previous_week + 1}..{latest}."
        return True, None


def _results_rows(instance: Any, access: list[dict[str, Any]], scenario: str) -> list[dict[str, Any]]:
    completion_week: dict[str, int] = defaultdict(int)
    for row in access:
        completion_week[row["activity_id"]] = max(completion_week[row["activity_id"]], row["week"])
    rows = []
    for contract, project in sorted(instance.projects_by_contract.items()):
        week = max((completion_week[activity.activity_id]
                    for activity in instance.activities_by_id.values()
                    if activity.contract_number == contract), default=0)
        completion = instance.horizon_start + timedelta(days=max(0, week * 7 - 1))
        rows.append({"scenario": scenario, "contract_number": contract,
                     "simulated_completion_date": completion.isoformat(),
                     "overrun_days": max(0, (completion - project.planned_completion_date).days)})
    return rows


def solve(instance: Any, scenario: str = "A", time_limit_seconds: float = 20,
          baseline: dict[str, Any] | None = None,
          disruptions: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build and independently validate a complete PS1 scenario schedule.

    ``status='success'`` is returned only for a complete workload with zero
    independent-validator violations.  Timeouts and construction failures are
    ``unresolved`` rather than mislabeled infeasible.
    """
    scenario = str(scenario).upper()
    if scenario not in {"A", "B", "C"}:
        raise ValueError("scenario must be A, B, or C")
    if isinstance(time_limit_seconds, bool) or not 0 < float(time_limit_seconds) <= 300:
        raise ValueError("time_limit_seconds must be greater than 0 and at most 300")
    started, deadline = time.monotonic(), time.monotonic() + float(time_limit_seconds)
    attempts: list[tuple[dict[str, int], str, str, bool]] = [
        ({}, "scenario", "standard-scenario-order", False)
    ]
    if scenario != "B":
        attempts.append(({}, "deadline", "standard-deadline-order", False))
    if scenario == "C":
        # Every strict-supply A construction is also a valid C candidate. Keep
        # it in C's bounded pool so relaxed supply cannot dominate by accident.
        attempts.extend([
            ({}, "scenario", "strict-supply-scenario-order", True),
            ({}, "deadline", "strict-supply-deadline-order", True),
        ])
    if scenario == "B":
        # Strict dates often require ECLO across several programmes. Evaluate
        # bounded policies and retain the lowest published penalty.
        max_access = max((int(Decimal(str(a.total_accesses)).to_integral_value(rounding=ROUND_CEILING))
                          for a in instance.activities_by_id.values()), default=0)
        for count in range(1, max_access + 1):
            plan = {aid: min(count, int(Decimal(str(activity.total_accesses))))
                    for aid, activity in instance.activities_by_id.items()}
            attempts.append((plan, "deadline", f"global-eclo-{count}", False))
    last_reason = "No construction attempt was run."
    best_result = None
    best_key = None
    evaluated = 0
    queued = {(tuple(sorted(plan.items())), mode, strict) for plan, mode, _, strict in attempts}
    index = 0
    while index < len(attempts):
        eclo_plan, order_mode, policy_name, strict_supply = attempts[index]
        index += 1
        builder = _Builder(instance, scenario, deadline, baseline, disruptions,
                           order_mode, strict_supply)
        try:
            complete, reason = builder.build(eclo_plan)
        except TimeoutError:
            last_reason = "The bounded search time expired before a complete schedule was constructed."
            break
        if not complete:
            last_reason = reason or "Construction did not complete."
            continue
        witness = [
            {"activity_id": aid, "week": week, "physical_night": night}
            for (week, night), aids in sorted(builder.group_members.items())
            for aid in sorted(aids)
        ]
        grouped_witness = {"possessions": [
            {"week": week, "night": night, "activity_ids": sorted(aids)}
            for (week, night), aids in sorted(builder.group_members.items())
        ]}
        submission = {"scenario": scenario, "schedule_access": builder.access,
                      "schedule_occupancy": builder.occupancy,
                      "results": _results_rows(instance, builder.access, scenario),
                      "physical_night_witness": witness,
                      "validation_witness": grouped_witness}
        report = validate_submission(instance, submission, scenario)
        evaluated += 1
        if scenario == "B" and not eclo_plan:
            completion_week = defaultdict(int)
            for row in builder.access:
                completion_week[row["activity_id"]] = max(
                    completion_week[row["activity_id"]], row["week"])
            late = []
            for aid, week in completion_week.items():
                activity = instance.activities_by_id[aid]
                project = instance.projects_by_contract[activity.contract_number]
                if week > _week_for_date(instance, project.planned_completion_date):
                    late.append(aid)
            # The standard construction identifies the activities actually
            # blocked past their dates. Try ECLO only on that set before
            # accepting a uniform workload-wide policy.
            max_late_access = max((int(Decimal(str(instance.activities_by_id[aid].total_accesses)))
                                   for aid in late), default=0)
            for count in range(1, max_late_access + 1):
                plan = {aid: min(count, int(Decimal(str(instance.activities_by_id[aid].total_accesses))))
                        for aid in late}
                signature = (tuple(sorted(plan.items())), "deadline", False)
                if signature not in queued:
                    queued.add(signature)
                    attempts.append((plan, "deadline", f"late-activity-eclo-{count}", False))
        if scenario == "C" and not eclo_plan:
            completion_week = defaultdict(int)
            for row in builder.access:
                completion_week[row["activity_id"]] = max(completion_week[row["activity_id"]], row["week"])
            late = []
            for aid, week in completion_week.items():
                activity = instance.activities_by_id[aid]
                project = instance.projects_by_contract[activity.contract_number]
                if week > _week_for_date(instance, project.planned_completion_date) and activity.total_accesses >= 3:
                    late.append(aid)
            # Target one late activity per candidate. This keeps Scenario C's
            # line-specific two-week ECLO window coherent and avoids spraying
            # ECLO across unrelated early work.
            for aid in late:
                for mode in ("scenario", "deadline"):
                    plan = {aid: 2}
                    signature = (tuple(sorted(plan.items())), mode, False)
                    if signature not in queued:
                        queued.add(signature)
                        attempts.append((plan, mode, f"targeted-eclo-{aid}", False))
        if report["feasible"] and report["complete"]:
            baseline_rows = _preferred_rows(baseline)
            actual_rows = {(row["activity_id"], row["access_seq"]): row["week"] for row in builder.access}
            compared = set(baseline_rows) & set(actual_rows)
            report["soft_scores"]["baseline_accesses_compared"] = len(compared)
            report["soft_scores"]["moved_activity_week_accesses"] = sum(
                actual_rows[key] != baseline_rows[key][0] for key in compared
            )
            candidate = submission | {
                "status": "success", "feasible": True,
                "metrics": report["soft_scores"], "violations": [],
                "validation": report["validator"],
                "selection": {"policy": policy_name, "global_optimality_proven": False},
            }
            max_week = max((int(row["week"]) for row in builder.access), default=0)
            candidate["explanations"] = ([{
                "code": "extending_flat_nominal_assumption",
                "message": (
                    f"The schedule extends to week {max_week}, beyond the supplied "
                    f"{instance.horizon_weeks}-week horizon, using the final flat nominal "
                    "location capacity. The public rules do not confirm this interpretation."
                ),
            }] if max_week > instance.horizon_weeks else [])
            key = (candidate["metrics"]["objective_score"],
                   candidate["metrics"]["moved_activity_week_accesses"],
                   len(candidate["schedule_access"]))
            if best_key is None or key < best_key:
                best_key, best_result = key, candidate
                if scenario == "B" and eclo_plan and len(queued) < 250:
                    # Deterministic incumbent pruning: remove one ECLO use from
                    # each activity in turn, independently rebuild, and only
                    # expand a neighbor if it becomes the best fully validated
                    # plan. This is bounded local search, not optimality proof.
                    for aid in sorted(eclo_plan):
                        if eclo_plan[aid] <= 0 or len(queued) >= 250:
                            break
                        for retained in (0, eclo_plan[aid] - 1):
                            plan = dict(eclo_plan)
                            if retained:
                                plan[aid] = retained
                            else:
                                del plan[aid]
                            signature = (tuple(sorted(plan.items())), "deadline", False)
                            if signature not in queued:
                                queued.add(signature)
                                attempts.append((plan, "deadline",
                                                 "pruned-eclo-local-search", False))
                            if len(queued) >= 250:
                                break
            continue
        last_reason = "Independent validation rejected the constructed schedule."
        last_report = report
    if best_result is not None:
        best_result["metrics"]["search_candidates_evaluated"] = evaluated
        best_result["solve_time_seconds"] = round(time.monotonic() - started, 4)
        return best_result
    return {
        "scenario": scenario, "status": "unresolved", "feasible": False,
        "schedule_access": [], "schedule_occupancy": [], "results": [],
        "metrics": {}, "violations": (last_report["hard_violations"] if "last_report" in locals() else []),
        "validation": {"name": "ngeebula-independent-ps1", "official": False,
                       "note": "Official trackaccess validator is unavailable."},
        "explanation": last_reason,
        "solve_time_seconds": round(time.monotonic() - started, 4),
    }
