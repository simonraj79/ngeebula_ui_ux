"""Native Streamlit asset picker for the maintenance-request guide."""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


ASSET_DIR = Path(__file__).resolve().parent / "assets"

ASSETS: list[dict[str, str]] = [
    {
        "id": "train_doors",
        "label": "Train doors",
        "category": "rolling_stock",
        "activity": "Train door repair",
        "title_template": "Train door repair — {location}",
        "description": "Train door repair is required. Confirm the affected components and repair scope during planning review.",
        "location_hint": "Train number, car and door, or depot road",
    },
    {
        "id": "wheels_brakes",
        "label": "Wheels & brakes",
        "category": "rolling_stock",
        "activity": "Brake pad replacement",
        "title_template": "Brake pad replacement — {location}",
        "description": "Brake pad replacement is required. Confirm the affected components and repair scope during planning review.",
        "location_hint": "Train number, car and axle, or depot road",
    },
    {
        "id": "rails",
        "label": "Rails",
        "category": "track_and_permanent_way",
        "activity": "Rail replacement",
        "title_template": "Rail replacement — {location}",
        "description": "Rail replacement is required. Confirm the affected section and repair scope during planning review.",
        "location_hint": "Line, direction or track, and chainage or nearby station",
    },
    {
        "id": "points",
        "label": "Points",
        "category": "track_and_permanent_way",
        "activity": "Switch/point replacement",
        "title_template": "Point replacement — {location}",
        "description": "Switch or point replacement is required. Confirm the affected components and repair scope during planning review.",
        "location_hint": "Point number, line and nearby station or depot area",
    },
    {
        "id": "signals",
        "label": "Signals",
        "category": "signalling_and_train_control",
        "activity": "Signal replacement",
        "title_template": "Signal replacement — {location}",
        "description": "Signal replacement is required. Confirm the affected components and repair scope during planning review.",
        "location_hint": "Signal ID, line and nearby station or chainage",
    },
    {
        "id": "power",
        "label": "Power",
        "category": "power_and_electrical_systems",
        "activity": "Traction power fault troubleshooting",
        "title_template": "Traction power fault — {location}",
        "description": "Traction power fault troubleshooting is required. Confirm the affected equipment and investigation scope during planning review.",
        "location_hint": "Substation, power section or equipment ID",
    },
    {
        "id": "drainage_pumps",
        "label": "Drainage & pumps",
        "category": "station_equipment",
        "activity": "Drainage pump repair",
        "title_template": "Drainage pump repair — {location}",
        "description": "Drainage pump repair is required. Confirm the affected equipment and repair scope during planning review.",
        "location_hint": "Station, tunnel section, plant room or sump ID",
    },
    {
        "id": "platform_doors",
        "label": "Platform doors",
        "category": "platform_screen_doors",
        "activity": "Door obstruction sensor repair",
        "title_template": "Platform door sensor repair — {location}",
        "description": "Platform door obstruction sensor repair is required. Confirm the affected components and repair scope during planning review.",
        "location_hint": "Station, platform and platform-door number",
    },
]

_ASSETS_BY_ID = {asset["id"]: asset for asset in ASSETS}


def get_asset(asset_id: str | None) -> dict[str, str] | None:
    """Return an asset definition by stable ID."""
    return _ASSETS_BY_ID.get(str(asset_id)) if asset_id else None


def _schematic(selected_id: str | None) -> str:
    svg = (ASSET_DIR / "maintenance-assets.svg").read_text(encoding="utf-8")
    if selected_id in _ASSETS_BY_ID:
        svg = svg.replace(
            f'id="marker-{selected_id}" class="marker"',
            f'id="marker-{selected_id}" class="marker selected"',
        )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def render_asset_picker(selected_id: str | None = None) -> str | None:
    """Render the full schematic and eight native choices; return only a clicked ID."""
    st.image(
        _schematic(selected_id),
        caption="Maintenance asset schematic — a visual guide, not a live network map.",
        width="stretch",
    )
    clicked_asset: str | None = None
    with st.container(key="asset_choices"):
        for row_start in range(0, len(ASSETS), 4):
            columns = st.columns(4)
            for column, asset in zip(columns, ASSETS[row_start : row_start + 4]):
                number = ASSETS.index(asset) + 1
                with column:
                    with st.container(border=True):
                        if st.button(
                            f"{number} · {asset['label']}",
                            key=f"asset_{asset['id']}",
                            type="primary" if asset["id"] == selected_id else "secondary",
                            width="stretch",
                        ):
                            clicked_asset = asset["id"]
                        st.caption(asset["activity"])
    return clicked_asset


def render_asset_summary(selected_id: str | None) -> None:
    """Render a concise native summary of the selected catalog mapping."""
    asset = get_asset(selected_id)
    if not asset:
        return
    with st.container(border=True):
        st.caption("SELECTED ASSET")
        st.write(f"**{asset['label']}** · {asset['activity']}")
        st.caption(f"Location to provide: {asset['location_hint']}")
