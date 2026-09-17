"""Bounded, isolated PS1 planning API. No uploads are sent to an AI provider."""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
import logging
from pathlib import Path
import threading
import time
import traceback
from typing import Any, Literal
from uuid import uuid4
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

try:
    from .ps1_data import PS1DataError, SCHEMAS, load_ps1_instance
    from .ps1_validator import validate_submission
except ImportError:
    from ps1_data import PS1DataError, SCHEMAS, load_ps1_instance
    from ps1_validator import validate_submission

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'ps1'
SOURCE_URL = 'https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement/tree/16526c02579c7f37e54eaaa42a4cc6d4ceb19994/PS1'
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_INSTANCES = 8
MAX_RUNS = 32
router = APIRouter(prefix='/ps1', tags=['PS1 track access'])
_lock = threading.RLock()
_instances: OrderedDict[str, dict[str, Any]] = OrderedDict()
_runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ps1-planning')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry(dataset_id: str = 'default') -> dict[str, Any]:
    with _lock:
        if dataset_id == 'default' and dataset_id not in _instances:
            _instances['default'] = {'instance': load_ps1_instance(DATA / '01_data'),
                'label': 'Supplied PS1 demand book', 'created_at': _now(), 'default': True}
        entry = _instances.get(dataset_id)
        if entry is None:
            raise HTTPException(404, 'This uploaded dataset has expired. Import the eight CSV files again.')
        _instances.move_to_end(dataset_id)
        return entry


def _public(dataset_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    instance = entry['instance']
    public = instance.to_public_dict()
    weeks = [{'week': week,
              'start': (instance.horizon_start + timedelta(weeks=week - 1)).isoformat(),
              'end': (instance.horizon_start + timedelta(weeks=week, days=-1)).isoformat()}
             for week in range(1, instance.horizon_weeks + 1)]
    source = {'url': SOURCE_URL if entry.get('default') else None,
              'commit': '16526c02579c7f37e54eaaa42a4cc6d4ceb19994' if entry.get('default') else None,
              'kind': 'Published challenge dataset' if entry.get('default') else 'User-uploaded instance',
              'attribution': 'NebulaX PS1 repository; identified by the project owner as SMRT-supplied.' if entry.get('default') else 'Uploaded for this planning session.',
              'official_validator_available': False}
    counts = {'lines': len(instance.lines), 'stations': len(instance.stations),
              'sectors': len(instance.sectors), 'locations': len(instance.location_supply),
              'contracts': len(instance.projects), 'activities': len(instance.activities),
              'weeks': instance.horizon_weeks,
              'workload': float(sum(a.total_accesses for a in instance.activities))}
    issues = [
        {'severity': 'info', 'message': 'Local checks implement the published rules. The official trackaccess validator is not bundled.'},
        {'severity': 'info', 'message': 'Alpha/Beta is the supplied challenge topology, not a live MRT operating network.'},
        {'severity': 'info', 'message': 'Supply is the remaining weekly access pool; no dated maintenance closure calendar is supplied.'},
    ]
    return {**public, 'dataset_id': dataset_id, 'label': entry['label'], 'source': source,
            'created_at': entry['created_at'], 'audit': {'valid': True, 'issues': issues, 'counts': counts},
            'contracts': public['projects'], 'locations': public['location_supply'], 'weeks': weeks,
            'network': {key: public[key] for key in ('lines', 'stations', 'sectors')},
            'scenarios': [
                {'id': 'A', 'name': 'Protect access supply', 'description': 'Fixed supply, no ECLO. Allow and penalize completion delay.'},
                {'id': 'B', 'name': 'Protect target dates', 'description': 'Fixed planned dates. Penalize additional access and ECLO.'},
                {'id': 'C', 'name': 'Balance both', 'description': 'At most one extra access per location-week and a two-week ECLO window per line.'}],
            'limits': {'max_upload_bytes': MAX_UPLOAD_BYTES, 'max_activities': 300,
                       'max_horizon_weeks': 156, 'storage': 'Temporary server memory; resets on restart.'}}


@router.get('/dataset')
def dataset(dataset_id: str = 'default'):
    return _public(dataset_id, _entry(dataset_id))


def _zip_files(payload: bytes) -> dict[str, str]:
    files: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > 1000 or sum(info.file_size for info in members) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, 'The extracted archive must be at most 10 MB and contain at most 1,000 entries.')
            for info in members:
                name = Path(info.filename.replace('\\', '/')).name
                if name not in SCHEMAS:
                    continue
                if name in files:
                    raise HTTPException(422, f'Duplicate input file in archive: {name}')
                if info.flag_bits & 1:
                    raise HTTPException(422, 'Encrypted archives are not supported.')
                files[name] = archive.read(info).decode('utf-8-sig')
    except (zipfile.BadZipFile, UnicodeDecodeError, RuntimeError):
        raise HTTPException(422, 'Upload a valid ZIP containing UTF-8 PS1 CSV files.') from None
    return files


