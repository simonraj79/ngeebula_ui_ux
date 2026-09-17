"""Capture supplemental real-UI frames for the Ngeebula how-to video."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from capture_video_screenshots import settle, wait_for


FRONTEND = "http://127.0.0.1:8511"
BACKEND = "http://127.0.0.1:8011"
OUTPUT = Path("video/public/screenshots")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT / name), full_page=False)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    wait_for(BACKEND + "/jobs/")
    wait_for(FRONTEND)
    metadata = {
        "02b_asset_buttons.png": {
            "state": "All eight native clickable asset shortcuts below the schematic",
            "logical_crop": [300, 275, 1600, 900],
            "annotations": {"asset_buttons": [920, 585]},
        },
        "03b_fibre_details.png": {
            "state": "Manual fibre-optic repair details before location selection",
            "logical_crop": [300, 70, 1600, 900],
            "annotations": {"repair_description": [930, 470], "short_title": [930, 635]},
        },
        "05b_request_review_details.png": {
            "state": "Unsaved fibre-optic wizard final review with location, deadline and catalog requirements",
            "logical_crop": [300, 70, 1600, 900],
            "annotations": {"review_card": [930, 360], "requirements": [930, 700]},
        },
        "06b_gantt_detail.png": {
            "state": "Real three-job solver Gantt with exact job labels and time axis",
            "logical_crop": [300, 360, 1600, 850],
            "annotations": {"gantt": [950, 680], "job_labels": [830, 710]},
        },
        "07b_approval_review.png": {
            "state": "Review and approve tab with human decision controls",
            "logical_crop": [300, 70, 1600, 900],
            "annotations": {"job_review": [930, 300], "decision_controls": [930, 745]},
        },
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        page.goto(FRONTEND, wait_until="domcontentloaded")
        settle(page)

        # Asset shortcuts: enter the wizard and scroll until the two rows of
        # native buttons are visible together.
        page.get_by_text("Requests", exact=True).first.click(); settle(page)
        page.get_by_role("button", name="Add work").first.click(); settle(page)
        page.mouse.wheel(0, 620); page.wait_for_timeout(700)
        shot(page, "02b_asset_buttons.png")

        # Build an unsaved fibre-optic draft through the station-first path.
        # The explicit title and symptoms keep the walkthrough continuous with
        # the saved fibre scenario without creating another database record.
        page.get_by_role("button", name="Describe another issue").click(); settle(page)
        details = page.get_by_label("What work is needed? *")
        details.fill("Repair the damaged trackside fibre-optic cable serving the Clementi signalling cabinet.")
        page.get_by_role("textbox", name="Short title (optional)", exact=True).fill("Clementi fibre-optic cable repair")
        shot(page, "03b_fibre_details.png")
        page.get_by_role("button", name="Next: where & when").click(); settle(page)
        station = page.get_by_label("Station *")
        station.click(); station.fill("Clementi"); page.wait_for_timeout(400)
        page.keyboard.press("ArrowDown"); page.keyboard.press("Enter"); settle(page)
        page.get_by_role("button", name="Next: review").click(); settle(page)
        page.get_by_text("Optional: use skills from a catalog activity", exact=True).click(); settle(page)
        page.get_by_label("Use catalog skills as manual requirements").check(force=True); settle(page)
        category = page.get_by_label("Category")
        category.click(); page.keyboard.type("communications_and_it_systems")
        page.keyboard.press("Enter"); settle(page)
        activity = page.get_by_label("Activity")
        activity.click(); page.keyboard.type("Fibre-optic cable repair")
        page.keyboard.press("Enter"); settle(page)
        page.mouse.wheel(0, 80); page.wait_for_timeout(500)
        shot(page, "05b_request_review_details.png")

        # Leave the unsaved wizard through its own controls, then review the
        # persisted schedule without changing it.
        page.get_by_role("button", name="Back").click(); settle(page)
        page.get_by_role("button", name="Back").click(); settle(page)
        page.get_by_role("button", name="Cancel").click(); settle(page)
        page.get_by_text("Plan & approve", exact=True).first.click(); settle(page)
        page.get_by_text("Proposed overnight schedule", exact=True).evaluate(
            "el => el.scrollIntoView({block: 'start', behavior: 'instant'})"
        )
        page.wait_for_timeout(700)
        shot(page, "06b_gantt_detail.png")

        # Review tab exposes the accountable human approval decision. Keep an
        # unapproved request selected so the controls remain actionable.
        page.get_by_role("tab", name="Review & approve").click(); settle(page)
        picker = page.get_by_label("Job to override or approve")
        picker.click(); page.keyboard.type("Clementi signalling link repair")
        page.keyboard.press("Enter"); settle(page)
        page.mouse.wheel(0, 520); page.wait_for_timeout(700)
        shot(page, "07b_approval_review.png")
        browser.close()

    (OUTPUT / "supplemental_capture_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
