# Research and data note

This note records the evidence used for the Ngeebula About page. It separates public context about Singapore rail maintenance from claims this repository can support about its own prototype and data.

## Public context

1. **[ST report](https://www.straitstimes.com/singapore/transport/behind-each-mrt-ride-how-trains-are-overhauled-tracks-maintained-on-north-south-east-west-lines), 2025.** Around 1,000 workers cover 150 worksites nightly.

2. **CNA, 1 April 2025 — [The night shift that keeps Singapore's trains running](https://www.channelnewsasia.com/singapore/tough-work-smrt-workers-train-rail-maintenance-5022391).** CNA observed an overnight rail replacement and described a narrow three-hour work period from 1:30 am to 4:30 am, including equipment movement and access to the worksite. This supports showing mobilisation and hand-back as real constraints. The current prototype does not model either one explicitly.

3. **Land Transport Authority, SMRT and SBS Transit, 30 December 2025 — [Rail Reliability Taskforce recommendations](https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/12/news-releases/rail_reliability_taskforce_submits_its_recommendations.html).** This primary joint release recommends setting aside more engineering hours, including full-day closures, and using comprehensive, standardised condition monitoring for timely maintenance interventions. It supports the broader case for structured planning and better data. Ngeebula does not implement condition monitoring or predictive maintenance.

4. **Ministry of Transport, 19 November 2025 — [International Metro Operators' Summit remarks](https://www.mot.gov.sg/news-resources/newsroom/opening-remarks-by-acting-minister-for-transport-jeffrey-siow-at-sbs-transit-s-international-metro-operators--summit/).** The official speech describes a 3.5-hour shutdown window, about two hours after equipment movement, and the difficulty of retrofitting legacy systems for condition monitoring. This corroborates the maintenance-window context without validating the prototype's fixed 00:30–05:00 assumption.

These pages were accessible during research on 17 September 2026. No paywall was bypassed. Headlines, publication dates, and concise factual summaries are recorded instead of reproducing article text.

## Repository data provenance

The original repository links to [notjerrygoh/ngeebula](https://github.com/notjerrygoh/ngeebula). Its supplied files contain no data dictionary, source citation, collection method, licence, owner, extraction date, or refresh process for the JSON datasets. The README does not link to a Google document.

| File | Observed contents | Supported conclusion |
|---|---|---|
| `backend/maintenance_db.json` | 161 activities across 9 categories plus a skill list | A reference catalog for this demonstration. Its operational authority is unknown. |
| `backend/engineers_db.json` | 700 original records; 697 engineers after duplicate-email removal | Project owner confirmed on 17 September 2026 that this is dummy data and requested its inclusion. Not operational staff or a staffing estimate. |
| `backend/stations_db.json` | 221 entries across 6 MRT and 3 LRT groupings | Useful labels for the demo. Accuracy and freshness are unverified because the file has no cited source or update date. |
| `backend/jobs.json` | Two sample jobs with 2026 dates | The root README explicitly calls this an example and says it is not automatically imported. |
| `backend/smrt_maintenance.db` | Locally seeded roster, operator-entered jobs, assignments, approvals, and audit entries | Runtime demo state, not an enterprise system of record. |

The original crew roster is dummy data according to the project owner. Its generation process is not documented. The maintenance catalog remains an unverified demonstration reference; public station evidence is documented separately in [the LTA research note](PUBLIC_DATA_RESEARCH.md).

## Model boundaries

The scheduling engine is Google OR-Tools CP-SAT, a constraint optimiser rather than a trained predictive model. It models a fixed prototype 00:30–05:00 SGT window, deadlines, line-and-track exclusion, engineer overlap, exact all-skills qualification, Boolean whole-window availability, headcount, and saved manual commitments. This window is a modeling assumption, not a claim about official hours or net productive time. The objective minimises priority-weighted displacement from original starts using Urgent 4, High 3, Medium 2, and Low 1. These weights protect higher-priority starts from movement; they do not require priority-first execution.

Gemini is optional. When configured on the backend, it may propose a catalog activity and bounded assessment. The backend accepts only a known category/activity, the full exact catalog skill list, allowed labels, and bounded numeric values. Invalid output falls back to deterministic catalog and deadline rules. Gemini does not schedule, approve, or bypass constraints.

There is no historical training dataset, fitted predictive model, held-out evaluation, or model-performance report in the repository. The application therefore must not claim to predict failures, repair duration, staffing demand, or reliability. Public calls for condition monitoring and predictive maintenance describe a sector direction, not a capability of this prototype.

## Claims discipline

Reasonable expected benefits are a shared request queue, earlier visibility of modeled conflicts and skill shortages, faster exploration of feasible combinations, and recorded planner decisions. These are product hypotheses until measured in a pilot.

The repository provides no baseline or evaluation proving improvements in safety, reliability, cost, planning time, worker productivity, schedule optimality under real conditions, or passenger outcomes. The prototype also lacks structured travel time, mobilisation and extraction time, breaks and fatigue limits, permits, possessions, line authorisations, equipment capacity, granular shift calendars, authentication, and tamper-proof audit storage.
