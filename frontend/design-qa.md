# Frontend design audit

## Latest showcase review

The current interface keeps live planning separate from demonstration and estimated value. The cockpit offers a direct comparison entry; Explore & learn groups the comparison, insertion example, glossary and About. Schedule & issues and Review & approve are separate tabs, keeping editable controls out of the initial timeline view. Comparison inputs are one scenario plus Run; savings assumptions are collapsed with the current values summarized next to results.

Browser review verified the crew timeline, cost chart, source text and CP-SAT glossary on desktop and 375 × 812. Refined task labels/time ticks, grouped navigation and corrected currency Markdown parsing. Phone document width is 375 pixels without page overflow. Result counts have visible meanings; unfinished work is explicit; tables retain exact values. The calculator retains assumptions across view changes, shows negative returns honestly and labels a zero setup premium accurately.

The final full suite passes **163 tests**. Tests cover comparison parity and limits, no writes/provider calls, preliminary-check limits, ROI formulas/edge cases, official reference reconciliation, offline learning pages and edited-input persistence. See [showcase implementation and acceptance evidence](../docs/SHOWCASE_IMPLEMENTATION.md).

## Audit scope

The September 2026 refinement reviewed the planner journey at desktop and narrow widths: cockpit triage, guided request creation, queue review, schedule generation, override and approval, execution tracking, alerts, audit history, secure AI setup, and the offline About page. The UI remains Streamlit with Plotly for the schedule timeline.

## Findings and changes

The prior interface encoded headings, job summaries, status cards, and tables as custom HTML. Those surfaces were harder for Streamlit to lay out responsively, duplicated native semantics, and forced tests to inspect CSS classes. They were replaced with native titles, captions, bordered containers, metrics, alerts, expanders, and dataframes. CSS now provides theme-level spacing, contrast, focus, and touch-target polish rather than defining application components.

Review queues now support search by job title, ID, or location plus line, status, and priority filters. Filters affect the visible review list only; schedule generation continues to include every eligible request. Empty filtered results explain how to recover without disabling schedule generation.

Job summaries keep the decision-critical facts visible: priority, lifecycle status, approval, assigned versus required crew, start, end, deadline, duration, and crew names. Skills and manual planning locks use progressive disclosure. Tables provide the same information as an accessible alternative to the chart.

The Plotly timeline uses a 24-hour SGT clock. When all work belongs to one engineering window, it shows the complete 00:30–05:00 range derived from the scheduled date. Hover details include exact start, end, duration, priority, and crew. No safety buffer is invented.

Alerts translate API type codes into operator labels. Audit history extracts actor, job ID, reason, and SGT timestamp into a readable table; selected before/after data and raw payloads remain available in expanders.

The sidebar describes fetched data as a snapshot and provides an explicit Refresh snapshot action. Planner identity, navigation values, critical journey widget keys, current-job ID selection, and override snapshot resets remain stable.

The latest audit found that the complete request form and 161-item activity list made the starting state feel like a database editor. The default is now a compact chief's cockpit with three numeric readiness signals and one prioritized action queue. The timeline lives in a separate tab. Primary navigation contains four operational destinations; alerts, history, AI setup, and About sit under Utilities.

Request creation is a three-step guide: describe the work, choose location and deadline, then review. The draft is copied into session state before every step transition, so Back and validation errors preserve entered details even though Streamlit removes unrendered widget state. Catalog category and filtered activity appear only in an optional review expander and are described accurately as a required-skills override. Planning defaults and manual crew assignment are a second optional expander.

AI setup displays only the backend's configured flag, redacted source label, and model. Its primary instructions point to the root `.env` with safe placeholder content and explain the refresh-then-test sequence; the current key is never read into the page. A provider test is user-initiated, records its own timestamp, and shows success only when the backend returns a validated `success` result. The browser has no API-key field.

## Accessibility and interaction checks

