"""Capture real Ngeebula UI states from an isolated local demo instance.

The backend/frontend must already be running on the supplied URLs. This script
uses only the disposable backend API and a fresh browser context.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from playwright.sync_api import Page, sync_playwright


SGT = timezone(timedelta(hours=8))


def api(base: str, method: str, path: str, payload: dict | None = None):
    response = requests.request(method, base + path, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def wait_for(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=2).status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def choose_demo_activity(catalog: dict, activity_name: str) -> dict:
    matches = [a for a in catalog["activities"] if a.get("activity") == activity_name]
    if not matches:
        raise RuntimeError(f"Catalog activity missing: {activity_name}")
    return matches[0]


def seed(base: str) -> list[dict]:
    existing = api(base, "GET", "/jobs/")
    if existing:
        return existing
    catalog = api(base, "GET", "/catalog/")
    deadline = (datetime.now(SGT) + timedelta(days=3)).replace(hour=5, minute=0, second=0, microsecond=0)
    scenarios = [
        ("Clementi fibre integrity check", "Inspect and restore a degraded fibre link found during the preventive communications round.", "Fibre-optic cable repair", "Medium", 45),
        ("Clementi fibre cable repair", "Repair a damaged trackside fibre link beside the eastbound platform during the next engineering window.", "Fibre-optic cable repair", "Urgent", 75),
        ("Clementi signalling link repair", "Restore the intermittent fibre connection serving the platform signalling cabinet.", "Fibre-optic cable repair", "High", 60),
    ]
    for title, description, activity_name, priority, duration in scenarios:
        activity = choose_demo_activity(catalog, activity_name)
        api(base, "POST", "/jobs/parse-and-create", {
            "name": title,
            "description": description,
            "line": "East West Line",
            "track": "Clementi station — trackside work",
            "station_code": "EW23",
            "deadline": deadline.isoformat(),
            "priority": priority,
            "duration_mins": duration,
            "catalog_category": activity["category"],
            "catalog_activity": activity["activity"],
            "created_by": "Video demo planner",
        })
    return api(base, "GET", "/jobs/")


def settle(page: Page) -> None:
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1800)


def shot(page: Page, output: Path, name: str) -> None:
    page.screenshot(path=str(output / name), full_page=False)


def click_text(page: Page, text: str, exact: bool = True) -> None:
    locator = page.get_by_text(text, exact=exact)
    locator.first.click()
    settle(page)


def capture(frontend: str, backend: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    wait_for(backend + "/jobs/")
    wait_for(frontend)
    jobs = seed(backend)
    metadata: dict[str, dict] = {}
    with sync_playwright() as p:
        # Use the installed Chrome build so capture does not depend on a
        # Playwright-managed browser download being present on the review host.
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        page.goto(frontend, wait_until="domcontentloaded")
        settle(page)

        shot(page, output, "01_cockpit.png")
        metadata["01_cockpit.png"] = {"state": "Cockpit with three synthetic local requests", "annotations": {"workflow": [560, 180], "queue": [670, 360], "timeline": [900, 700]}}

        click_text(page, "Requests")
        page.get_by_role("button", name="Add work").first.click(); settle(page)
        shot(page, output, "02_asset_picker.png")
        metadata["02_asset_picker.png"] = {"state": "Eight curated asset shortcuts", "annotations": {"asset_grid": [920, 510], "safety_scope": [880, 225]}}

        # Continue one draft far enough to show real repair details without saving it.
        page.get_by_role("button", name="3 · Rails").click(); settle(page)
        shot(page, output, "03_repair_details.png")
        metadata["03_repair_details.png"] = {"state": "Selected Rails repair with editable observed symptoms", "annotations": {"selected_repair": [900, 270], "details": [900, 500]}}

        page.get_by_role("button", name="Next: where & when").click(); settle(page)
        # Station-first control: use the visible Clementi option.
        station = page.get_by_label("Station *")
        station.click(); station.fill("Clementi"); page.wait_for_timeout(500)
        page.keyboard.press("ArrowDown"); page.keyboard.press("Enter"); settle(page)
        shot(page, output, "04_station_first_clementi.png")
        metadata["04_station_first_clementi.png"] = {"state": "Station-first Clementi selection derives East West Line", "annotations": {"station": [850, 300], "derived_line": [850, 390], "deadline": [850, 590]}}

        # Cancel the unsaved walkthrough draft and return to the saved queue.
        page.get_by_role("button", name="Back").click(); settle(page)
        page.get_by_role("button", name="Cancel").click(); settle(page)
        shot(page, output, "05_request_review.png")
        metadata["05_request_review.png"] = {"state": "Saved request review queue with requirements and next actions", "annotations": {"queue": [930, 575], "request_summary": [900, 825]}}

        api(backend, "POST", "/schedule/propose")
        page.reload(); settle(page)
        click_text(page, "Plan & approve")
        shot(page, output, "06_planning_gantt.png")
        metadata["06_planning_gantt.png"] = {"state": "Real CP-SAT proposal and overnight Gantt", "annotations": {"metrics": [900, 210], "gantt": [930, 570], "generate": [380, 360]}}

        # Approve the urgent corrective request via API, then show approval and execution UI.
        planned = api(backend, "GET", "/jobs/")
        target = next(j for j in planned if "fibre cable repair" in j["name"].lower())
        api(backend, "POST", f"/approval/{target['job_id']}", {"approved": True, "approved_by": "Video demo planner", "reason": "Synthetic stakeholder walkthrough"})
        page.reload(); settle(page)
        click_text(page, "Execution")
        execution_picker = page.get_by_label("Scheduled job")
        execution_picker.click()
        page.keyboard.type("Clementi fibre cable repair")
        page.keyboard.press("Enter")
        settle(page)
        shot(page, output, "07_approved_execution.png")
        metadata["07_approved_execution.png"] = {"state": "Approved corrective job ready for controlled execution", "annotations": {"approval_state": [930, 300], "execution_controls": [920, 590], "audit_identity": [290, 675]}}

        # Built-in example is explicitly synthetic and never saves invented jobs.
        click_text(page, "Explore & learn")
        page.get_by_role("button", name="Compare approaches").click(); settle(page)
        page.get_by_role("button", name="Run comparison").click(); settle(page)
        page.mouse.wheel(0, 430); page.wait_for_timeout(500)
        shot(page, output, "08_compare_approaches.png")
        metadata["08_compare_approaches.png"] = {"state": "Clearly labeled synthetic 2 jobs / 2 engineers comparison results", "annotations": {"synthetic_label": [900, 100], "outcomes": [930, 500]}}
        browser.close()
    (output / "capture_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default="http://127.0.0.1:8511")
    parser.add_argument("--backend", default="http://127.0.0.1:8011")
    parser.add_argument("--output", type=Path, default=Path("video/public/screenshots"))
    args = parser.parse_args()
    capture(args.frontend.rstrip("/"), args.backend.rstrip("/"), args.output)
