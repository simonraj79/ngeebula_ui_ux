# PS1 backend gap audit

Checked on 17 September 2026 against the current Ngeebula backend/tests and the upstream [PS1 participant brief](https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement/blob/main/PS1/PS1_README.md). The user has explicitly requested a React interface for this PS1 work, overriding the earlier Streamlit-preservation rule for this scope. This document covers the backend contract; frontend and deployment are coordinated separately.

## Finding

The existing scheduler and PS1 solve different problems. The current backend schedules minute-level repair jobs into one 00:30–05:00 SGT window, assigning fully qualified engineers while preserving approved commitments. PS1 schedules weekly physical track possessions across a dual-line topology. It must deliver every activity’s full workload and export three CSV answer keys for each policy scenario. Reusing the current `RepairJob`/`Engineer` persistence or `/schedule/propose` contract would hide essential PS1 concepts and produce the wrong answer shape.

The PS1 implementation is therefore isolated in `ps1_data.py`, `ps1_solver.py`, and `ps1_validator.py`. It does not read or mutate the local maintenance database, roster, saved jobs, or credentials.

## Exact domain differences

| Concern | Existing Ngeebula scheduler | PS1 requirement |
|---|---|---|
| Unit of planning | Whole-minute timestamp in one overnight window | One access per activity per week; standard yield 1.0, ECLO yield 1.5 |
| Demand | Repair job with duration, deadline, line/track and skills | Contract activities with access workload, planned-start week, path endpoints, priorities and optional predecessor reference |
| Resource | Named engineers with exact skills and availability | Track possession supply, contract weekly access nights and concurrent workfronts |
| Geography | A string-valued line/track or optional sector | Every SEC and PLAT location along the book-in/book-out path, by line and bound |
| Conflict | No overlap on identical location key or engineer | Occupancy, exclusion buffers, opposite-bound Live mirroring, Live-only cross-line interchange closure, legal possession mixes and co-sharing |
| Commitment | Approved/time-locked job interval | Complete workload baseline; no activity may be omitted or truncated |
| Congestion | All-or-none solver can return infeasible | Require full workload; label any post-horizon flat-capacity extension explicitly, and report unresolved when bounded construction cannot establish a complete valid answer |
| Objective | Minimize priority-weighted minutes moved from proposed starts | Scenario-specific overrun, excess access-night and ECLO penalties |
| Output | Persisted proposal plus job JSON | `SCHEDULE_ACCESS.csv`, `SCHEDULE_OCCUPANCY.csv`, and `RESULTS.csv` per scenario |
| Approval | Separate human approval and execution lifecycle | Works-controller decision support; official submission is mechanically validated |

Existing tests prove deadline, crew, same-track, fixed-commitment and lifecycle behavior. They do not establish PS1 workload conservation, network expansion, possession packing, scenario scoring or CSV validity.

## Published hard rules implemented

The normalized loader validates the eight exact CSV schemas and foreign keys. The solver and independent validator cover:

1. Every activity appears and delivered yield is at least `total_accesses`; `access_seq` is contiguous and an activity has at most one access per week.
2. No access precedes `planned_start_date`.
3. Occupancy exactly equals the activity’s expanded tunnel-and-platform span.
4. Location/week/group mixes are one PM alone, one PC with at most three C activities, or at most four C activities.
5. Distinct possession groups consume location supply. Scenario A permits no excess; C permits one excess group per location-week; B soft-scores excess.
6. A contract/type/week uses no more distinct local `access_night` values than `number_of_maximum_access_per_week`, and each night respects `number_of_workfronts`.
7. Scenario A forbids ECLO. Scenario C constrains ECLO affecting each line to one continuous span of at most two weeks; cross-line Live work contributes to both line windows.
8. Scenario B hard-fails planned-date overrun. Scenario A scores overrun only; B scores `7 × excess + 5 × ECLO`; C scores weighted overrun plus those terms.
9. Solver construction uses the normalized closure footprint conservatively: Consist adds one sector, Live adds two, Live mirrors the opposite bound, and Live at H01–H02 closes the other line’s tunnel and H01/H02 platforms.
10. Week-specific `capacity_for(location, week)` overrides support disruption what-if runs without changing the source instance.

The upstream `predecessor_activity_id` is preserved and foreign-key checked, but the public strict-rule list does not define predecessor timing semantics. It is not enforced until the official validator or organiser clarifies it.

## Important validator boundary

The public repository contains the eight input CSVs, network references, sample submission, and brief. It does **not** contain the referenced `trackaccess` Python package, `expand` command, or judge validator. The sample is described as feasible with zero hard violations, so it is the only public calibration oracle.

The sample establishes that `co_share_group` is location-local: one activity can use `b2` on platforms and `b4` on tunnel sectors in the same week. It is not a universal weekday or global possession-night ID. Likewise, `access_night` is local to `(contract_number, activity_type, week)`. Treating either value as a network-wide night rejected the official sample incorrectly.

The independent validator now accepts the complete upstream sample with zero observed hard violations and reproduces its 28 total overrun days. It validates exact footprints, local mixes, capacities, workload, weekly allocation, workfronts, dates, ECLO policy, strict `RESULTS` consistency and scores. Because the three published output files lack a universal night identifier, an arbitrary uploaded submission receives `complete=false` and `coverage.closure=unverified` even when no observed violation exists.

Schedules produced locally retain a non-exported `physical_night_witness`. The validator checks that it covers every activity-week exactly once and uses it to test same-night span/closure and buffer/buffer intersections, including opposite-bound and Live interchange effects. A legal same-location possession mix exempts only the locations actually co-shared; it does not waive another collision elsewhere along the pair. Locally generated output is exportable only when `feasible=true`, `complete=true`, and closure coverage is `checked`. Every result still reports `official: false`; an official-validator pass remains a separate status when that tool becomes available.

