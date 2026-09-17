"""Plain-English, offline glossary for the planning interface."""
from __future__ import annotations

import streamlit as st


GLOSSARY_DEFINITIONS: dict[str, dict[str, str]] = {
    "CP-SAT": {
        "category": "Solver",
        "plain": "A planning engine that finds combinations of start times and crews that obey the supplied rules.",
        "detail": (
            "CP means constraint programming. SAT means satisfiability: checking whether logical rules can all be true together. "
            "Google OR-Tools combines these methods to search whole-number choices, such as start minutes and crew assignments. "
            "It is mathematical optimisation, not a trained machine-learning model."
        ),
        "source": "https://developers.google.com/optimization/cp",
    },
    "Constraint": {
        "category": "Solver",
        "plain": "A rule every accepted schedule must obey.",
        "detail": (
            "Examples are finishing before a deadline, avoiding overlapping work on one track, "
            "and assigning the required number of qualified people."
        ),
    },
    "Hard constraint": {
        "category": "Solver",
        "plain": "A rule the solver is never allowed to trade away.",
        "detail": (
            "If all hard constraints cannot be satisfied together, the result is infeasible. "
            "Priority does not permit the solver to break a hard safety or staffing rule."
        ),
    },
    "Objective": {
        "category": "Solver",
        "plain": "The score the solver tries to make as small or large as possible after satisfying every hard rule.",
        "detail": (
            "Ngeebula minimises priority-weighted movement from requested start times. The objective "
            "selects among feasible schedules; it does not relax a constraint."
        ),
    },
    "Priority-weighted displacement": {
        "category": "Solver",
        "plain": "A penalty for moving a job away from its requested start, multiplied by its priority weight.",
        "detail": (
            "Urgent work costs the solver more to move than low-priority work. This does not mean the "
            "highest-priority job must always start first."
        ),
    },
    "Feasible": {
        "category": "Result",
        "plain": "At least one schedule satisfies all modeled hard constraints.",
        "detail": (
            "Feasible describes the supplied data and model only. It does not certify possessions, "
            "field controls, travel time, fatigue limits, or any operational input the prototype does not hold."
        ),
    },
    "Infeasible": {
        "category": "Result",
        "plain": "No schedule can satisfy all supplied hard constraints together.",
        "detail": (
            "The operator may need a later deadline, another qualified person, a longer window, or an "
            "explicitly deferred job. The solver does not silently drop work."
        ),
    },
    "Optimal": {
        "category": "Result",
        "plain": "The solver proved that no feasible schedule has a better objective score.",
        "detail": (
            "A merely feasible result is not automatically optimal. The displayed solver status is the "
            "source of truth for whether optimality was proved."
        ),
    },
    "Unknown solver status": {
        "category": "Result",
        "plain": "The search ended without a schedule and without proving that none exists.",
        "detail": (
            "Unknown is different from infeasible. It can occur when a search limit is reached, so it "
            "should lead to review or retry rather than a no-capacity claim."
        ),
    },
    "Fixed commitment": {
        "category": "Planning",
        "plain": "Approved or locked work that a new proposal must preserve.",
        "detail": (
            "It occupies its saved track and crew intervals while other unapproved jobs are replanned around it."
        ),
    },
    "Time lock": {
        "category": "Planning",
        "plain": "A planner-set start time that schedule regeneration must preserve.",
        "detail": "Changing a job's location clears its old time lock because the prior proposal is no longer valid.",
    },
    "Crew lock": {
        "category": "Planning",
        "plain": "A planner-set engineer team that regeneration must preserve.",
        "detail": "The locked team must still meet headcount, skills, availability, and overlap checks.",
    },
    "Qualified team": {
        "category": "Planning",
        "plain": "The exact headcount where every assigned engineer holds every required skill.",
        "detail": (
            "Skill names are matched case-insensitively but otherwise exactly in this prototype. A person "
            "with only some of the required skills is not counted as fully qualified."
        ),
    },
    "Maintenance window": {
        "category": "Planning",
        "plain": "The modeled start and end boundary within which scheduled work must fit.",
        "detail": (
            "The prototype uses the next complete 00:30-05:00 SGT window. This is a modeling assumption, "
            "not a statement of net engineering access time."
        ),
    },
    "Proposal": {
        "category": "Governance",
        "plain": "A solver-generated plan that still requires human review.",
        "detail": "A proposal can be corrected or overridden. It becomes a commitment only through the approval workflow.",
    },
    "Approval": {
        "category": "Governance",
        "plain": "A named planner's recorded decision to accept a validated proposal.",
        "detail": "Approval does not replace operational authority, track access, or a safe system of work.",
    },
    "First-fit": {
        "category": "Comparison",
        "plain": "A simple rule that takes jobs in a defined order and places each into the first available valid slot.",
        "detail": (
            "It is fast and understandable, but an early local choice can block a better later combination. "
            "The comparison must state its job order and tie-break rules."
        ),
    },
    "Requested-slots proxy": {
        "category": "Comparison",
        "plain": "A spreadsheet-like proxy that keeps each requested start instead of searching combinations.",
        "detail": (
            "It is a transparent demonstration baseline, not measured evidence of a real planner's process, "
            "speed, or quality."
        ),
    },
    "ROI": {
        "category": "Evidence",
        "plain": "Return on investment: net benefit divided by the investment cost over a defined period.",
        "detail": (
            "A synthetic schedule comparison can show modeled conflicts, movement, and feasibility. It cannot "
            "prove financial ROI or planner time saved without observed baseline data and implementation costs. "
            "The savings calculator shows an estimate from your assumptions, not a measured operational result."
        ),
    },
    "Solver runtime": {
        "category": "Evidence",
        "plain": "How long the optimization code takes to return on the measured machine and scenario.",
        "detail": (
            "Runtime is not the same as total planning effort. Data preparation, review, correction, approval, "
            "and operational coordination remain human work."
        ),
    },
}

GLOSSARY_TOOLTIPS: dict[str, str] = {
    term: definition["plain"] for term, definition in GLOSSARY_DEFINITIONS.items()
}


def glossary_tooltip(term: str) -> str:
    """Return reusable help text for a labeled Streamlit control."""
    return GLOSSARY_TOOLTIPS.get(term, "")


def render_glossary() -> None:
    """Render the searchable glossary using native Streamlit components."""
    st.subheader("Planning words, without the jargon")
    st.write(
        "Search for a solver, planning, comparison, or evidence term. Definitions describe "
        "what each word means in this prototype."
    )
    query = st.text_input(
        "Search glossary",
        placeholder="Try feasible, first-fit, priority, ROI, or approval",
        key="glossary_search",
    ).strip().casefold()
    matches = []
    for term, definition in GLOSSARY_DEFINITIONS.items():
        searchable = " ".join((term, *definition.values())).casefold()
        if not query or query in searchable:
            matches.append((term, definition))
    st.caption(f"{len(matches)} of {len(GLOSSARY_DEFINITIONS)} terms")
    if not matches:
        st.info("No matching term. Try a shorter word such as crew, solver, plan, or result.")
        return
    for term, definition in matches:
        with st.expander(f"{term} · {definition['category']}", expanded=bool(query)):
            st.write(f"**{definition['plain']}**")
            st.write(definition["detail"])
            if source := definition.get("source"):
                st.markdown(f"[Official reference]({source})")
