# Verification record

Verified locally on Windows with Python 3.12 on 17 September 2026. The implementation retains FastAPI, SQLAlchemy/SQLite, OR-Tools, the Google GenAI SDK, Streamlit, pandas, and Plotly.

## Automated results

Commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q backend frontend
.\.venv\Scripts\python.exe -m pip check
```

- **163 tests passed** in the final showcase integration run (30.91 seconds): the previous 118 cases plus 20 planning-comparison/ROI cases, 10 official-reference cases, and 15 showcase endpoint/UI cases. This includes both baseline comparisons, three scheduling situations, unknown/error status distinctions, negative/undefined ROI, official station reconciliation, read-only readiness, offline reference views and assumption retention. Two upstream Starlette/TestClient deprecation warnings remain.
- Python compilation succeeded.
- Dependency verification reported no broken requirements.
- Two upstream deprecation warnings remain in Starlette's TestClient/httpx and AnyIO integration. They do not fail the tests.
- Tests use disposable SQLite databases, isolated credential paths and a deterministic roster. Automated tests never load the user's key, send data to Gemini or change the live local database.

## Requirement-by-requirement evidence

| Requirement | Implemented evidence | Verification |
|---|---|---|
| Read and audit the repository/README | Initial audit and plan in IMPLEMENTATION_PLAN.md | Inspected README, main API, models, solver adapter/core, client, dashboard, catalogs; no Google Doc link was present |
| Engineer assignment | Creation assigns fully qualified available engineers; manual teams are validated; proposal persists solver selections | Automatic/manual API tests; UI creation and actual reassignment to a different engineer; shortages, count, duplicate/unknown/unavailable/unqualified IDs tested |
| Priority assignment | Automatic deadline/interchange rule or validated GenAI suggestion; explicit creation/override priority | API and UI tests for automatic and manual priority, invalid values, persisted changes; live browser override Urgent → High |
| Delete | Confirmed UI deletion with identity and reason; backend policy allows Not started jobs; retained audit snapshot | UI deletion test; active/completed protection, atomic failure, and non-reused IDs after delete/recreate |
| Override | Separate priority, crew, start time, and requirements controls; reason required; approval reset | Backend and UI tests verify changed crew, priority, time, audit reason, and fresh displayed values; invalid edits preserve the stored plan |
| Working schedule | Correct API/solver contract, assigned crew persistence, canonical lines, UTC storage/SGT display | Real OR-Tools tests for track/staff overlap and deadlines; fixed commitments, joint schedule swap, and alias checks |
| Planner review and execution | Approval gate, explicit valid status transitions, reasons and audit | API lifecycle tests plus UI page/control checks; no implicit approval when marking completion |
| About and workflow diagram | Offline About with five-step workflow, AI/optimization distinction, model limits, user guidance | AppTest with HTTP forbidden; rendered desktop and 375-pixel-wide inspection |
| Retain/document tech stack | TECH_STACK.md, requirements-lock.txt, pinned backend requirements | Installed dependency check and current module imports; no replacement frontend, database, or ML framework |
| Optional Gemini | Validated catalog-bound suggestions; safe rule fallback | Mocked success, provider failure, malformed/invalid values, empty/partial/unknown skill sets; no live API key available |
| ML suitability | Retain CP-SAT; do not introduce an untrained predictive model | No historical training/evaluation data exists; decision explained in TECH_STACK.md and About |
| Plan, delegate, implement, test, refine | Backend, frontend, and tests delegated to three GPT-5.6 Sol agents; integration reviewed by the coordinating agent | Shared API contract, root code audit, negative tests, live browser findings and fixes |

## Live application check

- Backend API docs and read endpoints respond at http://127.0.0.1:8000.
- Streamlit responds at http://127.0.0.1:8501 and its health endpoint returns 200.
- The supplied roster loads 697 distinct engineer records; the catalog contains 161 activities.
- A request labeled **Demo — Fibre-optic cable repair** was created through the browser. It initially received automatic Urgent priority and two qualified engineers.
- Generating a proposal scheduled the demo for **18 September 2026, 00:30–02:00 SGT**, with qualified crew displayed in the timeline/table and selected job card.
- A live planner override changed its priority to High with an audit reason. The demo remains **Not started and unapproved** for the user's review. This is demonstration data, not an authorization to perform real work.
- The backend was restarted without reload after development so code-watcher restarts do not interrupt user requests. Both services remain running on loopback.

## Refinements from actual failures

1. Repaired the incomplete solver input/result contract and UTC/SGT handling.
2. Rejected empty crews, null overrides, invalid qualifications, bad timing, and conflicts without partial mutations.
3. Preserved manual crew/time commitments across regeneration and validated a joint new schedule against its new state rather than stale candidate times.
4. Prevented starting unapproved/unscheduled work, changing completed work, and reusing deleted job IDs.
5. Tightened Gemini validation so missing skill requirements cannot bypass qualification checks.
6. Moved dependent request controls out of a batched form so manual mode can be filled on the first attempt.
7. Live inspection exposed a stale selected-job dictionary after generation. Selection now stores only the ID and resolves the latest API record; edit fields reset only when the saved record changes. Regression assertions now check the displayed summary and current crew, not just database persistence.
8. Removed unimplemented buffer claims, corrected chart labels/spacing, and kept model-limit warnings in one place.
9. Replaced custom HTML application content with native Streamlit structure, metrics, tables and expandable controls; retained only a small CSS styling layer.
10. Added request search and filters, with regression coverage proving that a filtered review list does not exclude eligible work from schedule generation.
11. Added sourced Singapore context, a scoped problem statement, algorithm/design rationale and explicit unknown data provenance to the offline About page. Public facts were checked against the linked articles and government releases.
12. Actual browser measurement exposed an excessively tall, stretched vertical Graphviz diagram. Content-width rendering reduced it from roughly 3,759 pixels to 513 pixels high while retaining legibility at phone width.
13. Desktop inspection caught an ellipsized lifecycle status. Smaller, wrapping summary values now show the full status. Phone inspection caught crowded Gantt axes; shorter display labels and fewer time ticks preserve room for bars while full values remain in hover and tables.

## Native UI review evidence

- Reviewed the coordinated GPT-5.6 agents' interface, research and regression work; checked source claims and algorithm explanations against the articles and local solver code.
- Browser inspection covered the 1280-pixel desktop planner and 375 × 812 phone-width About/workflow and timeline. Document width matched viewport width, with no page-level horizontal overflow in those checked views.
- Captured and inspected the current desktop summary and Gantt, and phone About/workflow/timeline. Early screenshot attempts temporarily failed; subsequent captures succeeded.
- The selected live demo stayed **Not started and unapproved**; this UI pass did not approve, execute or replace the live demonstration work.
- Connection settings are secondary controls; the visible status describes a fetched API snapshot, not live telemetry.
- Native dataframes can scroll horizontally to expose additional columns. Selected-job summaries carry decision-critical details outside the scrollable table.
- These checks do not constitute a complete assistive-technology audit or real-operator usability study.

## Cockpit and secure AI refinement

- Replaced the default form-heavy entry with a chief's queue, three readiness counts, direct next actions and an optional overnight Gantt tab. Crew shortages have concise explanations outside the table.
- Replaced the 161-activity initial dropdown with three steps: describe work, choose location/deadline, review. Category-based catalog skills and manual planning overrides are optional review controls.
- Verified draft retention across Back/Next, including advanced crew options, and deadline boundaries at 00:29, 00:30, 00:31 and 02:00 SGT. The default deadline matches the solver's next complete engineering window.
- Inspected the live desktop wizard and its 375 × 812 review layout. The narrow page measured 375 pixels wide with no page-level horizontal overflow; long location text and the review notice wrapped. Navigated back through the live draft and cancelled it without submission.
- Removed the redundant Add work button during the wizard after browser review showed it could reset the draft accidentally.
- Added Windows CurrentUser DPAPI key storage outside the repo, a redacted configuration endpoint, and a synthetic provider-test endpoint using production validation. Configured and successfully tested are distinct UI states.
- An actual Windows PowerShell 5.1 test exposed a missing ProtectedData assembly and module-resolution incompatibility. The helper now explicitly loads its dependencies. A dummy-key round trip through PowerShell encryption and Python decryption passes in temporary storage without exposing the dummy value.
- Tested missing credentials, provider failures, invalid model output, successful validated output, environment precedence, redaction and absence of job/audit writes. These provider responses are mocked; the DPAPI round trip is real.
- The running backend reports `configured: false`. The live test returns `not_configured`, and existing jobs remain unchanged. A real Gemini call remains pending the user's local key setup; fallback success is not presented as Gemini success.
- Updated README, frontend/backend guidance, TECH_STACK.md, COCKPIT_AND_AI_PLAN.md and docs/GEMINI_SETUP.md. Compilation and dependency checks pass.
- Applied the user's subsequent preference for a root `.env` with an empty key and `GEMINI_MODEL=gemini-3.8-flash`; `.env` is excluded by the existing Git ignore rule, with a secret-free `.env.example`. Verified the model ID against Google's current model page. Added pinned python-dotenv to backend requirements and the root dependency lock.
- Added isolated tests for dynamic `.env` key/model reloads, blank values, literal non-interpolated credential strings, process-environment precedence and matching status/provider model selection. The backend was restarted once and reports `configured: false`, `model: gemini-3.8-flash`; later configuration edits need no restart.
- Live browser verification confirmed utility pages clear the main-workspace selection and allow returning to the same prior workspace. AI setup displays `.env` instructions and the new model without exposing configuration values. The remaining live-provider test requires the user's key.

## Live Gemini test after key setup

After the user entered the key locally, `GET /ai/status` reported `configured: true`, source `dotenv`, model `gemini-3.8-flash`. The synthetic production-validation test failed at the provider call. A minimal SDK diagnostic confirmed **HTTP 429 RESOURCE_EXHAUSTED** with a billing-related message; no raw exception or key was printed. Saved jobs and audit records were identical before and after the test.

This confirms local configuration loading and a provider response, but **does not establish successful model generation or validation**. The user's Google AI Studio project requires a billing/quota check before a successful retry. Failure presentation was refined to use allowlisted status codes and fixed messages, retaining the no-secret response policy.

All 19 focused Gemini tests and the full 89-test suite pass after that refinement. Coverage includes numeric/status-only 429, authentication/access failures, missing model and generic failure; each verifies redaction, client cleanup and unchanged jobs/audit records. The backend was restarted to load the refinement; both local services remain healthy. No further real requests were made after diagnosing the quota/billing condition.

## Visual repair and insertion review

- Replaced the initial description form with eight curated, numbered train/infrastructure assets plus an Other path. Local SVG graphics and native labelled buttons supply equivalent visual/text navigation; phone cards render in two columns.
- Exact catalog pairs are preserved through creation and bypass AI reclassification. Catalog skills are prepopulated and protected; changing assets resets manual requirements/crew and preserves location, deadline and priority for review.
- Removed the duplicate wizard header, fixed the train-door label contrast, shortened the selected repair's automatic title and hid irrelevant catalog controls after selecting a shortcut.
- Added a read-only worked example with real CP-SAT results: same fixed routine jobs, same two engineers, same 45-minute door repair; only the completion deadline changes. The feasible result is 01:30–02:15 SGT; the tighter case is genuinely infeasible.
- Live API checks confirmed identical baselines across scenarios, all approved jobs preserved, and byte-for-byte-equivalent decoded job/audit responses before and after both examples. No demo record was created and no Gemini request was made.
- Browser inspection covered the desktop picker, 375 × 812 phone picker and selected-repair review. The phone document and viewport both measured 375 pixels. The browser draft was cancelled without submission. Updated About, README, API/frontend docs and TECH_STACK.md explain the teacher-cover analogy, planned-corrective scope, synthetic inputs and limits.
- Desktop chart review caught an overflowing task label and reversed comparison order. Short in-bar labels and explicit original/updated row order corrected the issue; exact names remain in hover and the table. The affected insertion journey passed again after this change.
- Inspected the final comparison at 375 pixels: bars, time ticks, original/updated labels and legend remain distinct without document overflow. Bar text hides when it cannot fit; the native exact-times table scrolls independently. Returned the browser to the desktop asset picker for use.

## Station-first location audit and refinement

- The user-created Clementi/NSL request exposed an arbitrary first-line default plus unrelated free text. The native station search now derives a single serving line; interchanges require an explicit choice. Train/depot work has a separate known-line and worksite path.
- The API exposes 221 station-line reference rows, rejects clear name/code/line contradictions before provider calls or writes, and distinguishes longer station names. Legacy records carry a visible conflict warning and cannot be scheduled/approved until corrected.
- Correct location is available for Not started work, suggests a station from the saved code/name, preserves area details, requires a reason, and clears affected proposal/approval/time locks on save. Negative tests verify no partial changes. Missing correction reasons preserve the draft and send no mutation.
- Three GPT-5.6 Sol agents handled the backend contract, location component and regression tests; the coordinating agent integrated and reviewed them. The final full suite passes 118 tests with two upstream deprecation warnings. Compilation passes. No test accessed the real key, provider or live database.
- Live browser checks covered existing job #4's prefilled correction, searching `EW23`, automatic Clementi/EWL resolution, review and Back retention, desktop layout and 375 × 812 phone layout. Document and viewport widths both measured 375 pixels. The automatic-line text was changed from a blue notice to ordinary high-contrast text after screenshot review.
- Cancelled the browser test draft. Compared saved job fields before/after (excluding newly computed response fields) and audit responses: all three saved jobs and audit history were unchanged. Both local services are running. No real Gemini call was needed for this refinement.
- Created AGENTS.md with persistent UX, data-integrity, secret-handling and test-isolation rules. README, API/frontend guidance, TECH_STACK.md and docs/LOCATION_UX_REVIEW.md describe the implemented workflow and reference-data limits.

## Visual showcase, ROI and public-data verification

- Compared the requested-slots worksheet proxy, priority-first-fit and actual CP-SAT on identical synthetic inputs. The specialist case placed 1/2, 1/2 and 2/2 new jobs respectively. The easy case placed 2/2 for each; the no-capacity case had no complete plan. All retained the same fixed inspection. Live read-only API runs reproduced these results.
- Financial estimates use caller-supplied planning frequency, staff effort, hourly cost, setup and recurring cost, independently of synthetic schedule counts. Both baseline choices are tested, including negative first-year benefit and undefined ROI when extra setup cost is zero. No-setup payback wording was corrected, and explicit draft state preserves edited inputs across comparison views.
- The new readiness endpoint identifies obvious location, qualification, fixed-crew and deadline blockers without writing or solving. A regression constructs individually valid jobs whose shared crew makes the joint plan impossible: readiness passes but proposal generation rejects atomically. Preliminary readiness is not advertised as feasibility.
- Downloaded official LTA station and line tables using public URLs; retained hashes, publication/access dates, mapping and licence in a versioned snapshot. Offline reconciliation yields 222 rows: 211 matched, CE1 corrected to Bayfront, Hume appended, and nine local-only rows unverified. API tests verify provenance, no mutation of source objects/jobs, and rejection of CE1/Promenade before provider use.
- Desktop and 375 × 812 browser checks inspected the comparison timeline, assumptions, both ROI baselines, cost chart and glossary. Phone document width equals the 375-pixel viewport. Refined task labels, time ticks and navigation grouping; fixed Markdown treating multiple currency signs as math. Exact values remain available in native tables. Verified the planning tabs show only Schedule & issues or Review & approve as selected.
- Both services are running; health returns 200. Saved job and audit responses remained identical throughout live showcase and planning-readiness checks. No production request, approval, override or provider call was issued for testing.
- Compileall for backend, frontend and scripts passes. `pip check` reports no broken requirements. Optional spreadsheet import readers are pinned separately; the application stack is retained. No full assistive-technology study or operational certification is claimed.
- Requirement-by-requirement implementation evidence and the workflow diagram are in [SHOWCASE_IMPLEMENTATION.md](docs/SHOWCASE_IMPLEMENTATION.md). Research limits and primary URLs are in [PUBLIC_DATA_RESEARCH.md](docs/PUBLIC_DATA_RESEARCH.md).

## Current operational limits

**Subsequent successful live retry:** After the user resolved the provider condition, the same synthetic test returned HTTP 200 with `result: success`, model `gemini-3.8-flash`, source `dotenv`, and `assessment_source: gemini-validated`. Gemini selected `track_and_permanent_way` / `Rail wear inspection` and passed the production catalog validator. Saved jobs and audit records were unchanged. This supersedes the earlier billing/quota blocker; it verifies this live request, not unrestricted future quota or all possible assessments.

- The supplied catalog and roster often use different skill names. The app exposes shortages instead of silently treating different qualifications as equivalent. Each crew member must have every required skill under the current model.
- Availability means available throughout the maintenance window. Travel, fatigue, possession/access approval, and live field conditions are not modeled.
- Priority weights protect start times; they do not guarantee strict priority-first execution.
- Gemini validation/fallback behavior passes mocked tests, and the subsequent real Gemini 3.8 Flash retry passed production validation. Future requests still depend on provider availability, quota and valid model output. Core functions work without Gemini.
- Planner names are attribution rather than authentication; the local SQLite audit is retained by the API, not tamper-proof against direct database edits.
- Visual checks cover the tested desktop and narrow layouts, labels, focus, and chart/table readability. No full assistive-technology or operational certification is claimed.

## Public repository and Render preparation

- The project owner confirmed the original 700-record roster is dummy data and requested its inclusion; a fresh disposable database seeds 697 unique-email engineers. Existing databases are preserved.
- Organized historical plans under `docs/plans`, added a documentation index, `.gitignore`, `.gitattributes`, publication audit and deployment guide. All local Markdown links resolve.
- Full suite: **167 passed**, with two upstream deprecation warnings. Backend/frontend/scripts compile successfully. Supervisor tests check loopback API binding, startup failure and sibling shutdown without running live services.
- `render.yaml` validates against Render's official JSON schema. The configured deployment key was verified without displaying it. Git publication audit checked 71 candidate files and found no private paths or known credential patterns. Deployment verification is recorded separately once the service is live.
