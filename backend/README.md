# Ngeebula API

FastAPI, SQLAlchemy/SQLite, OR-Tools CP-SAT, and optional Google GenAI. See the root TECH_STACK.md for the current React and PS1 architecture.


## PS1 and React (current primary workflow)

Run from the repository root with `python -m uvicorn backend.main:app --port 8000`. Build `web/` first to serve the React UI from the same origin.

| Endpoint | Purpose |
|---|---|
| GET /healthz | Runtime/frontend/data availability |
| GET /ps1/dataset?dataset_id=default | Active input, network, audit and source |
| POST /ps1/datasets/import | Eight UTF-8 CSVs in JSON files mapping or a raw ZIP |
| POST /ps1/runs | Queue scenario A/B/C with dataset ID, optional baseline and capacity overrides |
| GET /ps1/runs/{id} | Poll status and locally validated result |
| GET /ps1/runs/{id}/download | Exact three-CSV ZIP; complete-local-validation gate |
| GET /ps1/runs/{id}/validation.json | Separate checks, physical-night witness and assumptions |
| POST /ps1/validate | Validate output rows; closure coverage partial without witness |

Runs/imports are bounded, temporary and isolated from maintenance SQLite. One background worker executes at most four queued/running requests. API schemas at /docs show limits. Inputs are never sent to Gemini. The official organiser validator is not supplied, so local results are not an official pass.

## Retained maintenance API

After installing the root requirements-lock.txt, run from this directory:

```powershell
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

[Interactive API schemas](http://127.0.0.1:8000/docs)

| Endpoint | Purpose |
|---|---|
| GET /jobs/ | Rich requests, including pending work and crew IDs/names |
| GET /engineers/ | Roster, skills, availability |
| GET /catalog/ | Activities, skills, lines and normalized station records |
| GET /ai/status | Redacted optional Gemini configuration status |
| POST /ai/test | Real synthetic Gemini call through production validation |
| POST /jobs/parse-and-create | Assess a request and assign qualified crew |
| PATCH /jobs/{job_id} | Validate and audit overrides |
| DELETE /jobs/{job_id} | Delete eligible requests with audit snapshots |
| POST /schedule/propose | Run the solver and save a proposal |
| GET /schedule/readiness | Explain obvious candidate blockers; read-only, not a joint feasibility proof |
| POST /schedule/compare | Three synthetic planning approaches under identical inputs; no writes |
| POST /schedule/roi | Validated assumption-based planning-effort estimates; no writes |
| POST /schedule/insertion-demo | Read-only synthetic insertion example; scenario fits or no_capacity |
| POST /approval/{job_id} | Review/approve a plan |
| PATCH /checklist/{job_id} | Record execution status |
| GET /dashboard/gantt | Timeline data |
| GET /alerts/ | Deadline and start reminders |
| GET /audit-logs/ | Change history |

Use the interactive schema for exact payloads. Overrides require identity and reason. API timestamps carry offsets; naive SQLite timestamps represent UTC. Planning targets the next complete 00:30–05:00 Singapore window.

Create requests can supply `catalog_category` and `catalog_activity` together to select an exact catalog repair. The selection bypasses Gemini, preserves classification and skills, and rejects mismatched manual skills. Free-text requests retain the existing assessment flow. The insertion-demo endpoint uses invented jobs/crew with the real solver, touches no database and has no apply action.

`GET /catalog/` includes `stations` with `name`, `code`, `line` and `interchange`. Creation accepts optional `station_code` and validates it, plus recognized location names/codes, against the selected line before assessment or writes. Unknown train/depot identifiers remain allowed. Responses expose `station_name` and `location_warning` for older conflicts; conflicts block planning and approval. `PATCH /jobs/{job_id}` supports `line`, `track` and nullable `station_code` for Not started work, with the existing mandatory identity/reason. A changed location clears scheduled timestamps/minutes, approval and time lock and records the before/after location in the audit. A correction cannot be combined with a fixed start-time override; replan after correcting.

DATABASE_URL optionally changes the database location; default SQLite lives beside database.py. Fresh databases seed the original `engineers_db.json`, confirmed by the project owner as dummy data. Its 700 records yield 697 engineers after duplicate-email removal; the first record is retained. Existing databases are never reseeded. Local SQLite files are ignored by Git.

Station records carry `reference_status`; `/catalog/` also supplies LTA publication/access/licence metadata. Offline reconciliation uses the committed snapshot to correct known code/name/line conflicts and append missing official codes. Unmatched local entries stay unverified; saved jobs are never migrated by a read. Dynamic LTA APIs are not configured. See [public-data research](../docs/PUBLIC_DATA_RESEARCH.md) for source hashes, coverage, attribution and refresh instructions.

Comparison scenarios are `joint_planning`, `straightforward`, and `no_capacity`. The requested-slots proxy is not a human benchmark, and sequential partial results cannot be applied. CP-SAT uses the live all-or-none policy. ROI inputs specify all three methods' planning minutes, monthly frequency, hourly labour cost, initial cost and monthly running cost, with either alternative selected as baseline. Negative returns are preserved; zero incremental initial cost has no defined ROI percentage. Outcomes never monetize safety, reliability or avoided disruption.

Gemini remains optional. Enter `GEMINI_API_KEY` in the repository-root `.env` file and use `GEMINI_MODEL=gemini-3.8-flash`. The backend resolves this path independently of its working directory and reads changes without a restart. Nonempty backend environment variables take precedence over `.env`; the Windows DPAPI store remains a credential fallback. `.env` is ignored by Git, and `.env.example` is a secret-free template. No API endpoint accepts or returns a raw key.

Use `GET /ai/status` to inspect redacted configuration and `POST /ai/test` to make one real call with a synthetic maintenance request. A successful test requires a provider response that passes the same strict catalog validation as production; the test writes no jobs or audit records. See [the secure setup guide](../docs/GEMINI_SETUP.md) for commands, failure meanings, key removal, and security boundaries. Without a key, catalog/rules work. Suggestions never bypass scheduling constraints.

Run tests from the root using `.\.venv\Scripts\python.exe -m pytest -q`; tests use isolated databases.
