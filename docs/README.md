# Documentation

Start with the root [README](../README.md), [technology report](../TECH_STACK.md) and [verification record](../VALIDATION.md).

| Topic | Document |
|---|---|
| Supplied PS1 data and provenance | [Dataset audit](PS1_DATA_AUDIT.md) |
| PS1 rules and algorithm | [Backend audit](PS1_BACKEND_GAP_AUDIT.md) |
| PS1 validation boundaries | [Acceptance review](PS1_ACCEPTANCE_REVIEW.md) |
| React interface decisions | [UX plan](PS1_UX_PLAN.md) |
| Current migration scope | [Implementation plan](plans/PS1_REACT_MIGRATION.md) |
| Public GitHub preparation | [Publication guide](PUBLIC_RELEASE.md) |
| Showcase, comparison and ROI | [Implementation and evidence](SHOWCASE_IMPLEMENTATION.md) |
| Public APIs and station provenance | [LTA and SMRT research](PUBLIC_DATA_RESEARCH.md) |
| Singapore problem context and data limitations | [Research and data](RESEARCH_AND_DATA.md) |
| Optional Gemini setup | [Configuration guide](GEMINI_SETUP.md) |
| Guided visual repair intake | [Visual repair design](VISUAL_REPAIR_PLAN.md) |
| Station-first location selection | [Location review](LOCATION_UX_REVIEW.md) |
| Showcase design audit | [UX audit](SHOWCASE_UX_AUDIT.md) |

Historical implementation plans live in [plans/](plans/). They record earlier decisions and test counts; use the current verification record for the latest state.

- [Render deployment](RENDER_DEPLOYMENT.md) — runtime, secrets, hosting and persistence limits.

The current deployed frontend is React in `web/`. Documents describing Streamlit, comparison/ROI or the stakeholder video describe retained legacy capabilities; they are not PS1 submission evidence.
