# Operations dashboard

Python, native Streamlit, pandas and Plotly, with a small local styling layer. The frontend talks to FastAPI and never writes SQLite directly.

After installing the root requirements-lock.txt, run from this directory:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

FastAPI defaults to http://127.0.0.1:8000. Set NGEEBULA_API_URL or change the sidebar setting. Backend failures are shown explicitly; no demo schedule is silently substituted. About remains available offline.

Operators start in a maintenance-chief cockpit, add requests through a three-step guide, inspect priority and crews, generate schedules, override with reasons, approve work, update status, and confirm deletion. All displayed/input times are Singapore time; API timestamps carry offsets.

## Finding the next action

**Explore & learn** groups **Compare approaches**, **Schedule example**, **Glossary** and **About**. Comparison has three lightweight views: schedules, estimated savings, and data/evidence. Method counts and crew timelines show the synthetic result; financial assumptions remain separate and editable. The searchable glossary works offline. Operational alerts, history and AI settings stay in **Utilities**.

**Plan & approve** now surfaces read-only preliminary location, qualification and deadline checks before generation. Clear preliminary checks do not promise joint feasibility. The station picker attributes its reconciled LTA snapshot and flags local-only entries without inferring current service status.

- **Cockpit:** see three readiness counts and a short queue ordered by operational attention, planning, then approval. Open the next decision directly; the overnight timeline is a separate tab.
- **Requests:** review and filter existing work. **Add work** starts with eight numbered asset buttons beside a train/infrastructure schematic. Search by station name/code to fill the line automatically; interchanges ask for the serving line. Train/depot sites have a separate manual path. Confirm the deadline before review. **Correct location** provides an audited correction with replanning for Not started work. **Describe another issue** supports free text. Selected activities retain their catalog classification and full skills; manual duration, priority and crew remain review controls.
- **Schedule example:** use **See how a repair fits** on Cockpit. Run the solver on synthetic routine commitments and a late repair, compare before/after Gantt charts, and inspect the no-capacity case. Nothing is saved and no Gemini call is made.
- **Plan & approve:** generate a proposal, inspect the Gantt chart and native schedule table, then review one current job. Filters narrow the display; generation uses all eligible requests.
- **Execution:** record a valid next status. Starting work requires an approved schedule. Delays and errors return to planner review.
- **Alerts / History:** inspect issues and the recorded reasons for changes from the sidebar Utilities section.
- **AI setup:** see whether the backend has a redacted Gemini configuration, add `GEMINI_API_KEY` to the root `.env`, refresh the snapshot, and run a synthetic provider test. The backend rereads the file without a restart. API keys are never entered or displayed in the browser. An operating-system environment value takes precedence over `.env`; the Windows secure store remains an optional fallback.
- **About:** read the scoped problem statement, dated Singapore evidence, visual workflow, algorithm rationale, and data provenance. No backend is needed for this page.

The UI selects jobs by ID and resolves the latest API record on each rerun. This avoids stale crew/time summaries after proposal generation. Editor values refresh when the saved record changes. Invalid submissions retain form values for correction.

The request guide keeps an explicit draft while moving forward or back. A successful create clears that draft once, shows the created request, and offers planning as the next action, preventing accidental duplicate submissions on rerun.

Connection status describes the last fetch; this is not a live telemetry feed. Use **Refresh snapshot** to fetch current records. Planner names provide audit attribution, not a login.

The interface uses native headings, containers, metrics, dataframes, forms/inputs, expanders and feedback. Plotly supplies the Gantt chart; tabular details provide exact values alongside it. The About diagram uses Streamlit's native chart support. Desktop and narrow-width validation is recorded in [design-qa.md](design-qa.md).

See the root README for the complete journey and TECH_STACK.md for the architecture contract.
