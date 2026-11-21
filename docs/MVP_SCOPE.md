# MVP scope

## The scenario
A safety manager of a metal-working production hall watches AEROGUARD TRUST in the control room. Recorded, real sensor data from the Industrial Hall dataset is **replayed** (clearly labelled as historical replay) and analysed by the trained model in real time.

| Item | Definition |
|---|---|
| Facility type | Production hall of a metal-working plant (automotive components / fabrication). **Illustrative facility**; the measurements come from the Industrial Hall dataset (10 × 22 × 8 m hall, controlled experiments, July 2023). |
| Monitored object | The hall zone, instrumented with **9 multi-gas sensor nodes** (IDs from the dataset). Node positions on the map are illustrative. |
| Measurements | CO (ppm), CO₂ (ppm), H₂ (raw), VOC (raw), particles by size (counts), air temperature (°C), humidity (%), every 10 s per node. |
| Abnormal condition detected | Incipient fire (smouldering / flaming; including a cable fire) as opposed to routine nuisances (welding, abrasive cutting, exhaust, fog, solvents). |
| AI model | Gradient-boosted trees on causal features relative to each node's recent background; outputs P(fire), P(nuisance) per node. Replay uses a **held-out model** that never saw the replayed event. |
| Risk logic | Transparent rules on model output: persistence (30 s), number of agreeing nodes (coincidence), sensor health (missing/frozen data), zone criticality. Levels NORMAL / WATCH / HIGH / CRITICAL. Not calibrated probabilities. |
| Operational response | Alert → Digital Safety Case → drone inspection request (**simulated**) → technician action → independent verifier → stabilization check on **measured** data → closure. Emergency Fire Pack available. |
| Evidence recorded | Sensor snapshot at alert, model outputs and reasons, every human action with role and time, stabilization check result. Stored in SQLite and chained with SHA-256 (local integrity). |
| Blockchain | **Not implemented yet.** Records show "Hedera anchoring: pending". No fake transaction is shown. |

## Feature status

| Feature | Status |
|---|---|
| Historical replay of real hall data with start / pause / speed / event choice | Operational |
| Live model inference during replay (no future data) | Operational |
| Risk engine with reasons | Operational |
| Alerts and Digital Safety Case with 3-step closure | Operational (demo roles, not real authentication) |
| Stabilization check on live post-event data | Operational. On this dataset no fire event has 15 min of live recovery data (held values after experiments), so cases correctly stay *awaiting stabilization* |
| Drone inspection | **Simulated workflow**; reference thermal image labelled as illustrative (motor dataset, not this hall) |
| Safety Passport of the zone | Operational (local records, integrity hash chain) |
| Black Box timeline | Operational (from persisted events) |
| Emergency Fire Pack | Operational; facility map, exits and hazard list are **illustrative** |
| Hedera anchoring | Planned |
| Secondary research demos (lab lead time, compressor, motor) | Shown as evidence in the AI evidence page |
| Real authentication, multi-site, hardware sensors, real drone | Planned |

## Safety boundaries
- Certified fire alarms and emergency shutdown systems remain independent. AEROGUARD never authorises a dangerous operation and never replaces them.
- Human roles (technician, verifier) are **demo roles** chosen in the UI.
