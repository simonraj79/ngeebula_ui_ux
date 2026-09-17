"""PS1 API import boundaries and separation from live maintenance data."""
import io
import json
from pathlib import Path
import zipfile
import time
import csv

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ps1_api(api):
    module = api.main.ps1_api
    with module._lock:
        module._instances.clear()
        module._runs.clear()
    return api.client, module


def source_files():
    return {p.name: p.read_text(encoding='utf-8-sig') for p in (ROOT / 'data/ps1/01_data').glob('*.csv')}


def test_default_dataset_is_complete_and_distinct_from_legacy_jobs(ps1_api):
    client, _ = ps1_api
    response = client.get('/ps1/dataset')
    assert response.status_code == 200
    payload = response.json()
    assert payload['audit']['counts'] == {'lines': 2, 'stations': 20, 'sectors': 18, 'locations': 76,
        'contracts': 14, 'activities': 54, 'weeks': 30, 'workload': 192.0}
    assert {line['line_code'] for line in payload['network']['lines']} == {'ALP', 'BET'}
    assert payload['source']['official_validator_available'] is False
    assert client.get('/jobs/').json() == []


def test_upload_has_own_id_and_does_not_replace_default(ps1_api):
    client, _ = ps1_api
    files = source_files()
    files['06_PARAMETERS.csv'] = files['06_PARAMETERS.csv'].replace('horizon_weeks,30', 'horizon_weeks,31')
    response = client.post('/ps1/datasets/import', json={'name': 'Test 31-week instance', 'files': files})
    assert response.status_code == 201, response.text
    dataset_id = response.json()['dataset_id']
    assert dataset_id != 'default'
    assert client.get('/ps1/dataset', params={'dataset_id': dataset_id}).json()['horizon_weeks'] == 31
    assert client.get('/ps1/dataset').json()['horizon_weeks'] == 30


def test_zip_accepts_nested_pack_and_rejects_duplicate_input(ps1_api):
    client, _ = ps1_api
    files = source_files()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in files.items():
            archive.writestr('PS1/01_data/' + name, content)
    response = client.post('/ps1/datasets/import', content=stream.getvalue(), headers={'Content-Type': 'application/zip'})
    assert response.status_code == 201, response.text
    with zipfile.ZipFile(stream, 'a') as archive:
        archive.writestr('duplicate/01_LINES.csv', files['01_LINES.csv'])
    response = client.post('/ps1/datasets/import', content=stream.getvalue(), headers={'Content-Type': 'application/zip'})
    assert response.status_code == 422
    assert 'Duplicate' in response.json()['detail']


def test_bad_import_reports_actionable_error_and_preserves_default(ps1_api):
    client, _ = ps1_api
    response = client.post('/ps1/datasets/import', json={'files': {'01_LINES.csv': 'wrong,column\na,b'}})
    assert response.status_code == 422
    assert client.get('/ps1/dataset').json()['audit']['counts']['activities'] == 54
    assert client.post('/ps1/datasets/import', content=b'not-a-zip', headers={'Content-Type': 'application/zip'}).status_code == 422
    assert client.post('/ps1/datasets/import', json={'files': []}).status_code == 422


def test_submission_validation_cannot_approve_empty_or_partial_work(ps1_api):
    client, _ = ps1_api
    response = client.post('/ps1/validate', json={'scenario': 'A', 'access': [], 'occupancy': [], 'results': []})
    assert response.status_code == 200
    assert response.json()['feasible'] is False
    assert any(row['rule'] == 'workload' for row in response.json()['hard_violations'])


def test_export_rejects_incomplete_run_and_unknown_api_returns_404(ps1_api):
    client, module = ps1_api
    module._runs['unresolved'] = {'run_id': 'unresolved', 'status': 'completed', 'scenario': 'A', 'result': {'feasible': False}}
    assert client.get('/ps1/runs/unresolved/download').status_code == 409
    assert client.get('/ps1/missing').status_code == 404
    assert client.get('/healthz').json()['frontend'] == 'react'
    for page in ('plan', 'schedule', 'data', 'requests', 'about'):
        assert client.get('/' + page).status_code == 200
    assert client.get('/schedule/missing').status_code == 404


def test_imported_instance_runs_and_roundtrips_exact_exports(ps1_api):
    client, module = ps1_api
    imported = client.post('/ps1/datasets/import', json={'files': source_files()}).json()
    queued = client.post('/ps1/runs', json={'dataset_id': imported['dataset_id'],
        'scenario': 'A', 'time_limit_seconds': 5})
    assert queued.status_code == 202
    run_id = queued.json()['run_id']
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = client.get(f'/ps1/runs/{run_id}').json()
        if run['status'] in {'completed', 'failed'}:
            break
        time.sleep(0.05)
    assert run['status'] == 'completed', run
    assert run['dataset_id'] == imported['dataset_id'] != 'default'
    assert run['result']['feasible'] and run['result']['validation']['complete']
    response = client.get(f'/ps1/runs/{run_id}/download')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'SCHEDULE_ACCESS.csv', 'SCHEDULE_OCCUPANCY.csv', 'RESULTS.csv'}
        tables = {name: list(csv.DictReader(io.StringIO(archive.read(name).decode()))) for name in archive.namelist()}
    evidence = client.get(f'/ps1/runs/{run_id}/validation.json').json()
    check = client.post('/ps1/validate', json={'dataset_id': imported['dataset_id'], 'scenario': 'A',
        'access': tables['SCHEDULE_ACCESS.csv'], 'occupancy': tables['SCHEDULE_OCCUPANCY.csv'],
        'results': tables['RESULTS.csv'], 'physical_night_witness': evidence['physical_night_witness']})
    assert check.status_code == 200
    assert check.json()['complete'] and not check.json()['hard_violations']
    assert len({row['activity_id'] for row in tables['SCHEDULE_ACCESS.csv']}) == 54
    assert client.get('/jobs/').json() == []
