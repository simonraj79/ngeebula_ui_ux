"""Decision-first showcase; synthetic outcomes and assumed financial value stay separate."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import ApiClient, ApiClientError
from data_evidence import render_data_evidence
from glossary import glossary_tooltip

METHOD_NAMES = {"manual_proxy": "Requested slots", "priority_first_fit": "First available slot", "cp_sat": "Joint planning"}
SHORT_NAMES = {"manual_proxy": "1 · Slots", "priority_first_fit": "2 · First fit", "cp_sat": "3 · Joint plan"}
SCENARIOS = {"joint_planning": "Two repairs need the same specialist", "straightforward": "Plenty of room: all methods work", "no_capacity": "Not enough time: no complete plan"}


def schedule_comparison_chart(result: dict):
    records = []
    candidate_names = {str(job["id"]): job["name"] for job in result["candidates"]}
    crew_ids = sorted({str(person) for method in result["methods"] for row in method["schedule"] + result["commitments"] for person in row["assigned_engineer_ids"]})
    crew_labels = {value: f"Crew {chr(65 + index)}" for index, value in enumerate(crew_ids)}
    for method in result["methods"]:
        for row in result["commitments"] + method["schedule"]:
            start, end = (pd.Timestamp(row[field]).tz_convert("Asia/Singapore") for field in ("scheduled_start", "scheduled_end"))
            for person in row["assigned_engineer_ids"]:
                records.append({"Lane": f"{SHORT_NAMES[method['method_id']]} / {crew_labels[str(person)]}",
                                "Method": METHOD_NAMES[method["method_id"]], "Crew": crew_labels[str(person)],
                                "Work": candidate_names.get(str(row["job_id"]), "Fixed inspection"),
                                "Start": start, "Finish": end, "Site": row["track"],
                                "Time": f"{start:%H:%M}–{end:%H:%M} SGT"})
    frame = pd.DataFrame(records)
    frame["Label"] = frame["Work"].map(lambda value: "Fixed" if value == "Fixed inspection" else "Signal" if "Signal" in value or "signalling" in value else "Door" if "door" in value else "Repair")
    lanes = [f"{SHORT_NAMES[method['method_id']]} / {crew_labels[person]}" for method in result["methods"] for person in crew_ids]
    colors = ["#85baf6", "#ffc46b", "#74d6b4"]
    fig = px.timeline(frame, x_start="Start", x_end="Finish", y="Lane", color="Work", text="Label", color_discrete_sequence=colors,
                      custom_data=["Method", "Crew", "Work", "Time", "Site"])
    fig.update_traces(textfont=dict(color="#081522", size=12), textposition="inside", insidetextanchor="middle",
                      hovertemplate="<b>%{customdata[2]}</b><br>%{customdata[0]} · %{customdata[1]}<br>%{customdata[3]}<br>%{customdata[4]}<extra></extra>")
    window_start = pd.Timestamp(result["window"]["start"]).tz_convert("Asia/Singapore")
    window_end = pd.Timestamp(result["window"]["end"]).tz_convert("Asia/Singapore")
    fig.update_layout(height=440, margin=dict(l=0, r=28, t=25, b=15), bargap=.28,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#cfdded"),
                      uniformtext=dict(minsize=12,mode="hide"),
                      xaxis=dict(range=[window_start, window_end], tickvals=pd.date_range(window_start, window_end, periods=4),
                                 tickformat="%H:%M", title="Time (SGT)", side="top", gridcolor="#29415a"),
                      yaxis=dict(title=None, autorange="reversed", categoryorder="array", categoryarray=lanes),
                      legend=dict(title=None, orientation="h", y=-.2))
    return fig, frame


def render_schedule_comparison(client: ApiClient) -> None:
    scenario = st.selectbox("Choose a situation", list(SCENARIOS), format_func=SCENARIOS.get, key="compare_scenario")
    result = st.session_state.get("planning_comparison")
    rerun = st.button("Run comparison", key="compare_run", type="primary")
    if rerun:
        with st.spinner("Trying the same work and crew with all three approaches…"):
            try:
                result = client.compare_planning(scenario)
            except ApiClientError as exc:
                st.session_state.pop("planning_comparison", None)
                st.error(f"Comparison unavailable. {exc}")
                return
            st.session_state["planning_comparison"] = result
    if not result or result.get("scenario") != scenario:
        st.write("**1 · Keep requested slots** — check a worksheet without rearranging it.")
        st.write("**2 · First available slot** — place each job in turn, without revisiting earlier choices.")
        st.write("**3 · Joint planning** — consider job times and crew assignments together.")
        st.caption("Run a comparison to reveal the outcomes. The first approach is a scripted worksheet proxy, not a benchmark of human planners.")
        return
    st.caption(result["comparison_basis"])
    st.caption("Requested slots is a scripted worksheet proxy, not measured human performance. Joint planning is Ngeebula’s constraint-based approach.")
    st.write("**New repairs placed before their deadlines**")
    columns = st.columns(3)
    for col, method in zip(columns, result["methods"]):
        counts = method["metrics"]
        col.metric(METHOD_NAMES[method["method_id"]], f"{counts['on_time_jobs']} / {counts['candidate_jobs']}", help="New repairs placed before their deadlines; fixed preventive work is counted separately.")
        col.caption("All new repairs fit" if method["status"] == "complete" else "Incomplete plan" if method["status"] in {"incomplete", "infeasible"} else "Search did not finish successfully")
    cp = next(method for method in result["methods"] if method["method_id"] == "cp_sat")
    if cp["status"] == "complete":
        st.write("**All repairs fit together.** Review which crew performs each job; approved preventive work stays fixed.")
    elif cp["status"] == "infeasible":
        st.warning("No complete plan fits these inputs. The joint planner returns no partial proposal; review the work scope, deadline or resources.")
    else:
        st.warning("The search did not establish a complete plan. This is not proof that no plan exists.")
    st.write(result.get("scenario_explanation") or "In the first scenario, assigning the multi-skilled engineer to the first job leaves the specialist task without a crew. Joint planning can reconsider that choice.")
    st.subheader("Who works when")
    st.caption(f"Example shift: {pd.Timestamp(result['window']['start']).tz_convert('Asia/Singapore'):%d %b %Y}, 00:30–05:00 SGT")
    st.caption("One row per crew and approach. Empty time does not prove operational access. All methods retain the fixed inspection.")
    st.caption("Crew A: mechanical + signalling skills. Crew B: mechanical skills. These are invented demonstration roles.")
    fig, frame = schedule_comparison_chart(result)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="compare_timeline")
    with st.expander("Exact work, crew and times"):
        st.dataframe(frame[["Method", "Crew", "Work", "Time", "Site"]], hide_index=True, width="stretch")
    not_placed = [{"Approach": METHOD_NAMES[method["method_id"]], "Repair": next(job["name"] for job in result["candidates"] if job["id"] == item["job_id"]), "Reason": item["reason"]}
                  for method in result["methods"] for item in method["unscheduled"]]
    if not_placed:
        st.subheader("Work still needing a plan")
        st.dataframe(not_placed, hide_index=True, width="stretch")
    with st.expander("Why the approaches differ"):
        for method in result["methods"]:
            st.write(f"**{METHOD_NAMES[method['method_id']]}:** {method['method_description']}")
        st.write("The worksheet proxy is deliberately limited; an experienced planner or another heuristic may find the same plan as the joint planner. These examples do not establish typical performance.")
        st.write(f"**Search result:** {cp.get('solver_status', 'Not supplied')} · **Computer runtime:** {cp.get('wall_time_ms', 0):,.1f} ms")
        st.caption("Runtime is not staff time saved. The live planner also requires all eligible jobs to fit; partial heuristic results above cannot be applied.")


def render_savings(client: ApiClient) -> None:
    st.subheader("Estimate the value of planning time")
    st.write("Savings depend on preparation, review and approval effort, plus the cost of running the tool. This calculator uses editable assumptions; it does not turn a synthetic schedule into proven savings.")
    st.caption("Illustrative inputs only · Singapore dollars · No disruption, reliability or safety benefit is priced in")
    defaults = {"roi_baseline": "manual_proxy", "roi_shifts": 22, "roi_rate": 60.0, "roi_initial": 3000.0, "roi_monthly": 100.0,
                "roi_minutes_manual_proxy": 45.0, "roi_minutes_priority_first_fit": 25.0, "roi_minutes_cp_sat": 15.0}
    draft = st.session_state.get("roi_input_draft", {})
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = draft.get(key, default)
    baseline = st.radio("Compare joint planning with", ["manual_proxy", "priority_first_fit"], format_func=METHOD_NAMES.get, horizontal=True, key="roi_baseline")
    with st.expander("Adjust the example assumptions"):
        shifts = st.number_input("Planning runs per month", min_value=0, max_value=10000, key="roi_shifts")
        rate = st.number_input("Planner cost per hour (S$)", min_value=0.0, max_value=100000.0, step=5.0, key="roi_rate")
        st.caption("Include the full preparation, correction and review time for each planning run.")
        minutes = {}
        for method in METHOD_NAMES:
            minutes[method] = st.number_input(f"{METHOD_NAMES[method]} — minutes per run", min_value=0.0, max_value=10000.0, step=5.0, key=f"roi_minutes_{method}")
        initial = st.number_input("Joint planning — one-off setup cost (S$)", min_value=0.0, max_value=10000000.0, step=100.0, key="roi_initial")
        recurring = st.number_input("Joint planning — running cost per month (S$)", min_value=0.0, max_value=1000000.0, step=25.0, key="roi_monthly")
        st.caption("This simplified comparison assumes no new setup or running cost for the existing alternatives. Include integration, training, hosting and support in joint planning costs.")
    st.session_state["roi_input_draft"] = {key: st.session_state[key] for key in defaults}
    payload = dict(planning_shifts_per_month=shifts, minutes_per_cycle=minutes, loaded_hourly_cost_sgd=rate,
                   initial_cost_sgd={method: initial if method == "cp_sat" else 0 for method in METHOD_NAMES},
                   monthly_operating_cost_sgd={method: recurring if method == "cp_sat" else 0 for method in METHOD_NAMES}, baseline_method=baseline)
    st.caption(f"Current example: {shifts} runs/month · SGD {rate:,.0f}/hour · {minutes[baseline]:g} → {minutes['cp_sat']:g} min/run · SGD {initial:,.0f} setup + SGD {recurring:,.0f}/month")
    try:
        result = client.estimate_roi(payload)
    except ApiClientError as exc:
        st.error(f"Estimate unavailable. {exc}")
        return
    render_roi_outputs(result, baseline)


def render_roi_outputs(result: dict, baseline: str) -> None:
    outputs = result["calculated_outputs"]
    joint = outputs["cp_sat"]
    metrics = st.columns(3)
    metrics[0].metric("First-year net benefit", f"S${joint['first_year_net_benefit_sgd']:,.0f}", help="Assumed labour savings minus incremental running and setup costs in the first year.")
    roi = joint.get("first_year_roi_percent")
    metrics[1].metric("First-year ROI", f"{roi:,.0f}%" if roi is not None else "Not defined", help=glossary_tooltip("ROI"))
    payback = joint.get("payback_months")
    payback_label = f"{payback:.1f} months" if payback is not None else "No setup premium" if joint["incremental_initial_cost_sgd"] <= 0 else "Not reached"
    metrics[2].metric("Estimated payback", payback_label)
    if roi is None:
        st.caption(joint.get("roi_note", "A positive initial investment is needed for this ROI percentage."))
    if joint["first_year_net_benefit_sgd"] < 0:
        st.warning("These assumptions do not recover the extra cost in the first year. Change the assumptions only if there is evidence to support them.")
    else:
        st.write(f"**Illustrative result versus {METHOD_NAMES[baseline].lower()}:** {joint['hours_saved_vs_baseline']:,.1f} planning hours released per year. Time released is not automatically cash saved.")
    records = []
    for method, values in outputs.items():
        for label, field in [("Planner effort", "annual_planning_labour_cost_sgd"), ("Running cost", "annual_operating_cost_sgd"), ("Setup cost", "initial_cost_sgd")]:
            records.append({"Approach": METHOD_NAMES[method], "Cost": label, "S$": values[field]})
    figure = px.bar(pd.DataFrame(records), y="Approach", x="S$", color="Cost", orientation="h",
                    color_discrete_sequence=["#85baf6", "#ffc46b", "#74d6b4"], labels={"S$": "Estimated first-year cost (S$)"})
    figure.update_layout(height=300, margin=dict(l=0,r=5,t=15,b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(color="#cfdded"), yaxis=dict(title=None), legend=dict(title=None,orientation="h",y=-.3))
    st.subheader("Compare first-year costs")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar":False}, key="roi_cost_chart")
    st.dataframe([{"Approach": METHOD_NAMES[method], "Staff hours / year": round(row["annual_planning_hours"], 1),
                   "First-year cost (S$)": round(row["annual_planning_labour_cost_sgd"] + row["annual_operating_cost_sgd"] + row["initial_cost_sgd"], 2)}
                  for method, row in outputs.items()], hide_index=True, width="stretch")
    with st.expander("Formula and evidence needed"):
        st.write("Annual hours = runs per month × 12 × minutes per run ÷ 60. Annual net benefit = labour-cost difference − extra annual running cost. First-year net benefit also subtracts extra setup cost.")
        st.write("First-year ROI = first-year net benefit ÷ extra setup cost × 100. Payback = extra setup cost ÷ monthly net benefit, only when both are positive. These are undiscounted estimates with constant monthly use and no tax or financing effects.")
        st.write("Validate time per accepted plan in a pilot, including data preparation and human review. Record actual integration, training and support costs. No schedule completion, disruption, reliability or safety outcome has been converted into money.")


def render_comparison_page(client: ApiClient) -> None:
    st.title("See the plan. Understand the value.")
    st.write("A late repair needs a slot, a qualified crew and a plan that keeps existing commitments.")
    st.caption("SYNTHETIC SHOWCASE · No live jobs are changed · No Gemini call")
    view = st.radio("Explore", ["Compare plans", "Estimated savings", "Data & evidence"], horizontal=True, key="comparison_view")
    if view == "Compare plans":
        render_schedule_comparison(client)
    elif view == "Estimated savings":
        render_savings(client)
    else:
        render_data_evidence()
