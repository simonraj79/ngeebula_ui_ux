"""Offline reconciliation helpers for the committed LTA station snapshot.

This module never downloads data. It enriches a caller-supplied local catalog
without mutating it and makes every correction or unsupported local row visible.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_REFERENCE_PATH = Path(__file__).with_name("lta_station_reference.json")

# Explicit mapping from the station sheet's published line names to Ngeebula's
# existing canonical labels. Branch/extension rows remain on their parent local
# line because those are the only corresponding local catalog groups.
PUBLISHED_LINE_TO_LOCAL = {
    "North-South Line": "North-South Line (NSL)",
    "East-West Line": "East-West Line (EWL)",
    "Changi Airport Branch Line": "East-West Line (EWL)",
    "North East Line": "North-East Line (NEL)",
    "Circle Line": "Circle Line (CCL)",
    "Circle Line Extension": "Circle Line (CCL)",
    "Downtown Line": "Downtown Line (DTL)",
    "Thomson-East Coast Line": "Thomson-East Coast Line (TEL)",
    "Bukit Panjang LRT": "Bukit Panjang LRT (BPLRT)",
    "Sengkang LRT": "Sengkang LRT (SKLRT)",
    "Punggol LRT": "Punggol LRT (PGLRT)",
}


def load_reference(path: Path | str = DEFAULT_REFERENCE_PATH) -> dict[str, Any]:
    """Load and minimally validate the committed snapshot from disk only."""
    reference = json.loads(Path(path).read_text(encoding="utf-8"))
    if reference.get("schema_version") != 1 or not isinstance(reference.get("stations"), list):
        raise ValueError("Unsupported LTA station reference schema")
    return reference


def reference_attribution(reference: dict[str, Any]) -> dict[str, Any]:
    """Return display-ready access and licence metadata from provenance."""
    provenance = reference["provenance"]
    source = provenance["station_source"]
    retrieved_on = provenance["retrieved_on"]
    licence_url = provenance["licence_url"]
    notice = (
        f"Contains information from {source['title']} accessed on {retrieved_on} "
        f"from {source['url']}, made available under the terms of "
        f"{provenance['licence']} ({licence_url})."
    )
    return {
        "available": True,
        "publisher": provenance["publisher"],
        "dataset_title": source["title"],
        "dataset_url": source["url"],
        "portal_last_update": source["portal_last_update"],
        "retrieved_on": retrieved_on,
        "licence": provenance["licence"],
        "licence_url": licence_url,
        "notice": notice,
    }


def enrich_station_catalog(
    local_rows: Iterable[dict[str, Any]],
    reference: dict[str, Any] | None = None,
    *,
    reference_path: Path | str = DEFAULT_REFERENCE_PATH,
) -> dict[str, Any]:
    """Reconcile local rows by station code and append missing official rows.

    Names are compared case-insensitively. Local rows absent from the older LTA
    snapshot are preserved as ``unverified``. A code/name conflict is corrected
    for the returned catalog only and retains ``old_name`` and a warning. Saved
    jobs and source JSON are never changed.
    """
    if reference is None:
        try:
            snapshot = load_reference(reference_path)
        except FileNotFoundError:
            rows = []
            for original in local_rows:
                row = copy.deepcopy(original)
                row["reference_status"] = "unverified"
                rows.append(row)
            return {
                "stations": rows,
                "provenance": {
                    "available": False,
                    "warning": "Official LTA station reference is unavailable; local rows are unchanged.",
                },
            }
    else:
        snapshot = reference
    official_by_code: dict[str, dict[str, Any]] = {}
    for station in snapshot["stations"]:
        code = str(station["station_code"]).strip().upper()
        if code in official_by_code:
            raise ValueError(f"Duplicate station code in official reference: {code}")
        official_by_code[code] = station

    enriched: list[dict[str, Any]] = []
    local_codes: set[str] = set()
    for original in local_rows:
        row = copy.deepcopy(original)
        code = str(row.get("code", "")).strip().upper()
        name = str(row.get("name", "")).strip()
        if not code or not name:
            raise ValueError(f"Local station row requires code and name: {original!r}")
        if code in local_codes:
            raise ValueError(f"Duplicate station code in local catalog: {code}")
        local_codes.add(code)
        row["code"] = code
        official = official_by_code.get(code)
        if official is None:
            row["reference_status"] = "unverified"
        else:
            official_line = PUBLISHED_LINE_TO_LOCAL.get(str(official["published_line_name"]))
            if official_line is None:
                raise ValueError(
                    f"No explicit local line mapping for {official['published_line_name']!r}"
                )
            local_line = str(row.get("line", "")).strip()
            name_matches = name.casefold() == str(official["station_name"]).strip().casefold()
            line_matches = local_line.casefold() == official_line.casefold()
            if name_matches and line_matches:
                row["reference_status"] = "matched"
            else:
                official_name = str(official["station_name"]).strip()
                row["reference_status"] = "corrected"
                corrections = []
                if not name_matches:
                    row["old_name"] = name
                    row["name"] = official_name
                    corrections.append(f"name {name!r} to {official_name!r}")
                if not line_matches:
                    row["old_line"] = local_line
                    row["line"] = official_line
                    corrections.append(f"line {local_line!r} to {official_line!r}")
                row["reference_warning"] = (
                    f"Local station {code} conflicts with the LTA snapshot; corrected "
                    + " and ".join(corrections)
                    + " in this catalog view."
                )
        enriched.append(row)

    for code, official in official_by_code.items():
        if code in local_codes:
            continue
        published_line = str(official["published_line_name"])
        try:
            local_line = PUBLISHED_LINE_TO_LOCAL[published_line]
        except KeyError as exc:
            raise ValueError(f"No explicit local line mapping for {published_line!r}") from exc
        enriched.append(
            {
                "code": code,
                "name": str(official["station_name"]).strip(),
                "line": local_line,
                "interchange": False,
                "reference_status": "official",
            }
        )

    # Interchange is a property of a name having multiple published/local codes.
    # This does not assert opening status or invent cross-line membership.
    codes_by_name: dict[str, set[str]] = {}
    for row in enriched:
        codes_by_name.setdefault(str(row["name"]).strip().casefold(), set()).add(row["code"])
    for row in enriched:
        row["interchange"] = len(codes_by_name[str(row["name"]).strip().casefold()]) > 1

    return {
        "stations": enriched,
        "provenance": reference_attribution(snapshot),
    }
