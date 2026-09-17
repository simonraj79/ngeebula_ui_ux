# Stakeholder video capture notes

These frames are real Ngeebula Streamlit UI screenshots captured at **1600 × 900** on 17 September 2026. The working data is a clearly synthetic local scenario in a disposable SQLite database. No live jobs, credentials, provider calls, Render services, or ports 8000/8501 were touched.

## Frames and annotation anchors

Coordinates are `(x, y)` pixels in the 1600 × 900 source image. Exact machine-readable values also live in `video/public/screenshots/capture_metadata.json`.

| File | UI state | Useful anchors |
| --- | --- | --- |
| `01_cockpit.png` | Cockpit with synthetic preventive and corrective fibre work | workflow `(560,180)`; action queue `(670,360)`; timeline `(900,700)` |
| `02_asset_picker.png` | Eight curated asset shortcuts and schematic | asset guide `(920,510)`; scope note `(880,225)` |
| `03_repair_details.png` | Rails / Rail replacement selected; symptoms remain editable | selected repair `(900,270)`; details `(900,500)` |
| `04_station_first_clementi.png` | Clementi selected by station; East-West Line (EWL) and EW23 derived | station `(850,300)`; derived line `(850,390)`; deadline `(850,590)` |
| `05_request_review.png` | Three saved requests with exact values and selected request summary | queue `(930,575)`; request summary `(900,825)` |
| `06_planning_gantt.png` | Complete real CP-SAT proposal: 3 scheduled, 0 unscheduled | metrics `(900,210)`; Gantt `(930,570)`; generate control `(450,365)` |
| `07_approved_execution.png` | Urgent corrective repair approved with 2/2 crew and valid next action | approval `(1080,480)`; execution control `(930,800)` |
| `08_compare_approaches.png` | Labeled synthetic comparison: 1/2, 1/2, and 2/2 jobs placed | outcome cards `(930,175)`; schedule comparison `(930,700)` |

Supplemental how-to frames preserve the original eight files:

| File | UI state | Suggested logical crop `(left, top, right, bottom)` |
| --- | --- | --- |
| `02b_asset_buttons.png` | All eight native clickable asset buttons | `(300, 275, 1600, 900)` |
| `03b_fibre_details.png` | Fibre-optic symptoms and short title before location selection | `(300, 70, 1600, 900)` |
| `05b_request_review_details.png` | Final unsaved fibre request review with Clementi/EWL, deadline, Fibre-optic cable repair, required skill, and qualified roster count | `(300, 70, 1600, 900)` |
| `06b_gantt_detail.png` | Real three-job CP-SAT Gantt with exact job labels and time axis | `(300, 360, 1600, 850)` |
| `07b_approval_review.png` | Pending job summary and accountable human approval controls | `(300, 70, 1600, 900)` |
| `05c_assessed_requirements.png` | Existing job #2 assessed record: Clementi/EWL location, 75-minute duration, 2/2 named crew, Fibre optics skill and solver-lock state | `(330, 55, 1560, 660)` |
| `07c_approval_same_job.png` | The same existing job #2 with Approved state, assessment rationale and human decision controls | `(330, 0, 1560, 860)` |
| `07d_execution_controls.png` | Existing approved job #2 with native next-action selector, required field update reason, untouched submit control and tonight's exact execution list | `(330, 0, 1560, 850)` |

Their exact state descriptions, crops, and callout anchors are stored in `video/public/screenshots/supplemental_capture_metadata.json`.

## Disposable setup

- Backend: `http://127.0.0.1:8011`
- Frontend: `http://127.0.0.1:8511`
- Database: `.run/video-demo.sqlite3`
- Empty environment file: `.run/video-empty.env`
- Empty Gemini credential file: `.run/video-empty-gemini.key`
- Isolated local app data: `.run/video-localappdata/`
- PID files: `.run/video-backend.pid` and `.run/video-frontend.pid`
- Logs: `.run/video-backend.*.log` and `.run/video-frontend.*.log`

The backend and frontend were started as hidden Windows processes with `scripts/capture_video_start.py`. They are intentionally left running for review. The capture script is `scripts/capture_video_screenshots.py`; it seeds only the disposable API, walks the real UI in a fresh headless Chrome context, approves one synthetic repair through the disposable API, and writes the frames plus metadata.

The dummy roster has enough fully qualified available crew for the Fibre-optic cable repair catalog activity. The saved scenario therefore uses one preventive-round finding and two corrective fibre repairs at Clementi, all mapped to that catalog activity. This keeps the plan feasible without inventing people or bypassing qualifications. The separate comparison frame is the application's built-in labeled synthetic demonstration; it uses the real solver and saves nothing.

## Verification

- All eight PNG files were inspected at 1600 × 900.
- The planning frame reports 3 requests, 3 scheduled, 0 unscheduled.
- The execution frame shows the urgent Clementi fibre cable repair as Approved with 2/2 crew.
- The comparison frame shows identical synthetic inputs and outcomes of 1/2, 1/2, and 2/2 for the three approaches.
- `python -m compileall -q scripts/capture_video_screenshots.py scripts/capture_video_start.py` passes in the project virtual environment.
