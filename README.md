# AEROGUARD TRUST

**Earlier fire warning for metal-working production halls, with a verified response workflow.**

Built for **AeroEntrepreneur 2026** (Tunisian Aeroday × Protection Civile × INJAZ Tunisia).

> Prototype. Sensor data is a **historical replay of real recordings** (Industrial Hall dataset, controlled fire and nuisance experiments, 2023). The facility layout is illustrative. Human roles are demo roles. Drone inspection is a simulated workflow. Hedera anchoring is planned, not implemented.

## What it does

1. **9 multi-gas sensor nodes** in a production hall (CO, CO₂, H₂, VOC, particles, temperature, humidity).
2. **AI zone model** tells incipient fires (incl. a cable fire) apart from routine nuisances such as welding, cutting and exhaust.
3. **Explainable risk engine**: persistence + two-node coincidence (as in "double-knock" fire systems) + sensor health → NORMAL / WATCH / HIGH / CRITICAL with reasons.
4. **Digital Safety Case** opens on CRITICAL and closes only with three confirmations: the technician's action, an **independent** verifier, and **15 minutes of measured readings back to normal**.
5. **Safety Passport**, **Black Box** timeline (hash-chained event log) and **Emergency Fire Pack** for the Protection Civile.

Certified fire alarms and emergency shutdown systems always remain independent of AEROGUARD.

## Evidence (real data, held-out)

| Claim | Result | Status |
|---|---|---|
| Detect fires in an industrial hall (held-out events) | AI 16/17 fires, 4/15 nuisance alarms; a calibrated particle threshold does as well (17/17, 3/15) and raises fewer background alarms | held-out, small sample |
| Alarm earlier than a calibrated particle threshold | earlier on 14/16 fires detected by both, median 195 s | held-out, small sample |
| Earlier than a conventional detector (lab) | electrical fires warned 3.8–11.9 min earlier; 6/7 fires earlier | laboratory |
| Equipment failure early warning (railway compressor) | 4/4 failures detected, 2 before onset | exploratory, secondary |
| Prevents fires | – | **not demonstrated** |

Details: [ai/reports/evaluation.md](ai/reports/evaluation.md) · [docs/DATA_PROVENANCE_AUDIT.md](docs/DATA_PROVENANCE_AUDIT.md) · [docs/INDUSTRY_SELECTION.md](docs/INDUSTRY_SELECTION.md) · [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) · [docs/DATASETS.md](docs/DATASETS.md)

## Run it (Python 3.11+; no Node.js needed)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m ingest download        # real datasets from official sources, hash-checked
.venv/Scripts/python -m ai.train               # train + evaluate all models (~10 min; --fast reuses cached CV)
.venv/Scripts/python -m ai.holdout             # held-out models used by the replay (~1 min)
.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
```

Open **http://localhost:8000**. The backend serves the interface; there is no separate frontend build. On macOS/Linux use `.venv/bin/python`.

## Demo walkthrough (about 3 minutes)

1. **Live monitoring** → choose **Cable#4** (real cable fire) → speed 60× or 120× → **Start replay**.
2. Watch the model's P(fire) rise on the chart and the hall map turn red. At **CRITICAL** a Safety Case opens and the replay **pauses automatically**.
3. Open the case: AI findings with the recorded readings, recommended inspection.
4. **Drone inspection** (simulated): request → approve → launch → complete.
5. Switch the demo role (top right) to **Technician** → record the corrective action.
6. Switch to **Verifier** → approve (must be a different person).
7. Back to **Live monitoring** → **Resume** → the real post-fire readings play.
8. In the case → **Run stabilization check**. The case closes only after 15 consecutive minutes of **live** normal readings. In this dataset the recording holds its last values after each experiment, so the check reports *awaiting stabilization* and explains why: AEROGUARD does not close a case on data it cannot trust.
9. **Safety Passport**, **Black Box** and **Fire Pack** show the result.
10. Try **Exhaust#1** (nuisance: no case opens) and **Welding#1** (known limitation: the model never saw welding in training).

Use **Reset demo** (sidebar) to start again.

## Feature status

| Feature | Status |
|---|---|
| Replay of real recordings, live inference with held-out models, no future data | ✅ operational |
| Risk engine, alerts, Safety Case workflow with enforced rules | ✅ operational (demo roles, no real authentication) |
| Stabilization measured on real post-event readings | ✅ operational |
| Safety Passport, Black Box, local SHA-256 hash chain | ✅ operational |
| Emergency Fire Pack (printable) | ✅ operational, layout/contacts illustrative |
| Drone inspection | 🟣 simulated workflow, no imagery invented |
| Hedera anchoring | ⏳ planned (shown as "pending") |
| Real sensors, real drone, authentication, multi-site | ⏳ planned |

## Tests

```bash
.venv/Scripts/python -m pytest -q
```
Covers dataset integrity, loaders, physics model, AI models, registry tamper detection, causal (no-future-data) features, risk engine, Safety Case rules (independent verifier, stabilization), event-chain tampering, API errors, UI assets and the full workflow on real data.

## Build tracker
```bash
.venv/Scripts/python scripts/tracker/server.py
```
Then open http://localhost:8765.

## Repository

| Folder | Content |
|---|---|
| `ingest/` | Dataset registry, hash-checked download, loaders |
| `ai/` | Models, evaluation, held-out models, registry with model cards |
| `physics/` | Thermal energy-balance model fitted on real data (secondary) |
| `backend/` | FastAPI: replay, risk engine, Safety Cases, event store |
| `dashboard/` | Control-room interface (Preact + Chart.js, vendored, works offline) |
| `docs/` | Audit, sector selection, MVP scope, datasets, requirements |
| `scripts/` | Data audit, figures, build tracker |

## Data credits
Industrial Hall and Test Chamber fire datasets (Mendeley Data, CC BY 4.0), Indoor Laboratory Fire Dataset (Zayed University, CC BY 4.0), SKAB (GPL-3.0), MetroPT-3 (UCI, CC BY 4.0), induction-motor thermal images (Najafi et al., CC BY 4.0), ARIA (BARPI, Licence Ouverte 2.0). Full citations in [docs/DATASETS.md](docs/DATASETS.md).

## Team
ORBITA · INSAT.
