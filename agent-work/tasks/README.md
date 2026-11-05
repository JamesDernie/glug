# Per-feature task directories

Create one directory per feature, e.g. `agent-work/tasks/material-movement/`.

Copy `agent-work/requirements.example.json` to `requirements.json` and replace its contents with the actual feature requirements.

Recommended files:
- `design.md` — a copy or stable reference to the source design.
- `requirements.json` — atomic requirements and verification mapping.
- `plan.md` — dependency-aware implementation plan.
- `architecture-map.md` — relevant modules, patterns, and dependencies.
- `decisions.md` — accepted decisions, rationale, and deviations.
- `progress.md` — completed work and next actions.
- `review-findings.json` — structured independent review findings.
- `verification.json` — test and quality evidence.

Never store secrets, credentials, personal data, or production dumps in task artifacts.
