# Working on Ngeebula

## Product and scope

Ngeebula's primary workflow is the supplied NebulaX PS1 railway track-access planning problem: inspect the demand book, choose scenario A/B/C, generate a complete possession plan, review local validation and trade-offs, and export the three submission CSVs. The separate maintenance-request workflow fits corrective repairs around approved commitments. Active incident response and decisions about safe operation remain outside this prototype.

The user explicitly requested React on 17 September 2026. The primary frontend is React/TypeScript in `web/`; Streamlit in `frontend/` is the legacy interface. The backend remains FastAPI, SQLAlchemy/SQLite and OR-Tools. Preserve existing records while migrating presentation. Use labelled SVG network diagrams and accessible charts instead of decorative 3D controls.

## PS1 data and validation

- Preserve the supplied eight CSV files byte-for-byte in `data/ps1`, with upstream commit and hashes. Public headers saying nine files conflict with the actual eight-file instance; validate the actual schema, not that count typo.
- Keep Alpha/Beta, H01/H02 and supplied location IDs intact. Do not relabel the abstract challenge network as actual Singapore lines/stations or mix it with the legacy dummy roster.
- Account for every activity and its full workload. Partial, timed-out or infeasible output is not a feasible complete schedule. Never silently drop demand to improve a score.
- Respect scenario-specific supply, date and ECLO rules, span/platform occupancy, buffers, Live mirroring/crossover, co-sharing, weekly allocations and workfronts. Document ambiguities against the source brief.
- The public pack does not contain the referenced official `trackaccess` validator. Label application checks as local validation until the official tool is available and actually run. Do not call a local pass official certification or operational approval.
- Uploaded instances and capacity-change simulations must be isolated from the shipped source data and live maintenance jobs. Show changed assumptions, displaced work and validation results.
- Keep Gemini optional and outside the scheduling/validation authority. Never send uploaded demand books to an AI service implicitly.

## UX rules from user reviews

Start PS1 in the demand overview with dataset-backed scenario/location/week choices. Imported datasets must remain active across navigation and generation; scope saved plans by dataset and scenario. Gantt weeks must sort numerically and preserve empty weeks. The following repair-specific rules apply to the secondary maintenance workflow.

- Start with the cockpit and eight curated asset shortcuts. Keep the full catalog and manual requirements secondary.
- Use station-first location selection. Search by station name/code and derive a single serving line automatically. At an interchange, explicitly ask which serving line the work concerns; never default silently to the first line.
- Distinguish a station/track location from train, depot or other-site work. Do not invent fleet/depot reference data or infer a train's work site from its service line.
- Use the supplied station reference consistently on both sides of the API. Reject clear line/station contradictions, including Clementi with NSL. Label unknown or unverified data honestly.
- Preserve draft fields across steps, reruns and errors. When changing a parent selection, clear dependent values that would become stale.
- After creating a request, show the next useful action and any blocking condition. Do not promise that the scheduler will find a crew when the current qualifications/roster show a shortage.
- Allow an accountable correction of a mistaken location. Reset affected proposals/approval and retain an audit reason; never silently rewrite an existing operator request.
- Prefer compact native controls, descriptive labels, meaningful defaults, visible validation, Gantt charts and exact-value tables. Keep information usable on a 375-pixel-wide screen and with a keyboard.
- Clearly label synthetic demonstrations. The insertion example uses the real solver but never saves or applies its invented jobs.
- Compare identical jobs, people, deadlines and fixed work across the requested-slots proxy, first-fit rule and joint planner. The proxy is not a measured human benchmark. Include easy and impossible cases, and never call a partial or unknown result a feasible complete plan.
- Keep scheduling evidence separate from ROI assumptions. Show negative returns, include setup/running costs, and leave ROI undefined when its incremental investment denominator is not positive. Computer runtime is not planner effort saved.
- Explain terminology through the searchable Glossary and short help text. Use plain-English outcome labels before algorithm names; keep detailed assumptions and schedules behind optional expanders.
- Preliminary planning checks flag obvious problems only. Only the solver checks joint feasibility; neither check grants operational approval.
- Reconcile the local station lookup with the committed, attributed LTA snapshot without changing saved jobs. Preserve unmatched entries as unverified and never infer current service status from inclusion or absence in an older table. Dynamic public APIs require separate credentials and are not connected.

## Implementation and validation

- Read the applicable code and tests before editing. Check for existing user changes; check the current branch, remote and user changes.
- Use `.venv\Scripts\python.exe`. From the repository root, run relevant pytest cases and `python -m compileall -q backend frontend`. Broaden to the full suite for changes crossing the UI/API workflow.
- Tests must use disposable databases and isolated credential paths (`NGEEBULA_ENV_FILE`, `NGEEBULA_GEMINI_KEY_FILE`, temporary `LOCALAPPDATA`); never consume the user's API key or mutate live jobs.
- Preserve qualification checks, fixed/approved commitments, valid lifecycle transitions, reasoned overrides, UTC storage and SGT presentation. A proposal does not approve execution.
- Gemini is optional. Explicit catalog choices stay authoritative and bypass free-text AI classification. Core rules and scheduling work without Gemini. A fallback result must not be described as a successful Gemini call.
- Never print `.env`, API keys, raw provider exceptions or credential values. Use redacted status routes. Local `.env` is ignored by Git and read by the backend on demand.
- Review screenshots and actual browser behavior for UI changes. Automated tests do not establish visual usability. Build React with `npm --prefix web run build` and verify real browser imports, scenario selection, exports and narrow-screen behavior. Never create, modify or delete the user's live work merely for testing.
- Backend changes need a controlled restart of the matching local process; `.env` changes do not. Verify process identity before stopping it. Start background Windows services hidden.
- Coordinate delegated edits by file ownership. Evaluate agents' results and rerun the affected integration paths before reporting completion.

## Public repository rules

- Keep credentials, databases and runtime files out of Git. Never force-add ignored local data. Before release, run `scripts/audit_public_release.py` and inspect the candidate/staged file list; the audit must not print secret values or read ignored files.
- Fresh databases use the original `backend/engineers_db.json`. The project owner explicitly confirmed it is dummy data and authorized publishing it on 17 September 2026. Preserve this original seed and existing local databases; never add real operational personal data.
- Historical plans belong in `docs/plans/`; keep relative Markdown links valid when moving documentation. The root README, TECH_STACK and VALIDATION remain the current entry points.
- Preserve upstream and LTA source attribution. Do not choose a software reuse licence, publish, push or create a remote repository unless the user requests those actions.

## Documentation

Keep README.md, TECH_STACK.md and VALIDATION.md aligned with the implemented behavior and verified results. Record design decisions in docs/ and distinguish repository reference data, synthetic examples, user-entered work and verified external sources. This file is the canonical agent guidance requested by the user; update it when subsequent UX decisions change these rules.