## Solver interface and output

```python
solve(
    instance: PS1Instance,
    scenario: str = "A",
    time_limit_seconds: float = 20,
    baseline: dict | None = None,
    disruptions: dict | None = None,
) -> dict
```

The API layer should apply disruption rows with `instance.with_capacity_overrides(...)`; the retained `disruptions` argument supports direct callers. The result contains:

```text
scenario, status, feasible
schedule_access[]       activity_id, access_seq, week, eclo, access_night
schedule_occupancy[]    activity_id, week, location_id, co_share_group
results[]               scenario, contract_number, simulated_completion_date, overrun_days
metrics                 scenario scores plus baseline churn counts
violations              independent hard-rule diagnostics
validation              validator name, official=false, limitation note
physical_night_witness  non-exported activity/week/night proof for full local closure checking
solve_time_seconds
```

`success` is returned only after full workload and independent validation pass. A timeout or failed bounded construction returns `unresolved`, an empty export schedule, and an explanation; it is not mislabeled infeasible. Baseline runs report how many identical access sequences were compared and how many moved to another week. The heuristic uses the baseline as a placement preference but does not claim minimum churn or mathematical optimality.

On the published dataset, the bounded constructor returns complete independently validated A, B and C schedules. It evaluates multiple orderings and ECLO policies and keeps the lowest published objective found, breaking ties on observed baseline churn. Scenario C includes strict-supply Scenario A constructions in its candidate pool, because every such construction also satisfies C; this prevents C from returning a score dominated by the known A incumbent. Scenario B starts from the first complete uniform ECLO plan and performs a bounded deterministic neighborhood search that removes ECLO uses one activity at a time, retaining only fully rebuilt and validated improvements. The current B incumbent improves from objective 897 with 115 ECLO nights to objective 862 with 108 ECLO nights. It remains a feasible incumbent rather than a competitive benchmark. Results explicitly say `global_optimality_proven=false`.

Scenario A currently extends beyond the supplied 30-week horizon. The public rules require full delivery and permit schedule overrun, while location supply is flat and no rule explicitly caps output week. Such a result carries an `explanations` entry with code `extending_flat_nominal_assumption`: capacity after week 30 is assumed to remain at the final flat nominal level. This is a documented interpretation, not a confirmed judge behavior; expose it in the UI and verify it against the official validator when available.

## Implemented API boundary

Keep PS1 endpoints separate from repair-job endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /ps1/dataset` | Return the bundled dataset digest and normalized summary |
| `POST /ps1/datasets/import` | Import exactly eight CSVs into an ephemeral in-memory dataset and return its ID and summary |
| `POST /ps1/runs` | Start an A/B/C run with a time limit, optional imported dataset, baseline run and capacity overrides |
| `GET /ps1/runs/{run_id}` | Poll status and retrieve metrics, schedules, explanations and local validation |
| `GET /ps1/runs/{run_id}/download` | Download a ZIP containing exactly the three canonical submission CSVs |
| `GET /ps1/runs/{run_id}/validation.json` | Download the separate local, non-official validation report |
| `POST /ps1/validate` | Validate three uploaded output CSVs independently and label closure coverage limitations |

Uploads should be size-limited, UTF-8 CSV only, isolated per run and deleted on expiry. Do not write uploaded instances into the maintenance SQLite database. A worker/process boundary and progress polling are preferable to holding an HTTP request open for hidden-instance solves.

## Objective and optimization roadmap

The present constructor is a deterministic feasible-first heuristic. The next solver should retain its validator/export boundary and use integer-scaled work units (`standard=2`, `ECLO=3`) to avoid fractional arithmetic. Useful CP-SAT variables are activity/week access, ECLO, local access-night assignment, activity/location/week possession group, completion week, capacity excess and line ECLO-window start. Hard constraints should be added independently of objective terms so a low score can never mask a safety breach.

Use lexicographic phases rather than one opaque coefficient sum:

1. prove complete workload and zero hard violations;
2. minimize scenario formula exactly;
3. minimize baseline week changes when replanning;
4. minimize unnecessary fragmentation and provide stable deterministic tie-breaking.

Report the published components separately: overrun days and contracts, raw priority overrun, banded activity-adjusted score, excess access nights, ECLO nights, capacity hotspots and churn. Never call a feasible heuristic result optimal unless the solver proves optimality.

## Meaningful verification

`tests/test_ps1_solver.py` provides the first independent backend checks:

- the upstream sample validates with zero hard violations and 28 total overrun days;
- A, B and C each produce complete schedules covering every published activity;
- each generated result revalidates independently and exports one result per contract;
- A contains no ECLO or excess supply; B has zero planned-date overrun;
- deleting one activity produces a hard workload violation;
- A rejects ECLO and capacity excess;
- a week-specific zero-capacity override moves affected work;
- rerunning against its own baseline reports zero week moves;
- impossible construction is `unresolved`, returns no partial export, and is not called infeasible.
- malformed, mixed-scenario, incomplete or schedule-inconsistent `RESULTS` rows fail, and objective metadata is withheld on invalid output;
- the solver’s physical-night witness covers every activity-week and has no residual pairwise closure collision after location-specific co-share exemptions.
- two disjoint Consist spans whose one-sector buffers intersect are placed on different physical nights, and forcing them together is independently rejected;
- post-horizon output carries the explicit `extending_flat_nominal_assumption` explanation.

Further tests needed before submission are mutation tests for every individual hard-rule tag, small brute-force instances compared with an exhaustive oracle, deterministic repeatability under a fixed seed, CSV round trips, API upload isolation/limits, cancellation/timeouts, concurrent runs, and calibration against the official validator when organisers provide it. Hidden-instance performance and score competitiveness remain unproven.
