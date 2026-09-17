"""Display structured workflow failures without raw Python dictionaries."""
import importlib.util
import json
from pathlib import Path

import requests


_path = Path(__file__).resolve().parents[1] / "frontend" / "api_client.py"
_spec = importlib.util.spec_from_file_location("client_under_test", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def response(detail):
    result = requests.Response()
    result.status_code = 409
    result._content = json.dumps({"detail": detail}).encode()
    return result


def test_scheduler_failure_retains_message_and_actionable_warnings():
    result = _module.ApiClient._error_detail(response({
        "message": "No qualified crew can cover this request.",
        "warnings": ["Review the required skills.", "Confirm availability."],
    }))
    assert result == (
        "No qualified crew can cover this request. "
        "Review the required skills. Confirm availability."
    )


def test_field_validation_keeps_field_names():
    result = _module.ApiClient._error_detail(response([
        {"loc": ["body", "deadline"], "msg": "A timezone is required"},
        {"loc": ["body", "engineers_needed"], "msg": "Must be positive"},
    ]))
    assert result == "deadline: A timezone is required; engineers_needed: Must be positive"
