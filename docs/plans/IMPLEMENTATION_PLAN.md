# Implementation plan and initial audit

## Scope

Deliver engineer assignment, priority assignment, deletion, and planner overrides in both FastAPI and Streamlit. Keep the existing Python stack, document it, add an operator-focused About page, and verify the full journey. Coordinate implementation with separate backend, frontend, and regression-test agents; the primary agent owns integration and final review.

## Evidence from the starting repository

- The root README describes FastAPI, SQLAlchemy/SQLite, OR-Tools CP-SAT, optional Gemini, and Streamlit/Plotly. It links to GitHub; it does not link to a Google document.
- `main.py` passes incomplete jobs to the solver and iterates its result dictionary as though it were a list of jobs. Proposed schedules cannot be persisted correctly.
- Creation assigns engineers by a score even when the team lacks the required skills. The dashboard has no request-creation or assignment controls.
- Priority is assigned internally but there is no usable planner workflow to review or change it.
- The approval endpoint applies overrides without adequate validation. No deletion endpoint or interface exists.
- SQLite returns naive datetimes while alerts use aware UTC datetimes. The frontend also interprets naive dates as Singapore time.
- Dashboard guidance claims 30-minute buffers that the solver does not enforce. Fallback text sometimes calls ordinary rules “AI”.
- The checkout has no training dataset, trained predictive model, or evaluation results supporting a new ML model.

## Delivery sequence

1. Agree API contracts and the operator journey before parallel edits.
2. Repair the scheduling integration and add validated, auditable backend actions. Preserve explicit planner assignments and times during regeneration.
3. Provide request creation, queue review, scheduling, edit/override, approval, status, and confirmed deletion in Streamlit. Display crew and priority before and after scheduling.
4. Add About with a process diagram, daily usage guidance, and a plain-language distinction between rules, mathematical optimization, and optional GenAI.
5. Keep dependency and architecture records. Test against isolated databases, verify UI interactions against the backend, inspect the rendered app, and refine defects found.

## Operator journey and UI decisions

| Stage | Operator question | Required interface behavior |
|---|---|---|
| Request | What needs repair, where, and by when? | Labeled request form, explicit Singapore time, maintenance catalog guidance |
| Review | How urgent is this and who can do it? | Priority, skill requirements, team names, assignment and assessment explanation |
| Plan | Does tonight's work fit? | Generate action, visible pending jobs, Gantt chart, actionable solver failures |
| Adjust | Can I change the crew, urgency, or start time? | Prefilled override form, reason and planner identity, conflict errors, saved feedback |
| Approve | Is this reviewed and ready? | Explicit approval action and status; changed plans require review again |
| Execute | What is underway, delayed, or complete? | Status controls and reason fields, alerts, audit history |
| Correct | How do I remove an erroneous request? | Named job confirmation and reason; retain audit history after deletion |

Use semantic Streamlit controls, visible labels, keyboard focus, textual statuses alongside colors, readable contrast, progressive disclosure, and clear empty/error states. Preserve the existing dark operations-dashboard direction. The UI/UX skill's design search recommended minimal enterprise styling but returned a marketing page pattern even after a narrower retry; that page pattern is not appropriate here. The task-based journey above is an explicit product decision using the skill's general accessibility/form guidance.

## Acceptance evidence

- Test automatic and manual engineer/priority selection, qualifications, availability, headcount, and persistence.
- Test creation → proposal → override → approval → execution, including UTC/SGT conversions.
- Reject conflicting or invalid edits without partially modifying stored jobs or audit history.
- Preserve manual commitments on replanning and prevent crew and track overlaps.
- Delete eligible requests with an audit snapshot; reject deletion of active work.
- Exercise Streamlit forms and offline About. Inspect desktop and narrow viewport rendering.
- Verify the existing local backend and frontend run on ports 8000 and 8501 after integration.

Final outcomes and remaining limits will be recorded in `VALIDATION.md` after implementation, not inferred from this plan.
