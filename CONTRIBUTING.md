# ARGOS — contributor guide

Hackathon: **AeroEntrepreneur / Tunisian Aeroday**, in partnership with the Protection Civile and INJAZ Tunisia.
**Hard deadline: Sunday 22 November, 09:00** (deliverables uploaded to the team Google Drive). The organizers' specification is kept locally (not in the repository); the early planning checklist is `docs/REQUIREMENTS.md`. The current state of the prototype is in `README.md` and `docs/MVP_SCOPE.md`.

## The product (as built)
Earlier fire warning for a metal-working production hall, with a verified response workflow:
1. **Sensors**: 9 multi-gas nodes of the Industrial Hall dataset, replayed from real recordings.
2. **AI zone model** (held-out) separating incipient fires from routine work fumes; evaluated in `ai/reports/evaluation.md`.
3. **Risk engine**: transparent rules (persistence, two-node coincidence, sensor health) → NORMAL / WATCH / HIGH / CRITICAL.
4. **Inspection drone**: **simulated** patrols, alert inspections and findings (no physical drone, no imagery).
5. **Digital Safety Case**: closes only with the technician's action, an independent verifier (a different person) and 15 minutes of live readings back to normal.
6. **Emergency Fire Pack** (site sheet) and, for each CRITICAL fire incident, a **Firefighter Emergency Pack**: signed, expiring QR link, mobile briefing and PDF on a fictional demo factory.
7. **Digital Black Box**: hash-chained incident timeline.
8. **Hedera Consensus Service** (testnet): only SHA-256 fingerprints are anchored (no confidential data).
9. **AI learning**: controlled data pipeline only; no automatic retraining or promotion.

Ideas from the original concept that were **not** built: MEL mode, aviation-style drone dispatch, drone thermal re-check, a hardware drone adapter, current and vibration sensors on live assets.

Certified fire alarms always remain independent of ARGOS. Never write code or copy that implies otherwise.

## Mandatory constraints from the spec
Realism and consistency with aeronautical standards · real-time interactivity (the user makes decisions live) · **real data only, never generated** (see docs/DATASETS.md) · **physical simulation** = physics models fitted on real measurements (`physics/`) · safety of people and the environment first.

## Repo layout
```
docs/        model report, data audit, datasets, MVP scope, contracts, demo script
backend/     FastAPI app: replay, risk engine, Safety Cases, event store, emergency pack
backend/app/data/facility.json         production hall used by the replay (illustrative layout)
backend/app/data/emergency_site.json   fictional factory of the firefighter briefing
backend/app/data/site.json             original multi-asset contract model (tests only)
ingest/      dataset registry, downloader (hash-checked) and loaders for the real datasets
physics/     physics models identified on real data (thermal energy balance)
ai/          models, training, evaluation, model registry, inference
hedera/      HCS anchoring + mirror-node verification
learning/    outcome eligibility, dataset manifests, leakage check
drone/       simulated missions, scheduler and findings
dashboard/   static web UI served by FastAPI (no Node.js build step)
tests/       pytest suite
scripts/     data audit, figures, model report, internal build tracker
```

## Conventions
- Python 3.14, venv in `.venv` (`.venv/Scripts/python` on Windows). Install deps from `requirements.txt`.
- Run tests: `.venv/Scripts/python -m pytest -q`. Every part must keep the suite green.
- All timestamps are timezone-aware UTC. All IDs are strings. Units go in field names (`temperature_c`, `current_a`, `gas_ppm`, `vibration_mm_s`).
- Import contracts from `backend.app.schemas`. Never redefine them elsewhere.
- Report **only measured numbers** for AI results. Never invent or round up metrics.
- **Never generate or synthesise data.** Use the real datasets in docs/DATASETS.md. Raw data stays in data/raw/ (not committed).
- **Never commit `.env`** or any Hedera key. Use `.env.example` for names only.
- Hedera must never block a safety action: anchoring is asynchronous with a retry queue.
