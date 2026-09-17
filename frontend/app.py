from __future__ import annotations

import os
import json
import re
from datetime import date, datetime, time, timedelta
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import ApiClient, ApiClientError
from data_utils import STATUS_COLORS, normalise_schedule
from asset_picker import get_asset, render_asset_picker
from insertion_visual import render_insertion_example
from location_picker import MANUAL_MODE, STATION_MODE, grouped_stations, render_location_picker
from glossary import render_glossary, glossary_tooltip
from comparison_page import render_comparison_page


APP_DIR = Path(__file__).resolve().parent
SGT = ZoneInfo("Asia/Singapore")
PRIORITIES = ["Urgent", "High", "Medium", "Low"]
STATUSES = ["Not started", "In progress", "Delay", "Error", "Done"]
MAIN_PAGES = ["Cockpit", "1 · Requests", "2 · Plan & approve", "3 · Execution"]
UTILITY_PAGES = ["Compare approaches", "Schedule example", "Glossary", "About", "Alerts", "Audit log", "AI setup"]
PAGES = [*MAIN_PAGES, *UTILITY_PAGES]
PAGE_LABELS = {
    "Cockpit": "Cockpit",
    "1 · Requests": "Requests",
    "2 · Plan & approve": "Plan & approve",
    "3 · Execution": "Execution",
    "Alerts": "Alerts",
    "Audit log": "History",
    "AI setup": "AI setup",
    "About": "About",
    "Schedule example": "Schedule example",
    "Compare approaches": "Compare approaches",
    "Glossary": "Glossary",
}
try:
    DEFAULT_API_URL = os.getenv("NGEEBULA_API_URL") or st.secrets.get(
        "NGEEBULA_API_URL", "http://127.0.0.1:8000"
    )
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    DEFAULT_API_URL = os.getenv("NGEEBULA_API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Ngeebula Rail Maintenance",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_styles() -> None:
    path = APP_DIR / "styles.css"
    if path.exists():
        st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def go_to_page(page: str) -> None:
    st.session_state["_navigation_target"] = page


def select_main_page() -> None:
    st.session_state["page"] = st.session_state["main_navigation"]


def set_feedback(kind: str, message: str, details: list[str] | None = None) -> None:
    st.session_state["feedback"] = {"kind": kind, "message": message, "details": details or []}


def clear_feedback() -> None:
    st.session_state.pop("feedback", None)


def render_feedback() -> None:
    feedback = st.session_state.get("feedback")
    if not feedback:
        return
    message = feedback["message"]
    kind = feedback.get("kind", "info")
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    elif kind == "error":
        st.error(message)
    else:
        st.info(message)
    for detail in feedback.get("details", []):
        st.warning(str(detail))
    if st.button("Dismiss message", key="dismiss_feedback", type="tertiary"):
        clear_feedback()
        st.rerun()


def to_sgt(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        return timestamp.tz_convert("Asia/Singapore")
    except (TypeError, ValueError):
        return None


def to_sgt_iso(day: date, clock: time) -> str:
    return datetime.combine(day, clock).replace(tzinfo=SGT).isoformat()


def format_datetime(value: Any, fallback: str = "Awaiting proposal") -> str:
    timestamp = to_sgt(value)
    if timestamp is None:
        return fallback
    return timestamp.strftime("%d %b %Y, %H:%M SGT")


def normal_priority(value: Any) -> str:
    text = str(value or "Medium").strip().title()
    return text if text in PRIORITIES else "Medium"


def normal_status(value: Any) -> str:
    text = str(value or "Not started").strip().replace("_", " ").lower()
    return {status.lower(): status for status in STATUSES}.get(text, str(value or "Not started"))


def engineer_names(job: dict) -> list[str]:
    names = job.get("assigned_engineers") or []
    return [str(item.get("name", "Unknown")) if isinstance(item, dict) else str(item) for item in names]


def engineer_ids(job: dict) -> list[int]:
    ids = job.get("assigned_engineer_ids") or []
    if ids:
        return [int(value) for value in ids]
    return [int(item["id"]) for item in job.get("assigned_engineers", []) if isinstance(item, dict) and item.get("id")]


def job_label(job: dict) -> str:
    return f"#{job.get('job_id', '?')} · {job.get('name', 'Untitled')} · {job.get('line', '—')} {job.get('track', '—')}"


def select_current_job(label: str, jobs: list[dict], key: str) -> dict:
    """Store only the ID in widget state; always display the latest API record."""
    lookup = {int(job["job_id"]): job for job in jobs}
    previous = st.session_state.get(key)
    if isinstance(previous, dict):
        previous = previous.get("job_id")
        st.session_state[key] = previous
    if previous is not None and previous not in lookup:
        st.session_state.pop(key, None)
    selected_id = st.selectbox(label, list(lookup), format_func=lambda value: job_label(lookup[value]), key=key)
    return lookup[selected_id]


def render_header(title: str, subtitle: str, is_live: bool | None) -> None:
    title_col, status_col = st.columns([4.5, 1.5], vertical_alignment="center")
    with title_col:
        st.title(title)
        st.caption(subtitle)
    with status_col:
        if is_live is None:
            label, detail = "Offline reference", "No API required"
        elif is_live:
            label, detail = "API snapshot", "Use Refresh snapshot for latest data"
        else:
            label, detail = "Backend offline", "Actions unavailable"
        st.caption("DATA SOURCE")
        if is_live is None:
            st.info(label)
        elif is_live:
            st.success(label)
        else:
            st.error(label)
        st.caption(detail)


def render_empty(title: str, body: str, button_label: str | None = None, target: str | None = None) -> None:
    with st.container(border=True):
        st.subheader(title)
        st.write(body)
        if button_label and target:
            st.button(button_label, type="primary", on_click=go_to_page, args=(target,))


def render_job_summary(job: dict) -> None:
    priority = normal_priority(job.get("priority"))
    status = normal_status(job.get("status"))
    crew = ", ".join(engineer_names(job)) or "Unassigned — review qualifications and roster availability"
    crew_count = len(engineer_names(job))
    crew_needed = int(job.get("engineers_needed") or 0)
    crew_shortage = max(0, crew_needed - crew_count)
    if crew_needed:
        crew_coverage = f"{crew_count} of {crew_needed} assigned"
        if crew_shortage:
            crew_coverage += f" — {crew_shortage} short"
    else:
        crew_coverage = f"{crew_count} assigned" if crew_count else "Crew size awaiting assessment"
    skills = ", ".join(str(skill) for skill in (job.get("required_skills") or [])) or "Awaiting assessment"
    approved = "Approved" if job.get("is_approved") else "Pending"
    scheduled = format_datetime(job.get("scheduled_start"))
    scheduled_end = format_datetime(job.get("scheduled_end"), "Awaiting proposal")
    deadline = format_datetime(job.get("deadline"), "Not provided")
    duration = f"{int(job.get('duration_mins') or 0)} min" if job.get("duration_mins") else "Not assessed"
    locks = []
    if job.get("time_locked"):
        locks.append("Start time locked by planner")
    if job.get("assignment_locked"):
        locks.append("Crew locked by planner")
    lock_text = " · ".join(locks) if locks else "No manual locks — solver may assign time and crew"
    with st.container(border=True, key="job_summary"):
        st.caption(f"JOB #{job.get('job_id', '—')} · {job.get('line', '—')} / {job.get('track', '—')}")
        if job.get("location_warning"):
            st.warning(job["location_warning"])
        st.subheader(str(job.get("name", "Untitled maintenance request")))
        st.write(str(job.get("description") or "No description provided."))
        summary_cols = st.columns(4)
        summary_cols[0].metric("Priority", priority)
        summary_cols[1].metric("Status", status)
        summary_cols[2].metric("Approval", approved)
        summary_cols[3].metric("Crew assigned", f"{crew_count} / {crew_needed}" if crew_needed else str(crew_count))
        timing_cols = st.columns(2)
        with timing_cols[0]:
            st.write(f"**Scheduled start:** {scheduled}")
            st.write(f"**Scheduled end:** {scheduled_end}")
        with timing_cols[1]:
            st.write(f"**Deadline:** {deadline}")
            st.write(f"**Duration:** {duration}")
        st.write(f"**Assigned crew:** {crew}")
        with st.expander("Planning requirements and locks"):
            st.write(f"**Required skills:** {skills}")
            st.write(f"**Planning locks:** {lock_text}")
    if crew_shortage:
        st.warning(
            f"Qualified crew shortage: this job needs {crew_needed} engineer(s), but {crew_count} are assigned. "
            "Review the required skills and available roster before generating or approving the schedule."
        )
        st.caption(f"Required skills: {skills}. The app will not assign staff who lack the complete required skill set.")


def render_jobs_table(jobs: list[dict]) -> None:
    rows: list[dict[str, Any]] = []
    for job in sorted(jobs, key=lambda item: (to_sgt(item.get("scheduled_start")) is None, str(item.get("scheduled_start") or ""))):
        priority = normal_priority(job.get("priority"))
        status = normal_status(job.get("status"))
        crew = ", ".join(engineer_names(job)) or "Unassigned"
        locks = []
        if job.get("time_locked"):
            locks.append("Time")
        if job.get("assignment_locked"):
            locks.append("Crew")
        rows.append(
            {
                "Job ID": job.get("job_id"),
                "Job": str(job.get("name", "Untitled")),
                "Line": str(job.get("line", "—")),
                "Track / location": str(job.get("track", "—")),
                "Start (SGT)": format_datetime(job.get("scheduled_start"), "Unscheduled"),
                "End (SGT)": format_datetime(job.get("scheduled_end"), "Unscheduled"),
                "Deadline (SGT)": format_datetime(job.get("deadline"), "Not provided"),
                "Duration (min)": int(job.get("duration_mins") or 0) or None,
                "Priority": priority,
                "Assigned crew": crew,
                "Status": status,
                "Approved": bool(job.get("is_approved")),
                "Manual locks": ", ".join(locks) or "None",
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Job ID": st.column_config.NumberColumn(format="#%d"),
            "Approved": st.column_config.CheckboxColumn(),
            "Job": st.column_config.TextColumn(width="medium"),
            "Assigned crew": st.column_config.TextColumn(width="large"),
        },
    )


def filter_jobs(jobs: list[dict], key_prefix: str) -> list[dict]:
    """Apply lightweight review filters without changing the underlying job list."""
    query = st.text_input(
        "Search jobs",
        key=f"{key_prefix}_search",
        placeholder="Job title, job ID, or track / location",
    ).strip().casefold()
    filter_cols = st.columns(3)
    lines = sorted({str(job.get("line", "Unknown")) for job in jobs})
    statuses = [status for status in STATUSES if any(normal_status(job.get("status")) == status for job in jobs)]
    priorities = [priority for priority in PRIORITIES if any(normal_priority(job.get("priority")) == priority for job in jobs)]
    with filter_cols[0]:
        line = st.selectbox("Line", ["All lines", *lines], key=f"{key_prefix}_line")
    with filter_cols[1]:
        status = st.selectbox("Status", ["All statuses", *statuses], key=f"{key_prefix}_status")
    with filter_cols[2]:
        priority = st.selectbox("Priority", ["All priorities", *priorities], key=f"{key_prefix}_priority")
    return [
        job
        for job in jobs
        if (
            not query
            or query in str(job.get("name", "")).casefold()
            or query in str(job.get("job_id", "")).casefold()
            or query in str(job.get("track", "")).casefold()
        )
        and (line == "All lines" or str(job.get("line")) == line)
        and (status == "All statuses" or normal_status(job.get("status")) == status)
        and (priority == "All priorities" or normal_priority(job.get("priority")) == priority)
    ]


def build_timeline(jobs: list[dict]) -> Any:
    schedule = normalise_schedule(jobs)
    schedule["status"] = schedule["status"].map(normal_status)
    schedule["priority"] = schedule["priority"].map(normal_priority)
    schedule["start_label"] = schedule["scheduled_start"].map(lambda value: value.strftime("%d %b %Y, %H:%M SGT"))
    schedule["end_label"] = schedule["scheduled_end"].map(lambda value: value.strftime("%d %b %Y, %H:%M SGT"))
    schedule["duration_label"] = (
        (schedule["scheduled_end"] - schedule["scheduled_start"]).dt.total_seconds().div(60).round().astype(int).astype(str)
        + " min"
    )
    category_order = list(dict.fromkeys(schedule["track_label"].tolist()))[::-1]
    axis_labels = {}
    for row in schedule.to_dict("records"):
        line = str(row["line"])
        line_code = line.rsplit("(", 1)[-1].rstrip(")") if "(" in line else line
        track = str(row["track"])
        short_track = track if len(track) <= 22 else track[:21] + "…"
        axis_labels[row["track_label"]] = f"{escape(line_code)}<br>{escape(short_track)}"
    fig = px.timeline(
        schedule,
        x_start="scheduled_start",
        x_end="scheduled_end",
        y="track_label",
        color="status",
        text="name",
        color_discrete_map=STATUS_COLORS,
        category_orders={"track_label": category_order, "status": STATUSES},
        custom_data=["name", "line", "track", "priority", "engineer_text", "start_label", "end_label", "duration_label"],
    )
    fig.update_traces(
        textposition="inside",
        insidetextanchor="start",
        textfont={"color": "#071422", "size": 12},
        width=0.42,
        marker_line_width=0,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Line: %{customdata[1]}<br>Track: %{customdata[2]}"
            "<br>Priority: %{customdata[3]}<br>Crew: %{customdata[4]}"
            "<br>Start: %{customdata[5]}<br>End: %{customdata[6]}<br>Duration: %{customdata[7]}<extra></extra>"
        ),
    )
    earliest = schedule["scheduled_start"].min()
    latest = schedule["scheduled_end"].max()
    window_day = earliest.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
    engineering_start = window_day + timedelta(minutes=30)
    engineering_end = window_day + timedelta(hours=5)
    same_engineering_window = (
        latest.date() == earliest.date()
        and earliest.to_pydatetime() >= engineering_start
        and latest.to_pydatetime() <= engineering_end
    )
    chart_start = engineering_start if same_engineering_window else earliest.to_pydatetime()
    chart_end = engineering_end if same_engineering_window else latest.to_pydatetime()
    fig.update_layout(
        height=max(290, 70 * len(category_order) + 160),
        uniformtext={"minsize": 11, "mode": "hide"},
        margin={"l": 12, "r": 22, "t": 80, "b": 50},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0B1C2D",
        font={"family": "Inter, Segoe UI, sans-serif", "color": "#C5D4E6", "size": 12},
        hoverlabel={"bgcolor": "#12283D", "font_color": "#F4F7FB", "bordercolor": "#36516C"},
        legend={"orientation": "h", "yanchor": "top", "y": -0.10, "xanchor": "left", "x": 0, "title": None},
        xaxis={
            "range": [chart_start, chart_end],
            "tickformat": "%H:%M" if same_engineering_window else "%d %b<br>%H:%M",
            "nticks": 4,
            "tickangle": 0,
            "showgrid": True,
            "gridcolor": "rgba(109,139,168,.20)",
            "zeroline": False,
            "title": f"{earliest.strftime('%d %b %Y')} · SGT" if same_engineering_window else "Time (SGT)",
            "side": "top",
        },
        yaxis={"title": None, "showgrid": True, "gridcolor": "rgba(109,139,168,.15)", "automargin": True,
               "tickmode": "array", "tickvals": category_order, "ticktext": [axis_labels[label] for label in category_order]},
        bargap=0.32,
    )
    return fig


def engineer_format(engineer_id: int, engineers_by_id: dict[int, dict]) -> str:
    engineer = engineers_by_id.get(int(engineer_id), {})
    availability = "available" if engineer.get("is_available", False) else "unavailable"
    skills = ", ".join(engineer.get("skills") or []) or "skills not listed"
    return f"{engineer.get('name', engineer_id)} · {availability} · {skills}"


def next_window_end(now: datetime | None = None) -> datetime:
    current = now or datetime.now(SGT)
    window_start = current.replace(hour=0, minute=30, second=0, microsecond=0)
    if current > window_start:
        window_start += timedelta(days=1)
    return window_start + timedelta(hours=4, minutes=30)


def derive_request_title(description: str) -> str:
    words = description.strip().replace("\n", " ").split()
    title = " ".join(words[:8]).rstrip(".,;:")
    return (title[:77] + "…") if len(title) > 78 else title


def reset_request_wizard() -> None:
    for state_key in list(st.session_state):
        if state_key.startswith("wizard_"):
            st.session_state.pop(state_key, None)
    st.session_state["request_draft"] = {}
    st.session_state["wizard_step"] = 1


def start_request_wizard() -> None:
    reset_request_wizard()
    st.session_state["request_mode"] = "wizard"


def sync_request_draft(**field_keys: str) -> None:
    draft = st.session_state.setdefault("request_draft", {})
    for field, state_key in field_keys.items():
        if state_key in st.session_state:
            draft[field] = st.session_state[state_key]


def sync_custom_deadline() -> None:
    day = st.session_state.get("wizard_deadline_date")
    clock = st.session_state.get("wizard_deadline_time")
    if day and clock:
        st.session_state.setdefault("request_draft", {})["deadline"] = datetime.combine(day, clock).replace(tzinfo=SGT).isoformat()


def render_wizard_progress(step: int) -> None:
    labels = ["Choose the repair", "Where & when", "Review"]
    columns = st.columns(3)
    for index, label in enumerate(labels, start=1):
        prefix = "Current" if index == step else "Complete" if index < step else "Next"
        columns[index - 1].caption(f"{index}. {label} · {prefix}")
    st.progress(step / 3)


def render_request_wizard(client: ApiClient, catalog: dict, engineers: list[dict], planner: str) -> None:
    step = int(st.session_state.get("wizard_step", 1))
    draft = st.session_state.setdefault("request_draft", {})
    st.title("Add maintenance work")
    render_wizard_progress(step)

    if step == 1:
        asset_id = draft.get("asset_id")
        if not asset_id or st.session_state.get("wizard_change_asset"):
            st.write("**What needs attention?** Choose a part, then confirm the repair.")
            st.caption("For work assessed as suitable for a planned maintenance window. Active incidents or uncertain safety conditions need operational review first.")
            selected_asset = render_asset_picker(asset_id)
            if st.button("Describe another issue", key="wizard_other_asset"):
                selected_asset = "other"
            if selected_asset:
                asset = get_asset(selected_asset)
                draft["asset_id"] = selected_asset
                if selected_asset != asset_id:
                    draft["description"] = asset["description"] if asset else ""
                    draft["title"] = ""
                    for field in ("wizard_description", "wizard_title"):
                        st.session_state.pop(field, None)
                    # Requirements from the previous asset must not follow a new choice.
                    for field in ("use_catalog", "category", "activity", "manual_work", "skills", "assigned_ids", "assignment_mode"):
                        draft.pop(field, None)
                    for field in ("wizard_use_catalog", "wizard_category", "wizard_activity", "wizard_manual_work", "wizard_skills", "wizard_assigned_ids", "wizard_assignment_mode"):
                        st.session_state.pop(field, None)
                    if asset:
                        selected_entry = next((item for item in catalog.get("activities", [])
                                               if item.get("category") == asset["category"] and item.get("activity") == asset["activity"]), {})
                        draft["skills"] = list(selected_entry.get("required_skills", []))
                st.session_state["wizard_change_asset"] = False
                st.rerun()
            if st.button("Cancel", key="wizard_cancel_picker"):
                reset_request_wizard()
                st.session_state["request_mode"] = "queue"
                st.rerun()
            return
        asset = get_asset(asset_id)
        if asset:
            with st.container(border=True):
                st.caption("SELECTED REPAIR")
                st.subheader(asset["label"])
                st.write(f"**{asset['activity']}**")
                st.caption("This catalog activity will be preserved. Add the observed symptoms below; choose another issue if this repair is not the right match.")
        if st.button("Change asset", key="wizard_change_asset_button", type="tertiary"):
            st.session_state["wizard_change_asset"] = True
            st.rerun()
        st.write("Confirm what needs fixing. You will review the location and deadline next.")
        description = st.text_area(
            "What work is needed? *",
            value=str(draft.get("description", "")),
            key="wizard_description",
            height=100,
            placeholder="Example: Replace the damaged fibre-optic cable beside the northbound track at Bishan.",
            on_change=sync_request_draft,
            kwargs={"description": "wizard_description"},
        )
        title = st.text_input(
            "Short title (optional)",
            value=str(draft.get("title", "")),
            key="wizard_title",
            help="Leave blank and a short title will be derived from your description.",
            on_change=sync_request_draft,
            kwargs={"title": "wizard_title"},
        )
        action_cols = st.columns([1, 1, 4])
        with action_cols[0]:
            if st.button("Cancel", key="wizard_cancel_1"):
                reset_request_wizard()
                st.session_state["request_mode"] = "queue"
                st.rerun()
        with action_cols[1]:
            if st.button("Next: where & when", type="primary", key="wizard_next_1"):
                if not description.strip():
                    st.error("Describe the maintenance work before continuing.")
                else:
                    draft.update(description=description.strip(), title=title.strip())
                    st.session_state["wizard_step"] = 2
                    st.rerun()
        return

    default_deadline = next_window_end()
    if step == 2:
        st.write("Choose where the work will happen. We will fill in the line when the station has one match.")
        location = render_location_picker(catalog, draft, prefix="wizard")
        draft["station_code"] = location.get("station_code")
        line, track = location.get("line") or "", location.get("track") or ""
        deadline_options = ["next_window", "custom"]
        deadline_choice = st.radio(
            "Completion deadline *",
            deadline_options,
            index=deadline_options.index(str(draft.get("deadline_choice", "next_window"))),
            format_func=lambda value: (
                f"End of the next engineering window — {default_deadline.strftime('%d %b %Y, %H:%M SGT')}"
                if value == "next_window"
                else "Choose a custom deadline"
            ),
            key="wizard_deadline_choice",
            on_change=sync_request_draft,
            kwargs={"deadline_choice": "wizard_deadline_choice"},
        )
        if deadline_choice == "custom":
            saved_deadline = to_sgt(draft.get("deadline")) or pd.Timestamp(default_deadline)
            deadline_cols = st.columns(2)
            with deadline_cols[0]:
                deadline_date = st.date_input(
                    "Deadline date (SGT) *", value=saved_deadline.date(), key="wizard_deadline_date",
                    on_change=sync_custom_deadline,
                )
            with deadline_cols[1]:
                deadline_time = st.time_input(
                    "Deadline time (SGT) *",
                    value=saved_deadline.time().replace(second=0, microsecond=0),
                    key="wizard_deadline_time",
                    on_change=sync_custom_deadline,
                )
            deadline = datetime.combine(deadline_date, deadline_time).replace(tzinfo=SGT)
        else:
            deadline = default_deadline
        action_cols = st.columns([1, 1, 4])
        with action_cols[0]:
            if st.button("Back", key="wizard_back_2"):
                draft.update(
                    line=line,
                    track=track,
                    deadline_choice=deadline_choice,
                    deadline=deadline.isoformat(),
                )
                st.session_state["wizard_step"] = 1
                st.rerun()
        with action_cols[1]:
            if st.button("Next: review", type="primary", key="wizard_next_2"):
                if location.get("error"):
                    st.error(location["error"])
                elif deadline <= datetime.now(SGT):
                    st.error("Choose a deadline in the future.")
                else:
                    draft.update(
                        line=line,
                        track=track.strip(),
                        deadline_choice=deadline_choice,
                        deadline=deadline.isoformat(),
                    )
                    st.session_state["wizard_step"] = 3
                    st.rerun()
        return

    chosen_asset = get_asset(draft.get("asset_id"))
    title = str(draft.get("title") or (chosen_asset["activity"] if chosen_asset else derive_request_title(str(draft.get("description", "")))))
    deadline_value = str(draft.get("deadline") or default_deadline.isoformat())
    with st.container(border=True):
        st.caption("REQUEST TO CREATE")
        st.subheader(title or "Untitled maintenance work")
        st.write(str(draft.get("description", "")))
        chosen_asset = get_asset(draft.get("asset_id"))
        if chosen_asset:
            st.write(f"**Selected catalog repair:** {chosen_asset['activity']}")
        review_cols = st.columns(2)
        with review_cols[0]:
            st.caption("LINE AND LOCATION")
            st.write(f"**{draft.get('line', '—')} · {draft.get('track', '—')}**")
        with review_cols[1]:
            st.caption("COMPLETION DEADLINE")
            st.write(f"**{format_datetime(deadline_value)}**")
        st.info(
            "After creation, the selected repair supplies catalog requirements; the backend checks priority and qualified crew. Review duration and staffing before planning."
            if chosen_asset else
            "After creation, the backend will assess the catalog match, priority, duration, required skills, and crew size. You will review those results before scheduling or approval."
        )

    activities = [activity for activity in catalog.get("activities", []) if isinstance(activity, dict)]
    catalog_skills: list[str] | None = None
    for state_key, default in {
        "wizard_use_catalog": bool(draft.get("use_catalog", False)),
        "wizard_priority": str(draft.get("priority", "Automatic")),
        "wizard_manual_work": bool(draft.get("manual_work", False)),
        "wizard_duration": int(draft.get("duration", 60)),
        "wizard_skills": list(draft.get("skills", [])),
        "wizard_engineers_needed": int(draft.get("engineers_needed", 2)),
        "wizard_assignment_mode": str(draft.get("assignment_mode", "Automatic — match qualified available engineers")),
        "wizard_assigned_ids": list(draft.get("assigned_ids", [])),
    }.items():
        st.session_state.setdefault(state_key, default)
    use_catalog_skills = False
    if not chosen_asset:
        with st.expander("Optional: use skills from a catalog activity"):
            st.caption("This overrides required skills only; the backend still assesses the request's final catalog classification.")
            use_catalog_skills = st.checkbox(
                "Use catalog skills as manual requirements", key="wizard_use_catalog",
                disabled=chosen_asset is not None,
                on_change=sync_request_draft, kwargs={"use_catalog": "wizard_use_catalog"},
            )
            categories = sorted({str(activity.get("category", "Maintenance")) for activity in activities})
            if use_catalog_skills and categories:
                saved_category = str(draft.get("category", categories[0]))
                category = st.selectbox(
                    "Category", categories,
                    index=categories.index(saved_category) if saved_category in categories else 0,
                    key="wizard_category",
                    on_change=sync_request_draft,
                    kwargs={"category": "wizard_category"},
                )
                category_activities = [activity for activity in activities if str(activity.get("category")) == category]
                activity_names = [str(item.get("activity", "General work")) for item in category_activities]
                saved_activity = str(draft.get("activity", activity_names[0]))
                selected_name = st.selectbox(
                    "Activity", activity_names,
                    index=activity_names.index(saved_activity) if saved_activity in activity_names else 0,
                    key="wizard_activity",
                    on_change=sync_request_draft,
                    kwargs={"activity": "wizard_activity"},
                )
                selected_activity = next(item for item in category_activities if str(item.get("activity", "General work")) == selected_name)
                catalog_skills = [str(skill) for skill in selected_activity.get("required_skills", [])]
                qualified = int(selected_activity.get("available_fully_qualified_engineers") or 0)
                st.write(f"**Required skills:** {', '.join(catalog_skills) or 'None listed'}")
                st.caption(f"{qualified} available engineer(s) currently possess every listed skill.")

    all_skills = list(
        dict.fromkeys(
            [str(skill) for skill in catalog.get("skills", [])]
            + [str(skill) for engineer in engineers for skill in (engineer.get("skills") or [])]
        )
    )
    engineer_choices = [int(engineer["id"]) for engineer in engineers if engineer.get("id") is not None]
    engineers_by_id = {int(engineer["id"]): engineer for engineer in engineers if engineer.get("id") is not None}
    with st.expander("Optional: override planning defaults"):
        priority_choice = st.selectbox(
            "Priority", ["Automatic", *PRIORITIES], key="wizard_priority",
            on_change=sync_request_draft, kwargs={"priority": "wizard_priority"},
        )
        manual_work = st.checkbox(
            "Set duration and crew size" if chosen_asset else "Set duration, skills, and crew size", key="wizard_manual_work",
            on_change=sync_request_draft, kwargs={"manual_work": "wizard_manual_work"},
        )
        duration = st.number_input(
            "Estimated duration (minutes)", min_value=15, max_value=270, step=15,
            key="wizard_duration", disabled=not manual_work,
            on_change=sync_request_draft, kwargs={"duration": "wizard_duration"},
        )
        required_skills = st.multiselect(
            "Required skills", all_skills, key="wizard_skills", disabled=not manual_work or chosen_asset is not None,
            on_change=sync_request_draft, kwargs={"skills": "wizard_skills"},
        )
        if chosen_asset:
            st.caption("Skills come from the selected repair. The backend requires the complete catalog skill set.")
        engineers_needed = st.number_input(
            "Engineers needed", min_value=1, max_value=10, step=1,
            key="wizard_engineers_needed", disabled=not manual_work,
            on_change=sync_request_draft, kwargs={"engineers_needed": "wizard_engineers_needed"},
        )
        assignment_mode = st.radio(
            "Crew assignment",
            ["Automatic — match qualified available engineers", "Manual — choose engineers"],
            key="wizard_assignment_mode",
            on_change=sync_request_draft,
            kwargs={"assignment_mode": "wizard_assignment_mode"},
        )
        assigned_ids = st.multiselect(
            "Assigned engineers",
            engineer_choices,
            format_func=lambda value: engineer_format(value, engineers_by_id),
            key="wizard_assigned_ids",
            disabled=assignment_mode.startswith("Automatic"),
            on_change=sync_request_draft,
            kwargs={"assigned_ids": "wizard_assigned_ids"},
        )

    action_cols = st.columns([1, 1, 4])
    with action_cols[0]:
        if st.button("Back", key="wizard_back_3"):
            draft.update(
                use_catalog=use_catalog_skills,
                category=st.session_state.get("wizard_category"),
                activity=st.session_state.get("wizard_activity"),
                priority=priority_choice,
                manual_work=manual_work,
                duration=int(duration),
                skills=list(required_skills),
                engineers_needed=int(engineers_needed),
                assignment_mode=assignment_mode,
                assigned_ids=list(assigned_ids),
            )
            st.session_state["wizard_step"] = 2
            st.rerun()
    with action_cols[1]:
        create = st.button("Create request", type="primary", key="wizard_create")
    if not create:
        return
    if assignment_mode.startswith("Manual") and not assigned_ids:
        st.error("Choose at least one engineer or use automatic crew assignment.")
        return
    payload: dict[str, Any] = {
        "name": title,
        "description": str(draft.get("description", "")),
        "line": str(draft.get("line", "")),
        "track": str(draft.get("track", "")),
        "deadline": deadline_value,
        "created_by": planner,
    }
    selected_asset = get_asset(draft.get("asset_id"))
    if selected_asset:
        payload.update(catalog_category=selected_asset["category"], catalog_activity=selected_asset["activity"])
    if draft.get("station_code"):
        payload["station_code"] = draft["station_code"]
    if priority_choice != "Automatic":
        payload["priority"] = priority_choice
    if manual_work:
        payload.update(
            duration_mins=int(duration),
            required_skills=required_skills,
            engineers_needed=int(engineers_needed),
        )
    elif catalog_skills is not None:
        payload["required_skills"] = catalog_skills
    if assignment_mode.startswith("Manual"):
        payload["assigned_engineer_ids"] = assigned_ids
    with st.spinner("Assessing the request and checking qualified crew…"):
        try:
            created = client.create_job(payload)
        except ApiClientError as exc:
            message = f"Request was not created. {exc} Your draft is still available."
            set_feedback("error", message)
            st.error(message)
            return
    created_job = created.get("job") if isinstance(created.get("job"), dict) else created
    created_id = int(created_job.get("job_id"))
    conflict = created.get("assignment_conflict") or created_job.get("assignment_conflict")
    reset_request_wizard()
    st.session_state["request_mode"] = "created"
    st.session_state["created_job_id"] = created_id
    if conflict:
        set_feedback("warning", f"Request #{created_id} was created but needs crew review.", [str(conflict)])
    else:
        set_feedback("success", f"Request #{created_id} created. Review the assessed defaults, then plan it.")
    st.rerun()


def render_override_editor(client: ApiClient, job: dict, engineers: list[dict], catalog: dict, planner: str, prefix: str) -> None:
    job_id = int(job["job_id"])
    # Streamlit retains explicit widget values across reruns. Reset this editor
    # only when its saved API record changes, never while the user is typing.
    snapshot_key = f"{prefix}_saved_record_{job_id}"
    snapshot = json.dumps(job, sort_keys=True, default=str)
    if st.session_state.get(snapshot_key) != snapshot:
        for state_key in list(st.session_state):
            if state_key.startswith(f"{prefix}_") and state_key.endswith(f"_{job_id}"):
                st.session_state.pop(state_key, None)
        st.session_state[snapshot_key] = snapshot
    engineers_by_id = {int(item["id"]): item for item in engineers if item.get("id") is not None}
    choices = list(engineers_by_id)
    skill_choices = list(
        dict.fromkeys(
            [*(catalog.get("skills") or []), *(job.get("required_skills") or [])]
            + [skill for engineer in engineers for skill in (engineer.get("skills") or [])]
        )
    )
    current_start = to_sgt(job.get("scheduled_start")) or pd.Timestamp(datetime.now(SGT).replace(second=0, microsecond=0))
    st.subheader("Planner overrides")
    if normal_status(job.get("status")) != "Not started":
        st.info("Overrides are available only while a job is Not started. Use the execution lifecycle to complete or return active work for replanning.")
        return
    st.caption("Select only the fields you intend to change. Every override requires an accountable planner and reason.")

    priority_on = st.checkbox("Change priority", key=f"{prefix}_priority_on_{job_id}")
    priority = st.selectbox(
        "Priority", PRIORITIES, index=PRIORITIES.index(normal_priority(job.get("priority"))),
        disabled=not priority_on, key=f"{prefix}_priority_{job_id}"
    )
    crew_on = st.checkbox("Change assigned crew", key=f"{prefix}_crew_on_{job_id}")
    selected_crew = st.multiselect(
        "Assigned engineers",
        choices,
        default=[value for value in engineer_ids(job) if value in choices],
        format_func=lambda value: engineer_format(value, engineers_by_id),
        disabled=not crew_on,
        key=f"{prefix}_crew_{job_id}",
    )
    start_on = st.checkbox("Change scheduled start", key=f"{prefix}_start_on_{job_id}")
    start_cols = st.columns(2)
    with start_cols[0]:
        start_date = st.date_input("Start date (SGT)", value=current_start.date(), disabled=not start_on, key=f"{prefix}_date_{job_id}")
    with start_cols[1]:
        start_time = st.time_input(
            "Start time (SGT)", value=current_start.time().replace(second=0, microsecond=0), disabled=not start_on,
            key=f"{prefix}_time_{job_id}"
        )
    work_on = st.checkbox("Change work requirements", key=f"{prefix}_work_on_{job_id}")
    work_cols = st.columns(2)
    with work_cols[0]:
        duration = st.number_input(
            "Duration (minutes)", 15, 270, int(job.get("duration_mins") or 60), 15,
            disabled=not work_on, key=f"{prefix}_duration_{job_id}"
        )
        engineers_needed = st.number_input(
            "Engineers needed", 1, 10, int(job.get("engineers_needed") or 2), 1,
            disabled=not work_on, key=f"{prefix}_needed_{job_id}"
        )
    with work_cols[1]:
        requirements = st.multiselect(
            "Required skills", skill_choices, default=job.get("required_skills") or [],
            disabled=not work_on, key=f"{prefix}_skills_{job_id}"
        )
    reason = st.text_area(
        "Reason for override *", key=f"{prefix}_reason_{job_id}",
        placeholder="State the operational evidence or constraint behind this change.", height=80,
    )
    changed = priority_on or crew_on or start_on or work_on
    if st.button("Save selected overrides", type="primary", disabled=not changed, key=f"{prefix}_save_{job_id}"):
        if not reason.strip():
            st.error("Enter a reason for the override. No changes were sent.")
            return
        payload: dict[str, Any] = {"updated_by": planner, "reason": reason.strip()}
        if priority_on:
            payload["priority"] = priority
        if crew_on:
            payload["assigned_engineer_ids"] = selected_crew
        if start_on:
            payload["scheduled_start"] = to_sgt_iso(start_date, start_time)
        if work_on:
            payload.update(duration_mins=int(duration), required_skills=requirements, engineers_needed=int(engineers_needed))
        try:
            client.update_job(job_id, payload)
        except ApiClientError as exc:
            message = f"Override was not saved. {exc} Your selections are still here."
            set_feedback("error", message)
            st.error(message)
            return
        set_feedback(
            "success",
            f"Overrides saved for job #{job_id}. The saved plan requires approval. Manual crew and start-time locks are preserved by future solver runs.",
        )
        st.rerun()


def render_delete_control(client: ApiClient, job: dict, planner: str) -> None:
    job_id = int(job["job_id"])
    with st.expander("Delete this request"):
        current_status = normal_status(job.get("status"))
        if current_status != "Not started":
            st.info(
                f"Deletion is unavailable while this job is {current_status}. Policy allows deletion only for Not started work; "
                "active and completed records remain in the audit history."
            )
            return
        st.warning("Deletion removes this request from planning and execution. The backend records who deleted it and why.")
        reason = st.text_area("Reason for deletion *", key=f"delete_reason_{job_id}", height=80)
        confirmed = st.checkbox(
            f"I confirm that job #{job_id} should be deleted", key=f"delete_confirm_{job_id}"
        )
        if st.button(
            "Delete request", type="secondary", disabled=not (confirmed and reason.strip()), key=f"delete_button_{job_id}"
        ):
            try:
                client.delete_job(job_id, {"deleted_by": planner, "reason": reason.strip()})
            except ApiClientError as exc:
                message = f"Request was not deleted. {exc}"
                set_feedback("error", message)
                st.error(message)
                return
            set_feedback("success", f"Job #{job_id} was deleted and the reason was recorded.")
            st.rerun()


def job_attention_reason(job: dict) -> str | None:
    if job.get("location_warning"):
        return "Check station and rail line"
    status = normal_status(job.get("status"))
    if status in {"Delay", "Error"}:
        return f"Execution status: {status}"
    assigned = len(engineer_names(job))
    needed = int(job.get("engineers_needed") or 1)
    if status == "Not started" and assigned < needed:
        return f"Crew shortage: {assigned} of {needed} assigned"
    conflict = job.get("assignment_conflict")
    if isinstance(conflict, list) and conflict:
        return "; ".join(str(item) for item in conflict)
    if conflict:
        return str(conflict)
    return None


def cockpit_queues(jobs: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    attention: list[dict] = []
    planning: list[dict] = []
    approval: list[dict] = []
    for job in jobs:
        if normal_status(job.get("status")) == "Done":
            continue
        reason = job_attention_reason(job)
        if reason:
            attention.append({**job, "_next_reason": reason, "_next_action": "Review request"})
        elif not (job.get("scheduled_start") and job.get("scheduled_end")):
            planning.append({**job, "_next_reason": "No proposed time", "_next_action": "Plan work"})
        elif not job.get("is_approved"):
            approval.append({**job, "_next_reason": "Proposed plan awaits approval", "_next_action": "Review approval"})
    priority_rank = {name: index for index, name in enumerate(PRIORITIES)}
    sort_key = lambda item: (
        priority_rank.get(normal_priority(item.get("priority")), 2),
        to_sgt(item.get("deadline")) or pd.Timestamp.max.tz_localize("UTC"),
    )
    return tuple(sorted(queue, key=sort_key) for queue in (attention, planning, approval))  # type: ignore[return-value]


def render_cockpit(jobs: list[dict], is_live: bool) -> None:
    render_header("Maintenance cockpit", "Keep routine work on track. Fit new repairs around approved commitments.", is_live)
    action_cols = st.columns([1, 1.5, 2])
    with action_cols[0]:
        if st.button("Add work", type="primary", key="cockpit_add_work", width="stretch"):
            start_request_wizard()
            go_to_page("1 · Requests")
            st.rerun()
    with action_cols[1]:
        if st.button("See how a repair fits", key="cockpit_example", width="stretch"):
            go_to_page("Schedule example")
            st.rerun()
    with action_cols[2]:
        if st.button("Compare approaches & savings", key="cockpit_compare", width="stretch"):
            go_to_page("Compare approaches")
            st.rerun()
    st.caption("Choose a part → Confirm the repair → Find a slot → Review and approve")
    attention, planning, approval = cockpit_queues(jobs)
    metrics = st.columns(3)
    metrics[0].metric("Needs attention", len(attention))
    metrics[1].metric("Needs planning", len(planning))
    metrics[2].metric("Awaiting approval", len(approval))

    actions_tab, timeline_tab = st.tabs(["Next actions", "Overnight timeline"])
    with actions_tab:
        next_actions = [*attention, *planning, *approval]
        if not next_actions:
            if jobs:
                st.success("No planning or approval decisions are waiting.")
                st.caption("Open Execution to follow approved work in the field.")
            else:
                render_empty("No maintenance requests", "Add work when a maintenance need is identified.")
        else:
            st.subheader(f"Chief's queue ({len(next_actions)})")
            st.caption("Exceptions come first, followed by unplanned work and plans awaiting approval.")
            rows = [
                {
                    "Request": f"#{int(job['job_id'])} · {job.get('name', 'Untitled')}",
                    "Why it needs review": job.get("_next_reason"),
                    "Next action": job.get("_next_action"),
                }
                for job in next_actions[:8]
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            selected = select_current_job("Work item", next_actions, key="cockpit_next_job")
            st.write(f"**Why it needs review:** {selected.get('_next_reason')}")
            st.caption(
                f"{normal_priority(selected.get('priority'))} priority · "
                f"{selected.get('line', '—')} · {selected.get('track', '—')} · "
                f"deadline {format_datetime(selected.get('deadline'), 'not set')}"
            )
            action = str(selected.get("_next_action"))
            destination = "1 · Requests" if action == "Review request" else "2 · Plan & approve"
            if st.button(action, type="primary", key="cockpit_open_action"):
                st.session_state["plan_default_tab"] = "Review & approve" if action == "Review approval" else "Schedule & issues"
                selected_key = "request_review_job" if destination == "1 · Requests" else "plan_selected_job"
                st.session_state[selected_key] = int(selected["job_id"])
                st.session_state["request_mode"] = "queue"
                go_to_page(destination)
                st.rerun()
            if len(next_actions) > 8:
                st.caption(f"{len(next_actions) - 8} more item(s) are available in Requests and Plan & approve.")
    with timeline_tab:
        scheduled = [job for job in jobs if job.get("scheduled_start") and job.get("scheduled_end")]
        if scheduled:
            st.caption("Full 00:30–05:00 SGT engineering window. Hover for exact timing, priority, and crew.")
            st.plotly_chart(build_timeline(scheduled), width="stretch", config={"displayModeBar": False})
        else:
            st.info("No proposed work is on the timeline yet. Open Plan & approve to generate a schedule.")


def render_location_correction(client: ApiClient, job: dict, catalog: dict, planner: str) -> None:
    if normal_status(job.get("status")) != "Not started":
        return
    job_id = int(job["job_id"])
    prefix = f"location_edit_{job_id}"
    snapshot = (job.get("line"), job.get("track"), job.get("station_code"))
    state_key = f"{prefix}_draft"
    if st.session_state.get(f"{prefix}_snapshot") != snapshot:
        for key in list(st.session_state):
            if key.startswith(f"{prefix}_"):
                del st.session_state[key]
        grouped = grouped_stations(catalog.get("stations", []))
        track = str(job.get("track") or "")
        station_name = job.get("station_name")
        if station_name not in grouped:
            station_name = next((
                name for name in sorted(grouped, key=len, reverse=True)
                if any(item["code"] == job.get("station_code") for item in grouped[name])
                or re.search(rf"(?<!\w){re.escape(name)}(?!\w)", track, re.I)
            ), None)
        draft: dict[str, Any] = {
            "location_mode": STATION_MODE if station_name else MANUAL_MODE,
            "manual_line": job.get("line"), "manual_track": track,
        }
        if station_name:
            serving_lines = [item["line"] for item in grouped[station_name]]
            detail = track
            for item in grouped[station_name]:
                detail = re.sub(rf"^\s*{re.escape(item['code'])}\b\s*", "", detail, flags=re.I)
            detail = re.sub(rf"^\s*{re.escape(station_name)}\b\s*", "", detail, flags=re.I).lstrip(" ·,/:-")
            draft.update(station_name=station_name,
                         station_line=job.get("line") if job.get("line") in serving_lines else None,
                         location_detail=detail)
        st.session_state[state_key] = draft
        st.session_state[f"{prefix}_snapshot"] = snapshot
    with st.expander("Correct location", expanded=bool(job.get("location_warning"))):
        st.caption(f"Currently saved: {job.get('line')} / {job.get('track')}")
        location = render_location_picker(catalog, st.session_state[state_key], prefix=prefix)
        reason = st.text_area("Reason for location correction *", key=f"{prefix}_reason",
                              placeholder="Explain the location correction for the audit log.", height=80)
        st.caption("Saving clears the current proposal, approval and fixed start time. Generate a new proposal afterwards.")
        changed = (location["line"], location["track"], location["station_code"]) != snapshot
        if st.button("Save corrected location", key=f"{prefix}_save", type="primary",
                     disabled=bool(location["error"]) or not changed):
            if not reason.strip():
                st.error("Enter a reason for the location correction. No changes were sent.")
                return
            try:
                client.update_job(job_id, {"updated_by": planner, "reason": reason.strip(),
                                          "line": location["line"], "track": location["track"],
                                          "station_code": location["station_code"]})
            except ApiClientError as exc:
                st.error(f"Location was not saved. {exc} Your selections are still here.")
                return
            set_feedback("success", f"Location corrected for job #{job_id}. Open Plan & approve to generate a new proposal.")
            st.rerun()


def render_requests(client: ApiClient, jobs: list[dict], engineers: list[dict], catalog: dict, planner: str, is_live: bool) -> None:
    mode = st.session_state.get("request_mode", "queue")
    if mode == "wizard":
        render_request_wizard(client, catalog, engineers, planner)
        return
    render_header("Requests", "Review assessed work or add a new maintenance request.", is_live)
    if mode != "wizard" and st.button("Add work", type="primary", key="add_work"):
        start_request_wizard()
        st.rerun()
    if mode == "created":
        created_id = st.session_state.get("created_job_id")
        created = next((job for job in jobs if job.get("job_id") == created_id), None)
        if created:
            st.subheader("Request created")
            render_job_summary(created)
            render_location_correction(client, created, catalog, planner)
            if len(engineer_names(created)) < int(created.get("engineers_needed") or 1):
                if st.button("Review crew and requirements", key="created_review_crew"):
                    st.session_state["request_mode"] = "queue"
                    st.session_state["request_review_job"] = int(created_id)
                    st.session_state["request_edit_open"] = True
                    st.rerun()
            next_cols = st.columns([1.2, 1, 4])
            with next_cols[0]:
                if st.button("Open planning", type="primary", key="created_open_plan"):
                    st.session_state["plan_selected_job"] = int(created_id)
                    st.session_state["request_mode"] = "queue"
                    go_to_page("2 · Plan & approve")
                    st.rerun()
            with next_cols[1]:
                if st.button("Back to queue", key="created_back_queue"):
                    st.session_state["request_mode"] = "queue"
                    st.rerun()
            return
        st.session_state["request_mode"] = "queue"

    if not jobs:
        render_empty("No requests yet", "Add the first maintenance job when work is identified.")
        return
    st.caption("Search or filter the queue, then choose one request to review.")
    filtered_jobs = filter_jobs(jobs, "request_filter")
    if not filtered_jobs:
        render_empty("No matching requests", "Change one or more filters to return jobs to the review queue.")
        return
    st.subheader(f"Request queue ({len(filtered_jobs)})")
    render_jobs_table(filtered_jobs)
    selected = select_current_job("Request to review", filtered_jobs, key="request_review_job")
    render_job_summary(selected)
    render_location_correction(client, selected, catalog, planner)
    with st.expander("Edit priority, crew, timing, or requirements", expanded=bool(st.session_state.pop("request_edit_open", False))):
        render_override_editor(client, selected, engineers, catalog, planner, "request")
    render_delete_control(client, selected, planner)


def render_proposal_result() -> None:
    result = st.session_state.get("last_proposal")
    if not result:
        return
    explanation = str(result.get("ai_explanation") or "The constraint solver generated a schedule proposal.")
    status = str(result.get("status") or "Proposal generated")
    warnings = result.get("warnings") or []
    with st.container(border=True):
        st.caption(f"LATEST SOLVER RESULT · {status.upper()}")
        st.subheader("What the proposal did")
        st.write(explanation)
    for warning in warnings:
        st.warning(str(warning))


def render_approval(client: ApiClient, job: dict, planner: str) -> None:
    job_id = int(job["job_id"])
    st.subheader("Approval decision")
    if normal_status(job.get("status")) != "Not started":
        st.info("Approval decisions are available only while a job is Not started. Active and completed work is controlled through the execution lifecycle.")
        return
    decision = st.radio(
        "Decision", ["Approve for execution", "Return for changes"], horizontal=True, key=f"approval_decision_{job_id}"
    )
    reason = st.text_area(
        "Decision note" + (" *" if decision == "Return for changes" else ""),
        key=f"approval_reason_{job_id}",
        placeholder="Add the evidence reviewed, conditions, or requested changes.",
        height=80,
    )
    if st.button("Record decision", type="primary", key=f"approve_button_{job_id}"):
        approved = decision == "Approve for execution"
        if not approved and not reason.strip():
            st.error("Enter a reason when returning a job for changes.")
            return
        try:
            client.submit_approval(
                job_id,
                {"approved": approved, "approved_by": planner, "reason": reason.strip() or None},
            )
        except ApiClientError as exc:
            message = f"Decision was not recorded. {exc}"
            set_feedback("error", message)
            st.error(message)
            return
        verb = "approved" if approved else "returned for changes"
        set_feedback("success", f"Job #{job_id} was {verb} by {planner}.")
        st.rerun()


def render_plan(client: ApiClient, jobs: list[dict], engineers: list[dict], catalog: dict, planner: str, is_live: bool) -> None:
    render_header("Plan and approve", "Find a time and qualified crew for every repair, review the changes, then approve.", is_live)
    if not jobs:
        render_empty("Nothing to schedule", "Create a maintenance request before generating a proposal.", "Create a request", "1 · Requests")
        return
    metrics = st.columns(4)
    scheduled = [job for job in jobs if job.get("scheduled_start") and job.get("scheduled_end")]
    metrics[0].metric("Requests", len(jobs))
    metrics[1].metric("Scheduled", len(scheduled))
    metrics[2].metric("Unscheduled", len(jobs) - len(scheduled))
    metrics[3].metric("Approved", sum(bool(job.get("is_approved")) for job in jobs))
    try:
        readiness = client.planning_readiness()
    except ApiClientError:
        readiness = None
        st.caption("Preliminary checks are unavailable. Generating a schedule will still validate the requests.")
    if readiness and readiness.get("blocked_count"):
        st.warning(f"{readiness['blocked_count']} request(s) need attention before a complete plan can be made.")
        rows = [{"Request": f"#{check['job_id']} · {check['name']}", "What needs attention": issue["message"],
                 "Next step": issue["action"]}
                for check in readiness["checks"] for issue in check["issues"]]
        st.dataframe(rows, hide_index=True, width="stretch")
        if st.button("Review these requests", key="plan_fix_requests"):
            blocked_job = next(check for check in readiness["checks"] if check["issues"])
            st.session_state["request_review_job"] = int(blocked_job["job_id"])
            st.session_state["request_mode"] = "queue"
            go_to_page("1 · Requests")
            st.rerun()
    elif readiness and readiness.get("candidate_count"):
        st.caption("Location, deadline and qualification checks passed. Generate the plan to check shared time and crew conflicts.")
    action_cols = st.columns([1.2, 4.8])
    with action_cols[0]:
        generate = st.button("Generate schedule", type="primary", width="stretch", help=glossary_tooltip("CP-SAT"))
    with action_cols[1]:
        st.caption(
            "The planner fits work into 00:30–05:00 SGT using deadlines, locations, priorities, and qualified available crew. "
            "Filters affect review only; Generate schedule plans all eligible requests."
        )
        st.caption("Approved and time-locked jobs stay fixed. Unapproved proposals may move. Generating saves a proposal; it does not approve work.")
    if generate:
        st.session_state["plan_default_tab"] = "Schedule & issues"
        with st.spinner("Finding times and qualified crews without double-booking…"):
            try:
                result = client.propose_schedule()
            except ApiClientError as exc:
                message = f"No proposal was generated. {exc} Review skills, crew availability, durations, and deadlines, then retry."
                set_feedback("error", message)
                st.error(message)
            else:
                st.session_state["last_proposal"] = result
                result_status = str(result.get("status") or "success").lower()
                accepted = result_status in {"success", "ok", "optimal", "feasible", "scheduled"}
                if accepted:
                    set_feedback("success", "Schedule proposal generated. Review every job before approval.")
                else:
                    set_feedback(
                        "warning",
                        "The solver could not produce a ready-to-approve schedule. Review the result and adjust skills, available crew, duration, or deadline.",
                        result.get("warnings") or [str(result.get("ai_explanation") or result.get("status"))],
                    )
                st.rerun()
    render_proposal_result()
    overview_tab, review_tab = st.tabs(["Schedule & issues", "Review & approve"],
                                     default=st.session_state.get("plan_default_tab", "Schedule & issues"), key="plan_tabs")
    with overview_tab:
        if scheduled:
            st.subheader("Proposed overnight schedule")
            st.caption(
                "The timeline shows the full 00:30–05:00 engineering window when all jobs share that window. "
                "Times use a 24-hour SGT clock; hover over a bar for exact start, end, duration, priority, and crew."
            )
            st.plotly_chart(build_timeline(scheduled), width="stretch", config={"displayModeBar": False})
        else:
            st.info("No jobs have proposed times. Generate a schedule after confirming each job has realistic skills, crew size, and duration.")
        unscheduled = [job for job in jobs if not (job.get("scheduled_start") and job.get("scheduled_end"))]
        if unscheduled:
            st.subheader("Unscheduled requests")
            st.warning(f"{len(unscheduled)} request(s) do not have a feasible proposed time yet. These are excluded from the timeline.")
            unscheduled_rows = []
            for job in unscheduled:
                conflict = job.get("assignment_conflict")
                if isinstance(conflict, list):
                    reason = "; ".join(str(item) for item in conflict)
                elif conflict:
                    reason = str(conflict)
                elif not engineer_names(job):
                    reason = "No crew assigned — confirm required skills and engineer availability."
                else:
                    reason = "Review duration, deadline, overnight window, and track constraints."
                unscheduled_rows.append(
                    {
                        "Request": job.get("name", "Untitled"),
                        "Priority": normal_priority(job.get("priority")),
                        "Assigned crew": ", ".join(engineer_names(job)) or "Unassigned",
                        "Action needed": reason,
                    }
                )
            st.dataframe(pd.DataFrame(unscheduled_rows), width="stretch", hide_index=True)
    with review_tab:
        st.subheader("Priority and crew review")
        st.caption("Use the filters to focus the review list. The Schedule & issues tab continues to show the complete proposal.")
        review_jobs = filter_jobs(jobs, "plan_filter")
        if not review_jobs:
            render_empty("No matching jobs", "Change one or more filters to continue priority and crew review.")
            return
        render_jobs_table(review_jobs)
        selected = select_current_job("Job to override or approve", review_jobs, key="plan_selected_job")
        render_job_summary(selected)
        assessment = selected.get("assessment_source") or "catalog/rules"
        rationale = selected.get("assessment_rationale") or selected.get("rationale")
        st.info(f"Assessment source: {assessment}. {rationale or 'Review the request details, priority, skills, and crew before deciding.'}")
        review_cols = st.columns(2, gap="large")
        with review_cols[0]:
            with st.expander("Override priority, crew, start time, or requirements"):
                render_override_editor(client, selected, engineers, catalog, planner, "plan")
        with review_cols[1]:
            render_approval(client, selected, planner)


def render_execution(client: ApiClient, jobs: list[dict], planner: str, is_live: bool) -> None:
    render_header("Track execution", "Update the field status with an auditable reason and keep the overnight plan current.", is_live)
    scheduled = [job for job in jobs if job.get("scheduled_start")]
    if not scheduled:
        render_empty("No scheduled work", "Generate and approve a schedule before field execution begins.", "Open planning", "2 · Plan & approve")
        return
    approved = [job for job in scheduled if job.get("is_approved")]
    if not approved:
        st.warning("Scheduled jobs are waiting for planner approval. Record approvals before releasing work to the field.")
    selected = select_current_job("Scheduled job", scheduled, key="execution_job")
    render_job_summary(selected)
    job_id = int(selected["job_id"])
    current = normal_status(selected.get("status"))
    next_statuses = {
        "Not started": ["In progress"],
        "In progress": ["Done", "Delay", "Error"],
        "Delay": ["Not started"],
        "Error": ["Not started"],
        "Done": [],
    }.get(current, [])
    can_start = bool(selected.get("is_approved") and selected.get("scheduled_start") and selected.get("scheduled_end"))
    if current == "Done":
        st.success("This job is complete and read-only. Its final status and audit history are retained.")
    elif current == "Not started" and not can_start:
        st.warning("This job cannot start until it has a scheduled start and end time and an approved plan.")
    else:
        if current in {"Delay", "Error"}:
            st.info(
                "Returning this job to Not started sends it back for replanning. Its proposed time and approval will be cleared; "
                "the planner must generate or save a new plan and approve it again."
            )
        display_status = {
            "In progress": "Start work — In progress",
            "Done": "Mark complete — Done",
            "Delay": "Report delay — Delay",
            "Error": "Report execution error — Error",
            "Not started": "Return for replanning — Not started",
        }
        with st.form(f"execution_update_{job_id}"):
            status = st.selectbox(
                "Valid next action *",
                next_statuses,
                format_func=lambda value: display_status.get(value, value),
            )
            reason = st.text_area(
                "Field update reason *",
                placeholder="Record the observed progress, issue, handover, or completion evidence.",
                height=90,
            )
            submitted = st.form_submit_button("Record execution update", type="primary")
        if submitted:
            if not reason.strip():
                st.error("Enter a reason for the status update. No change was sent.")
            else:
                try:
                    client.update_job_status(job_id, {"status": status, "updated_by": planner, "reason": reason.strip()})
                except ApiClientError as exc:
                    message = f"Status was not updated. {exc} Your entry is still here."
                    set_feedback("error", message)
                    st.error(message)
                else:
                    if status == "Not started":
                        set_feedback("success", f"Job #{job_id} returned for replanning. Its previous time and approval were cleared.")
                    else:
                        set_feedback("success", f"Job #{job_id} status updated to {status}.")
                    st.rerun()
    st.subheader("Tonight's execution list")
    render_jobs_table(scheduled)


def render_alerts(alerts: list[dict], is_live: bool) -> None:
    render_header("Alerts", "Review deadline, pre-maintenance, delay, and exception notices from the backend.", is_live)
    if not alerts:
        render_empty("No active alerts", "There are no active maintenance alerts from the backend.")
        return
    alert_labels = {
        "1day_deadline": "Deadline · within 1 day",
        "3days_deadline": "Deadline · within 3 days",
        "1week_deadline": "Deadline · within 1 week",
        "5min_before": "Start · within 5 minutes",
        "15min_before": "Start · within 15 minutes",
    }
    rows = [
        {
            "Job ID": item.get("job_id"),
            "Alert": alert_labels.get(str(item.get("type")), str(item.get("type", "Notice")).replace("_", " ").title()),
            "Message": item.get("message", "No message supplied"),
            "Audience": item.get("target", "Not specified"),
        }
        for item in alerts
    ]
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Job ID": st.column_config.NumberColumn(format="#%d"),
            "Message": st.column_config.TextColumn(width="large"),
        },
    )


def render_audit(audit_logs: list[dict], is_live: bool) -> None:
    render_header("Audit log", "Trace request creation, overrides, approvals, deletions, and execution updates.", is_live)
    if not audit_logs:
        render_empty("No audit records", "Recorded planner actions will appear here after the first change.")
        return
    parsed_logs = []
    for log in audit_logs:
        raw_details = log.get("details")
        try:
            details = json.loads(raw_details) if isinstance(raw_details, str) else (raw_details or {})
        except (TypeError, json.JSONDecodeError):
            details = {"raw": raw_details}
        parsed_logs.append({**log, "parsed_details": details})
    rows = [
        {
            "Event ID": log.get("id"),
            "Time (SGT)": format_datetime(log.get("timestamp"), str(log.get("timestamp", "Unknown"))),
            "Action": log.get("action", "Unknown action"),
            "Actor": log.get("approved_by") or "System",
            "Job ID": log["parsed_details"].get("job_id"),
            "Reason": log["parsed_details"].get("reason") or "—",
        }
        for log in parsed_logs
    ]
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Event ID": st.column_config.NumberColumn(format="#%d"),
            "Job ID": st.column_config.NumberColumn(format="#%d"),
            "Reason": st.column_config.TextColumn(width="large"),
        },
    )
    event_lookup = {int(log["id"]): log for log in parsed_logs if log.get("id") is not None}
    selected_id = st.selectbox(
        "Audit event details",
        list(event_lookup),
        format_func=lambda value: f"#{value} · {event_lookup[value].get('action', 'Unknown')} · {format_datetime(event_lookup[value].get('timestamp'))}",
        key="audit_event",
    )
    selected = event_lookup[selected_id]
    details = selected["parsed_details"]
    with st.expander("Recorded change", expanded=True):
        st.write(f"**Actor:** {selected.get('approved_by') or 'System'}")
        st.write(f"**Job ID:** {details.get('job_id', 'Not applicable')}")
        st.write(f"**Reason:** {details.get('reason') or 'No reason recorded'}")
        before, after = details.get("before"), details.get("after")
        if isinstance(before, dict) or isinstance(after, dict):
            before_col, after_col = st.columns(2)
            with before_col:
                st.caption("Before")
                st.json(before or {})
            with after_col:
                st.caption("After")
                st.json(after or {})
        elif isinstance(details.get("snapshot"), dict):
            st.caption("Deleted job snapshot")
            st.json(details["snapshot"])
    with st.expander("Technical event payload"):
        st.json(details)


