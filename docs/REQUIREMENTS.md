# Requirements checklist — AeroEntrepreneur (Tunisian Aeroday × Protection Civile × INJAZ)

> Planning checklist written at the start of the project. The statuses and the "how we answer" column are **not maintained** and include early ideas that were not built (MEL mode, aviation-style dispatch, drone thermal checks). The current state of the prototype is in [README.md](../README.md) and [MVP_SCOPE.md](MVP_SCOPE.md).

Source: the organizers' specification (kept locally, not in the repository). Section numbers (§) follow its own numbering.
Status: ⬜ todo · 🟡 in progress · ✅ done · ➖ not applicable / team task outside the repo

**Hard deadline: 22 November, 09:00.** Any deliverable submitted after 09:00 is rejected (§05). Submit to the team Google Drive folder.

## Problem to answer (§01)
> How can aeronautical technologies help improve the prevention, detection and management of fires in buildings, infrastructure and high-risk sites (factories, large companies), with innovative, effective and economically viable solutions based on AI models?

| # | Requirement | How AEROGUARD TRUST answers | Status |
|---|---|---|---|
| P1 | Aeronautical technology plays a real role | Inspection drone (UAS) + aviation methods: MEL, independent inspection (EASA Part-145), black box, ATC-style dispatch | ⬜ |
| P2 | Prevention | Anomaly detection before thresholds (compressor, motor), safety cases, MEL | 🟡 |
| P3 | Detection | Zone fire model + early warning (measured lead time); drone thermal check to come | 🟡 |
| P4 | Management / intervention | Fire Pack for the Protection Civile, black box | ⬜ |
| P5 | Based on AI models | 4 models evaluated on real data, see ai/reports/evaluation.md | ✅ |
| P6 | Economically viable | Cost estimate + BMC (team deliverable) | ⬜ |

## Main goals (§01 "Buts principaux")
| # | Requirement | Where | Status |
|---|---|---|---|
| G1 | Entrepreneurial study | BMC, team report, empathy map (team) | ⬜ |
| G2 | Model of the proposed solution | Architecture + simulation + dashboard + video | ⬜ |
| G3 | Prototype of an AI model | `ai/` evaluated on held-out events; `docs/MODEL_REPORT.md` | ✅ |

## Requirements and constraints (§03)
| # | Requirement | How we meet it | Status |
|---|---|---|---|
| C1 | Realism and precision: scenarios technically consistent with aeronautical standards | MEL rules per EASA/FAA MEL concept; independent inspection per EASA Part-145; drone flights on approved routes; standards cited in docs | ⬜ |
| C2 | Interactivity: the user can act, manipulate and decide in real time | Dashboard: inject faults, sign cases, approve/refuse MEL, dispatch drone | ⬜ |
| C3 | Integration of real data | 7 real public datasets (fire experiments, SKAB, MetroPT-3, thermal images, ARIA), see docs/DATASETS.md; Protection Civile database requested | ✅ |
| C4 | Physical simulation | Energy-balance thermal model (Joule heating + Newton cooling) identified on real compressor data, `physics/thermal.py` | 🟡 |
| C5 | BMC is mandatory | Team deliverable | ⬜ |
| C6 | Safety: mainly the safety of people and the environment | Hazmat/environment in risk engine, Fire Pack, certified alarms stay independent | ⬜ |

## Mandatory deliverables (§04) — upload to Google Drive before 09:00
| # | Deliverable | Points | Owner | Status |
|---|---|---|---|---|
| D1 | BMC (Business Model Canvas) | 25 | Team | ⬜ |
| D2 | Team report: how we analyzed the problem | 15 | Team | ⬜ |
| D3 | Empathy map | 10 | Team | ⬜ |
| D4 | Realism, precision and safety of the modelled solution | 10 | Repo + docs | ⬜ |
| D5 | Explanatory video (1 min) | 20 | Team (screen recording of the demo) | ⬜ |
| D6 | AI model report: architecture, why this model, dataset description | 30 (with D7) | `docs/MODEL_REPORT.md` + `.pdf` | ✅ |
| D7 | GitHub repo link, **must be public** | (with D6) | Repo audited and ready; not yet pushed or public (needs team approval) | 🟡 |
| D8 | Presentation in PDF format | — | Team | ⬜ |
| D9 | Summary file in the Google Drive folder presenting all elements and results | — | Team | ⬜ |

## Presentation content (§05)
| # | Section | Status |
|---|---|---|
| S1 | Needs study: target, justification, strategy to reveal the need; operational problem, users (rescue teams, managers, public bodies…), limits of current practice, added value | ⬜ |
| S2 | Technical feasibility: material and human resources, steps from idea to product, estimated duration, diagrams/videos/demos | ⬜ |
| S3 | Commercial feasibility: market, global cost estimate per step, financing needed for viability | ⬜ |
| S4 | Protection Civile partnership: deployment options, needs in equipment, data, training, maintenance and support | ⬜ |

## Pitch (§04-2, §05) — only the 6 preselected teams
| # | Item | Points | Status |
|---|---|---|---|
| T1 | Final presentation of the work | 15 | ⬜ |
| T2 | Oral quality and persuasion strategy | 10 | ⬜ |
| T3 | Q&A | 10 | ⬜ |
| T4 | 5 minutes, covering all mandatory elements | — | ⬜ |
| T5 | Slides as PowerPoint/Canva, **identical to the submitted PDF** (any change = −10 pts) | — | ⬜ |

## Penalties and tie-break
- −5 if another team has the same solution idea.
- −5 if fewer than two team members attend the workshops.
- −10 if the pitch slides differ from the submitted PDF.
- **Tie-break: the solution with the lowest implementation cost wins.** → Show a clear, low cost estimate.

## Gaps not yet covered by the concept
- Cost estimate (hardware per zone, drone + docks, software, deployment) is needed for S3 and the tie-break.
- Protection Civile deployment plan (S4): equipment, data, training, maintenance.
- 1-minute video script.
