# ARGOS — One Step Ahead

**Earlier fire warning for metal-working production halls, with a verified response workflow.** (Project formerly named AEROGUARD TRUST; the scientific report and audit keep the former name.)

Built for **AeroEntrepreneur 2026** (Tunisian Aeroday × Protection Civile × INJAZ Tunisia).

> Prototype. Sensor data is a **historical replay of real recordings** (Industrial Hall dataset, controlled fire and nuisance experiments, 2023). The facility layout is illustrative. Human roles are demo roles. Drone inspection is a simulated workflow. Hedera anchoring runs on the public **testnet** (see below). The firefighter briefing uses a fictional demo factory.

## What it does

1. **9 multi-gas sensor nodes** in a production hall (CO, CO₂, H₂, VOC, particles, temperature, humidity).
2. **AI zone model** tells incipient fires (incl. a cable fire) apart from routine nuisances such as welding, cutting and exhaust.
3. **Explainable risk engine**: persistence + two-node coincidence (as in "double-knock" fire systems) + sensor health → NORMAL / WATCH / HIGH / CRITICAL with reasons.
4. **Digital Safety Case** opens on CRITICAL and closes only with three confirmations: the technician's action, an **independent** verifier, and **15 minutes of measured readings back to normal**.
5. **Safety Passport**, **Black Box** timeline (hash-chained event log), a site-level **Emergency Fire Pack** page and, for each critical fire incident, a **Firefighter Emergency Pack** (QR code, mobile briefing, PDF).

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
Overview → load the authentic **Cable#4** recording → replay at 60× → CRITICAL when two sensors agree; a Safety Case opens and the replay pauses → Firefighter Emergency Pack (QR code, firefighter view, PDF) → approve the alert-triggered drone inspection → technician action → independent verification → resume the replay → closure check **refuses** to close because the post-fire recording repeats held values → Equipment Passport → Black Box.

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
| Emergency Fire Pack | Site-level printable sheet for responders (illustrative layout). Incident-specific briefings are the Firefighter Emergency Packs on each critical incident page |
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
| Hedera anchoring | **Real** on Hedera **testnet** (fingerprint only, mirror-node verification). Demo topic `0.0.11560556`: one evidence-chain fingerprint anchored and verified. Inactive without testnet credentials in `.env` |
| Firefighter Emergency Pack | **Real** QR link, signed expiring access, briefing built from real incident records; factory layout **fictional demo data**; demo access mode |
| AI learning from new incidents | **Data pipeline only**: outcome labels, eligibility, dataset manifest + SHA-256. No retraining has happened: replayed incidents come from recordings already used in training |

## Hedera evidence (testnet)

ARGOS stores a digital fingerprint of the incident history on Hedera so later changes can be detected. Only a small JSON snapshot is sent (chain id, last event number, chain-head SHA-256, UTC time, evidence type): never sensor data, names or files.

1. Create a free testnet account at portal.hedera.com.
2. Copy `.env.example` to `.env` (git-ignored) and fill `HEDERA_ACCOUNT_ID` and `HEDERA_PRIVATE_KEY`. Leave `HEDERA_TOPIC_ID` empty to create a topic on first anchor.
3. Restart the server, open **Equipment History → Hedera evidence**, click **Anchor evidence to Hedera**, then **Verify on Hedera**.

Verification reads the message back from the public mirror node and compares it with the stored snapshot and with a fresh recomputation of the local chain. Statuses: Verified on Hedera, Awaiting confirmation, Evidence mismatch, Hedera unavailable, Not anchored.

Testnet record for this prototype: topic `0.0.11560556`, message 1, transaction `0.0.11555158@1795303235.891794919` ([HashScan](https://hashscan.io/testnet/topic/0.0.11560556)). **Reset demo** clears the local database, including its anchor records, so after a reset the interface shows "Not anchored" until a new fingerprint is anchored. Hedera proves a fingerprint existed at a consensus time; it does not prove sensor readings or labels are physically true.

## Firefighter Emergency Pack (QR code)

When a fire-related incident reaches **CRITICAL**, ARGOS issues a Firefighter Emergency Pack automatically. The incident page shows a QR code, an **Open Firefighter View** button, and downloads for the QR image and a printable PDF briefing. Clicking the QR code or the button opens the same briefing on this computer (in a new tab; where the browser opens it in the same tab, a bar leads back to the incident).

- The QR code holds only a URL. The URL carries a signed, incident-specific token that expires after 2 hours (`ARGOS_PACK_TTL_MIN`). The operator can revoke it or issue a new one. The token never enters the evidence chain or Hedera.
- Scanning opens a mobile-first briefing: severity banner, immediate summary, factory floor plan, emergency access and hazards, sensor and AI analysis, the timeline, and provenance and verification. Confirmed facts, sensor observations, AI hypotheses and unknowns are shown separately. No entry route is ever recommended.
- The factory layout (`backend/app/data/emergency_site.json`) is a **fictional demonstration factory**. Only Hall A's sensor readings come from real recordings. Drone results are labelled simulated.
- The QR page needs network access to the ARGOS server. The PDF is the offline backup (copies are saved under `data/emergency_packs/`, which git ignores).
- To scan from a phone on the same network, start the server with `--host 0.0.0.0` and allow the port in the firewall. The QR code uses this computer's network address. Set `ARGOS_PUBLIC_URL` to use another address (for example an HTTPS host).
- Demo access only: a real deployment needs authenticated responders, HTTPS and the site's verified emergency plan. The briefing is decision support, not an approved emergency response plan. ARGOS never contacts emergency services on its own.

Guided Tour 2 includes the pack: after the incident opens, the tour shows the QR code, opens the firefighter view and offers the PDF.

## AI learning (controlled)

After the independent check, a second person confirms what really happened (real fire, nuisance, equipment problem, normal, not sure). An incident becomes training data only if: outcome confirmed by someone other than the technician, not inconclusive, not a simulated drone finding, evidence chain intact and verified on Hedera, and the recording is genuinely new (not already in the approved training data). **AI Evidence → AI learning** prepares a hashed dataset manifest, verifies it, can anchor its fingerprint, and refuses to train a candidate when there are no genuinely new verified incidents. A candidate is never promoted automatically.

## Tests

```bash
.venv/Scripts/python -m pytest -q
```
Covers dataset integrity, loaders, physics model, AI models, registry tamper detection, causal (no-future-data) features, risk engine, Safety Case rules (independent verifier, stabilization), event-chain tampering, Hedera anchoring and verification (network mocked), learning eligibility and dataset hashing, the Firefighter Emergency Pack (signed links, expiry, revocation, QR, PDF), API errors, UI assets and the full workflow on real data.

## Build tracker (internal team tool)
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
| `hedera/` | Hedera testnet anchoring and mirror-node verification |
| `learning/` | Outcome eligibility, dataset manifests, leakage check |
| `dashboard/` | Control-room interface (Preact + Chart.js, vendored, works offline) |
| `docs/` | Audit, sector selection, MVP scope, datasets, requirements |
| `scripts/` | Data audit, figures, build tracker |

## Data credits
Industrial Hall and Test Chamber fire datasets (Mendeley Data, CC BY 4.0), Indoor Laboratory Fire Dataset (Zayed University, CC BY 4.0), SKAB (GPL-3.0), MetroPT-3 (UCI, CC BY 4.0), induction-motor thermal images (Najafi et al., CC BY 4.0), ARIA (BARPI, Licence Ouverte 2.0). Full citations in [docs/DATASETS.md](docs/DATASETS.md).

## Team
ORBITA · INSAT.