def render_ai_setup(client: ApiClient, status: dict, is_live: bool) -> None:
    render_header("AI setup", "Check the optional Gemini request assessment without exposing its API key.", is_live)
    configured = bool(status.get("configured"))
    source_labels = {
        "environment": "Backend environment variable",
        "dotenv": "Root .env file",
        "secure_store": "Secure local store",
        "none": "Not configured",
    }
    with st.container(border=True):
        st.subheader("Gemini assessment")
        if configured:
            st.info("A Gemini API key is configured. Run the connection test to verify the provider and response format.")
        else:
            st.warning("Gemini is not configured. Local catalog and rules remain available for request creation.")
        facts = st.columns(2)
        with facts[0]:
            st.caption("CONFIGURATION SOURCE")
            st.write(f"**{source_labels.get(str(status.get('source')), 'Unknown')}**")
        with facts[1]:
            st.caption("MODEL")
            st.write(f"**{status.get('model') or 'gemini-3.8-flash'}**")
        if os.getenv("NGEEBULA_HOSTED") == "1":
            st.caption(
                "The service owner manages GEMINI_API_KEY in Render's Environment settings. "
                "Visitors do not need to enter a key here. Never put credentials in a maintenance request."
            )
        else:
            dotenv_path = APP_DIR.parent / ".env"
            st.write("Add the key to the root `.env` file. Keep the key after the equals sign on one line:")
            st.code(f"File: {dotenv_path}\nGEMINI_API_KEY=replace-with-your-key", language="text", wrap_lines=True)
            st.caption(
                "Save the file, choose Refresh snapshot in the sidebar, then run the connection test. "
                "The backend reads `.env` for each AI request, so no restart is required."
            )
            with st.expander("Alternative secure-store setup"):
                st.write(
                    "A Windows secure-store script remains available in `scripts/configure-gemini.ps1`. "
                    "An operating-system environment value takes precedence over `.env`, which takes precedence over the secure store."
                )
        st.caption("The connection test sends a synthetic maintenance description and catalog context. It does not send saved jobs or staff records.")

    if st.button("Test Gemini connection", type="primary", key="test_ai_connection", disabled=not configured):
        checked_at = datetime.now(SGT).strftime("%d %b %Y, %H:%M:%S SGT")
        with st.spinner("Sending a synthetic maintenance request to Gemini…"):
            try:
                outcome = client.test_ai_connection()
                if str(outcome.get("result", "")).lower() != "success":
                    raise ApiClientError(str(outcome.get("message") or "Gemini did not return a validated success response."))
            except ApiClientError as exc:
                st.session_state["ai_last_test"] = {"ok": False, "time": checked_at, "message": str(exc)}
            else:
                st.session_state["ai_last_test"] = {
                    "ok": True,
                    "time": checked_at,
                    "message": str(outcome.get("message") or "Gemini returned a validated catalog assessment."),
                }
        st.rerun()
    last_test = st.session_state.get("ai_last_test")
    if last_test:
        st.subheader("Last test")
        st.caption(str(last_test.get("time")))
        if last_test.get("ok"):
            st.success("Gemini responded and passed the production catalog validation.")
            backend_message = str(last_test.get("message") or "")
            if backend_message and "passed the production catalog validation" not in backend_message:
                st.caption(backend_message)
        else:
            st.error(str(last_test.get("message")))


