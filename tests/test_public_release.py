"""Public fixtures must boot without local credentials or databases."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_database_seeds_public_fixture_and_preserves_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{(tmp_path / 'fresh.sqlite3').as_posix()}")
    database = load_module('public_fresh_database', ROOT / 'backend/database.py')
    try:
        database.init_db()
        with database.SessionLocal() as session:
            assert session.query(database.Engineer).count() == 697
            first = session.query(database.Engineer).order_by(database.Engineer.id).first()
            first.name = 'Existing local entry'
            session.commit()
        database.init_db()
        with database.SessionLocal() as session:
            assert session.query(database.Engineer).count() == 697
            assert session.query(database.Engineer).order_by(database.Engineer.id).first().name == 'Existing local entry'
            assert session.query(database.RepairJob).count() == 0
            assert session.query(database.AuditLog).count() == 0
    finally:
        database.engine.dispose()


def test_release_audit_flags_private_paths_even_if_tracked():
    audit = load_module('publication_audit', ROOT / 'scripts/audit_public_release.py')
    for path in ['.env', 'backend/.env.local', 'frontend/.streamlit/secrets.toml',
                 'backend/smrt_maintenance.db-wal',
                 'service-account.json', '.run/state.json', 'data/private/roster.csv']:
        assert audit.private_path(path), path
    for path in ['.env.example', 'frontend/.streamlit/config.toml', 'backend/engineers_db.json']:
        assert not audit.private_path(path), path
