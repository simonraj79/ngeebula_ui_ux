# PS1 scheduler and validator acceptance review

Review basis: the pinned upstream brief and sample at commit `16526c02579c7f37e54eaaa42a4cc6d4ceb19994`. Checks use disposable in-memory submissions and do not touch the live database or credentials.

## Confirmed behavior

The supplied Scenario A sample is accepted with zero hard violations. The local calculation reports 28 total overrun days, matching the sample `RESULTS.csv` (C006 14, C010 7, C014 7). It covers all 54 activities and all 192 standard-night workload units.

Acceptance mutations verify that the validator rejects:

- missing workload, non-contiguous access sequences, and more than one access for an activity in a week;
- unknown locations, blank possession groups, missing or extra activity footprint rows;
- distinct possession groups beyond Scenario A capacity;
- PM co-sharing and illegal PC/PC or PM/C mixes, while allowing one PC with up to three C or up to four C;
- access-night indices beyond the project weekly allocation and activities beyond the workfront count;
- ECLO in A, ECLO outside a two-week per-line window in C, and completion after planned date in B;
- omitted, malformed, duplicate, mixed-scenario or schedule-inconsistent `RESULTS` rows.

The CSV loader also rejects nonfinite workloads (`NaN` and positive/negative infinity), mismatched headers, and extra row values. Submission integer fields reject fractional numbers and Booleans instead of truncating them. Witness validation requires exactly one occupancy row per activity/week/location, rejects malformed or duplicate placements without raising an exception, and checks both mappings: each location-local group corresponds to exactly one physical night (and vice versa), and each contract/type-local `access_night` corresponds consistently to one physical night.

`objective_score` is emitted only for a hard-feasible submission. This prevents a rejected plan from being presented with a comparable quality score.

## Buffer and Live-crossover coverage

The public occupancy schema makes a complete external check underdetermined. `co_share_group` is defined for `(location_id, week, group)`, and the official sample legitimately changes group labels along one activity's span. `access_night` is local to contract, activity type and week. Neither field supplies a universal physical-night identity across locations and contracts. An uploaded CSV can therefore prove footprints, local possession mixes and weekly capacity, but cannot prove that two nearby possessions ran on different physical nights. Buffer separation, opposite-bound Live mirroring and the Live-only H01–H02 cross-line closure remain unverified for arbitrary external submissions.

The UI/API should distinguish:

- **published-rule checks passed with partial coverage** for an arbitrary uploaded submission; and
- **solver witness checks passed** for a locally generated plan whose internal global `(week, physical night)` assignment is retained.

It should not label an external submission unconditionally safe or fully feasible when those collision rules cannot be reconstructed. The official `trackaccess` validator is absent, so local acceptance is not an official-validator result.

## Solver witness finding

The solver retains a flat `physical_night_witness` of `{activity_id, week, physical_night}` rows. This is sufficient to check every pair using exact spans and closure footprints. The literal rule is:

1. Calculate the conservative `closure(A) ∩ closure(B)` intersection.
2. At a location occupied by both activities in the same possession, waive the collision only when the PC/C mix is legal.
3. Any remaining collision is a hard buffer violation. The closure helper already includes Live opposite-bound mirroring and the H01–H02 cross-line exception, so the same test covers those cases.

An initial audit found a solver false positive: `can_place` waived every closure collision when a pair legally shared any one location. That was broader than the brief's same-location exemption. The first generated runs contained 37 affected pairs in A, 17 in B and 29 in C; for example A week 2/night 1 placed A006 with A035 while a nonshared buffer still intersected `PLAT:ALP:S02:WB` and `SEC:ALP:S02_S03:WB`. The construction check was narrowed to waive only shared span locations. The acceptance suite checks the retained witness pair by pair so this regression cannot return as a successful plan.

## Completion gate

For each A/B/C solver result, acceptance requires all of the following:

- `status=success` and zero independent-validator hard violations;
- exactly the full set of 54 activity IDs represented;
- delivered workload of at least `total_accesses` for every activity, using 1.0 standard and 1.5 ECLO yield;
- complete, schedule-consistent `RESULTS` rows for all 14 contracts;
- zero remaining pairwise collision in the global-night witness after only the local legal co-share exemption is applied.

All five gates now pass for the committed A, B and C plans. The release artifacts contain 192/154/192 access rows respectively and cover all 54 activities. A reaches week 38 with no ECLO, 224 overrun days and objective 316.4. B reaches week 27 with 108 ECLO rows, 46 excess access-nights, zero overrun and objective 862.0. C reaches week 38 with no ECLO, 224 overrun days and objective 316.4. These are feasible under the local written-rule interpretation, not evidence of score competitiveness with the unavailable official solver; global optimality is not proven.

The acceptance test reads the committed `SCHEDULE_ACCESS.csv`, `SCHEDULE_OCCUPANCY.csv` and `RESULTS.csv` for each scenario, combines them with the report's committed `physical_night_witness`, and runs the validator again. It requires zero hard violations, `complete=true`, closure coverage `checked`, all 54 activities, and exact agreement with the saved objective, overrun, excess-capacity and ECLO metrics. The reports also retain source commit and per-file hash metadata so the results remain tied to the audited input bytes.

Scenarios A and C extending to week 38 is a visible interpretation choice. The brief requires the solver to keep scheduling under congestion and permits completion overrun, while `horizon_weeks=30` names an input horizon but no strict rule explicitly forbids later weeks. Supply has no week column and is treated as flat beyond week 30. If the organiser intends week 30 as a hard scheduling boundary, those plans would instead be unresolved on this heuristic and that constraint must be added explicitly.