def render_about() -> None:
    render_header("How Ngeebula works", "A planner-led workflow for overnight rail maintenance scheduling.", None)
    from about_page import render_about_page

    render_about_page()


def fetch_workspace(client: ApiClient, page: str) -> tuple[list[dict], list[dict], dict, list[dict], list[dict], list[str]]:
    jobs: list[dict] = []
    engineers: list[dict] = []
    catalog: dict = {"activities": [], "lines": ["NS", "EW", "CCL"], "skills": []}
    alerts: list[dict] = []
    audit: list[dict] = []
    errors: list[str] = []
    try:
        jobs = client.get_jobs()
    except ApiClientError as exc:
        errors.append(str(exc))
        return jobs, engineers, catalog, alerts, audit, errors
    if page in ("1 · Requests", "2 · Plan & approve"):
        try:
            engineers = client.get_engineers()
        except ApiClientError as exc:
            errors.append(f"Engineer roster unavailable: {exc}")
        try:
            catalog = client.get_catalog()
        except ApiClientError as exc:
            errors.append(f"Maintenance catalog unavailable: {exc}")
    if page == "Alerts":
        try:
            alerts = client.get_alerts()
        except ApiClientError as exc:
            errors.append(f"Alerts unavailable: {exc}")
    if page == "Audit log":
        try:
            audit = client.get_audit_logs()
        except ApiClientError as exc:
            errors.append(f"Audit log unavailable: {exc}")
    return jobs, engineers, catalog, alerts, audit, errors


