# Showcase UX audit

## Goal and audience

The showcase should help a maintenance planner or evaluator answer one question quickly: **what changes when the same overnight workload is handled by requested slots, first-fit, or CP-SAT?** It should explain the result without turning the page into an algorithm tutorial or a large input form.

The current application already has strong foundations: a consistent dark operations theme, visible keyboard focus, 44-pixel controls, reduced-motion handling, native Streamlit feedback, a solver-backed insertion example, and explicit limits on what the prototype proves.

## Priority changes

### P0 — make the comparison truthful before making it impressive

- Give all three approaches the same jobs, fixed commitments, crew, window, skills, and deadlines.
- Label **Requested slots** as a spreadsheet-like proxy that keeps requested starts. It is not a benchmark of a real planner or spreadsheet process.
- State the first-fit job order and tie-break rule. A different order can produce a different result.
- Show whether every job was scheduled. Never improve a score by silently dropping infeasible work.
- Separate solver runtime from planner effort. Runtime does not include data preparation, review, approval, possessions, or field coordination.
- Use “modeled comparison” for synthetic outputs. Reserve “ROI” for measured benefit and cost over a defined period.
- Distinguish **feasible**, **infeasible**, **optimal**, and **unknown** in text. A feasible result is not automatically optimal.

### P0 — put the decision before the mechanism

The first viewport should contain:

1. one outcome sentence, such as “CP-SAT schedules all six jobs; first-fit leaves one deadline conflict”;
2. a compact strip of three or four directly comparable measures;
3. one grouped comparison chart with direct values;
4. an always-visible comparison table for exact values and accessibility.

Algorithm details, raw schedules, and scenario assumptions belong below the result in expanders.

### P1 — use progressive disclosure

- Keep one scenario selector and one **Run comparison** action.
- Show the same result order everywhere: Requested slots, First-fit, CP-SAT.
- Put “How each approach works,” “Scenario inputs,” and “Exact schedule” in collapsed expanders.
- Link technical labels to the glossary with reusable tooltip text.
- Keep the insertion example as the concrete story: fixed routine work stays in place while a late door repair either fits or receives a clear no-capacity result.

### P1 — support narrow screens and assistive reading

- Stack method summaries below 800 pixels rather than squeezing three columns.
- Pair chart color with method names, direct values, and status words.
- Keep a visible table below every comparison chart; hover cannot be the only way to retrieve a value.
- Use native Streamlit controls and preserve the existing focus, disabled, contrast, and reduced-motion rules.
- Keep headings short enough to wrap naturally. Do not force line breaks for one viewport.

### P2 — reduce About-page scanning cost

The About page has accurate content but places several long explanations and two-column sections at the same visual level. Keep the planner workflow and one short solver summary visible. Move hard constraints, objective weights, status meanings, Gemini boundaries, data provenance, and qualification limits into clearly named expanders. Keep the external evidence and prototype limitations available without competing with the primary explanation.

## Recommended compact showcase layout

```text
Compare approaches
Same work. Same people. Same deadline.

[ Joint pressure | Easy fit | No capacity ]       [ Run comparison ]

Outcome sentence
[ Jobs placed ] [ Deadline misses ] [ Jobs moved ] [ Solver runtime* ]

Grouped bars or compact comparison plot
Visible exact-value table

▸ Why the results differ
▸ Exact schedule and constraints
▸ What this does — and does not — say about ROI
```

`Solver runtime*` must be labeled as machine runtime for this synthetic run. It is not planner time saved.

Recommended scenario names:

- **Joint pressure:** several constraints interact, showing the benefit of considering combinations together.
- **Easy fit:** all approaches succeed, preventing a one-sided demonstration.
- **No capacity:** the same hard limits make the workload infeasible, showing that CP-SAT does not invent capacity.

## Comparison definitions

| Approach | Plain-English definition | Required disclosure |
|---|---|---|
| Requested slots | Keep each requested start and report resulting conflicts. | Spreadsheet-like proxy; not a measured manual benchmark. |
| First-fit | In a stated order, place each job in the first valid available slot. | Publish order and tie-breaks; no backtracking. |
| CP-SAT | Search start-time and crew combinations together under hard constraints, then optimize the stated objective. | Show solver status and objective meaning; feasible is not necessarily optimal. |

Google describes constraint programming as finding feasible solutions among many candidates under constraints, and describes CP-SAT as a constraint-programming solver that also uses SAT (satisfiability) methods. The application should use this precise explanation rather than expanding CP-SAT into an invented product name. [Google OR-Tools: Constraint Optimization](https://developers.google.com/optimization/cp) · [Google OR-Tools: CP-SAT Solver](https://developers.google.com/optimization/cp/cp_solver)

## Backend questions that affect UI truthfulness

The comparison page should not make the corresponding claim until each answer is explicit in the API response or fixed scenario definition.

1. What does the requested-slots proxy do when two jobs conflict: flag both, preserve input order, or mark the later one unscheduled?
2. What exact order and tie-breaks does first-fit use: priority, deadline, request order, duration, or job ID?
3. Are all three approaches evaluated against the identical fixed commitments, skills, availability, deadlines, and window?
4. Does every result return scheduled, unscheduled, deadline-missed, and moved-job counts using the same definitions?
5. Can any method silently omit a job? The intended answer should be no.
6. Is CP-SAT runtime measured around solving only, and on which machine/run?
7. What objective value and unit are returned? Priority-weighted displacement should not be labeled “efficiency” without a defined conversion.
8. Does a status distinguish optimal, feasible, infeasible, invalid, and unknown?
9. Which figures are synthetic scenario outputs, and which—if any—come from observed operational data?
10. If financial ROI is displayed later, what baseline labor time, loaded cost, implementation cost, adoption period, and confidence range support it?

## Glossary integration contract

`frontend/glossary.py` provides:

- `render_glossary() -> None` for a dedicated offline utility page;
- `GLOSSARY_DEFINITIONS` for full category, plain-English, detailed, and optional source content;
- `GLOSSARY_TOOLTIPS` for short reusable help text;
- `glossary_tooltip(term: str) -> str` for safe lookup by other components.

The glossary requires no backend, network request, or API key. Its CP-SAT wording follows official Google OR-Tools documentation; all application-specific limitations match the current prototype behavior.
