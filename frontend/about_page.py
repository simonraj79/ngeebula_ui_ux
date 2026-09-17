"""Offline, operator-facing explanation of the Ngeebula prototype."""

import streamlit as st


def render_about_page() -> None:
    """Render the About workspace using native Streamlit components only."""
    st.subheader("Plan constrained overnight work with a human in control")
    st.write(
        "Ngeebula brings maintenance requests, crew checks, scheduling, review, "
        "execution updates, and audit history into one planner-led workflow. It is a "
        "local planning prototype: it does not issue track access, certify a safe system "
        "of work, or replace engineering judgement."
    )

    st.markdown("### Problem statement and scope")
    st.write(
        "**Problem statement:** Overnight rail-maintenance planners must fit deadline-bound "
        "work, fully qualified people, shared track access, and fixed commitments into a "
        "narrow window. Unseen conflicts can leave an infeasible plan and force late manual rework."
    )
    st.write(
        "**Scope:** This prototype supports the request-to-execution planning decision: capture, "
        "assess, allocate, schedule, review, approve, and record status. It does not manage "
        "possessions, certify field controls, monitor assets, or dispatch trains."
    )
    with st.container(border=True):
        st.markdown("#### The everyday problem: a new repair meets a fixed timetable")
        st.write(
            "A school's lessons already have rooms and teachers. When someone is absent, cover must fit around those commitments. "
            "For a maintenance chief, approved preventive jobs form the fixed timetable. A newly reported door, rail or pump fault "
            "adds a corrective request that needs a suitable slot, qualified people and a completion deadline."
        )
        st.write(
            "The app helps plan that repair once the operational team has assessed it as suitable for a maintenance window. "
            "Active flooding, an unsafe door or a live service disruption first belongs to the operator's incident process. "
            "The planner cannot infer that a fault is safe to defer from a picture, a description or an AI assessment."
        )
        st.caption("Try Schedule example from the cockpit: the real solver inserts a synthetic repair or explains why its deadline leaves no feasible slot. It changes no live records.")

    context, scope = st.columns(2, gap="large")
    with context:
        st.markdown("#### Why the planning window matters")
        st.markdown(
            "Singapore reporting shows how much work must fit between the last and first "
            "train. CNA observed overnight rail work between 1:30 am and 4:30 am in March "
            "2025. Government reporting later described a 3.5-hour "
            "shutdown window that can leave about two engineering hours after equipment is "
            "deployed and removed. [CNA, 1 Apr 2025](https://www.channelnewsasia.com/singapore/tough-work-smrt-workers-train-rail-maintenance-5022391) · "
            "[Ministry of Transport, 19 Nov 2025](https://www.mot.gov.sg/news-resources/newsroom/opening-remarks-by-acting-minister-for-transport-jeffrey-siow-at-sbs-transit-s-international-metro-operators--summit/)"
        )
    with scope:
        st.markdown("#### What this prototype models")
        st.write(
            "The application currently plans the next 00:30–05:00 SGT window. That fixed "
            "window is a prototype modeling assumption, not a claim about SMRT's official "
            "maintenance hours or the net time available for work. "
            "Operators must confirm possessions, access, hand-back time, and field controls "
            "through the authorised operating process."
        )

    st.divider()
    st.markdown("### Planner workflow")
    st.caption("Five review points keep the accountable decision with the operations team.")
    st.markdown("**Create request → Review assessment → Generate plan → Override and approve → Track execution**")
    st.graphviz_chart(
        """
        digraph workflow {
          rankdir=TB;
          graph [bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.4"];
          node [shape=box, style="rounded,filled", fillcolor="#16324a", color="#4b89b6",
                fontcolor="white", fontname="Arial", margin="0.16,0.10"];
          edge [color="#6da7cc", penwidth=1.6, arrowsize=0.7];
          request [label="1  Create\nrequest"];
          review [label="2  Review\nassessment"];
          plan [label="3  Generate\nplan"];
          approve [label="4  Override\n& approve"];
          execute [label="5  Track\nexecution"];
          request -> review -> plan -> approve -> execute;
        }
        """,
        width="content",
    )
    workflow = [
        ("1 · Create request", "Pick one of eight familiar assets, confirm its repair, then enter the exact work location and deadline. Other issues can use a free-text request."),
        ("2 · Review assessment", "Confirm priority, catalog match, required skills, crew size, and any staffing shortage."),
        ("3 · Generate plan", "Run the constraint model and inspect its window, crew, conflicts, and warnings."),
        ("4 · Override and approve", "Change priority, crew, or start time with a named planner and a reason, then approve."),
        ("5 · Track execution", "Record start, delay, error, replanning, and completion through valid status transitions."),
    ]
    for title, detail in workflow:
        with st.expander(title):
            st.write(detail)

    st.markdown("#### How the interface supports each decision")
    st.table(
        [
            {"Need": "See what needs attention", "Interface": "Request queue and status filters", "Decision": "Review, correct, or remove"},
            {"Need": "Understand time interactions", "Interface": "Gantt timeline", "Decision": "Check sequence, gaps, and overlaps"},
            {"Need": "Inspect exact details", "Interface": "Tables and job summaries", "Decision": "Confirm crew, skills, times, and approval"},
            {"Need": "Make an accountable change", "Interface": "Native forms with reasons", "Decision": "Override, approve, or update status"},
        ]
    )
    st.markdown(
        "The **Gantt timeline** shows sequence and overlap; the tables preserve exact crew, "
        "skills, timestamps, and statuses. Native forms guide changes and keep validation "
        "messages beside the decision."
    )
    st.write(
        "The numbered **2D asset schematic** helps recognition without requiring a rotating 3D model or knowledge of 161 catalog entries. "
        "Eight labelled buttons work with keyboard and touch; the image is a guide, not a live map. Each shortcut names a specific "
        "catalog repair and preserves that selection. These are curated examples, not a measured ranking of the most frequent faults."
    )
    st.caption("Train and depot work uses the same simplified location/time model. Fleet availability, depot-bay routing, spare parts and operational release are not modelled.")

    st.divider()
    st.markdown("### How the schedule is produced")
    with st.container(border=True):
        st.markdown("#### OR-Tools CP-SAT, in one minute")
        st.write(
            "CP-SAT is an OR-Tools constraint-programming solver that also uses SAT "
            "(satisfiability) methods. Here it searches integer start-minute and crew choices. "
            "It is mathematical constraint optimisation, not a trained machine-learning model."
        )
        st.write(
            "It considers time and crew combinations together, keeps approved commitments fixed, "
            "and reports when the supplied constraints cannot all be met."
        )

    with st.expander("Hard checks the solver must obey"):
        st.markdown(
            """
            - work fits the modeled maintenance window and finishes before its deadline;
            - jobs do not overlap on the same line and track;
            - one engineer cannot work on two overlapping jobs;
            - each assigned engineer holds every required skill and is marked available;
            - saved planner times and crews remain commitments during regeneration.
            """
        )
    with st.expander("Why priority is weighted — objective, not safety rules"):
        st.write(
            "The objective minimises movement from each job's original start. Displacement "
            "is weighted Urgent 4, High 3, Medium 2, and Low 1, so moving urgent work costs "
            "the solver more. This protects higher-priority starts when constraints compete."
        )
        st.info(
            "Priority-weighted displacement does not mean ‘highest priority always starts "
            "first’. A feasible result is only feasible for the data and constraints supplied."
        )
    with st.expander("What feasible, infeasible, optimal, and unknown mean"):
        st.markdown(
            "- **Feasible:** at least one schedule satisfies every modeled hard constraint.\n"
            "- **Infeasible:** no schedule can satisfy all supplied hard constraints together.\n"
            "- **Optimal:** the solver proved no feasible schedule has a better objective score.\n"
            "- **Unknown:** the search ended without a schedule and without proving impossibility."
        )
        st.caption(
            "A feasible result is not proof of global optimality unless the solver reports optimal. "
            "The Glossary utility keeps these definitions available offline."
        )

    st.markdown("### Rules, optional Gemini, and human approval")
    st.table(
        [
            {
                "Component": "Catalog + rules",
                "What it does": "Works offline; matches request terms to an activity and derives reviewable defaults.",
                "What it cannot do": "Infer missing qualifications or approve work.",
            },
            {
                "Component": "Gemini (optional)",
                "What it does": "Suggests a bounded catalog assessment when a backend API key is configured.",
                "What it cannot do": "Bypass exact catalog skills, numeric bounds, scheduling checks, or approval.",
            },
            {
                "Component": "Planner",
                "What it does": "Reviews shortages, records overrides and reasons, and approves a proposed plan.",
                "What it cannot do": "Save a conflicting override through the API.",
            },
        ]
    )
    st.info("Predictive ML is intentionally outside the current scope.")
    st.markdown(
        "There is no predictive ML model or **training dataset** in this repository. The app "
        "does not predict failures, repair durations, or reliability outcomes. A future model "
        "would need governed historical outcomes and measured validation error."
    )

    st.divider()
    st.markdown("### Data used by this demonstration")
    st.write(
        "Maintenance activities and example jobs remain synthetic or unverified demonstration inputs. The project owner confirmed the original crew roster is dummy data. "
        "Station names and codes are now reconciled with a versioned LTA snapshot, with source links, access date and licence. "
        "Public station data does not turn the remaining demonstration inputs into official operational records."
    )
    st.table(
        [
            {"Data": "Maintenance catalog", "Repository evidence": "161 activities in 9 categories; no provenance metadata", "Use": "Rules and skill requirements"},
            {"Data": "Public engineer seed", "Repository evidence": "700 original dummy records, confirmed by the project owner; 697 engineers after duplicate-email removal.", "Use": "Demonstration skills and availability only"},
            {"Data": "Station reference", "Repository evidence": "222 reconciled entries: 213 codes checked against the Jan 2025 LTA snapshot; 9 local-only entries remain unverified", "Use": "Station search and line consistency; not current operating status"},
            {"Data": "Example jobs", "Repository evidence": "Two examples; README says they are not imported", "Use": "Illustration only"},
            {"Data": "Schedule insertion example", "Repository evidence": "Invented routine jobs, corrective task, durations and qualified crew in backend/main.py", "Use": "Read-only demonstration using the real constraint solver"},
        ]
    )
    st.markdown("Station reference contains information from **LTA Train Station Codes and Chinese Names**, accessed **17 September 2026**, under the [Singapore Open Data Licence](https://datamall.lta.gov.sg/content/datamall/en/SingaporeOpenDataLicence.html). [Source files](https://datamall.lta.gov.sg/content/datamall/en/static-data.html).")
    with st.expander("Qualification and availability limitations"):
        st.write(
            "Automatic assignment uses case-insensitive exact skill names, and every assigned "
            "engineer must hold the complete required set. Catalog and roster terminology do "
            "not always align, so a visible shortage can be correct for this dataset. The "
            "availability flag assumes a person is free for the whole window; shifts, travel, "
            "breaks, fatigue limits, line authorisations, permits, equipment, and sector access "
            "are not structured inputs."
        )

    st.markdown("### Expected value and evidence still needed")
    benefits, claims = st.columns(2, gap="large")
    with benefits:
        st.success("Expected operational support")
        st.markdown(
            """
            - one visible queue for requests, crews, priorities, and decisions;
            - earlier detection of modeled track and engineer conflicts;
            - faster comparison of feasible combinations;
            - an audit trail for planner changes and deletion reasons.
            """
        )
    with claims:
        st.info("Not yet measured")
        st.markdown(
            """
            - reliability, safety, cost, or productivity improvement;
            - time saved versus the current SMRT planning process;
            - schedule quality under real possessions and workforce rules;
            - model accuracy, because no predictive model is present.
            """
        )

    st.divider()
    st.markdown("### Singapore rail-maintenance context")
    st.caption("External links provide context only; this page remains usable offline.")
    st.markdown(
        "- [The Straits Times maintenance report (1 Apr 2025)](https://www.straitstimes.com/singapore/transport/behind-each-mrt-ride-how-trains-are-overhauled-tracks-maintained-on-north-south-east-west-lines)  \n"
        "- [CNA — The night shift that keeps Singapore's trains running (1 Apr 2025)](https://www.channelnewsasia.com/singapore/tough-work-smrt-workers-train-rail-maintenance-5022391)  \n"
        "- [LTA, SMRT and SBS Transit — Rail Reliability Taskforce recommendations (30 Dec 2025)](https://www.lta.gov.sg/content/ltagov/en/newsroom/2025/12/news-releases/rail_reliability_taskforce_submits_its_recommendations.html) — recommends more engineering time and standardised condition data; those data are outside this prototype.  \n"
        "- [Ministry of Transport — International Metro Operators' Summit remarks (19 Nov 2025)](https://www.mot.gov.sg/news-resources/newsroom/opening-remarks-by-acting-minister-for-transport-jeffrey-siow-at-sbs-transit-s-international-metro-operators--summit/)"
    )