load_styles()
if "page" not in st.session_state:
    st.session_state["page"] = "Cockpit"
navigation_target = st.session_state.pop("_navigation_target", None)
if navigation_target in PAGES:
    st.session_state["page"] = navigation_target
    if navigation_target in MAIN_PAGES:
        st.session_state["main_navigation"] = navigation_target
    else:
        st.session_state["main_navigation"] = None
current_page = st.session_state.get("page", "Cockpit")
if current_page in UTILITY_PAGES:
    st.session_state["main_navigation"] = None
elif "main_navigation" not in st.session_state:
    st.session_state["main_navigation"] = current_page if current_page in MAIN_PAGES else "Cockpit"

with st.sidebar:
    st.header("Ngeebula")
    st.caption("Rail maintenance planning")
    st.radio(
        "Main navigation",
        MAIN_PAGES,
        format_func=lambda value: PAGE_LABELS[value],
        key="main_navigation",
        on_change=select_main_page,
        index=None if current_page in UTILITY_PAGES else 0,
    )
    for group_label, group_pages in [
        ("Explore & learn", ["Compare approaches", "Schedule example", "Glossary", "About"]),
        ("Utilities", ["Alerts", "Audit log", "AI setup"]),
    ]:
        with st.expander(group_label, expanded=current_page in group_pages):
            for utility_page in group_pages:
                st.button(PAGE_LABELS[utility_page], key=f"utility_{utility_page}", width="stretch",
                          on_click=go_to_page, args=(utility_page,))
    st.divider()
    planner = st.text_input(
        "Planner name", value=st.session_state.get("planner_name", "Planner"), key="planner_name_input",
        help="Recorded with overrides, approvals, deletions, and execution updates.",
    ).strip() or "Planner"
    st.session_state["planner_name"] = planner
    if os.getenv("NGEEBULA_HOSTED") == "1":
        api_url = DEFAULT_API_URL
        st.caption("Shared demo · Dummy roster. Saved work resets when the service restarts.")
    else:
        with st.expander("Connection settings"):
            api_url = st.text_input(
                "Backend server URL", value=DEFAULT_API_URL,
                help="Use the local address when the backend runs on this computer.",
            )
    if st.button("Refresh snapshot", width="stretch", type="secondary"):
        st.rerun()

