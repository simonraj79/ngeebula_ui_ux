from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests


class ApiClientError(RuntimeError):
    """The frontend could not get a usable response from FastAPI."""


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return "The backend returned an unreadable error. Check its server logs."
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        if isinstance(detail, dict):
            outcome = str(detail.get("result") or "").replace("_", " ").strip()
            message = str(detail.get("message") or "Request failed.")
            warnings = detail.get("warnings") or []
            if isinstance(warnings, str):
                warnings = [warnings]
            if isinstance(warnings, list):
                message = " ".join([message, *(str(item) for item in warnings if item)])
            return f"{outcome.title()}: {message}" if outcome else message
        if isinstance(detail, list):
            messages = []
            for issue in detail:
                if isinstance(issue, dict):
                    location = ".".join(str(item) for item in issue.get("loc", []) if item != "body")
                    message = str(issue.get("msg", "Invalid value"))
                    messages.append(f"{location}: {message}" if location else message)
                else:
                    messages.append(str(issue))
            return "; ".join(messages)
        return str(detail)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urlsplit(self.base_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise ApiClientError("Enter a FastAPI server URL beginning with http:// or https://.")
        timeout = kwargs.pop("timeout", (5, self.timeout_seconds))
        try:
            response = requests.request(method, self.base_url + path, timeout=timeout, **kwargs)
            if response.status_code >= 400:
                raise ApiClientError(f"Backend HTTP {response.status_code}: {self._error_detail(response)}")
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except requests.Timeout as exc:
            raise ApiClientError(
                "The backend timed out. Refresh before retrying because the request may still be processing."
            ) from exc
        except requests.ConnectionError as exc:
            raise ApiClientError("Cannot connect to FastAPI. Start the backend and check the server URL.") from exc
        except requests.RequestException as exc:
            raise ApiClientError("The backend request failed. Check the server URL and try again.") from exc
        except ValueError as exc:
            raise ApiClientError("The backend returned an invalid response. Check its server logs.") from exc

    def get_jobs(self) -> list[dict]:
        data = self._request("GET", "/jobs/")
        if not isinstance(data, list):
            raise ApiClientError("Unexpected response from /jobs/.")
        return data

    def get_engineers(self) -> list[dict]:
        data = self._request("GET", "/engineers/")
        if not isinstance(data, list):
            raise ApiClientError("Unexpected response from /engineers/.")
        return data

    def get_catalog(self) -> dict:
        data = self._request("GET", "/catalog/")
        if not isinstance(data, dict):
            raise ApiClientError("Unexpected response from /catalog/.")
        return data

    def get_gantt_data(self) -> list[dict]:
        data = self._request("GET", "/dashboard/gantt")
        if not isinstance(data, list):
            raise ApiClientError("Unexpected response from /dashboard/gantt.")
        return data

    def get_alerts(self) -> list[dict]:
        data = self._request("GET", "/alerts/")
        return data if isinstance(data, list) else []

    def get_audit_logs(self) -> list[dict]:
        data = self._request("GET", "/audit-logs/")
        return data if isinstance(data, list) else []

    def get_ai_status(self) -> dict:
        data = self._request("GET", "/ai/status")
        if not isinstance(data, dict):
            raise ApiClientError("Unexpected response from /ai/status.")
        return data

    def test_ai_connection(self) -> dict:
        data = self._request("POST", "/ai/test", timeout=(5, 60))
        if not isinstance(data, dict):
            raise ApiClientError("Unexpected response from /ai/test.")
        return data

    def create_job(self, payload: dict) -> dict:
        data = self._request("POST", "/jobs/parse-and-create", json=payload, timeout=(5, 60))
        if not isinstance(data, dict):
            raise ApiClientError("Unexpected job creation response.")
        return data

    def update_job(self, job_id: int, payload: dict) -> dict:
        data = self._request("PATCH", f"/jobs/{job_id}", json=payload)
        return data if isinstance(data, dict) else {}

    def delete_job(self, job_id: int, payload: dict) -> dict:
        data = self._request("DELETE", f"/jobs/{job_id}", json=payload)
        return data if isinstance(data, dict) else {}

    def propose_schedule(self) -> dict:
        data = self._request("POST", "/schedule/propose", timeout=(5, 90))
        if not isinstance(data, dict):
            raise ApiClientError("Unexpected scheduling response.")
        return data

    def planning_readiness(self) -> dict:
        data = self._request("GET", "/schedule/readiness")
        if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
            raise ApiClientError("The planning checks returned an unexpected response.")
        return data

    def compare_planning(self, scenario: str) -> dict:
        data = self._request("POST", "/schedule/compare", json={"scenario": scenario}, timeout=(5, 45))
        if not isinstance(data, dict) or data.get("synthetic") is not True:
            raise ApiClientError("The comparison did not return a labelled synthetic example.")
        return data

    def estimate_roi(self, payload: dict) -> dict:
        data = self._request("POST", "/schedule/roi", json=payload)
        if not isinstance(data, dict) or "calculated_outputs" not in data:
            raise ApiClientError("The savings estimate returned an unexpected response.")
        return data

    def insertion_demo(self, scenario: str) -> dict:
        data = self._request("POST", "/schedule/insertion-demo", json={"scenario": scenario}, timeout=(5, 30))
        if not isinstance(data, dict) or data.get("synthetic") is not True:
            raise ApiClientError("The backend did not return a labelled synthetic example.")
        return data

    def update_job_status(self, job_id: int, payload: dict) -> dict:
        data = self._request("PATCH", f"/checklist/{job_id}", json=payload)
        return data if isinstance(data, dict) else {}

    def submit_approval(self, job_id: int, payload: dict) -> dict:
        data = self._request("POST", f"/approval/{job_id}", json=payload)
        return data if isinstance(data, dict) else {}
