"""A read-only, solver-backed explanation of adding corrective work."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import ApiClient, ApiClientError


def comparison_chart(result: dict):
    records = []
    new_id = result.get("added_request", {}).get("job_id")
    for label, rows in (("Original plan", result["baseline"]), ("With new repair", result["proposed"])):
        for row in rows:
            if not row.get("scheduled_start") or not row.get("scheduled_end"):
                continue
            start = pd.Timestamp(row["scheduled_start"]).tz_convert("Asia/Singapore")
            end = pd.Timestamp(row["scheduled_end"]).tz_convert("Asia/Singapore")
            records.append({
                "Plan": label, "Work": row["name"], "Start": start, "Finish": end,
                "Label": "Door repair" if row.get("job_id") == new_id else row["name"].removeprefix("Routine ").capitalize(),
                "Type": "New repair" if row.get("job_id") == new_id else "Fixed routine work",
                "Time": f"{start:%H:%M}–{end:%H:%M} SGT",
                "Location": row.get("track", ""),
                "Crew": ", ".join(str(value) for value in row.get("assigned_engineers", [])),
            })
    frame = pd.DataFrame(records)
    fig = px.timeline(
        frame, x_start="Start", x_end="Finish", y="Plan", color="Type", text="Label",
        color_discrete_map={"Fixed routine work": "#85baf6", "New repair": "#ffc46b"},
        category_orders={"Plan": ["Original plan", "With new repair"]},
        custom_data=["Work", "Time", "Location", "Crew", "Type"],
    )
    fig.update_traces(
        textfont={"color": "#081725", "size": 13}, insidetextanchor="middle", textposition="inside",
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[4]}<br>%{customdata[1]}<br>%{customdata[2]}<br>Crew: %{customdata[3]}<extra></extra>",
    )
    window = result["window"]
    start = pd.Timestamp(window["start"]).tz_convert("Asia/Singapore")
    end = pd.Timestamp(window["end"]).tz_convert("Asia/Singapore")
    fig.update_layout(
        height=300, margin={"l": 0, "r": 12, "t": 35, "b": 20}, bargap=0.35,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#cfdded", "size": 13},
        uniformtext={"minsize": 12, "mode": "hide"},
        xaxis={"range": [start, end], "tickformat": "%H:%M", "nticks": 5,
               "title": f"{start:%d %b %Y} · Singapore time", "side": "top",
               "gridcolor": "#29415a"},
        yaxis={"title": None, "autorange": "reversed", "categoryorder": "array", "categoryarray": ["Original plan", "With new repair"]},
        legend={"title": None, "orientation": "h", "y": -0.25},
    )
    return fig, frame


def render_insertion_example(client: ApiClient) -> None:
    st.title("A late repair. One fixed night shift.")
    st.caption("WORKED EXAMPLE · Synthetic jobs and crew · Nothing is saved to your live schedule")
    st.write(
        "Think of a school timetable: lessons already agreed stay in place, and cover must fit around them. "
        "Here, approved preventive work stays fixed while a newly reported repair needs a qualified crew and a free slot."
    )
    st.info("This example starts after the fault has been assessed as suitable for planned maintenance. It does not decide whether a train can run or dispatch a response to an active incident.")
    scenario = st.radio(
        "Try a planning situation", ["fits", "no_capacity"],
        format_func=lambda value: "Repair fits before the deadline" if value == "fits" else "Deadline leaves no feasible slot",
        horizontal=True, key="demo_scenario",
    )
    if st.button("Run example", type="primary", key="demo_run"):
        with st.spinner("Checking the sample crew, fixed jobs and deadline with OR-Tools…"):
            try:
                result = client.insertion_demo(scenario)
            except ApiClientError as exc:
                st.session_state.pop("insertion_example_result", None)
                st.error(str(exc))
            else:
                st.session_state["insertion_example_result"] = result
    result = st.session_state.get("insertion_example_result")
    if not result or result.get("scenario") != scenario:
        st.caption("Run the example to see the original plan beside the solver's result. It makes no Gemini call.")
        return

    added = result.get("added_request", {})
    if result.get("status") == "success":
        st.success("The repair fits. Approved routine work stays in place.")
    elif result.get("status") == "infeasible":
        st.warning("No feasible slot. The existing plan stays unchanged.")
    else:
        st.error("The example could not be solved. No schedule was changed.")
        st.write(str(result.get("explanation", "Please retry or check the backend.")))
        return
    st.write(str(result.get("explanation", "")))
    with st.container(border=True):
        st.caption("LATE CORRECTIVE REQUEST")
        st.write(f"**{added.get('name', 'Additional repair')}** · {added.get('duration_mins', '—')} minutes")
        deadline = added.get("deadline")
        if deadline:
            st.write(f"Complete by **{pd.Timestamp(deadline).tz_convert('Asia/Singapore'):%d %b, %H:%M SGT}**")
        st.caption("Sample task durations and crew are invented for this example; they are not engineering estimates.")

    st.subheader("Before and after")
    st.caption("Blue: fixed routine work. Amber: the new repair. Empty space is time without a job in this example, not confirmed operational access.")
    figure, frame = comparison_chart(result)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False}, key="demo_comparison")
    with st.expander("Exact times and crew", expanded=True):
        st.dataframe(frame[["Plan", "Work", "Type", "Time", "Location", "Crew"]], hide_index=True, width="stretch")
    st.subheader("Use this in your own plan")
    st.write("**1. Choose the part** → **2. Confirm the repair and deadline** → **3. Generate a proposal** → **4. Review and approve**")
    st.caption("In the live workspace, approved and time-locked work is preserved. Unapproved proposals may move. If no feasible plan exists, review the constraints; the app does not silently drop work or approve a plan.")
