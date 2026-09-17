# Video sources and claims

Checked against the linked original pages and the repository on **17 September 2026**. These lines are suitable for a 1–2 minute stakeholder video when shown as paraphrases with a small source credit.

## Safe on-screen context

- **“A reported Singapore rail-replacement shift had only three hours—from 1:30 am to 4:30 am—to complete the work.”** Source: CNA, 1 Apr 2025, [“The night shift that keeps Singapore's trains running”](https://www.channelnewsasia.com/singapore/tough-work-smrt-workers-train-rail-maintenance-5022391). CNA describes this observed rail-replacement window and the movement of equipment and workers to the site; it is not a universal timetable for every maintenance activity.
- **“Singapore's Transport Ministry says most rail maintenance fits within a 3.5-hour shutdown, with about two hours left after heavy equipment is deployed and extracted.”** Source: Ministry of Transport, 19 Nov 2025, [International Metro Operators' Summit opening remarks](https://www.mot.gov.sg/news-resources/newsroom/opening-remarks-by-acting-minister-for-transport-jeffrey-siow-at-sbs-transit-s-international-metro-operators--summit/). This is the best primary-source statement of the time constraint.
- **“Singapore's Rail Reliability Taskforce recommended more engineering hours and more timely maintenance interventions supported by standardised condition monitoring.”** Source: LTA, SMRT and SBS Transit joint release, 30 Dec 2025, [Rail Reliability Taskforce recommendations](https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/12/news-releases/rail_reliability_taskforce_submits_its_recommendations.html). Do not imply that Ngeebula performs condition monitoring or predictive maintenance.

An optional scale statistic is: **“SMRT said about 1,000 workers carry out maintenance across 150 worksites each night.”** Source: The Straits Times, 1 Apr 2025 (updated 3 Apr), [“Behind each MRT ride”](https://www.straitstimes.com/singapore/transport/behind-each-mrt-ride-how-trains-are-overhauled-tracks-maintained-on-north-south-east-west-lines). Attribute the figure to SMRT and do not generalise it to all Singapore operators.

## Safe product wording

- **“Ngeebula helps a planner fit corrective work around approved preventive commitments, qualified crew and modeled location constraints.”** The OR-Tools CP-SAT engine checks the encoded window, deadline, qualification, headcount, engineer-overlap and line/track constraints. Approved and time-locked work stays fixed.
- **“Select the asset, confirm its station and serving line, review requirements, generate a proposal, then approve.”** Single-line stations resolve automatically; interchanges require a line choice. Explicit catalog selections remain authoritative, and free-text Gemini assistance is optional.
- **“When the modeled inputs do not fit, Ngeebula surfaces the conflict for planner review instead of silently dropping work.”** A proposal remains subject to human review and does not authorise execution.

Use **“modeled proposal”**, **“planning prototype”**, and **“planner review”** in captions. The app's fixed 00:30–05:00 SGT window is a prototype assumption, not an official or net productive maintenance window. The repository roster is dummy data, demonstrations are synthetic, the maintenance catalog is unverified, and the station lookup is a versioned LTA-reference reconciliation rather than a live operations feed.

## Claims to avoid

Do not claim measured savings, faster planning, fewer disruptions, improved safety or reliability, predictive maintenance, failure prediction, optimal real-world operations, guaranteed crew availability, or operator/LTA endorsement. The repository contains no pilot baseline or operational evaluation supporting those outcomes. It also does not model mobilisation, extraction, travel, breaks, fatigue, permits, possessions, equipment capacity or safe-access authority.

## Media and rights guidance

Paraphrase the facts above and display a compact text citation or link. Do not reproduce article screenshots, headlines as a graphic treatment, publisher videos, or CNA/Straits Times photographs without permission; those pages identify publisher and photographer copyrights. Prefer original Ngeebula screen recordings, the repository's local SVG illustrations, and newly created generic rail-maintenance visuals. Government-source facts may also be paraphrased with an LTA/MOT credit and link; agency logos, crests and third-party images should not be used to suggest endorsement. For station-reference attribution, retain the dataset name, access date and [Singapore Open Data Licence 1.0](https://datamall.lta.gov.sg/content/datamall/en/SingaporeOpenDataLicence.html) link.