@router.post('/datasets/import', status_code=201)
async def import_dataset(request: Request):
    declared = request.headers.get('content-length')
    if declared and (not declared.isdigit() or int(declared) > MAX_UPLOAD_BYTES):
        raise HTTPException(413, 'Upload at most 10 MB.')
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'Upload at most 10 MB.')
    content_type = request.headers.get('content-type', '').split(';')[0]
    name = 'Uploaded PS1 instance'
    if content_type in {'application/zip', 'application/x-zip-compressed', 'application/octet-stream'}:
        files = _zip_files(bytes(payload))
    else:
        try:
            body = json.loads(payload)
            files = body['files']
            name = str(body.get('name') or name)[:100]
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, 'Expected a ZIP archive or JSON with a files mapping of the eight CSV filenames to text.') from None
        if not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()):
            raise HTTPException(422, 'Each files entry must map a CSV filename to its text.')
    try:
        instance = load_ps1_instance(files)
    except (PS1DataError, ValueError) as exc:
        raise HTTPException(422, str(exc)[:400]) from None
    if len(instance.activities) > 300 or instance.horizon_weeks > 156 or len(instance.location_supply) > 500:
        raise HTTPException(422, 'This shared demo supports up to 300 activities, 500 locations and 156 weeks per instance.')
    dataset_id = uuid4().hex
    entry = {'instance': instance, 'label': name, 'created_at': _now(), 'default': False}
    with _lock:
        while len(_instances) >= MAX_INSTANCES:
            victim = next((key for key in _instances if key != 'default'), None)
            if victim is None:
                break
            del _instances[victim]
        _instances[dataset_id] = entry
    return _public(dataset_id, entry)


class CapacityChange(BaseModel):
    location_id: str = Field(min_length=1, max_length=100)
    week: int = Field(ge=1, le=156)
    capacity: int = Field(ge=0, le=50)


class RunInput(BaseModel):
    dataset_id: str = Field(default='default', max_length=64)
    scenario: Literal['A', 'B', 'C'] = 'C'
    time_limit_seconds: float = Field(default=20, ge=1, le=45)
    baseline_run_id: str | None = Field(default=None, max_length=64)
    disruptions: list[CapacityChange] = Field(default_factory=list, max_length=100)


def _enrich(instance, submission):
    groups = defaultdict(set)
    for row in submission.get('schedule_occupancy', []):
        groups[(row['activity_id'], int(row['week']))].add(str(row['co_share_group']))
    rows = []
    for access in submission.get('schedule_access', []):
        activity = instance.activities_by_id[access['activity_id']]
        project = instance.projects_by_contract[activity.contract_number]
        location = instance.locations_by_id[activity.start_location_id]
        week = int(access['week'])
        rows.append({**access, 'contract_number': activity.contract_number,
                     'line_code': location.line_code, 'line': instance.lines_by_code[location.line_code].line_name,
                     'bound': location.bound, 'access_type': project.access_type,
                     'activity_type': activity.activity_type, 'nature_of_activity': project.nature_of_activity,
                     'contract_priority': project.contract_priority, 'activity_priority': activity.activity_priority,
                     'start_location_id': activity.start_location_id, 'end_location_id': activity.end_location_id,
                     'start_date': (instance.horizon_start + timedelta(weeks=week-1)).isoformat(),
                     'end_date': (instance.horizon_start + timedelta(weeks=week, days=-1)).isoformat(),
                     'co_share_groups': sorted(groups[(activity.activity_id, week)]),
                     'occupied_locations': list(instance.activity_span_ids(activity.activity_id))})
    return rows


def _changes(submission, baseline):
    if not baseline:
        return {'baseline_run_id': None, 'moved_activities': [], 'count': 0}
    def positions(value):
        result = defaultdict(list)
        for row in value.get('schedule_access', []):
            result[row['activity_id']].append((int(row['week']), int(row['eclo']), int(row['access_night'])))
        return {key: sorted(values) for key, values in result.items()}
    old, new = positions(baseline), positions(submission)
    moved = [{'activity_id': key, 'before': old.get(key, []), 'after': new.get(key, [])}
             for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]
    return {'moved_activities': moved, 'count': len(moved),
            'note': 'Changes compare week, ECLO and local access-night index. No globally minimum churn is claimed.'}


def _work(run_id, instance, payload, baseline):
    started = time.monotonic()
    with _lock:
        _runs[run_id].update(status='running', started_at=_now())
    try:
        try:
            from .ps1_solver import solve
        except ImportError:
            from ps1_solver import solve
        result = solve(instance, scenario=payload.scenario,
                       time_limit_seconds=payload.time_limit_seconds, baseline=baseline)
        submission = {key: result.get(key, []) for key in (
            'schedule_access', 'schedule_occupancy', 'results', 'physical_night_witness')}
        # Always revalidate the actual exported rows, never trust a solver status alone.
        validation = validate_submission(instance, submission, payload.scenario)
        changes = _changes(submission, baseline)
        changes['baseline_run_id'] = payload.baseline_run_id
        public = {**result, 'scenario': payload.scenario,
                  'feasible': validation['feasible'] and validation.get('complete', False),
                  'submission': submission, 'validation': validation,
                  'metrics': validation.get('soft_scores', {}), 'schedule': _enrich(instance, submission),
                  'changes': changes,
                  'disruptions': [change.model_dump() for change in payload.disruptions],
                  'elapsed_seconds': round(time.monotonic() - started, 3)}
        with _lock:
            _runs[run_id].update(status='completed', completed_at=_now(), result=public)
    except Exception as exc:
        # Provider/file/solver tracebacks may expose local details. Keep public failures bounded.
        last_frame = traceback.extract_tb(exc.__traceback__)[-1]
        logging.getLogger(__name__).error('PS1 run failed: %s in %s:%s',
            type(exc).__name__, Path(last_frame.filename).name, last_frame.lineno)
        with _lock:
            _runs[run_id].update(status='failed', completed_at=_now(),
                                error='The planner could not complete this run. Check the instance and try a smaller or longer run; no valid schedule is claimed.')


