"""Validated loader for the pinned PS1 railway track-access instance."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class PS1DataError(ValueError):
    """Raised when an instance file does not satisfy the published PS1 schema."""


@dataclass(frozen=True)
class Line:
    line_code: str
    line_name: str


@dataclass(frozen=True)
class Station:
    station_id: str
    line_code: str
    seq: int
    is_interchange: bool


@dataclass(frozen=True)
class Sector:
    sector_id: str
    line_code: str
    from_station_id: str
    to_station_id: str
    seq: int
    is_shared: bool


@dataclass(frozen=True)
class LocationSupply:
    location_id: str
    location_kind: str
    line_code: str
    bound: str
    supply_capacity: int


@dataclass(frozen=True)
class BufferRule:
    nature_of_works: str
    up_to_buffer_sectors: int
    opposite_bound_required: bool


@dataclass(frozen=True)
class Project:
    contract_number: str
    contract_description: str
    contract_award_date: date
    activity_type: str
    nature_of_activity: str
    contract_priority: int
    contract_completion_date: date
    planned_completion_date: date
    number_of_workfronts: int
    access_type: str
    number_of_maximum_access_per_week: int


@dataclass(frozen=True)
class Activity:
    activity_id: str
    contract_number: str
    activity_type: str
    start_location_id: str
    end_location_id: str
    total_accesses: Decimal
    planned_start_date: date
    predecessor_activity_id: str | None
    activity_priority: int


@dataclass(frozen=True)
class PS1Instance:
    lines: tuple[Line, ...]
    stations: tuple[Station, ...]
    sectors: tuple[Sector, ...]
    location_supply: tuple[LocationSupply, ...]
    buffer_rules: tuple[BufferRule, ...]
    projects: tuple[Project, ...]
    activities: tuple[Activity, ...]
    horizon_start: date
    horizon_weeks: int
    lines_by_code: Mapping[str, Line]
    stations_by_line: Mapping[str, tuple[Station, ...]]
    sectors_by_line: Mapping[str, tuple[Sector, ...]]
    locations_by_id: Mapping[str, LocationSupply]
    buffers_by_nature: Mapping[str, BufferRule]
    projects_by_contract: Mapping[str, Project]
    activities_by_id: Mapping[str, Activity]
    capacity_overrides: Mapping[tuple[str, int], int] = field(default_factory=lambda: MappingProxyType({}))

    def week_for_date(self, value: date) -> int:
        """Return the 1-based horizon week containing ``value``."""
        return (value - self.horizon_start).days // 7 + 1

    def capacity_for(self, location_id: str, week: int) -> int:
        if location_id not in self.locations_by_id:
            raise PS1DataError("capacity lookup has unknown location_id")
        if not 1 <= week <= self.horizon_weeks:
            raise PS1DataError("capacity lookup week is outside the horizon")
        return self.capacity_overrides.get((location_id, week), self.locations_by_id[location_id].supply_capacity)

    def with_capacity_overrides(self, overrides) -> "PS1Instance":
        """Return a run-local instance with validated week-specific capacities."""
        normalized: dict[tuple[str, int], int] = {}
        items = overrides.items() if isinstance(overrides, Mapping) else (
            ((item.get("location_id"), item.get("week")), item.get("capacity")) for item in overrides
        )
        for key, capacity in items:
            if not isinstance(key, tuple) or len(key) != 2:
                raise PS1DataError("capacity override requires location_id and week")
            location_id, week = key
            if location_id not in self.locations_by_id:
                raise PS1DataError("capacity override has unknown location_id")
            if not isinstance(week, int) or not 1 <= week <= self.horizon_weeks:
                raise PS1DataError("capacity override week is outside the horizon")
            if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 0:
                raise PS1DataError("capacity override must be a non-negative integer")
            if key in normalized:
                raise PS1DataError("capacity override is duplicated")
            normalized[key] = capacity
        return replace(self, capacity_overrides=MappingProxyType(normalized))

    def activity_span_ids(self, activity_id: str) -> tuple[str, ...]:
        """Return the exact occupied tunnel and platform locations for an activity."""
        activity = self._activity(activity_id)
        start = self.locations_by_id[activity.start_location_id]
        end = self.locations_by_id[activity.end_location_id]
        if start.location_kind != "tunnel sector" or end.location_kind != "tunnel sector":
            raise PS1DataError(f"{activity_id}: activity endpoints must be tunnel sectors")
        sector_by_location = {
            f"{sector.sector_id}:{start.bound}": sector for sector in self.sectors_by_line[start.line_code]
        }
        first = sector_by_location[start.location_id].seq
        last = sector_by_location[end.location_id].seq
        low, high = sorted((first, last))
        selected = [s for s in self.sectors_by_line[start.line_code] if low <= s.seq <= high]
        location_ids: list[str] = []
        for sector in selected:
            location_ids.append(f"{sector.sector_id}:{start.bound}")
        station_ids = [selected[0].from_station_id] + [s.to_station_id for s in selected]
        location_ids.extend(f"PLAT:{start.line_code}:{station_id}:{start.bound}" for station_id in station_ids)
        return tuple(location_ids)

    def closure_footprint(self, activity_id: str) -> tuple[str, ...]:
        """Return occupied locations plus the published buffer/mirroring closure."""
        activity = self._activity(activity_id)
        project = self.projects_by_contract[activity.contract_number]
        rule = self.buffers_by_nature[project.nature_of_activity]
        start = self.locations_by_id[activity.start_location_id]
        sectors = self.sectors_by_line[start.line_code]
        sector_locations = {f"{s.sector_id}:{start.bound}": s for s in sectors}
        span_seqs = [sector_locations[x].seq for x in self.activity_span_ids(activity_id) if x.startswith("SEC:")]
        low = max(min(s.seq for s in sectors), min(span_seqs) - rule.up_to_buffer_sectors)
        high = min(max(s.seq for s in sectors), max(span_seqs) + rule.up_to_buffer_sectors)
        selected = [s for s in sectors if low <= s.seq <= high]
        station_ids = [selected[0].from_station_id] + [s.to_station_id for s in selected]
        footprint = {f"{s.sector_id}:{start.bound}" for s in selected}
        footprint.update(f"PLAT:{start.line_code}:{station_id}:{start.bound}" for station_id in station_ids)

        if rule.opposite_bound_required:
            opposite = "WB" if start.bound == "EB" else "EB"
            footprint.update(x[:-2] + opposite for x in tuple(footprint))

        interchange_markers = (":H01_H02:", ":H01:", ":H02:")
        if project.nature_of_activity == "Live" and any(m in x for x in footprint for m in interchange_markers):
            other_line = next(code for code in self.lines_by_code if code != start.line_code)
            for bound in ("EB", "WB"):
                footprint.add(f"SEC:{other_line}:H01_H02:{bound}")
                footprint.add(f"PLAT:{other_line}:H01:{bound}")
                footprint.add(f"PLAT:{other_line}:H02:{bound}")
        return tuple(sorted(footprint))

    def _activity(self, activity_id: str) -> Activity:
        try:
            return self.activities_by_id[activity_id]
        except KeyError as exc:
            raise PS1DataError(f"unknown activity_id: {activity_id}") from exc

    def to_public_dict(self) -> dict:
        """Return JSON-serializable instance metadata and normalized records."""
        def record(row) -> dict:
            result = {}
            for key, value in row.__dict__.items():
                result[key] = value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value
            return result

        return {
            "horizon_start": self.horizon_start.isoformat(),
            "horizon_weeks": self.horizon_weeks,
            "lines": [record(x) for x in self.lines],
            "stations": [record(x) for x in self.stations],
            "sectors": [record(x) for x in self.sectors],
            "location_supply": [record(x) for x in self.location_supply],
            "buffer_rules": [record(x) for x in self.buffer_rules],
            "projects": [record(x) for x in self.projects],
            "activities": [record(x) for x in self.activities],
            "capacity_overrides": [
                {"location_id": location_id, "week": week, "capacity": capacity}
                for (location_id, week), capacity in sorted(self.capacity_overrides.items())
            ],
        }


SCHEMAS = {
    "01_LINES.csv": ("line_code", "line_name"),
    "02_STATIONS.csv": ("station_id", "line_code", "seq", "is_interchange"),
    "03_SECTORS.csv": ("sector_id", "line_code", "from_station_id", "to_station_id", "seq", "is_shared"),
    "04_LOCATION_SUPPLY.csv": ("location_id", "location_kind", "line_code", "bound", "supply_capacity"),
    "05_BUFFER_LOCATION.csv": ("nature_of_works", "up_to_buffer_sectors", "opposite_bound_required"),
    "06_PARAMETERS.csv": ("key", "value"),
    "07_PROJECT_DETAILS.csv": ("contract_number", "contract_description", "contract_award_date", "activity_type", "nature_of_activity", "contract_priority", "contract_completion_date", "planned_completion_date", "number_of_workfronts", "access_type", "number_of_maximum_access_per_week"),
    "08_ACTIVITY_DETAILS.csv": ("activity_id", "contract_number", "activity_type", "start_location_id", "end_location_id", "total_accesses", "planned_start_date", "predecessor_activity_id", "activity_priority"),
}


def load_ps1_instance(source: str | Path | Mapping[str, str | bytes]) -> PS1Instance:
    rows = {name: _read_source(source, name, columns) for name, columns in SCHEMAS.items()}
    lines = tuple(Line(r["line_code"], r["line_name"]) for r in rows["01_LINES.csv"])
    stations = tuple(Station(r["station_id"], r["line_code"], _int(r, "seq"), _bool(r, "is_interchange")) for r in rows["02_STATIONS.csv"])
    sectors = tuple(Sector(r["sector_id"], r["line_code"], r["from_station_id"], r["to_station_id"], _int(r, "seq"), _bool(r, "is_shared")) for r in rows["03_SECTORS.csv"])
    locations = tuple(LocationSupply(r["location_id"], r["location_kind"], r["line_code"], r["bound"], _int(r, "supply_capacity")) for r in rows["04_LOCATION_SUPPLY.csv"])
    buffers = tuple(BufferRule(r["nature_of_works"], _int(r, "up_to_buffer_sectors"), _bool(r, "opposite_bound_required")) for r in rows["05_BUFFER_LOCATION.csv"])
    projects = tuple(Project(r["contract_number"], r["contract_description"], _date(r, "contract_award_date"), r["activity_type"], r["nature_of_activity"], _int(r, "contract_priority"), _date(r, "contract_completion_date"), _date(r, "planned_completion_date"), _int(r, "number_of_workfronts"), r["access_type"], _int(r, "number_of_maximum_access_per_week")) for r in rows["07_PROJECT_DETAILS.csv"])
    activities = tuple(Activity(r["activity_id"], r["contract_number"], r["activity_type"], r["start_location_id"], r["end_location_id"], _decimal(r, "total_accesses"), _date(r, "planned_start_date"), r["predecessor_activity_id"] or None, _int(r, "activity_priority")) for r in rows["08_ACTIVITY_DETAILS.csv"])
    parameters = _unique(rows["06_PARAMETERS.csv"], "key", "parameter")

    line_map = _unique_objects(lines, "line_code", "line")
    location_map = _unique_objects(locations, "location_id", "location")
    buffer_map = _unique_objects(buffers, "nature_of_works", "buffer rule")
    project_map = _unique_objects(projects, "contract_number", "project")
    activity_map = _unique_objects(activities, "activity_id", "activity")
    station_lines = {code: tuple(sorted((s for s in stations if s.line_code == code), key=lambda x: x.seq)) for code in line_map}
    sector_lines = {code: tuple(sorted((s for s in sectors if s.line_code == code), key=lambda x: x.seq)) for code in line_map}
    _validate_relations(line_map, station_lines, sector_lines, location_map, buffer_map, project_map, activity_map)
    try:
        horizon_start = date.fromisoformat(parameters["horizon_start"]["value"])
        horizon_weeks = int(parameters["horizon_weeks"]["value"])
    except (KeyError, ValueError) as exc:
        raise PS1DataError("parameters require ISO horizon_start and positive integer horizon_weeks") from exc
    if horizon_weeks <= 0:
        raise PS1DataError("horizon_weeks must be positive")
    return PS1Instance(lines, stations, sectors, locations, buffers, projects, activities, horizon_start, horizon_weeks, MappingProxyType(line_map), MappingProxyType(station_lines), MappingProxyType(sector_lines), MappingProxyType(location_map), MappingProxyType(buffer_map), MappingProxyType(project_map), MappingProxyType(activity_map))


load_instance = load_ps1_instance


def _read_source(source: str | Path | Mapping[str, str | bytes], name: str, expected: tuple[str, ...]) -> list[dict[str, str]]:
    if isinstance(source, Mapping):
        if name not in source:
            raise PS1DataError(f"missing required file: {name}")
        payload = source[name]
        try:
            text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        except UnicodeDecodeError as exc:
            raise PS1DataError(f"{name}: file is not valid UTF-8") from exc
        handle = io.StringIO(text, newline="")
    else:
        path = Path(source) / name
        if not path.is_file():
            raise PS1DataError(f"missing required file: {name}")
        handle = path.open(encoding="utf-8-sig", newline="")
    with handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected:
            raise PS1DataError(f"{name}: schema does not match the published columns")
        result = list(reader)
        for row_number, row in enumerate(result, start=2):
            if None in row or set(row) != set(expected):
                raise PS1DataError(f"{name}: row {row_number} has extra or missing columns")
            row["__row__"] = str(row_number)
    if not result:
        raise PS1DataError(f"{name}: file must contain data rows")
    if any(value is None for row in result for value in row.values()):
        raise PS1DataError(f"{name}: malformed row")
    return result


def _int(row: Mapping[str, str], key: str) -> int:
    try:
        return int(row[key])
    except ValueError as exc:
        raise PS1DataError(f"row {row.get('__row__', '?')}: invalid integer field {key}") from exc


def _bool(row: Mapping[str, str], key: str) -> bool:
    if row[key] not in {"0", "1"}:
        raise PS1DataError(f"row {row.get('__row__', '?')}: invalid Boolean field {key}")
    return row[key] == "1"


def _date(row: Mapping[str, str], key: str) -> date:
    try:
        return date.fromisoformat(row[key])
    except ValueError as exc:
        raise PS1DataError(f"row {row.get('__row__', '?')}: invalid ISO date field {key}") from exc


def _decimal(row: Mapping[str, str], key: str) -> Decimal:
    try:
        value = Decimal(row[key])
    except InvalidOperation as exc:
        raise PS1DataError(f"row {row.get('__row__', '?')}: invalid decimal field {key}") from exc
    if not value.is_finite() or value <= 0:
        raise PS1DataError(f"row {row.get('__row__', '?')}: {key} must be a finite positive number")
    return value


def _unique(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row[key]
        if not value or value in result:
            raise PS1DataError(f"invalid or duplicate {label} id: {value!r}")
        result[value] = row
    return result


def _unique_objects(rows: tuple, key: str, label: str) -> dict:
    result = {}
    for row in rows:
        value = getattr(row, key)
        if not value or value in result:
            raise PS1DataError(f"invalid or duplicate {label} id: {value!r}")
        result[value] = row
    return result


def _validate_relations(lines, stations_by_line, sectors_by_line, locations, buffers, projects, activities) -> None:
    for line, stations in stations_by_line.items():
        if [s.seq for s in stations] != list(range(1, len(stations) + 1)):
            raise PS1DataError(f"{line}: station seq must be contiguous from 1")
    for line, sectors in sectors_by_line.items():
        station_ids = {s.station_id for s in stations_by_line[line]}
        sequence = [s.seq for s in sectors]
        if sequence != list(range(min(sequence), max(sequence) + 1)):
            raise PS1DataError(f"{line}: sector seq must be contiguous")
        for sector in sectors:
            if sector.from_station_id not in station_ids or sector.to_station_id not in station_ids:
                raise PS1DataError(f"{sector.sector_id}: station foreign key is invalid")
    expected_locations = set()
    for line, sectors in sectors_by_line.items():
        for bound in ("EB", "WB"):
            expected_locations.update(f"{s.sector_id}:{bound}" for s in sectors)
            expected_locations.update(f"PLAT:{line}:{s.station_id}:{bound}" for s in stations_by_line[line])
    if set(locations) != expected_locations:
        raise PS1DataError("location supply does not exactly cover all tunnel/platform locations and bounds")
    for project in projects.values():
        if project.nature_of_activity not in buffers:
            raise PS1DataError(f"{project.contract_number}: unknown buffer nature")
        if project.access_type not in {"PM", "PC", "C"} or project.contract_priority not in {1, 2, 3}:
            raise PS1DataError(f"{project.contract_number}: invalid access type or priority")
    for activity in activities.values():
        project = projects.get(activity.contract_number)
        if project is None or project.activity_type != activity.activity_type:
            raise PS1DataError(f"{activity.activity_id}: invalid project/type foreign key")
        if activity.start_location_id not in locations or activity.end_location_id not in locations:
            raise PS1DataError(f"{activity.activity_id}: unknown endpoint location")
        start, end = locations[activity.start_location_id], locations[activity.end_location_id]
        if start.line_code != end.line_code or start.bound != end.bound:
            raise PS1DataError(f"{activity.activity_id}: endpoints must share line and bound")
        if activity.activity_priority not in {1, 2, 3}:
            raise PS1DataError(f"{activity.activity_id}: invalid priority")
        if activity.predecessor_activity_id and activity.predecessor_activity_id not in activities:
            raise PS1DataError(f"{activity.activity_id}: unknown predecessor")
