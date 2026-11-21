# ARGOS — contributor guide

Hackathon: **AeroEntrepreneur / Tunisian Aeroday**, in partnership with the Protection Civile and INJAZ Tunisia.
**Hard deadline: Sunday 22 November, 09:00** (deliverables uploaded to the team Google Drive). The spec is `docs/cahier_des_charges.pdf`; every requirement is tracked in `docs/REQUIREMENTS.md`. Check that file before and after each work session.

## The product
An industrial fire-safety platform for factories and high-risk sites that applies aviation safety principles:
1. **IoT sensors** (temperature, current, gas, vibration) on critical assets.
2. **AI anomaly detection** learns each asset's *normal signature* and flags drifts before fixed thresholds fire. It does not try to predict specific causes, because the Civil Protection told us causes are too varied to predict one by one.
3. **Risk engine** scores severity (LOW / MEDIUM / HIGH / CRITICAL) with transparent, explainable rules.
4. **Inspection drone**: dispatched by the platform with ATC-style priorities, flies only pre-mapped routes from docking stations, and brings thermal/visual evidence.
5. **Digital Safety Case** that closes only with **3 signatures**: technician, independent verifier (a different person), and the **system** (readings back to normal over a stabilization period, plus a drone thermal re-check). Inspired by the independent inspection in EASA Part-145.
6. **MEL mode** (Minimum Equipment List, as in EASA/FAA MMEL/MEL): MEDIUM cases can run under time-limited restrictions. HIGH/CRITICAL cases never can.
7. **Emergency Fire Pack** for the Protection Civile: zone, hazmat, exits, last readings, secure link + QR + offline PDF.
8. **Digital Black Box**: incident timeline replay.
9. **Hedera Consensus Service**: only SHA-256 fingerprints are anchored (no confidential data). Detailed data stays private.

Certified fire alarms always remain independent of ARGOS. Never write code or copy that implies otherwise.

## Mandatory constraints from the spec
Realism and consistency with aeronautical standards · real-time interactivity (the user makes decisions live) · **real data only, never generated** (see docs/DATASETS.md; Protection Civile data when received) · **physical simulation** = physics models fitted on real measurements (`physics/`) · safety of people and the environment first.

## Repo layout
```
docs/        spec PDF, REQUIREMENTS.md, CONTRACTS.md, later MODEL_REPORT.md, HEDERA.md, DEMO.md
backend/     FastAPI app. backend/app/schemas.py = SINGLE SOURCE OF TRUTH for data contracts
backend/app/data/site.json   demo factory (zones, assets, docks, exits, hazmat)
ingest/      dataset registry, downloader (hash-checked) and loaders for the real datasets
physics/     physics models identified on real data (thermal energy balance)
ai/          anomaly models, training, evaluation, model registry, inference API
hedera/      HCS anchoring + verification
drone/       mission dispatcher + flight simulation (+ optional DJI Tello adapter, off by default)
dashboard/   static web UI served by FastAPI (NO Node.js build step: Node is not installed)
tests/       pytest suite
scripts/     demo and utility scripts
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