@router.post('/runs', status_code=202)
def create_run(payload: RunInput):
    entry = _entry(payload.dataset_id)
    instance = entry['instance']
    if payload.disruptions:
        try:
            instance = instance.with_capacity_overrides([change.model_dump() for change in payload.disruptions])
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:400]) from None
    baseline = None
    if payload.baseline_run_id:
        with _lock:
            prior = _runs.get(payload.baseline_run_id)
            if not prior or prior['status'] != 'completed':
                raise HTTPException(422, 'Choose a completed baseline plan still available on this server.')
            if prior['dataset_id'] != payload.dataset_id or prior['scenario'] != payload.scenario:
                raise HTTPException(422, 'Baseline must use the same dataset and scenario.')
            baseline = prior['result']['submission']
    run_id = uuid4().hex
    with _lock:
        active = sum(run['status'] in {'queued', 'running'} for run in _runs.values())
        if active >= 4:
            raise HTTPException(429, 'The shared planner is busy. Wait for a current run to finish and try again.')
        while len(_runs) >= MAX_RUNS:
            victim = next((key for key, run in _runs.items() if run['status'] not in {'queued', 'running'}), None)
            if victim is None:
                break
            del _runs[victim]
        run = {'run_id': run_id, 'dataset_id': payload.dataset_id, 'scenario': payload.scenario,
               'status': 'queued', 'created_at': _now(), 'result': None}
        _runs[run_id] = run
        _executor.submit(_work, run_id, instance, payload, baseline)
        return dict(run)


@router.get('/runs/{run_id}')
def get_run(run_id: str):
    with _lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(404, 'Run not found or expired. Generate a new plan.')
        return dict(run)


def _csv_bytes(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


@router.get('/runs/{run_id}/download')
def download(run_id: str):
    run = get_run(run_id)
    if run['status'] != 'completed' or not run['result']['feasible']:
        raise HTTPException(409, 'Only a complete plan that passes local validation can be exported as a submission.')
    result = run['result']
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for key, filename, columns in [
            ('schedule_access', 'SCHEDULE_ACCESS.csv', ['activity_id', 'access_seq', 'week', 'eclo', 'access_night']),
            ('schedule_occupancy', 'SCHEDULE_OCCUPANCY.csv', ['activity_id', 'week', 'location_id', 'co_share_group']),
            ('results', 'RESULTS.csv', ['scenario', 'contract_number', 'simulated_completion_date', 'overrun_days'])]:
            archive.writestr(filename, _csv_bytes(result['submission'][key], columns))
    return Response(stream.getvalue(), media_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="PS1-scenario-{run["scenario"]}.zip"',
        'Cache-Control': 'no-store'})


class ValidateInput(BaseModel):
    dataset_id: str = Field(default='default', max_length=64)
    scenario: Literal['A', 'B', 'C'] = 'A'
    access: list[dict[str, Any]] = Field(default_factory=list, max_length=50000)
    occupancy: list[dict[str, Any]] = Field(default_factory=list, max_length=200000)
    results: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    physical_night_witness: list[dict[str, Any]] | None = Field(default=None, max_length=50000)


@router.post('/validate')
def validate(payload: ValidateInput):
    instance = _entry(payload.dataset_id)['instance']
    try:
        submission = {'schedule_access': payload.access,
            'schedule_occupancy': payload.occupancy, 'results': payload.results}
        if payload.physical_night_witness is not None:
            submission['physical_night_witness'] = payload.physical_night_witness
        return validate_submission(instance, submission, payload.scenario)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, 'Submission rows do not match the published schedule schemas.') from None


@router.get('/runs/{run_id}/validation.json')
def validation_report(run_id: str):
    run = get_run(run_id)
    if run['status'] != 'completed':
        raise HTTPException(409, 'This run has not completed.')
    report = {'run_id': run_id, 'dataset_id': run['dataset_id'], 'scenario': run['scenario'],
              'validation': run['result']['validation'],
              'physical_night_witness': run['result']['submission'].get('physical_night_witness', []),
              'explanations': run['result'].get('explanations', []),
              'disruptions': run['result']['disruptions'], 'changes': run['result']['changes']}
    return Response(json.dumps(report, indent=2), media_type='application/json', headers={
        'Content-Disposition': f'attachment; filename="PS1-{run["scenario"]}-local-validation.json"',
        'Cache-Control': 'no-store'})
