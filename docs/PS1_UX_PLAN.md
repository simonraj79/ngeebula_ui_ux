# PS1 React UX plan

## Product boundary

The React application is the primary PS1 engineering-access planning surface. It uses the supplied **Alpha (ALP)** and **Beta (BET)** identifiers throughout and does not substitute public railway lines, infer rolling-stock locations, or blend PS1 contracts into the separate corrective-work workflow.

It supports a works controller moving through four decisions:

1. verify the active dataset and its provenance;
2. choose Scenario A, B, or C with the rigid and flexible policy levers stated in plain language;
3. generate a complete candidate, then gate feasibility on local validation;
4. review the timeline and exact values before downloading submission files.

Corrective requests, approvals, and execution remain available under the secondary **Work requests** page through the existing API. They are visibly separated from the PS1 schedule.

## Navigation and page intent

- **Overview** — dataset counts, horizon, source, audit warnings, Alpha/Beta schematic, and the non-negotiable rule groups.
- **Plan access** — three mutually exclusive policy cards, run progress, hard-violation feedback, and an optional location/week capacity-cut what-if.
- **Schedule** — scenario selector, contract/activity search, line and activity filters, accessible weekly timeline, and a keyboard-scrollable exact table.
- **Data & imports** — CSV/ZIP selection, validation feedback, active source evidence, and provenance checklist.
- **Work requests** — the existing eight-asset corrective workflow: station-first or explicit train/depot location, assessed requirements, proposal generation, accountable approval, reasoned execution update, and audit history. No PS1 relationship is inferred.
- **About** — problem, strict rules, scenario objectives, data boundaries, algorithm role, and the human-review sequence.

## Design system

The UI uses a restrained dark operations palette: deep navy surfaces, teal for primary actions and validated structure, amber for operational attention, blue/amber for Alpha/Beta, and red only for hard violations. It uses system sans-serif at a 16 px base and monospaced text only for IDs. Cards use solid high-contrast surfaces and subtle borders; blur is limited to the navigation/header layer.

The targeted UI/UX search matched a real-time operations pattern and a dark technical palette. Its glassmorphism recommendation was deliberately reduced to avoid low-contrast dashboard surfaces. The first React stack search returned no results; the required retry returned guidance to keep forms controlled and virtualize lists above 100 items. The initial schedule limits DOM rendering to 80 timeline rows; the exact table remains the complete alternative and should gain windowing if hidden-test datasets make it large.

## API contract

`web/src/api.ts` is the translation boundary for the backend contract:

- `GET /ps1/dataset?dataset_id=default`
- `POST /ps1/datasets/import` using raw ZIP or JSON `{name, files}`
- `POST /ps1/runs` followed by polling `GET /ps1/runs/{run_id}`
- completed run data normalized from `schedule`, `validation`, `metrics`, and `submission`
- gated submission ZIP and local-validation JSON downloads from completed run endpoints
- existing `GET /jobs/` for the separated work-request view

Completed scenario bundles are held in `sessionStorage` for immediate Schedule navigation. No result is fabricated if the API is absent, a run is pending, or normalization yields no rows. Export remains intentionally absent until the completed-run download endpoint and local-validation state are wired together; the UI must not imply that a generated candidate is an approved or officially certified answer.

The validator label must remain **local validation**, not official certification. The official reference validator is not bundled.

## Accessibility and responsive behavior

- Semantic landmarks, real buttons, labels, fieldsets, tables, and a skip link establish keyboard order.
- Focus rings are always visible; decorative Lucide icons are hidden from assistive technology where adjacent text supplies the name.
- Status and hard-failure messages use text and icons in addition to color.
- Controls have at least a 44 px target, body text starts at 16 px, and reduced-motion preferences disable non-essential animation.
- At 760 px, navigation becomes a labelled drawer, metrics/cards stack, sticky actions become full-width, and filters wrap without horizontal page scrolling.
- The schedule timeline may scroll within its panel; the exact-value table is the non-visual and keyboard-friendly equivalent.

## Follow-up integration checks

1. Reconcile normalized run rows with the final solver response fields and preserve exact numeric/ID types in exports.
2. Expose queued/running server messages if the run response adds progress detail.
3. Render `changes` for a capacity-cut run against `baseline_run_id`, with moved/unchanged counts and exact before/after rows.
4. Exercise imports with the supplied eight CSVs, raw ZIP, malformed ZIP, missing file, and hidden instance.
5. Verify 375, 768, 1024, and 1440 px layouts with keyboard-only navigation and reduced motion.

## Verified integration state

Against the isolated production build on port 8012:

- the supplied dataset loaded with its published counts and Alpha/Beta topology;
- a malformed ZIP was rejected inline with the backend's bounded validation message;
- Scenario A progressed through queued/running/completed and rendered as a complete locally feasible plan;
- the weekly timeline showed its capped 80-row visual window while the exact table exposed all 192 schedule rows;
- submission download enabled only for the complete locally feasible run;
- the 375 px Plan page had no page-level horizontal overflow;
- the Work requests page exposed all eight asset choices, and selecting Rails changed location entry to the station-and-serving-line control without creating a job.

## Coordinating review corrections

The final root review fixed direct /schedule navigation colliding with the API prefix, an explicit Scenario accessible name, mobile grid min-width overflow, and focusable hidden mobile navigation. Browser checks confirmed 192 exact Scenario A rows, a three-CSV download, correct scenario navigation and no page overflow at 375 pixels. Expired cached runs now clear and prompt regeneration instead of repeatedly submitting a stale baseline.
