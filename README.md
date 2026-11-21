# ARGOS — One Step Ahead

**Earlier fire warning for metal-working production halls, with a verified response workflow.** (Project formerly named AEROGUARD TRUST; the scientific report and audit keep the former name.)

Built for **AeroEntrepreneur 2026** (Tunisian Aeroday × Protection Civile × INJAZ Tunisia).

> Prototype. Sensor data is a **historical replay of real recordings** (Industrial Hall dataset, controlled fire and nuisance experiments, 2023). The facility layout is illustrative. Human roles are demo roles. Drone inspection is a simulated workflow. Hedera anchoring is planned, not implemented.

## What it does

1. **9 multi-gas sensor nodes** in a production hall (CO, CO₂, H₂, VOC, particles, temperature, humidity).
2. **AI zone model** tells incipient fires (incl. a cable fire) apart from routine nuisances such as welding, cutting and exhaust.
3. **Explainable risk engine**: persistence + two-node coincidence (as in "double-knock" fire systems) + sensor health → NORMAL / WATCH / HIGH / CRITICAL with reasons.
4. **Digital Safety Case** opens on CRITICAL and closes only with three confirmations: the technician's action, an **independent** verifier, and **15 minutes of measured readings back to normal**.
5. **Safety Passport**, **Black Box** timeline (hash-chained event log) and **Emergency Fire Pack** for the Protection Civile.

Certified fire alarms and emergency shutdown systems always remain independent of ARGOS.

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

## Guided demo (recommended for the jury)

Click **▶ Guided tour** (top right). Each step explains what you see; its button performs the real action in the application.

**Scenario 1 · Preventive drone inspection (simulated drone, illustrative finding)**
Patrol schedule → start the full patrol → watch the drone visit the checkpoints → record an illustrative finding (blocked east exit) → open a Safety Case → technician action → independent verification → follow-up drone inspection marks the exit clear → case closes (simulated inspection evidence, labelled).

**Scenario 2 · Real-data AI early warning (real recording, held-out model)**
Overview → load the authentic **Cable#4** recording → replay at 60× → CRITICAL when two sensors agree; a Safety Case opens and the replay pauses → approve the alert-triggered drone inspection → technician action → independent verification → resume the replay → closure check **refuses** to close because the post-fire recording repeats held values → Equipment Passport → Black Box.

Use **Reset demo** (sidebar) or "Start from a clean slate" in the picker to begin again. Try also **Exhaust#1** (nuisance: no case opens) and **Welding#1** (known limitation: the model never saw welding).

One-minute video plan: [docs/DEMO_VIDEO_SCRIPT.md](docs/DEMO_VIDEO_SCRIPT.md).

## Screens

| Screen | What it answers |
|---|---|
| Overview | Is my facility safe? What needs attention? What should I do next? Next patrol, drone status, findings |
| Live Monitoring | Replay of real recordings, AI fire/nuisance likelihood per sensor, risk level with reasons |
| Drone Inspections | Routine patrols (scheduled or manual), routes and checkpoints, live position, findings, approvals, history |
| Incident Follow-up (Safety Cases) | Investigations from sensor alerts or patrol findings; action, independent verification, closure rules |
| Equipment History | Zone history, cases, inspections, integrity chain, model provenance |
| Event Timeline (black box) | Every event in order, labelled by source (recorded data, model, risk engine, human demo role, simulated) |
| Emergency Fire Pack | Printable emergency sheet for responders |
| AI Evidence | What the real data supports and what it does not |

## Real versus simulated

| Component | Status |
|---|---|
| Sensor readings | **Real** recordings (Industrial Hall dataset, staged experiments), replayed |
| AI inference during replay | **Real** held-out models, causal features, no future data |
| Risk engine, Safety Case rules, independent verification, held-value detection | **Real** logic, tested |
| Stabilization check (sensor cases) | **Real** logic on replayed live readings; refuses held/missing data |
| Drone movement, missions, scheduler, findings | **Simulated** (no physical drone, no imagery, no validated vision/thermal model) |
| Closure of patrol-finding cases | Based on a **simulated** follow-up inspection, labelled as such |
| Facility layout, checkpoint positions, contacts | **Illustrative** |
| Roles | Demo roles, no authentication |
| Hedera anchoring | **Pending** (not implemented) |

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
