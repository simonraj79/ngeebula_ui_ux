import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"


@dataclass
class ApiHarness:
    client: TestClient
    main: object
    database: object
    real_get_credential: object | None = None


@pytest.fixture(scope="session")
def api_modules(tmp_path_factory):
    """Import the app once against a disposable SQLite database.

    Import order matters because database.py constructs its engine at import time and
    main.py calls init_db immediately.  Disabling the production JSON seed before the
    latter import keeps the integration fixture small and deterministic.
    """
    isolated_root = tmp_path_factory.mktemp("isolated-runtime")
    db_path = isolated_root / "integration.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GEMINI_MODEL", None)
    os.environ["NGEEBULA_ENV_FILE"] = str(isolated_root / "missing-test.env")
    # Never let integration tests discover or consume the operator's DPAPI file.
    # Individual credential tests replace the provider with deterministic fakes.
    os.environ["NGEEBULA_GEMINI_KEY_FILE"] = str(isolated_root / "missing-test-gemini-key.dpapi")
    os.environ["LOCALAPPDATA"] = str(isolated_root / "local-app-data")
    sys.path.insert(0, str(BACKEND_DIR))

    for module_name in ("main", "database", "solver", "solver_core"):
        sys.modules.pop(module_name, None)

    database = importlib.import_module("database")
    database.seed_engineers_if_empty = lambda: None
    main = importlib.import_module("main")
    # Most API tests use a tiny station fixture. Official snapshot reconciliation
    # is tested separately and explicitly enabled by the reference API tests.
    main.LTA_REFERENCE = None

    # The catalog endpoint and fallback classification should be deterministic even
    # when pytest is launched from a directory other than backend/.
    main.MAINTENANCE_DB = {
        "maintenance_catalog": {
            "track_and_permanent_way": [
                {
                    "activity": "Rail defect repair",
                    "type": "Corrective",
                    "required_skills": ["Track maintenance"],
                }
            ]
        }
    }
    main.STATIONS_DB = {
        "MRT_Lines": {
            "North-South Line (NSL)": [
                {"code": "NS9", "name": "Woodlands", "interchange": ["TE2"]},
                {"code": "NS17", "name": "Bishan", "interchange": ["CC15"]},
            ],
            "East-West Line (EWL)": [
                {"code": "EW23", "name": "Clementi", "interchange": []}
            ],
            "Thomson-East Coast Line (TEL)": [
                {"code": "TE1", "name": "Woodlands North", "interchange": []}
            ],
            "Circle Line (CCL)": [
                {"code": "CC15", "name": "Bishan", "interchange": ["NS17"]}
            ],
        },
        "LRT_Networks": {},
    }
    yield main, database
    database.engine.dispose()


@pytest.fixture()
def api(api_modules, monkeypatch):
    main, database = api_modules
    # All API/UI tests start with an empty synthetic credential provider. Tests
    # that exercise AI setup replace this seam with explicit dummy credentials.
    real_get_credential = None
    if hasattr(main, "gemini_config"):
        real_get_credential = main.gemini_config.get_credential
        monkeypatch.setattr(main.gemini_config, "get_credential", lambda: None)
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)

    staff = [
        database.Engineer(
            id=101,
            name="Aisha Track Lead",
            work_email="aisha@example.test",
            contact_no="+65 0000 0101",
            years_of_experience=12,
            job_role="Senior Engineer",
            specialized_lines=json.dumps(["North South Line"]),
            is_available=True,
            skills=[database.EngineerSkill(skill_name="Track maintenance")],
        ),
        database.Engineer(
            id=102,
            name="Ben Track Engineer",
            work_email="ben@example.test",
            contact_no="+65 0000 0102",
            years_of_experience=7,
            job_role="Engineer",
            specialized_lines=json.dumps(["North South Line"]),
            is_available=True,
            skills=[database.EngineerSkill(skill_name="Track maintenance")],
        ),
        database.Engineer(
            id=103,
            name="Chen Unavailable",
            work_email="chen@example.test",
            contact_no="+65 0000 0103",
            years_of_experience=20,
            job_role="Senior Engineer",
            specialized_lines=json.dumps(["North South Line"]),
            is_available=False,
            skills=[database.EngineerSkill(skill_name="Track maintenance")],
        ),
        database.Engineer(
            id=104,
            name="Devi Signalling",
            work_email="devi@example.test",
            contact_no="+65 0000 0104",
            years_of_experience=15,
            job_role="Signalling Engineer",
            specialized_lines=json.dumps(["North South Line"]),
            is_available=True,
            skills=[database.EngineerSkill(skill_name="Signalling")],
        ),
    ]
    with database.SessionLocal() as session:
        session.add_all(staff)
        session.commit()

    with TestClient(main.app, raise_server_exceptions=False) as client:
        yield ApiHarness(
            client=client,
            main=main,
            database=database,
            real_get_credential=real_get_credential,
        )
