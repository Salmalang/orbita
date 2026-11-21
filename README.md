# AEROGUARD TRUST

**Aviation-grade safety for every industrial machine.**
AI anomaly detection, an inspection drone, 3-signature safety cases and Hedera-anchored proof for factory fire prevention.

Built for **AeroEntrepreneur 2026** (Tunisian Aeroday × Protection Civile × INJAZ Tunisia).

> 🚧 Work in progress. Sections below are filled in as each part is built.

## The problem
Fire causes in industry are too numerous and varied to predict one by one, as the Protection Civile officers we interviewed told us. Conventional systems react to fixed thresholds or to smoke, which is often too late.

## The solution
1. **Sensors** on critical assets measure temperature, current, gas and vibration.
2. **AI** learns each machine's normal signature and flags drifts before fixed thresholds fire.
3. **Risk engine** with explainable severity scoring.
4. **Drone** dispatched like air traffic control to inspect and bring thermal evidence.
5. **Safety case** that closes only with 3 signatures: technician, independent verifier, and the machine itself.
6. **MEL mode** (from aviation's Minimum Equipment List): restricted operation instead of a full shutdown, MEDIUM cases only.
7. **Fire Pack** for the Protection Civile, plus a **black box** replay.
8. **Hedera** anchors fingerprints only; confidential data stays private.

Certified fire alarms always remain independent of AEROGUARD.

## Repository
| Folder | Content | Status |
|---|---|---|
| `docs/` | Spec, [requirements checklist](docs/REQUIREMENTS.md), [data contracts](docs/CONTRACTS.md) | ✅ |
| `backend/` | FastAPI platform, contracts, demo site | 🟡 |
| `ingest/` | Real datasets: registry, hash-checked download, loaders ([list](docs/DATASETS.md)) | ✅ |
| `physics/` | Thermal energy-balance model fitted on real data | ✅ |
| `ai/` | 4 AI models trained and evaluated on real data ([results](ai/reports/evaluation.md)) | ✅ |
| `hedera/` | Hedera Consensus Service anchoring | ⬜ |
| `drone/` | Mission dispatcher and flight simulation | ⬜ |
| `dashboard/` | Control-room web interface | ⬜ |

## Run
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m ingest download
.venv/Scripts/python -m ai.train
.venv/Scripts/python -m pytest -q
```

## Team
INSAT team. Names to be added.

### Build tracker
```bash
.venv/Scripts/python scripts/tracker/server.py
```
Then open http://localhost:8765 to see build progress, spec requirements, tests and recent commits.