- Visible labels remain on all fields; required inputs and SGT timezone are explicit.
- Primary controls and navigation targets have a minimum 44px height.
- Keyboard focus uses a visible blue outline.
- Text and border colors use the dark theme tokens in `.streamlit/config.toml`.
- Destructive deletion remains behind a reason plus confirmation and is unavailable outside `Not started`.
- Optional creation and override fields use expanders and enable immediately when selected.
- The creation guide uses plain language, a next-engineering-window deadline shortcut, and Back/Next controls with explicit draft persistence.
- Utility pages clear the main-navigation selection, so returning to the previously active workspace always triggers navigation.
- Feedback persists across reruns until dismissed.
- Reduced-motion preferences disable CSS transitions.
- The About page is native Streamlit and remains usable without the backend.

## Validation evidence

- Full repository suite: **80 passed**. The 16 frontend journeys cover the cockpit default and queue counts, guided-draft Back/Next retention, create-to-plan-to-approval flow, stale selected-job and crew refresh, review-filter versus solver scope, chart window and hover data, lifecycle restrictions, AI success/failure semantics, utility selection reset and re-entry, and offline About behavior.
- Python compilation passed for `frontend/app.py` and `frontend/about_page.py`.
- Offline AppTest rendered all six navigation destinations without exceptions; operational pages showed a recoverable connection error and About rendered without HTTP.
- Streamlit loaded the configured theme colors and sans-serif font from `frontend/.streamlit/config.toml`.

Two remaining test warnings come from third-party Starlette/TestClient deprecations and do not originate in the frontend.

## Coordinating-agent browser review and final refinements

- Inspected current screenshots at 1280-pixel desktop width and 375 × 812 phone width, alongside DOM dimensions and the accessibility tree. About and the planner had matching document/viewport widths; native tables handle their own horizontal scrolling.
- A stretched vertical About flowchart measured about 3,759 pixels tall on desktop. Changing its native `graphviz_chart` width to `content` restored a compact, legible 513-pixel diagram on desktop and phone.
- The desktop job summary initially truncated `Not started`. A scoped typography adjustment keeps all native metric values complete and wrapping when needed.
- Phone inspection exposed long Gantt location labels crowding bars and time ticks. Display labels now use line codes and bounded track text; the full location remains in hover data and the table. Fewer 24-hour ticks and a dated SGT axis title improve the compact view.
- Moved the backend URL into **Connection settings** and labeled it **Backend server URL**. **Refresh snapshot** stays visible.
- The final integration run passed **80 tests**, including all 16 frontend journeys. Compilation also passed.

This is a bounded visual and functional review, not full WCAG certification or a study with operational rail planners.

## Visual repair refinement

The latest pass introduces a numbered SVG guide with eight native asset buttons, exact catalog selection and a separate real-solver insertion example. Desktop inspection found a duplicated wizard header and low-contrast train-door label; both were corrected. Phone controls use two columns, larger headings were reduced, and the 375-pixel viewport has no document overflow. Selected-repair review uses an explicit catalog name and shorter automatic title; irrelevant catalog controls are hidden.

The integration suite now passes 99 tests, including 19 frontend journeys. All 19 frontend cases passed again after the final title/control refinement. Demo tests verify identical approved commitments and no writes across feasible/infeasible outcomes. Existing local jobs were preserved during browser/API checks.

## Station-first follow-up

The next user review identified a concrete error: Clementi could be saved with the default North–South Line. Station search now resolves the line, interchanges require a serving-line choice, and manual train/depot sites use a separate path. Existing location conflicts receive a cockpit action and an expanded, reasoned correction control. Crew shortages display the required skills and a direct review action after creation.

The latest full suite passes **118 tests**, including **23 frontend journeys** and **15 location-contract tests**. Desktop and 375 × 812 screenshots verified the picker, saved-location correction defaults and Back/Next retention. At phone width the document is 375 pixels with no horizontal page overflow. A low-contrast automatic-line notice was replaced with ordinary high-contrast text. The live browser draft was cancelled and saved job fields/audit records remained unchanged. See [the location UX review](../docs/LOCATION_UX_REVIEW.md) for the workflow diagram and design decisions.
