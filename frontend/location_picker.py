"""Station-first location entry for the maintenance-request guide."""

from __future__ import annotations

from typing import Any

import streamlit as st


STATION_MODE = "Station / nearby track"
MANUAL_MODE = "Train / depot / other site"
LOCATION_MODES = [STATION_MODE, MANUAL_MODE]


def grouped_stations(stations: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    """Group valid station records by name, with at most one code for each serving line."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for raw in stations or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        code = str(raw.get("code") or "").strip().upper()
        line = str(raw.get("line") or "").strip()
        if not (name and code and line):
            continue
        by_line = grouped.setdefault(name, {})
        by_line.setdefault(
            line,
            {"name": name, "code": code, "line": line, "interchange": bool(raw.get("interchange")),
             "reference_status": raw.get("reference_status", "unverified")},
        )
    return {
        name: sorted(by_line.values(), key=lambda station: (station["line"], station["code"]))
        for name, by_line in sorted(grouped.items(), key=lambda item: item[0].casefold())
    }


def _seed_widget(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _sync_field(draft: dict[str, Any], field: str, widget_key: str) -> None:
    draft[field] = st.session_state.get(widget_key)


def _sync_station(
    draft: dict[str, Any], widget_key: str, station_line_key: str, detail_key: str
) -> None:
    selected = st.session_state.get(widget_key)
    if selected != draft.get("station_name"):
        draft["station_line"] = None
        draft["location_detail"] = ""
        st.session_state[station_line_key] = None
        st.session_state[detail_key] = ""
    draft["station_name"] = selected


def _station_label(name: str, grouped: dict[str, list[dict[str, Any]]]) -> str:
    codes = " / ".join(station["code"] for station in grouped[name])
    return f"{name} · {codes}"


def render_location_picker(
    catalog: dict[str, Any], draft: dict[str, Any], prefix: str = "wizard"
) -> dict[str, str | None]:
    """Render location controls and return canonical line, track, station code, and error."""
    mode_key = f"{prefix}_location_mode"
    station_key = f"{prefix}_station"
    station_line_key = f"{prefix}_station_line"
    detail_key = f"{prefix}_location_detail"
    manual_line_key = f"{prefix}_line"
    manual_track_key = f"{prefix}_track"

    saved_mode = str(draft.get("location_mode") or STATION_MODE)
    if saved_mode not in LOCATION_MODES:
        saved_mode = STATION_MODE
    _seed_widget(mode_key, saved_mode)
    mode = st.radio(
        "Where is the work? *",
        LOCATION_MODES,
        key=mode_key,
        horizontal=True,
        on_change=_sync_field,
        args=(draft, "location_mode", mode_key),
    )
    draft["location_mode"] = mode

    if mode == MANUAL_MODE:
        lines = [str(line).strip() for line in catalog.get("lines", []) if str(line).strip()]
        saved_line = draft.get("manual_line")
        _seed_widget(manual_line_key, saved_line if saved_line in lines else None)
        line = st.selectbox(
            "Rail line *",
            lines,
            index=None,
            placeholder="Choose the relevant line",
            key=manual_line_key,
            on_change=_sync_field,
            args=(draft, "manual_line", manual_line_key),
        )
        _seed_widget(manual_track_key, str(draft.get("manual_track") or ""))
        track = st.text_input(
            "Train, depot or worksite *",
            key=manual_track_key,
            placeholder="Example: Train 512, car 3 · brake assembly; or depot road 4",
            help="Enter the operational identifier used by the crew. This path does not infer a station or fleet location.",
            on_change=_sync_field,
            args=(draft, "manual_track", manual_track_key),
        )
        draft["manual_line"] = line
        draft["manual_track"] = track
        error = None
        if not line:
            error = "Choose the rail line for this worksite."
        elif not track.strip():
            error = "Enter the train, depot or worksite."
        return {"line": line or "", "track": track.strip(), "station_code": None, "error": error}

    grouped = grouped_stations(catalog.get("stations", []))
    station_names = list(grouped)
    if not station_names:
        st.warning(
            "The station list is unavailable. Choose Train / depot / other site above to enter a known line and worksite."
        )
    saved_station = draft.get("station_name")
    _seed_widget(station_key, saved_station if saved_station in grouped else None)
    station_name = st.selectbox(
        "Station *",
        station_names,
        index=None,
        placeholder="Search by station name or code",
        format_func=lambda name: _station_label(name, grouped),
        key=station_key,
        on_change=_sync_station,
        args=(draft, station_key, station_line_key, detail_key),
    )
    if not station_name:
        st.caption("For example, choosing Clementi automatically sets East-West Line (EWL).")
    reference = catalog.get("station_reference")
    if reference:
        st.caption(f"Station codes: [LTA {reference['portal_last_update']} snapshot]({reference['dataset_url']}) · [Open Data Licence]({reference['licence_url']}) · accessed {reference['retrieved_on']}")

    selected_line: str | None = None
    station_code: str | None = None
    if station_name:
        serving = grouped[station_name]
        if len(serving) == 1:
            selected_line = serving[0]["line"]
            station_code = serving[0]["code"]
            draft["station_line"] = selected_line
            st.write(f"**Line set automatically:** {selected_line} · {station_code}")
        else:
            lines = [station["line"] for station in serving]
            saved_station_line = draft.get("station_line")
            _seed_widget(station_line_key, saved_station_line if saved_station_line in lines else None)
            selected_line = st.selectbox(
                "Serving line *",
                lines,
                index=None,
                placeholder="Choose the line where work will take place",
                format_func=lambda line: f"{line} · {next(item['code'] for item in serving if item['line'] == line)}",
                key=station_line_key,
                on_change=_sync_field,
                args=(draft, "station_line", station_line_key),
            )
            if selected_line:
                station_code = next(item["code"] for item in serving if item["line"] == selected_line)
                draft["station_line"] = selected_line

    _seed_widget(detail_key, str(draft.get("location_detail") or ""))
    detail = st.text_input(
        "Work area / asset ID (optional)",
        key=detail_key,
        placeholder="Example: crossover, equipment cabinet, or platform end",
        on_change=_sync_field,
        args=(draft, "location_detail", detail_key),
    )
    draft["station_name"] = station_name
    draft["location_detail"] = detail

    error = None
    if not station_names:
        error = "Station data is unavailable. Use Train / depot / other site to enter the location."
    elif not station_name:
        error = "Choose the station nearest to the work."
    elif not selected_line:
        error = f"Choose the serving line for {station_name}."
    track = ""
    if station_name and station_code:
        track = f"{station_code} {station_name}"
        if detail.strip():
            track += f" · {detail.strip()}"
        chosen = next(item for item in grouped[station_name] if item["code"] == station_code)
        if chosen.get("reference_status") == "unverified":
            st.caption("This local station entry is not covered by the available LTA snapshot. Confirm its code and worksite with the operator; no opening or service status is inferred.")
    return {"line": selected_line or "", "track": track, "station_code": station_code, "error": error}