page = st.session_state.get("page", "Cockpit")
client = ApiClient(api_url)
ai_status: dict = {}
if page in {"About", "Schedule example", "Compare approaches", "Glossary"}:
    jobs, engineers, catalog, alerts, audit_logs, errors = [], [], {}, [], [], []
    is_live: bool | None = None
elif page == "AI setup":
    jobs, engineers, catalog, alerts, audit_logs, errors = [], [], {}, [], [], []
    try:
        ai_status = client.get_ai_status()
    except ApiClientError as exc:
        errors = [str(exc)]
    is_live = not errors
else:
    jobs, engineers, catalog, alerts, audit_logs, errors = fetch_workspace(client, page)
    is_live = not errors or bool(jobs)
snapshot_time = datetime.now(SGT).strftime("%H:%M:%S SGT")

with st.sidebar:
    if is_live is None:
        st.caption("Examples use synthetic data; nothing changes your live plan." if page in {"Schedule example", "Compare approaches"} else "This reference page works without the backend.")
    elif is_live:
        st.success("API snapshot loaded")
        st.caption(f"Refreshed {snapshot_time}")
    else:
        st.error("Backend offline")
    st.caption("All dates and times are shown in Singapore Time (SGT).")

render_feedback()
if errors:
    primary_offline = not jobs and errors
    if primary_offline:
        st.error(f"Live workspace unavailable: {errors[0]}")
        st.info("Start FastAPI or correct the server URL in the sidebar. Your current form entries remain in this browser session.")
    for issue in errors[1 if primary_offline else 0 :]:
        st.warning(issue)

if page == "Cockpit":
    render_cockpit(jobs, bool(is_live))
elif page == "About":
    render_about()
elif page == "Glossary":
    st.title("Glossary")
    render_glossary()
elif page == "Compare approaches":
    render_comparison_page(client)
    if st.button("Plan a real repair", key="compare_add_work", type="primary"):
        start_request_wizard()
        go_to_page("1 · Requests")
        st.rerun()
elif page == "Schedule example":
    render_insertion_example(client)
    if st.button("Add a real maintenance request", type="primary", key="demo_add_work"):
        start_request_wizard()
        go_to_page("1 · Requests")
        st.rerun()
elif page == "AI setup":
    render_ai_setup(client, ai_status, bool(is_live))
elif page == "1 · Requests":
    render_requests(client, jobs, engineers, catalog, planner, bool(is_live))
elif page == "2 · Plan & approve":
    render_plan(client, jobs, engineers, catalog, planner, bool(is_live))
elif page == "3 · Execution":
    render_execution(client, jobs, planner, bool(is_live))
elif page == "Alerts":
    render_alerts(alerts, bool(is_live))
else:
    render_audit(audit_logs, bool(is_live))
