"""SMRT maintenance API. Core planning works without Gemini."""
from __future__ import annotations

import datetime as dt
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

try:
    from . import database, solver, gemini_config, planning_comparison, lta_reference
except ImportError:
    import database
    import solver
    import gemini_config
    import planning_comparison
    import lta_reference

UTC = dt.timezone.utc
SGT = dt.timezone(dt.timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent
PRIORITIES = ("Urgent", "High", "Medium", "Low")
STATUSES = ("Done", "Error", "Delay", "In progress", "Not started")
STATUS_COLORS = {"Done": "Green", "Error": "Red", "Delay": "Orange", "In progress": "Blue", "Not started": "Black"}
LOCAL_UI_ORIGINS = {"http://localhost:8501", "http://127.0.0.1:8501"}


def load_json_db(name: str) -> Dict[str, Any]:
    path = BASE_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


MAINTENANCE_DB = load_json_db("maintenance_db.json")
STATIONS_DB = load_json_db("stations_db.json")
try:
    LTA_REFERENCE = lta_reference.load_reference()
except (OSError, ValueError, KeyError):
    LTA_REFERENCE = None
database.init_db()
app = FastAPI(title="SMRT Railway Maintenance Backend API", version="5.0")
app.add_middleware(CORSMiddleware, allow_origins=sorted(LOCAL_UI_ORIGINS),
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)


def required_text(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value.strip()


def skills_field(value: Optional[List[str]]) -> Optional[List[str]]:
    if value is not None and (not value or any(not item.strip() for item in value)):
        raise ValueError("must contain nonblank values")
    return [item.strip() for item in value] if value is not None else None


class JobInput(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    line: str = Field(min_length=1)
    track: str = Field(min_length=1)
    deadline: dt.datetime
    priority: Optional[str] = None
    duration_mins: Optional[int] = Field(default=None, ge=1, le=270)
    required_skills: Optional[List[str]] = None
    engineers_needed: Optional[int] = Field(default=None, ge=1, le=10)
    assigned_engineer_ids: Optional[List[int]] = None
    station_code: Optional[str] = None
    catalog_category: Optional[str] = None
    catalog_activity: Optional[str] = None
    created_by: str = "Planner"

    _text = field_validator("name", "description", "line", "track", "created_by")(required_text)
    _catalog_text = field_validator("catalog_category", "catalog_activity")(lambda value: required_text(value) if value is not None else None)
    _station_text = field_validator("station_code")(lambda value: required_text(value).upper() if value is not None else None)
    _skills = field_validator("required_skills")(skills_field)

    @model_validator(mode="after")
    def complete_catalog_pair(self):
        if (self.catalog_category is None) != (self.catalog_activity is None):
            raise ValueError("catalog_category and catalog_activity must be supplied together")
        return self


class InsertionDemoInput(BaseModel):
    scenario: Literal["fits", "no_capacity"] = "fits"


class JobPatch(BaseModel):
    updated_by: str
    reason: str
    priority: Optional[str] = None
    assigned_engineer_ids: Optional[List[int]] = None
    scheduled_start: Optional[dt.datetime] = None
    duration_mins: Optional[int] = Field(default=None, ge=1, le=270)
    required_skills: Optional[List[str]] = None
    engineers_needed: Optional[int] = Field(default=None, ge=1, le=10)
    line: Optional[str] = None
    track: Optional[str] = None
    station_code: Optional[str] = None

    _text = field_validator("updated_by", "reason")(required_text)
    _location_text = field_validator("line", "track")(lambda value: required_text(value) if value is not None else None)
    _station_text = field_validator("station_code")(lambda value: required_text(value).upper() if value is not None else None)
    _skills = field_validator("required_skills")(skills_field)


class DeletePayload(BaseModel):
    deleted_by: str
    reason: str
    _text = field_validator("deleted_by", "reason")(required_text)


class ApprovalPayload(BaseModel):
    approved: bool
    approved_by: str
    reason: Optional[str] = None
    override_start_min: Optional[int] = Field(default=None, ge=0, le=269)
    override_priority: Optional[str] = None
    override_engineers: Optional[List[int]] = None
    _approver = field_validator("approved_by")(required_text)


class ChecklistUpdate(BaseModel):
    status: str
    updated_by: str
    reason: Optional[str] = None
    updated_repair_time_mins: Optional[int] = Field(default=None, ge=1, le=270)


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def aware_utc(value: dt.datetime | str) -> dt.datetime:
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(400, "Timestamps must include a timezone offset, for example +08:00.")
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def from_db(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def to_db(value: dt.datetime) -> dt.datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def clean_priority(value: str) -> str:
    result = next((item for item in PRIORITIES if item.casefold() == value.strip().casefold()), None)
    if not result:
        raise HTTPException(400, f"priority must be one of {list(PRIORITIES)}")
    return result


def normalized_skills(values: List[str]) -> set[str]:
    return {value.strip().casefold() for value in values}


def job_skills(job: database.RepairJob) -> List[str]:
    try:
        value = json.loads(job.required_skills or "[]")
    except json.JSONDecodeError:
        value = []
    return value if isinstance(value, list) else []


def catalog_entries() -> List[Dict[str, Any]]:
    result = []
    for category, activities in MAINTENANCE_DB.get("maintenance_catalog", {}).items():
        # The supplied production catalog is a list of activities. Accept the
        # earlier one-record-per-category shape as well for data portability.
        if isinstance(activities, dict):
            activities = [{"activity": activities.get("name", category.replace("_", " ").title()),
                           "type": activities.get("type", "Corrective"), **activities}]
        for activity in activities:
            if isinstance(activity, dict):
                result.append({"category": category, **activity})
    return result


def network_lines() -> List[str]:
    return list(STATIONS_DB.get("MRT_Lines", {})) + list(STATIONS_DB.get("LRT_Networks", {}))


def _line_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def canonical_line(value: str, reject_unknown: bool = False) -> str:
    """Resolve display names, punctuation variants, and parenthesised codes."""
    supplied = _line_token(value)
    supplied_base = _line_token(re.sub(r"\s*\([^)]*\)\s*$", "", value).strip())
    known_codes = {
        "ns": "northsouthline", "nsl": "northsouthline",
        "ew": "eastwestline", "ewl": "eastwestline",
        "ne": "northeastline", "nel": "northeastline",
        "cc": "circleline", "ccl": "circleline",
        "dt": "downtownline", "dtl": "downtownline",
        "te": "thomsoneastcoastline", "tel": "thomsoneastcoastline",
        "bp": "bukitpanjanglrt", "bplrt": "bukitpanjanglrt",
        "sk": "sengkanglrt", "sklrt": "sengkanglrt",
        "pg": "punggollrt", "pglrt": "punggollrt",
    }
    for line in network_lines():
        base = re.sub(r"\s*\([^)]*\)\s*$", "", line).strip()
        base_token = _line_token(base)
        codes = re.findall(r"\(([^)]*)\)", line)
        aliases = {_line_token(line), base_token, *(_line_token(code) for code in codes)}
        for code in codes:
            compact = _line_token(code)
            if compact.endswith("lrt"):
                aliases.add(compact[:-3])
            elif compact.endswith("l"):
                aliases.add(compact[:-1])
        if supplied in aliases or supplied_base == base_token or known_codes.get(supplied) == base_token:
            return line
    if reject_unknown and network_lines():
        raise HTTPException(400, f"Unknown rail line '{value}'. Select a line returned by GET /catalog/.")
    return value.strip()


def station_catalog() -> List[Dict[str, Any]]:
    result = []
    for network in ("MRT_Lines", "LRT_Networks"):
        for line, stations in STATIONS_DB.get(network, {}).items():
            for station in stations if isinstance(stations, list) else []:
                if not isinstance(station, dict) or not station.get("name") or not station.get("code"):
                    continue
                result.append({
                    "name": str(station["name"]).strip(),
                    "code": str(station["code"]).strip().upper(),
                    "line": canonical_line(line),
                    "interchange": bool(station.get("interchange")),
                })
    if LTA_REFERENCE:
        return lta_reference.enrich_station_catalog(result, LTA_REFERENCE)["stations"]
    return [{**row, "reference_status": "unverified"} for row in result]


def _station_name_hits(track_input: str, stations: List[Dict[str, Any]]) -> List[str]:
    """Return non-overlapping station names, preferring the longest at each span."""
    names = sorted({station["name"] for station in stations}, key=lambda value: (-len(value), value))
    occupied: List[tuple[int, int]] = []
    hits: List[str] = []
    for name in names:
        name_pattern = r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", name))
        pattern = rf"(?<![A-Za-z0-9]){name_pattern}(?![A-Za-z0-9])"
        for match in re.finditer(pattern, track_input, re.I):
            span = match.span()
            if any(max(span[0], start) < min(span[1], end) for start, end in occupied):
                continue
            occupied.append(span)
            hits.append(name)
    return hits


def resolve_station_location(line_name: str, track_input: str,
                             explicit_station_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Validate recognized station metadata while allowing unknown depot/train text."""
    selected_line = canonical_line(line_name, reject_unknown=True)
    stations = station_catalog()
    by_code = {station["code"]: station for station in stations}
    explicit = None
    if explicit_station_code:
        code = explicit_station_code.strip().upper()
        explicit = by_code.get(code)
        if explicit is None:
            raise HTTPException(400, f"Unknown station_code '{code}'. Select a code returned by GET /catalog/.")
        if canonical_line(explicit["line"]) != selected_line:
            raise HTTPException(
                400, f"Station {code} ({explicit['name']}) belongs to {explicit['line']}, not {selected_line}.",
            )

    code_hits = []
    for station in stations:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(station['code'])}(?![A-Za-z0-9])",
                     track_input, re.I):
            code_hits.append(station)
    wrong_codes = [station for station in code_hits if canonical_line(station["line"]) != selected_line]
    if wrong_codes:
        station = wrong_codes[0]
        raise HTTPException(
            400, f"Track references {station['code']} ({station['name']}) on {station['line']}, not {selected_line}.",
        )

    name_entries = []
    for name in _station_name_hits(track_input, stations):
        candidates = [station for station in stations if station["name"].casefold() == name.casefold()]
        matching = [station for station in candidates if canonical_line(station["line"]) == selected_line]
        if not matching:
            station = candidates[0]
            raise HTTPException(
                400, f"Track references {name}, which is not a station on {selected_line}.",
            )
        name_entries.append(matching[0])

    detected = code_hits + name_entries
    detected_keys = {(station["name"].casefold(), station["code"]) for station in detected}
    if len(detected_keys) > 1:
        raise HTTPException(400, "Track references more than one station; select one station location.")
    detected_station = detected[0] if detected else None
    if explicit and detected_station and explicit["name"].casefold() != detected_station["name"].casefold():
        raise HTTPException(
            400, f"station_code {explicit['code']} does not match station text '{detected_station['name']}'.",
        )
    return explicit or detected_station


def match_station_info(line_name: str, track_input: str,
                       explicit_station_code: Optional[str] = None) -> tuple[Optional[str], bool]:
    station = resolve_station_location(line_name, track_input, explicit_station_code)
    return ((station["code"], station["interchange"]) if station else (None, False))


def job_location_metadata(job: database.RepairJob) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        station = resolve_station_location(job.line, job.track, job.station_code)
        return station, None
    except HTTPException as exc:
        message = str(exc.detail)
        return None, f"Location conflict: {message} Correct the line, track, or station code before planning."


def require_valid_job_location(job: database.RepairJob) -> None:
    _, warning = job_location_metadata(job)
    if warning:
        raise HTTPException(409, warning)


def get_gemini_client(credential=None):
    """Compatibility seam used by production assessment and isolated tests."""
    try:
        return gemini_config.create_client(credential)
    except Exception:
        return None


def validate_gemini_suggestion(suggestion: Any, entries: List[Dict[str, Any]],
                               rules_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply the same strict domain validation to production and connection tests."""
    if not isinstance(suggestion, dict):
        return None
    required_fields = {"category", "activity", "activity_type", "required_skills",
                       "priority", "effort_level", "duration_mins", "engineers_needed"}
    if not required_fields <= suggestion.keys():
        return None
    if not (isinstance(suggestion["category"], str)
            and isinstance(suggestion["activity"], str)
            and isinstance(suggestion["activity_type"], str)
            and isinstance(suggestion["priority"], str)):
        return None
    valid = next((entry for entry in entries
                  if entry["category"] == suggestion["category"]
                  and entry["activity"] == suggestion["activity"]), None)
    if valid is None:
        return None
    proposed_skills = suggestion["required_skills"]
    expected_skills = valid.get("required_skills", [])
    skills_valid = (
        isinstance(proposed_skills, list) and bool(proposed_skills)
        and len(proposed_skills) == len(expected_skills)
        and all(isinstance(skill, str) and skill.strip() for skill in proposed_skills)
        and normalized_skills(proposed_skills) == normalized_skills(expected_skills)
    )
    if not (skills_valid
            and suggestion["priority"] in PRIORITIES
            and type(suggestion["duration_mins"]) is int and 1 <= suggestion["duration_mins"] <= 270
            and type(suggestion["engineers_needed"]) is int and 1 <= suggestion["engineers_needed"] <= 10
            and type(suggestion["effort_level"]) is int and 1 <= suggestion["effort_level"] <= 5
            and suggestion["activity_type"] in {"Preventive", "Corrective"}):
        return None
    accepted = dict(rules_result)
    accepted.update(
        matched_category=valid["category"], matched_activity=valid["activity"],
        activity_type=suggestion["activity_type"], required_skills=proposed_skills,
        priority=suggestion["priority"], effort_level=suggestion["effort_level"],
        duration_mins=suggestion["duration_mins"], engineers_needed=suggestion["engineers_needed"],
        assessment_source="gemini-validated",
        assessment_rationale=(
            "Gemini supplied a complete assessment whose category, activity, full skill list, "
            "type, priority, effort, duration and headcount passed local catalog and bounds "
            "validation. Scheduling safety constraints remain rules-based."
        ),
    )
    return accepted


def gemini_prompt(job: JobInput, entries: List[Dict[str, Any]], interchange: bool) -> str:
    choices = [{"category": entry["category"], "activity": entry["activity"],
                "activity_type": entry.get("type", "Corrective"),
                "required_skills": entry.get("required_skills", [])} for entry in entries]
    return (
        f"Choose exactly one catalog item for this synthetic or operator-supplied maintenance "
        f"request. Name: {job.name}. Description: {job.description}. Line: {job.line}. Track: "
        f"{job.track}. Deadline: {aware_utc(job.deadline).isoformat()}. Current UTC time: "
        f"{dt.datetime.now(UTC).replace(second=0, microsecond=0).isoformat()}. Interchange: "
        f"{interchange}. Use the deadline and interchange impact when selecting priority. Return "
        "one JSON object with category, activity, "
        "activity_type (Preventive or Corrective), required_skills (the complete exact catalog "
        "list), priority (Urgent, High, Medium, or Low), effort_level (integer 1-5), duration_mins "
        f"(integer 1-270), and engineers_needed (integer 1-10). Catalog: {json.dumps(choices)}"
    )


def safe_provider_failure(error: Exception) -> Dict[str, Any]:
    """Reduce provider exceptions to an allowlisted category without using their text."""
    raw_code = getattr(error, "code", None)
    code = raw_code if type(raw_code) is int else None
    raw_status = getattr(error, "status", None)
    status = raw_status if isinstance(raw_status, str) else None
    known_statuses = {
        "RESOURCE_EXHAUSTED": (429, "quota_or_billing"),
        "UNAUTHENTICATED": (401, "auth_or_access"),
        "PERMISSION_DENIED": (403, "auth_or_access"),
        "NOT_FOUND": (404, "model_unavailable"),
    }
    if code == 429 or status == "RESOURCE_EXHAUSTED":
        code, category = 429, "quota_or_billing"
    elif code in {401, 403} or status in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
        code = code if code in {401, 403} else known_statuses[status][0]
        category = "auth_or_access"
    elif code == 404 or status == "NOT_FOUND":
        code, category = 404, "model_unavailable"
    else:
        return {"result": "provider_failed", "assessment": None,
                "provider_error": "provider_failed"}
    return {"result": "provider_failed", "assessment": None,
            "provider_error": category, "provider_status": code}


def attempt_gemini_assessment(client, job: JobInput, entries: List[Dict[str, Any]],
                              rules_result: Dict[str, Any], interchange: bool = False,
                              model_name: Optional[str] = None) -> Dict[str, Any]:
    """Call Gemini once and return a safe outcome without provider exception text."""
    try:
        response = client.models.generate_content(
            model=model_name or gemini_config.get_model_name(),
            contents=gemini_prompt(job, entries, interchange),
            config={"response_mime_type": "application/json"},
        )
    except Exception as error:
        return safe_provider_failure(error)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    try:
        raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        suggestion = json.loads(raw)
    except (AttributeError, json.JSONDecodeError, TypeError):
        return {"result": "validation_fallback", "assessment": None}
    try:
        validated = validate_gemini_suggestion(suggestion, entries, rules_result)
    except (KeyError, TypeError, ValueError):
        validated = None
    if validated is None:
        return {"result": "validation_fallback", "assessment": None}
    return {"result": "success", "assessment": validated}


def deterministic_assessment(job: JobInput, interchange: bool) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    entries = catalog_entries()
    if not entries:
        raise HTTPException(503, "The maintenance catalog is empty. Restore backend/maintenance_db.json before creating jobs.")
    haystack = f"{job.name} {job.description}".casefold()
    words = set(re.findall(r"[a-z0-9]+", haystack))
    ranked = []
    for entry in entries:
        activity = entry["activity"].casefold()
        activity_words = set(re.findall(r"[a-z0-9]+", activity))
        score = (2.0 if activity in haystack else 0.0) + len(words & activity_words) / max(1, len(activity_words))
        score += SequenceMatcher(None, haystack, activity).ratio() * 0.25
        ranked.append((score, entry))
    score, selected = max(ranked, key=lambda item: item[0])
    hours = (aware_utc(job.deadline) - dt.datetime.now(UTC)).total_seconds() / 3600
    priority = "Urgent" if hours <= 24 else "High" if hours <= 168 or interchange else "Medium"
    result = {"matched_category": selected["category"], "matched_activity": selected["activity"],
              "activity_type": selected.get("type", "Corrective"), "required_skills": selected.get("required_skills", []),
              "priority": priority, "effort_level": 3,
              "duration_mins": selected.get("duration_mins", 60 if selected.get("type") == "Preventive" else 90),
              "engineers_needed": selected.get("engineers_needed", 2), "assessment_source": "rules",
              "assessment_rationale": f"Rules matched '{selected['activity']}' using request terms (score {score:.2f}); priority reflects deadline" + (" and interchange impact." if interchange else ".")}
    return entries, result


def catalog_selected_assessment(job: JobInput, interchange: bool) -> Dict[str, Any]:
    """Anchor domain fields to an exact operator-selected catalog pair."""
    entries, rules_result = deterministic_assessment(job, interchange)
    selected = next(
        (entry for entry in entries
         if entry["category"] == job.catalog_category
         and entry["activity"] == job.catalog_activity),
        None,
    )
    if selected is None:
        raise HTTPException(
            400,
            "catalog_category and catalog_activity must exactly match one pair returned by GET /catalog/.",
        )
    selected_skills = selected.get("required_skills", [])
    if (job.required_skills is not None
            and normalized_skills(job.required_skills) != normalized_skills(selected_skills)):
        raise HTTPException(400, "required_skills must match the selected catalog activity.")
    activity_type = selected.get("type", "Corrective")
    return {
        **rules_result,
        "matched_category": selected["category"],
        "matched_activity": selected["activity"],
        "activity_type": activity_type,
        "required_skills": list(selected_skills),
        "duration_mins": selected.get(
            "duration_mins", 60 if activity_type == "Preventive" else 90
        ),
        "engineers_needed": selected.get("engineers_needed", 2),
        "assessment_source": "catalog-selected",
        "assessment_rationale": (
            f'Catalog-selected activity "{selected["activity"]}" from category '
            f'"{selected["category"]}" anchored type and required skills. Priority reflects '
            "the deadline and interchange rule; duration and headcount remain planner-reviewable."
        ),
    }


def rules_assessment(job: JobInput, interchange: bool) -> Dict[str, Any]:
    entries, result = deterministic_assessment(job, interchange)
    client = get_gemini_client()
    if client:
        attempt = attempt_gemini_assessment(client, job, entries, result, interchange)
        if attempt["result"] == "success":
            result = attempt["assessment"]
    return result


def engineer_payload(engineer: database.Engineer) -> Dict[str, Any]:
    return {"id": engineer.id, "name": engineer.name, "skills": [s.skill_name for s in engineer.skills],
            "is_available": bool(engineer.is_available), "years_of_experience": engineer.years_of_experience}


def persisted_activity(job: database.RepairJob) -> Optional[str]:
    rationale = job.assessment_rationale or ""
    selected = re.match(r'^Catalog-selected activity "([^"]+)"', rationale)
    if selected:
        return selected.group(1)
    matches = [entry["activity"] for entry in catalog_entries()
               if entry["category"] == job.category
               and entry.get("type", "Corrective") == job.activity_type
               and normalized_skills(entry.get("required_skills", [])) == normalized_skills(job_skills(job))]
    return matches[0] if len(matches) == 1 else None


def job_payload(job: database.RepairJob) -> Dict[str, Any]:
    station, location_warning = job_location_metadata(job)
    return {"job_id": job.id, "name": job.name, "description": job.description, "line": job.line, "track": job.track,
            "deadline": from_db(job.deadline).isoformat() if job.deadline else None, "priority": job.priority,
            "required_skills": job_skills(job), "duration_mins": job.duration_mins, "engineers_needed": job.engineers_needed,
            "assigned_engineers": [e.name for e in job.assigned_engineers], "assigned_engineer_ids": [e.id for e in job.assigned_engineers],
            "status": job.status, "is_approved": bool(job.is_approved),
            "scheduled_start": from_db(job.scheduled_start).isoformat() if job.scheduled_start else None,
            "scheduled_end": from_db(job.scheduled_end).isoformat() if job.scheduled_end else None,
            "category": job.category, "activity": persisted_activity(job), "activity_type": job.activity_type,
            "assessment_source": job.assessment_source, "assessment_rationale": job.assessment_rationale,
            "rationale": job.assessment_rationale, "assignment_conflict": job.assignment_conflict,
            "assignment_locked": bool(job.assignment_locked), "time_locked": bool(job.time_locked),
            "station_code": job.station_code, "station_name": station["name"] if station else None,
            "is_interchange": bool(job.is_interchange), "location_warning": location_warning}


def get_engineers(db: Session, ids: List[int]) -> List[database.Engineer]:
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "Engineer IDs must be unique.")
    found = db.query(database.Engineer).filter(database.Engineer.id.in_(ids)).all() if ids else []
    if len(found) != len(ids):
        raise HTTPException(404, "One or more engineer IDs do not exist.")
    lookup = {e.id: e for e in found}
    return [lookup[value] for value in ids]


def qualified_team(engineers: List[database.Engineer], required: List[str], count: int) -> None:
    if len(engineers) != count:
        raise HTTPException(409, f"The plan requires exactly {count} engineers.")
    needed = normalized_skills(required)
    for engineer in engineers:
        if not engineer.is_available:
            raise HTTPException(409, f"{engineer.name} is not currently available.")
        missing = sorted(needed - normalized_skills([s.skill_name for s in engineer.skills]))
        if missing:
            raise HTTPException(409, f"{engineer.name} lacks required skills: {', '.join(missing)}.")


def auto_team(db: Session, required: List[str], count: int) -> tuple[List[database.Engineer], Optional[str]]:
    needed = normalized_skills(required)
    candidates = [e for e in db.query(database.Engineer).filter(database.Engineer.is_available.is_(True)).all()
                  if needed <= normalized_skills([s.skill_name for s in e.skills])]
    candidates.sort(key=lambda e: (-(e.years_of_experience or 0), e.name))
    if len(candidates) < count:
        return [], f"Only {len(candidates)} available engineers have every required skill; {count} are needed. Assignments were left empty for planner review."
    return candidates[:count], None


def validate_plan(db: Session, job: database.RepairJob, start: dt.datetime, duration: int,
                  engineers: List[database.Engineer], required: List[str], count: int,
                  allow_past: bool = False) -> dt.datetime:
    start = aware_utc(start)
    if not allow_past and start < dt.datetime.now(UTC):
        raise HTTPException(409, "Scheduled work must start in the future.")
    end = start + dt.timedelta(minutes=duration)
    local_start, local_end = start.astimezone(SGT), end.astimezone(SGT)
    window_start = local_start.replace(hour=0, minute=30, second=0, microsecond=0)
    window_end = local_start.replace(hour=5, minute=0, second=0, microsecond=0)
    if local_start < window_start or local_end > window_end or local_end.date() != local_start.date():
        raise HTTPException(409, "Work must fit within one 00:30-05:00 Singapore maintenance window.")
    if end > from_db(job.deadline):
        raise HTTPException(409, "Scheduled work would finish after its deadline.")
    qualified_team(engineers, required, count)
    others = db.query(database.RepairJob).filter(database.RepairJob.id != job.id,
        database.RepairJob.status != "Done", database.RepairJob.scheduled_start.isnot(None)).all()
    engineer_ids = {e.id for e in engineers}
    for other in others:
        other_start, other_end = from_db(other.scheduled_start), from_db(other.scheduled_end)
        if not other_start or not other_end or not (start < other_end and other_start < end):
            continue
        if canonical_line(other.line) == canonical_line(job.line) and other.track.strip().casefold() == job.track.strip().casefold():
            raise HTTPException(409, f"Track conflicts with job {other.id} during the requested time.")
        overlap = engineer_ids & {e.id for e in other.assigned_engineers}
        if overlap:
            raise HTTPException(409, f"Engineer overlap with job {other.id}: {sorted(overlap)}.")
    return end


def add_audit(db: Session, action: str, actor: str, details: Dict[str, Any]) -> None:
    db.add(database.AuditLog(action=action, approved_by=actor,
                             details=json.dumps(details, default=str, sort_keys=True)))


@app.get("/ai/status", response_model=Dict[str, Any])
def ai_status():
    """Return configuration metadata only; credentials are never serialized."""
    return gemini_config.public_status()


@app.post("/ai/test", response_model=Dict[str, Any])
def test_ai_connection(request: Request):
    """Make one real, bounded Gemini call using synthetic data and no database writes."""
    origin = request.headers.get("origin")
    if origin and origin not in LOCAL_UI_ORIGINS:
        return JSONResponse(status_code=403, content={
            "result": "forbidden",
            "message": "AI testing is available only to the local Ngeebula interface.",
        })
    configuration = gemini_config.resolve_configuration()
    credential = configuration.credential
    model_name = configuration.model
    if credential is None:
        return JSONResponse(status_code=400, content={
            "result": "not_configured", "model": model_name,
            "message": "Gemini is not configured for this Windows user.",
        })
    client = get_gemini_client(credential)
    if client is None:
        return JSONResponse(status_code=502, content={
            "result": "provider_failed", "source": credential.source,
            "model": model_name,
            "message": "The Gemini client could not be initialized.",
        })
    line = network_lines()[0] if network_lines() else "North-South Line (NSL)"
    synthetic = JobInput(
        name="Synthetic rail inspection connectivity test",
        description="Inspect a rail segment for wear; this is a connectivity test and is not saved.",
        line=line, track="Synthetic test track",
        deadline=dt.datetime.now(UTC) + dt.timedelta(days=14),
        created_by="AI connection test",
    )
    entries, rules_result = deterministic_assessment(synthetic, False)
    attempt = attempt_gemini_assessment(
        client, synthetic, entries, rules_result, model_name=model_name
    )
    if attempt["result"] == "provider_failed":
        category = attempt.get("provider_error", "provider_failed")
        failure_messages = {
            "quota_or_billing": (
                "Gemini rejected the request because its quota or billing limit was reached. "
                "Check this project in Google AI Studio."
            ),
            "auth_or_access": (
                "Gemini rejected the API key or project access. Check the key and project "
                "permissions in Google AI Studio."
            ),
            "model_unavailable": (
                "The configured Gemini model was not found or is unavailable to this project. "
                "Check GEMINI_MODEL and project access."
            ),
            "provider_failed": (
                "Gemini could not complete the test request. Check the key, network, quota, "
                "and billing status."
            ),
        }
        content = {
            "result": "provider_failed", "provider_error": category,
            "source": credential.source, "model": model_name,
            "message": failure_messages[category],
        }
        if "provider_status" in attempt:
            content["provider_status"] = attempt["provider_status"]
        return JSONResponse(status_code=502, content={
            **content,
        })
    if attempt["result"] == "validation_fallback":
        return JSONResponse(status_code=422, content={
            "result": "validation_fallback", "source": credential.source,
            "model": model_name,
            "message": "Gemini responded, but its assessment did not pass the production catalog validation.",
        })
    assessment = attempt["assessment"]
    return {
        "result": "success", "source": credential.source, "model": model_name,
        "message": "Gemini responded and passed the production catalog validation.",
        "assessment": {
            "category": assessment["matched_category"],
            "activity": assessment["matched_activity"],
            "assessment_source": assessment["assessment_source"],
        },
    }


@app.get("/jobs/", response_model=List[Dict[str, Any]])
def list_jobs(db: Session = Depends(get_db)):
    return [job_payload(j) for j in db.query(database.RepairJob).order_by(database.RepairJob.id).all()]


@app.get("/engineers/", response_model=List[Dict[str, Any]])
def list_engineers(db: Session = Depends(get_db)):
    return [engineer_payload(e) for e in db.query(database.Engineer).order_by(database.Engineer.name).all()]


@app.get("/catalog/", response_model=Dict[str, Any])
def get_catalog(db: Session = Depends(get_db)):
    entries = catalog_entries()
    if not entries:
        raise HTTPException(503, "The maintenance catalog is empty. Restore backend/maintenance_db.json.")
    available = db.query(database.Engineer).filter(database.Engineer.is_available.is_(True)).all()
    enriched = []
    for entry in entries:
        needed = normalized_skills(entry.get("required_skills", []))
        qualified_count = sum(needed <= normalized_skills([skill.skill_name for skill in engineer.skills])
                              for engineer in available)
        enriched.append(entry | {"available_fully_qualified_engineers": qualified_count})
    catalog_skills = {s for entry in entries for s in entry.get("required_skills", [])}
    roster_skills = {skill.skill_name for engineer in db.query(database.Engineer).all() for skill in engineer.skills}
    return {"activities": enriched, "lines": network_lines(),
            "stations": station_catalog(), "skills": sorted(catalog_skills | roster_skills),
            "station_reference": lta_reference.reference_attribution(LTA_REFERENCE) if LTA_REFERENCE else None}


@app.post("/jobs/parse-and-create", response_model=Dict[str, Any])
def create_job(job_in: JobInput, db: Session = Depends(get_db)):
    deadline = aware_utc(job_in.deadline)
    if deadline <= dt.datetime.now(UTC):
        raise HTTPException(400, "deadline must be in the future")
    line = canonical_line(job_in.line, reject_unknown=True)
    station = resolve_station_location(line, job_in.track, job_in.station_code)
    station_code = station["code"] if station else None
    interchange = station["interchange"] if station else False
    explicit_catalog = job_in.catalog_category is not None
    assessment = (catalog_selected_assessment(job_in, interchange)
                  if explicit_catalog else rules_assessment(job_in, interchange))
    priority = clean_priority(job_in.priority or assessment["priority"])
    skills = (assessment["required_skills"] if explicit_catalog
              else job_in.required_skills or assessment["required_skills"])
    duration, count = job_in.duration_mins or assessment["duration_mins"], job_in.engineers_needed or assessment["engineers_needed"]
    if job_in.assigned_engineer_ids is not None:
        team, conflict = get_engineers(db, job_in.assigned_engineer_ids), None
        qualified_team(team, skills, count)
    else:
        team, conflict = auto_team(db, skills, count)
    job = database.RepairJob(id=database.allocate_job_id(db), name=job_in.name, description=job_in.description, line=line, track=job_in.track,
        station_code=station_code, is_interchange=interchange, deadline=to_db(deadline), category=assessment["matched_category"],
        activity_type=assessment["activity_type"], priority=priority, effort_level=assessment["effort_level"], duration_mins=duration,
        required_skills=json.dumps(skills), engineers_needed=count, status="Not started", status_color="Black", is_approved=False,
        assessment_source=assessment["assessment_source"], assessment_rationale=assessment["assessment_rationale"],
        assignment_conflict=conflict,
        assignment_locked=job_in.assigned_engineer_ids is not None, time_locked=False, assigned_engineers=team)
    db.add(job); db.flush()
    add_audit(db, "Job created", job_in.created_by,
              {"job_id": job.id, "assignment_conflict": conflict,
               "location": {"line": line, "track": job_in.track,
                            "station_code": station_code,
                            "station_name": station["name"] if station else None}})
    db.commit(); db.refresh(job)
    rich = job_payload(job)
    return rich | {"job": rich, "result": "success", "assignment_conflict": conflict, "assessment": assessment}


@app.patch("/jobs/{job_id}", response_model=Dict[str, Any])
def update_job(job_id: int, payload: JobPatch, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter_by(id=job_id).first()
    if not job: raise HTTPException(404, "Job not found")
    if job.status != "Not started": raise HTTPException(409, "Only Not started jobs may be overridden.")
    before, fields = job_payload(job), payload.model_fields_set
    nullable_overrides = {"priority", "assigned_engineer_ids", "scheduled_start", "duration_mins",
                          "required_skills", "engineers_needed", "line", "track"}
    explicit_null = [name for name in nullable_overrides if name in fields and getattr(payload, name) is None]
    if explicit_null:
        raise HTTPException(400, f"Override fields cannot be null: {', '.join(sorted(explicit_null))}.")
    location_fields = fields & {"line", "track", "station_code"}
    new_line = canonical_line(payload.line, reject_unknown=True) if "line" in fields else job.line
    new_track = payload.track if "track" in fields else job.track
    station_override = (payload.station_code if "station_code" in fields
                        else None if location_fields else job.station_code)
    station = (resolve_station_location(new_line, new_track, station_override)
               if location_fields else None)
    new_station_code = station["code"] if station else (None if location_fields else job.station_code)
    new_interchange = station["interchange"] if station else (False if location_fields else bool(job.is_interchange))
    location_changed = bool(location_fields) and (
        canonical_line(new_line) != canonical_line(job.line)
        or new_track != job.track
        or new_station_code != job.station_code
    )
    if location_changed and "scheduled_start" in fields:
        raise HTTPException(400, "A location correction cannot include scheduled_start; save it, then replan.")
    priority = clean_priority(payload.priority) if "priority" in fields else job.priority
    required = payload.required_skills if "required_skills" in fields else job_skills(job)
    duration = payload.duration_mins if "duration_mins" in fields else job.duration_mins
    count = payload.engineers_needed if "engineers_needed" in fields else job.engineers_needed
    team = get_engineers(db, payload.assigned_engineer_ids) if "assigned_engineer_ids" in fields else list(job.assigned_engineers)
    requirements_changed = "required_skills" in fields or "engineers_needed" in fields
    conflict = job.assignment_conflict
    if "assigned_engineer_ids" in fields:
        qualified_team(team, required, count)
        conflict = None
    elif team:
        qualified_team(team, required, count)
        if requirements_changed:
            conflict = None
    elif requirements_changed:
        team, conflict = auto_team(db, required, count)
    start = (None if location_changed else
             aware_utc(payload.scheduled_start) if "scheduled_start" in fields
             else from_db(job.scheduled_start))
    if start:
        if not location_fields:
            require_valid_job_location(job)
        if not team: raise HTTPException(409, "A scheduled job must have its full qualified engineer team assigned.")
        end = validate_plan(db, job, start, duration, team, required, count)
    else: end = None
    job.priority, job.duration_mins, job.engineers_needed, job.required_skills = priority, duration, count, json.dumps(required)
    job.assigned_engineers = team
    job.assignment_conflict = conflict
    if location_fields:
        job.line, job.track = new_line, new_track
        job.station_code, job.is_interchange = new_station_code, new_interchange
    if "assigned_engineer_ids" in fields: job.assignment_locked = True
    if location_changed:
        job.time_locked = False
        job.scheduled_start_min = None
        job.scheduled_end_min = None
    elif "scheduled_start" in fields:
        job.time_locked = True
    job.scheduled_start, job.scheduled_end, job.is_approved = to_db(start) if start else None, to_db(end) if end else None, False
    db.flush(); after = job_payload(job)
    audit_details = {"job_id": job_id, "reason": payload.reason,
                     "before": before, "after": after}
    if location_fields:
        audit_details["location"] = {"line": new_line, "track": new_track,
                                     "station_code": new_station_code,
                                     "station_name": station["name"] if station else None}
    add_audit(db, "Job overridden", payload.updated_by, audit_details)
    db.commit()
    return after | {"status": "success", "job": after}


@app.delete("/jobs/{job_id}", response_model=Dict[str, Any])
def delete_job(job_id: int, payload: DeletePayload, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter_by(id=job_id).first()
    if not job: raise HTTPException(404, "Job not found")
    if job.status != "Not started":
        raise HTTPException(409, "Deletion policy permits only Not started work; retain active and completed work for operations history.")
    snapshot = job_payload(job)
    job.assigned_engineers = []; db.flush(); db.delete(job)
    add_audit(db, "Job deleted", payload.deleted_by, {"job_id": job_id, "reason": payload.reason, "snapshot": snapshot})
    db.commit()
    return {"status": "success", "deleted_job_id": job_id}


class ComparisonInput(BaseModel):
    scenario: Literal["joint_planning", "straightforward", "no_capacity"] = "joint_planning"


RoiMethod = Literal["manual_proxy", "priority_first_fit", "cp_sat"]
RoiValue = Annotated[float, Field(ge=0, le=100000000, allow_inf_nan=False, strict=True)]


class RoiInput(BaseModel):
    planning_shifts_per_month: float = Field(ge=0, le=10000, allow_inf_nan=False)
    minutes_per_cycle: Dict[RoiMethod, RoiValue]
    loaded_hourly_cost_sgd: float = Field(ge=0, le=100000, allow_inf_nan=False)
    initial_cost_sgd: Dict[RoiMethod, RoiValue]
    monthly_operating_cost_sgd: Dict[RoiMethod, RoiValue]
    baseline_method: Literal["manual_proxy", "priority_first_fit"] = "manual_proxy"

    @model_validator(mode="after")
    def complete_methods(self):
        if set(self.minutes_per_cycle) != {"manual_proxy", "priority_first_fit", "cp_sat"}:
            raise ValueError("Supply planning minutes for all three comparison approaches.")
        return self


@app.post("/schedule/compare", response_model=Dict[str, Any])
def compare_planning(payload: ComparisonInput):
    return planning_comparison.run_planning_comparison(payload.scenario)


@app.post("/schedule/roi", response_model=Dict[str, Any])
def planning_roi(payload: RoiInput):
    try:
        return planning_comparison.calculate_roi(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/schedule/readiness", response_model=Dict[str, Any])
def schedule_readiness(db: Session = Depends(get_db)):
    """Explain obvious blockers without solving, changing jobs or contacting AI."""
    candidates = [job for job in db.query(database.RepairJob).all()
                  if job.status == "Not started" and not job.is_approved and not job.time_locked]
    staff = db.query(database.Engineer).all()
    start, end = (solver.as_utc(value) for value in solver.next_window())
    checks = []
    for job in candidates:
        reasons = []
        _, location_warning = job_location_metadata(job)
        if location_warning:
            reasons.append({"code": "location", "message": location_warning, "action": "Correct location in Requests."})
        required = normalized_skills(job_skills(job))
        eligible = [person for person in staff if person.is_available
                    and required <= normalized_skills([skill.skill_name for skill in person.skills])]
        if not required:
            reasons.append({"code": "skills", "message": "Required skills are missing.", "action": "Confirm the repair requirements."})
        if len(eligible) < job.engineers_needed:
            reasons.append({"code": "crew", "message": f"{len(eligible)} available engineers hold every required skill; {job.engineers_needed} are needed.",
                            "action": "Review the qualified roster and requirements; do not substitute unqualified staff."})
        if job.assignment_locked:
            try:
                qualified_team(list(job.assigned_engineers), job_skills(job), job.engineers_needed)
            except HTTPException as exc:
                reasons.append({"code": "fixed_crew", "message": str(exc.detail), "action": "Review the saved crew selection."})
        latest = min(end, from_db(job.deadline)) if job.deadline else end
        if (latest - start).total_seconds() < job.duration_mins * 60:
            reasons.append({"code": "deadline", "message": "The full repair cannot finish before its deadline in the next planning window.",
                            "action": "Review the deadline and work scope with the operational team."})
        checks.append({"job_id": job.id, "name": job.name, "qualified_available": len(eligible),
                       "engineers_needed": job.engineers_needed, "issues": reasons})
    blocked = sum(bool(check["issues"]) for check in checks)
    return {"candidate_count": len(checks), "blocked_count": blocked, "checks": checks,
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "ready_for_solver": bool(checks) and blocked == 0,
            "explanation": "These are preliminary checks. Only generating a proposal checks all time, site and crew conflicts together."}


@app.post("/schedule/propose", response_model=Dict[str, Any])
def propose_schedule(db: Session = Depends(get_db)):
    all_jobs = db.query(database.RepairJob).all()
    candidates = [j for j in all_jobs if j.status == "Not started" and not j.is_approved and not j.time_locked]
    for candidate in candidates:
        require_valid_job_location(candidate)
    commitments = [j for j in all_jobs if j not in candidates and j.status != "Done" and j.scheduled_start and j.scheduled_end]
    jobs_data = [{"id": j.id, "name": j.name, "line": j.line, "track": j.track, "deadline": from_db(j.deadline),
                  "duration_mins": j.duration_mins, "priority": j.priority, "engineers_needed": j.engineers_needed,
                  "required_skills": job_skills(j), "status": j.status, "is_approved": bool(j.is_approved),
                  "scheduled_start": from_db(j.scheduled_start), "time_locked": bool(j.time_locked),
                  "assignment_locked": bool(j.assignment_locked), "assigned_engineer_ids": [e.id for e in j.assigned_engineers]}
                 for j in candidates]
    engineer_data = [engineer_payload(e) for e in db.query(database.Engineer).all()]
    commitments_data = [{"line": j.line, "track": j.track, "scheduled_start": from_db(j.scheduled_start),
                         "scheduled_end": from_db(j.scheduled_end), "assigned_engineer_ids": [e.id for e in j.assigned_engineers]}
                        for j in commitments]
    result = solver.solve_mrt_schedule(jobs_data, engineer_data, commitments=commitments_data)
    if result.get("status") != "success":
        raise HTTPException(409 if result.get("status") == "infeasible" else 400,
                            {"message": result.get("ai_explanation"), "warnings": result.get("warnings", [])})
    lookup = {j.id: j for j in candidates}
    # Remove stale candidate plans in-memory before validating the complete new
    # proposal. This lets a valid joint rearrangement replace the old schedule,
    # while committed/approved work remains visible as a hard constraint.
    for job in candidates:
        job.scheduled_start = None
        job.scheduled_end = None
        job.assigned_engineers = []
    for row in result["schedule"]:
        job = lookup[row["job_id"]]
        start, end = solver.as_utc(row["scheduled_start"]), solver.as_utc(row["scheduled_end"])
        team = get_engineers(db, [int(value) for value in row.get("assigned_engineers") or []])
        validate_plan(db, job, start, job.duration_mins, team, job_skills(job), job.engineers_needed)
        job.scheduled_start, job.scheduled_end = to_db(start), to_db(end)
        job.scheduled_start_min, job.scheduled_end_min, job.assigned_engineers = row["scheduled_start_min"], row["scheduled_end_min"], team
        job.assignment_conflict = None
    add_audit(db, "Schedule proposed", "OR-Tools planner",
              {"job_ids": [row["job_id"] for row in result["schedule"]],
               "preserved_job_ids": [job.id for job in commitments],
               "solver_status": result.get("solver_status")})
    db.commit()
    schedule = [job_payload(lookup[row["job_id"]]) for row in result["schedule"]]
    return {"status": "success", "options": [{"option_name": "OR-Tools recommended schedule", "schedule": schedule}],
            "base_schedule": schedule, "preserved_job_ids": [j.id for j in commitments],
            "window_start": result.get("window_start"), "window_end": result.get("window_end"),
            "solver_status": result.get("solver_status"), "warnings": result.get("warnings", []),
            "optimization_explanation": result.get("ai_explanation"),
            "ai_explanation": result.get("ai_explanation")}


def insertion_demo_row(*, job_id: str, name: str, track: str, deadline: dt.datetime,
                       duration: int, engineers_needed: int,
                       scheduled_start: Optional[dt.datetime] = None,
                       engineer_ids: Optional[List[int]] = None,
                       engineer_names: Optional[List[str]] = None,
                       approved: bool = False, activity: str = "Train door repair",
                       required_skills: Optional[List[str]] = None,
                       activity_type: str = "Corrective") -> Dict[str, Any]:
    scheduled_end = (scheduled_start + dt.timedelta(minutes=duration)
                     if scheduled_start else None)
    return {
        "job_id": job_id,
        "name": name,
        "description": "Synthetic planning illustration; no operational record is created.",
        "line": "North-South Line (NSL)",
        "track": track,
        "deadline": deadline.isoformat(),
        "priority": "High" if activity_type == "Corrective" else "Medium",
        "required_skills": required_skills or ["Mechanical"],
        "duration_mins": duration,
        "engineers_needed": engineers_needed,
        "assigned_engineers": engineer_names or [],
        "assigned_engineer_ids": engineer_ids or [],
        "status": "Not started",
        "is_approved": approved,
        "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
        "scheduled_end": scheduled_end.isoformat() if scheduled_end else None,
        "category": "rolling_stock",
        "activity": activity,
        "activity_type": activity_type,
        "assessment_source": "synthetic-demo",
        "assessment_rationale": "Fixed synthetic scenario for explaining constrained insertion.",
        "rationale": "Fixed synthetic scenario for explaining constrained insertion.",
        "assignment_conflict": None,
        "assignment_locked": approved,
        "time_locked": approved,
        "station_code": None,
        "is_interchange": False,
        "synthetic": True,
    }


@app.post("/schedule/insertion-demo", response_model=Dict[str, Any])
def insertion_demo(payload: InsertionDemoInput):
    """Run a synthetic, read-only insertion against three fixed commitments."""
    window_start, window_end = (solver.as_utc(value) for value in solver.next_window())
    staff_names = {
        9101: "Synthetic mechanical engineer A",
        9102: "Synthetic mechanical engineer B",
    }
    baseline_specs = [
        ("routine-1", "Routine door checks", "Door mechanism inspection",
         ["Mechanical", "Electrical"], 0, 60),
        ("routine-2", "Routine brake checks", "Train brake inspection",
         ["Mechanical", "Braking systems"], 120, 60),
        ("routine-3", "Routine bogie checks", "Bogie inspection",
         ["Mechanical"], 225, 30),
    ]
    baseline = [
        insertion_demo_row(
            job_id=job_id, name=name, track="Synthetic shared rolling-stock bay",
            deadline=window_end, duration=duration, engineers_needed=2,
            scheduled_start=window_start + dt.timedelta(minutes=offset),
            engineer_ids=[9101, 9102], engineer_names=list(staff_names.values()),
            approved=True, activity=activity, required_skills=required_skills,
            activity_type="Preventive",
        )
        for job_id, name, activity, required_skills, offset, duration in baseline_specs
    ]
    no_capacity = payload.scenario == "no_capacity"
    request_start = window_start + dt.timedelta(minutes=60)
    request_deadline = window_start + dt.timedelta(minutes=75 if no_capacity else 225)
    request_count = 2
    candidate = {
        "id": "late-corrective", "name": "Unexpected train door repair",
        "line": "North-South Line (NSL)", "track": "Synthetic shared rolling-stock bay",
        "deadline": request_deadline, "duration_mins": 45, "priority": "High",
        "engineers_needed": request_count, "required_skills": ["Mechanical"],
        "status": "Not started", "is_approved": False,
        "scheduled_start": request_start, "time_locked": False,
        "assignment_locked": False, "assigned_engineer_ids": [],
    }
    engineers = [
        {"id": engineer_id, "name": name,
         "skills": ["Mechanical", "Electrical", "Braking systems", "Door systems"],
         "is_available": True,
         "years_of_experience": 8}
        for engineer_id, name in staff_names.items()
    ]
    commitments = [
        {"line": row["line"], "track": row["track"],
         "scheduled_start": row["scheduled_start"], "scheduled_end": row["scheduled_end"],
         "assigned_engineer_ids": row["assigned_engineer_ids"]}
        for row in baseline
    ]
    result = solver.solve_mrt_schedule(
        [candidate], engineers, window_start=window_start, window_end=window_end,
        commitments=commitments,
    )
    result_status = result.get("status", "error")
    feasible = result_status == "success" and len(result.get("schedule", [])) == 1
    capacity_blocked = result_status == "infeasible"
    added = insertion_demo_row(
        job_id="late-corrective", name=candidate["name"], track=candidate["track"],
        deadline=request_deadline, duration=45, engineers_needed=request_count,
    )
    if feasible:
        scheduled = result["schedule"][0]
        assigned_ids = [int(value) for value in scheduled.get("assigned_engineers") or []]
        added.update(
            scheduled_start=scheduled["scheduled_start"],
            scheduled_end=scheduled["scheduled_end"],
            assigned_engineer_ids=assigned_ids,
            assigned_engineers=[staff_names[value] for value in assigned_ids],
        )
        explanation = (
            "The three approved routine commitments stay fixed. CP-SAT placed the unexpected "
            "repair into a genuine crew-available gap before its deadline, like assigning cover "
            "without moving the existing timetable."
        )
    elif capacity_blocked:
        explanation = (
            "The three approved routine commitments stay fixed. Before this repair's deadline "
            "there is no 45-minute interval when both required qualified engineers and the shared "
            "maintenance bay are free, "
            "so CP-SAT correctly reports no capacity and drops no routine work."
        )
    else:
        explanation = (
            "The synthetic solver run could not produce a result. The routine commitments remain "
            "unchanged; review the solver explanation before retrying."
        )
    return {
        "synthetic": True, "persisted": False, "can_apply": False,
        "scenario": payload.scenario, "status": "success" if feasible else result_status,
        "feasible": feasible, "no_capacity": capacity_blocked,
        "explanation": explanation, "solver_explanation": result.get("ai_explanation"),
        "solver_status": result.get("solver_status") or result.get("status", "unknown").upper(),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "baseline": baseline,
        "proposed": baseline + ([added] if feasible else []),
        "added_request": added,
    }


@app.post("/approval/{job_id}", response_model=Dict[str, Any])
def approve_job(job_id: int, payload: ApprovalPayload, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter_by(id=job_id).first()
    if not job: raise HTTPException(404, "Job not found")
    if job.status != "Not started":
        raise HTTPException(409, "Only Not started work may be approved or rejected.")
    require_valid_job_location(job)
    before = job_payload(job)
    priority = clean_priority(payload.override_priority) if payload.override_priority else job.priority
    team = get_engineers(db, payload.override_engineers) if payload.override_engineers is not None else list(job.assigned_engineers)
    start = from_db(job.scheduled_start)
    if payload.override_start_min is not None:
        start = solver.next_window()[0] + dt.timedelta(minutes=payload.override_start_min)
    if payload.approved:
        if not start: raise HTTPException(409, "Schedule the job before approval.")
        end = validate_plan(db, job, start, job.duration_mins, team, job_skills(job), job.engineers_needed)
        job.scheduled_start, job.scheduled_end, job.priority = to_db(start), to_db(end), priority
        job.assigned_engineers, job.is_approved = team, True
        if payload.override_start_min is not None: job.time_locked = True
        if payload.override_engineers is not None: job.assignment_locked = True
        action = "Approved"
    else:
        job.is_approved, action = False, "Rejected"
    db.flush(); add_audit(db, action, payload.approved_by, {"job_id": job_id, "reason": payload.reason, "before": before, "after": job_payload(job)})
    db.commit()
    return {"status": "success", "action": action, "job": job_payload(job)}


@app.patch("/checklist/{job_id}", response_model=Dict[str, Any])
def update_checklist(job_id: int, payload: ChecklistUpdate, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter_by(id=job_id).first()
    if not job: raise HTTPException(404, "Job not found")
    if payload.status not in STATUSES: raise HTTPException(400, f"Invalid status. Must be one of {list(STATUSES)}")
    if not payload.updated_by.strip(): raise HTTPException(400, "updated_by must not be blank")
    if payload.status in {"Delay", "Error"} and not (payload.reason and payload.reason.strip()):
        raise HTTPException(400, f"A reason is required for {payload.status}.")
    transitions = {"Not started": {"In progress"}, "In progress": {"Done", "Delay", "Error"},
                   "Delay": {"Not started"}, "Error": {"Not started"}, "Done": set()}
    if payload.status not in transitions.get(job.status, set()):
        raise HTTPException(409, f"Status cannot move from {job.status} to {payload.status}.")
    if payload.updated_repair_time_mins is not None and payload.status != "Delay":
        raise HTTPException(400, "updated_repair_time_mins is accepted only when reporting a Delay.")
    before, suggestion = job_payload(job), None
    if payload.status == "In progress":
        if not job.is_approved or not job.scheduled_start or not job.scheduled_end:
            raise HTTPException(409, "Approve a scheduled plan before starting work.")
        validate_plan(db, job, from_db(job.scheduled_start), job.duration_mins,
                      list(job.assigned_engineers), job_skills(job), job.engineers_needed,
                      allow_past=True)
    elif payload.status in {"Delay", "Error"}:
        if payload.status == "Delay":
            job.delay_reason = payload.reason
            if payload.updated_repair_time_mins:
                revised_end = validate_plan(db, job, from_db(job.scheduled_start), payload.updated_repair_time_mins,
                                            list(job.assigned_engineers), job_skills(job), job.engineers_needed,
                                            allow_past=True)
                job.duration_mins, job.scheduled_end = payload.updated_repair_time_mins, to_db(revised_end)
        else: job.error_reason = payload.reason
        suggestion = "Planner review required: reassess duration, staffing and the next available maintenance window."
        job.ai_suggested_action, job.is_approved = suggestion, False
    elif payload.status == "Not started":
        job.scheduled_start = job.scheduled_end = None
        job.scheduled_start_min = job.scheduled_end_min = None
        job.time_locked = False
        job.is_approved = False
    job.status, job.status_color = payload.status, STATUS_COLORS[payload.status]
    db.flush(); add_audit(db, f"Status -> {payload.status}", payload.updated_by,
                          {"job_id": job_id, "reason": payload.reason, "before": before, "after": job_payload(job)})
    db.commit()
    return {"status": "success", "job_id": job_id, "new_status": payload.status,
            "status_color": job.status_color, "ai_suggested_action": suggestion}


@app.get("/dashboard/gantt", response_model=List[Dict[str, Any]])
def gantt(db: Session = Depends(get_db)):
    return [job_payload(j) | {"color": j.status_color} for j in db.query(database.RepairJob).all()]


@app.get("/alerts/", response_model=List[Dict[str, Any]])
def alerts(db: Session = Depends(get_db)):
    now, result = dt.datetime.now(UTC), []
    for job in db.query(database.RepairJob).filter(database.RepairJob.status != "Done").all():
        hours = (from_db(job.deadline) - now).total_seconds() / 3600 if job.deadline else 9999
        if hours <= 24: result.append({"job_id": job.id, "type": "1day_deadline", "message": f"URGENT: Job '{job.name}' deadline is within 1 day!", "target": "Engineers"})
        elif hours <= 72: result.append({"job_id": job.id, "type": "3days_deadline", "message": f"WARNING: Job '{job.name}' deadline is within 3 days.", "target": "Engineers"})
        elif hours <= 168: result.append({"job_id": job.id, "type": "1week_deadline", "message": f"NOTICE: Job '{job.name}' deadline is within 1 week.", "target": "Engineers"})
        start = from_db(job.scheduled_start)
        if start:
            minutes = int((start - now).total_seconds() / 60)
            if 0 <= minutes <= 5: result.append({"job_id": job.id, "type": "5min_before", "message": f"IMMINENT: Job '{job.name}' starts in 5 minutes!", "target": "Engineers & Management"})
            elif 5 < minutes <= 15: result.append({"job_id": job.id, "type": "15min_before", "message": f"PREPARATION: Job '{job.name}' starts in 15 minutes.", "target": "Engineers & Management"})
    return result


@app.get("/audit-logs/", response_model=List[Dict[str, Any]])
def audit_logs(db: Session = Depends(get_db)):
    return [{"id": log.id, "timestamp": from_db(log.timestamp).isoformat(), "action": log.action,
             "details": log.details, "approved_by": log.approved_by}
            for log in db.query(database.AuditLog).order_by(database.AuditLog.timestamp.desc()).all()]
