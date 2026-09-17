# PS1 railway track-access dataset audit

Audited **17 September 2026** from [aochinwen/NebulaX-Hackathon-ProblemStatement](https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement), commit [`16526c0`](https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement/commit/16526c02579c7f37e54eaaa42a4cc6d4ceb19994). The repository was supplied to this project as the SMRT problem-statement source; the files themselves do not include a licence or an independent data-provenance statement. Treat them as challenge inputs, not current SMRT operational data.

The byte-identical PS1 brief, eight instance CSVs, two network references and three sample-submission CSVs are preserved under [`data/ps1`](../data/ps1). [`MANIFEST.json`](../data/ps1/MANIFEST.json) pins every byte length and SHA-256 hash. [`scripts/import_ps1_dataset.py`](../scripts/import_ps1_dataset.py) can verify the committed copy, copy from a local upstream PS1 directory, or fetch the pinned raw files. It never touches the existing Ngeebula seed files or runtime database.

## Instance inventory

| File | Rows | Columns and normalized types | Key / relationship findings |
|---|---:|---|---|
| `01_LINES.csv` | 2 | `line_code str`, `line_name str` | Unique `line_code`: ALP, BET. |
| `02_STATIONS.csv` | 20 | `station_id str`, `line_code str`, `seq int`, `is_interchange bool` | Ten ordered rows per line. H01/H02 legitimately repeat across lines; `(line_code, station_id)` is the natural key. |
| `03_SECTORS.csv` | 18 | `sector_id str`, `line_code str`, `from_station_id str`, `to_station_id str`, `seq int`, `is_shared bool` | Nine ordered sectors per line. Alpha uses sequence 1–9; Beta uses 11–19. All station references resolve on the same line. `is_shared` is 0 throughout; H01–H02 remains a separate sector on each line. |
| `04_LOCATION_SUPPLY.csv` | 76 | `location_id str`, `location_kind str`, `line_code str`, `bound str`, `supply_capacity int` | Exactly 36 bound-specific tunnel locations and 40 bound-specific platforms. Unique IDs; complete coverage of both bounds. Capacities: 24 rows at 4, 40 at 2, 12 at 1. With no week column, each value is the flat nominal capacity for every horizon week. |
| `05_BUFFER_LOCATION.csv` | 3 | `nature_of_works str`, `up_to_buffer_sectors int`, `opposite_bound_required bool` | Live = 2/true; Non-live (Consist) = 1/false; Non-live (Others) = 0/false. All project values resolve. |
| `06_PARAMETERS.csv` | 2 | `key str`, `value typed by key` | `horizon_start=2027-01-04`; `horizon_weeks=30`. Week is 1-based from that Monday. |
| `07_PROJECT_DETAILS.csv` | 14 | IDs/text `str`; dates `date`; priorities/workfronts/caps `int` | Unique C001–C014. Nine C, four PC, one PM; two Live, seven Consist and five Other contracts. Weekly caps are 2 for Live and 3 otherwise in this instance. |
| `08_ACTIVITY_DETAILS.csv` | 54 | IDs/type/locations `str`; `total_accesses Decimal`; `planned_start_date date`; optional predecessor; priority `int` | Unique activity IDs, 192 total standard-night work units. All contract/type and endpoint FKs resolve; every endpoint is a tunnel location and each pair shares line/bound. Six predecessor references resolve. IDs are deliberately non-contiguous, so code must not synthesize IDs. |

There are no duplicate full rows, duplicate declared primary IDs, unresolved foreign keys, malformed dates/numbers, or missing values except the allowed blank predecessor. The sample contains 14 result rows, 192 access rows and 928 occupancy rows, covers all 54 activities, has no duplicate `(activity_id, access_seq)` or duplicate occupancy rows, uses weeks 1–29, and uses no ECLO. Its 192 access rows exactly equal the instance's 192 standard-night work units.

## Planning interpretation

An activity's occupied span includes every tunnel sector from its start endpoint through its end endpoint and every bounding/intermediate platform on the same line and bound. Capacity is booked at both kinds of location. The loader exposes this as `activity_span_ids(activity_id)`.

Strict published rules require:

- 100% workload conservation; one standard access yields 1.0 unit and ECLO yields 1.5;
- no access before the activity's planned-start week;
- Live buffers of two sectors, opposite-bound mirroring, and Live-only cross-line closure at H01–H02; Consist buffers of one; Others none;
- location mixes of PM alone, one PC with at most three C, or at most four C; a shared `(location, week, co_share_group)` is one possession;
- a per-contract-and-activity-type count of distinct weekly `access_night` values no greater than the project cap, and a per-night activity count no greater than workfronts;
- scenario-specific capacity, planned-date and ECLO rules; Scenario C ECLO for each affected line must fit one continuous span of at most two calendar weeks.

The six `predecessor_activity_id` values are preserved and reference-validated. The published strict-rule list does not say how a predecessor constrains start or completion and provides no violation tag for it. The local implementation must not invent an ordering rule unless the official validator or an amended specification defines one.

### Scenarios and score

| Scenario | Hard constraints | Soft penalty |
|---|---|---|
| A — strict supply | Nominal capacity cannot be exceeded; ECLO forbidden | Priority-weighted overrun |
| B — strict schedule | No completion beyond planned date; supply excess permitted | `7 × excess access-nights + 5 × ECLO nights` |
| C — balanced | At most one excess access-night per location-week; per-line ECLO continuity window | Priority-weighted overrun plus the B terms |

Contract priority establishes the overrun band: 100, 10 or 1 for tiers 1, 2 or 3. Activity priority applies the documented within-band multiplier 1.3, 1.2 or 1.0. Lower score is better. Feasibility and full workload are gates; a partial schedule is not a valid answer.

Each scenario produces its own three files: `SCHEDULE_ACCESS.csv` (`activity_id,access_seq,week,eclo,access_night`), `SCHEDULE_OCCUPANCY.csv` (`activity_id,week,location_id,co_share_group`), and `RESULTS.csv` (`scenario,contract_number,simulated_completion_date,overrun_days`). A `RESULTS.csv` may contain only one scenario.

## Loader contract and gaps

[`backend/ps1_data.py`](../backend/ps1_data.py) provides `load_instance(source)` / `load_ps1_instance(source)`. `source` may be the eight-file directory or an in-memory mapping of exact filename to UTF-8 text/bytes, so uploaded hidden instances never overwrite the committed default. It returns a frozen `PS1Instance` with typed row tuples, lookup maps, `week_for_date`, `activity_span_ids`, `closure_footprint`, and JSON-safe `to_public_dict`.

What-if capacity changes are run-local: `with_capacity_overrides([{location_id, week, capacity}])` returns a new instance, and `capacity_for(location_id, week)` resolves the override or flat baseline. Inputs are checked for known locations, horizon weeks and non-negative integer capacity.

The upstream repository contains no reference validator package, solver, executable `trackaccess` module, requirements/lock file, schema file or automated tests. Although the brief mentions `python3 -m trackaccess expand` and states that the sample is validator-feasible, that command is not present in the supplied repository. Local validation can implement the published rules, but parity with the judges' hidden validator cannot be claimed until that tool is supplied or results are compared against it. The upstream tree also contains no licence file; redistribution and promotional attribution should therefore remain factual and avoid implying endorsement.
