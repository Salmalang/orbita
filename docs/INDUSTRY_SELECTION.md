# Industry and use-case selection

The MVP must rest on **one** sector and **one** use case supported by authentic data. We compared the candidates that the verified datasets can actually support.

## Candidates

| Candidate use case | Data behind it | Data class | Fire relevance | Label quality | Demo strength | Factory realism |
|---|---|---|---|---|---|---|
| **A. Early fire detection in a production hall, telling real incipient fires (incl. cable fire) from routine process nuisances (welding, grinding/cutting, exhaust)** | Industrial Hall: 9 multi-gas nodes, 17 fires, 15 nuisances, 64 h continuous | B (real hall, controlled events) | **Direct**: incipient fire | Event + stage labels, fire/nuisance flags | High: real timestamps, recovery data after each event, held-out models | High: welding and cutting are routine in metal-working plants |
| B. Electrical fire early warning vs a smoke detector | Indoor Laboratory: 4 electrical fires | B (lab) | Direct | Stage + detector labels | Medium: 8 short recordings | Medium (lab room) |
| C. Compressor failure early warning | MetroPT-3: 7 months, 4 failures | A, but **railway** | Indirect (air leak, not fire) | 4 failure reports only | Medium: long time scale | Low for a factory story: train equipment |
| D. Motor/pump anomaly detection | SKAB bench | B (lab) | Indirect | Point labels | Medium | Medium |
| E. Automotive-component plant, electrical/electromechanical equipment monitoring (team's first preference) | No authentic factory equipment data available | – | – | – | – | Would require inventing data → rejected |

## Decision

**Sector:** discrete manufacturing — **metal-working production halls** (automotive components, metal fabrication), where hot work such as welding and abrasive cutting is part of normal operation.

**Use case (primary MVP):** **zone-level early fire warning in halls where routine hot work produces smoke and gases**, followed by a verified response (Safety Case, simulated drone check, technician and independent verifier, measured stabilization).

Why this one:
1. It is the only candidate whose data directly contains **incipient fires and factory-type nuisances in an industrial hall**.
2. The labels are good enough to test on **held-out events** (each recording judged by a model that never saw it).
3. The recording continues **after** each event. However, the audit found that for 20–45 minutes after most experiments the recording repeats held values (not live measurements), so "return to normal" can rarely be confirmed on this dataset; the prototype keeps such cases open instead of closing them on untrustworthy data.
4. Nuisance alarms are a real operational pain: a system that alarms during welding gets disabled. The data let us measure this directly. Result: the AI model does not reject nuisances better than a calibrated particle threshold (4/15 vs 3/15 nuisance alarms), but it alarms earlier on 14 of 16 fires (median 195 s); see docs/MODEL_REPORT.md.
5. It matches the team's preferred sector (automotive-component plants) without inventing equipment data: the monitored object is the **production hall zone**, not a specific machine.

**Not chosen as primary, kept as clearly labelled secondary research demonstrations:** B (supports the "earlier than a conventional detector" message), C (railway compressor, exploratory), D (laboratory bench). They are never presented as data from the MVP facility.

## What we must not claim
- That the hall data comes from an automotive factory or from Tunisia. It is a controlled-experiment industrial hall.
- That the system prevents fires (not demonstrated).
- That risk levels are calibrated fire probabilities.
