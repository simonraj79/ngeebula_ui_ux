# Public GitHub publication

## Repository layout

```text
backend/          FastAPI, solver, reference catalogs and fictional demo seed
web/              Primary React/TypeScript UI and exact npm lock
frontend/         Retained historical Streamlit interface
data/ps1/         Byte-identical supplied pack and manifest
submissions/ps1/  Generated A/B/C CSVs and separate validation evidence
tests/            Isolated API, UI, data and scheduling tests
scripts/          Configuration, reference import and publication checks
docs/             Research, setup, design and publication documentation
docs/plans/       Historical implementation plans
README.md         Project overview and local setup
TECH_STACK.md     Architecture and technology decisions
VALIDATION.md     Verification history and limitations
AGENTS.md         Repository-specific coding guidance
```

## Private files stay local

`.gitignore` excludes `.env` and variants, Streamlit secrets, private keys, database files and journals, local exports, environments, logs, process state and caches. `.env.example`, Streamlit theme configuration and public source/reference files remain includable. Git ignore rules do not remove files already committed; the publication audit also checks tracked private paths.

The supplied PS1 pack is pinned and hashed under data/ps1. Preserve its attribution and do not treat the absence of an upstream licence as a reuse grant. Built web/dist and node_modules are ignored.

The original `backend/engineers_db.json` is included at the project owner's explicit request and confirmation that it is dummy data (17 September 2026). Its 700 source records produce 697 engineers after duplicate-email removal. Existing local databases and saved work are never reseeded. The roster is not operational staffing evidence.

## Review and publish when ready

The publication target is [simonraj79/ngeebula_ui_ux](https://github.com/simonraj79/ngeebula_ui_ux), branch `main`. Run these checks before subsequent commits:

```powershell
.\.venv\Scripts\python.exe scripts/audit_public_release.py
.\.venv\Scripts\python.exe -m pytest -q
git status --short
git add .
git diff --cached --stat
git diff --cached --check
.\.venv\Scripts\python.exe scripts/audit_public_release.py
```

Inspect staged files before committing and pushing to the configured remote. Avoid uploading an archive of the whole workspace: Git ignore rules protect Git operations, not arbitrary ZIP files. Never use `git add -f` for excluded secrets or local data. The audit looks for common credential formats and private paths; it is a focused check, not a guarantee against every possible secret.

## Attribution and licensing

Original project attribution remains in the root README. LTA station data retains its source URLs, access date, hashes and Singapore Open Data Licence notice. No software licence has been selected or added as part of this organization task; decide the project licence separately, accounting for the original source. Publishing publicly and choosing a reuse licence are separate decisions.
