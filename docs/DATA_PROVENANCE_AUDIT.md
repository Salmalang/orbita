# Data provenance audit

Audit of every dataset used by AEROGUARD TRUST, done on the **actual records** (`scripts/audit_data.py`, raw output in [`docs/audit/data_checks.json`](audit/data_checks.json)), not only on the publishers' descriptions.

**Classes:** A = real industrial operational measurements · B = real controlled laboratory/test measurements · C = synthetic or simulated · D = unverified provenance. No dataset in the project is class C.

## Summary

| Dataset | Publisher / source | DOI | License | Class | Integrity check | Used as |
|---|---|---|---|---|---|---|
| Indoor Fire Dataset, Industrial Hall | Mendeley Data | 10.17632/yghykzm4km.1 | CC BY 4.0 | **B**: controlled fire and nuisance experiments in a real 10×22×8 m industrial hall | ✅ matches publisher SHA-256 | **Primary MVP data** |
| Indoor Laboratory Fire Dataset | Mendeley Data (Zayed University); paper in *Fire* 5(1):11, 2022 | 10.17632/f3mjnbm9b3.1 | CC BY 4.0 | **B**: laboratory fires | ✅ 8/8 files match | Secondary: lead time vs detector |
| Indoor Fire Dataset, Small-Scale Test Chamber | Mendeley Data | 10.17632/m85f9h6g9j.1 | CC BY 4.0 | **B**: test chamber | ✅ matches | Not used by a model (documented only) |
| SKAB | GitHub waico/SKAB (Skoltech) | 10.34740/KAGGLE/DSV/1693952 | GPL-3.0 | **B**: laboratory pump/motor bench | ⚠️ no publisher hash; local hash recorded only | Secondary research demo |
| MetroPT-3 | UCI ML Repository; papers Davari et al. 2021, Veloso et al. 2022 | 10.24432/C5VW3R | CC BY 4.0 | **A**: real operational data, **railway** (metro train air compressor), not a factory | ⚠️ no publisher hash; local hash recorded only | Secondary research demo |
| Thermal images of an induction motor | Mendeley Data (Babol Noshirvani Univ. of Technology) | 10.17632/m4sbt8hbvk.3 | CC BY 4.0 | **B**: laboratory images of induced faults | ✅ 3/3 files match | Illustrative reference images only |
| ARIA (BARPI) | data.gouv.fr extraction (2020-10-12) of the French ARIA database | – | Licence Ouverte 2.0 on the data.gouv.fr copy | Real **incident reports** (administrative records, not sensor data) | ⚠️ no publisher hash; third-party extraction | Context statistics only |

**What the hashes prove.** Where the publisher publishes a SHA-256 (all Mendeley files), our download is byte-identical to the published file. Where no publisher hash exists (SKAB, MetroPT-3, ARIA), the locally computed hash only records *which* file we used, so later changes can be detected. It does **not** independently prove authenticity; for those datasets authenticity rests on the publisher (UCI, the authors' GitHub, data.gouv.fr) and the associated peer-reviewed papers.

**What was not verified.** We did not contact the dataset authors. The provenance of the Industrial Hall and Test Chamber datasets rests on the Mendeley record (the API lists the contributor only by initial; we cite by DOI). ARIA's data.gouv.fr copy was published by a third-party account that has since been deleted; the original BARPI database is official but its own export is limited.

## Findings on the records

### Industrial Hall (primary)
- 248,502 rows, 9 sensor nodes, 10 s sampling on every node, 10–13 July 2023 (continuous, nights included).
- No duplicate rows, no duplicate (node, timestamp), no missing values, no negative values. Longest gap on a node: 1,000 s.
- Units: CO and CO₂ in ppm, temperature °C (20.4–35.2), humidity %. H₂ and VOC are **raw sensor values** (no unit); particles are counts by size class.
- **Label inconsistencies:** 639 rows on 13 July 12:00–12:20 (right after the abrasive-cutting run) are labelled `anomaly=1, nuisance=1` but `scenario=Background`; they look like an unnamed nuisance. One stray row is labelled `Cable`, experiment 0. Both are kept and documented; the stray row is not treated as an event.
- Fires: wood ×7, candles ×4, cable ×3, lunts ×3 = 17. Nuisances: 15 recordings, **welding and abrasive cutting only once each**.
- The hall is unventilated: smoke lingers after events, which matters for false-alarm counting.

### Indoor Laboratory
- 8 recordings, **timestamps are relative** (no calendar date). Sampling is **1 s** for six files and **2 s** for `electrical_1`/`electrical_2` (earlier docs said 2 s for all; corrected).
- Column names differ between files (`Humidity%`, `Reading ID#`, spaces); the loader harmonises them.
- `Detector` = state of a conventional smoke detector; `Status` = authors' stage label. Stage 1 starts when the heating source is switched on, stage 2 coincides with the detector in most recordings.
- `clothing_2`: the detector switches on at 0.3 min, before the authors' stage 1. It is excluded from lead-time scoring (inside our calibration window).

### Test Chamber
- Intensity labels reach **4**, although the description says "up to 6". Contains scenarios not in the description (heptane flame, polyurethane, H₂, CO, ventilation). **291 negative CO readings** (sensor offset). Not used by any model.

### SKAB
- 35 experiments at 1 s, no missing values, no duplicate timestamps. About 35 % of points are labelled anomalous.
- **`other/2` has 296 anomalous points inside its first 400 samples**, which the SKAB protocol treats as normal training data. It is now excluded from the motor evaluation.

### MetroPT-3
- 1,516,948 rows, February to 1 September 2020, monotonic timestamps, no duplicates, no missing values.
- **Sampling is about 10 s**, although the UCI page and the dataset PDF say 1 Hz. 160 gaps longer than 1 h, the longest 48 h.
- 4 failures from the operator's maintenance reports; the official table numbers two rows "#1" and lists a maintenance date (30 April) that precedes its failure (29 May). Kept exactly as published.

### Thermal images
- 369 BMP images, 320×240, 11 conditions. They are **pseudo-colour renderings without radiometric temperatures**, so no temperature can be read from them. Used only as illustrative reference images, labelled with their source.

### ARIA
- 53,958 records, 25,687 involving fire, 8,333 fires with a primary cause. Dates from **1794** to May 2020 (historical events included). One duplicated ARIA number. 88 % France. Causes are flattened category lists; statistics use the first-listed category per event.

## Audit of earlier claims (Part 2 report)

| Earlier claim | Verified? | Correction |
|---|---|---|
| 17/17 hall fires detected | Reproduced, but the decision rule (P ≥ 0.95, 2 nodes) was selected on the same held-out predictions | **Optimistic.** Nested leave-one-event-out selection gives **16/17 (95 % CI 73–99 %)**; now the headline |
| 4/15 nuisances raise a fire alarm | Reproduced; unchanged under nested selection | Reported with interval (11–52 %) |
| Background: 1 quiet, 11 post-event, 1 warm-up | Reproduced | The 70-min post-event window was defined after seeing the alarms; labelled descriptive. 6 of the 13 episodes start within 15 min after live data resumes following held values (see below) |
| "15/15 nuisances" for the particle baseline | **Bug** | The threshold was derived from a stray single-row label (peak 0). Calibrated with the same nested protocol, the particle rule gets 17/17 fires, 3/15 nuisances, 0 background alarms, i.e. **as good as or better than the AI** on those metrics; the AI alarms earlier on 14/16 fires (median 195 s). All documents corrected |
| "Case closed with 44.7 min of measured normal readings" (Cable#4) | **Invalid** | Those 44.7 min are held values (identical on all nodes and channels). Live normal run after the action: 0.5 min. The case now stays awaiting stabilization |
| Electrical fires warned 3.8–11.9 min before the detector | Reproduced | Confirmation is 5 readings = 5 s or 10 s depending on the file (earlier said 10 s) |
| 6/7 lab fires warned earlier | Reproduced | "Stage 0" check covers little time; not a false-alarm rate |
| Compressor 4/4 detected, 36 h and 47.5 h ahead, ~1 false alarm/week | Reproduced | **Exploratory**: autoencoder preferred after seeing the 4 failures; 47.5 h is at the window edge |
| Motor F1 0.77 | Reproduced 0.770; after excluding contaminated `other/2`: **0.776** (k-sigma 0.782) | Report says "matches", not "beats" |
| 30 passing tests | Reproduced | – |
| 5 commits | **Wrong** | There were 4 commits |
| "Physics model R² 0.38" | Reproduced | – |

## Held values in the Industrial Hall recording (found in the second audit)

15.5 % of rows have all 13 channels identical to the two previous readings on that node. These stretches last 20–45 minutes and start right after most experiments (17.9 % of background rows; 54 % of the green-waste recording); nights are live. Real sensors (CO₂, humidity, temperature) never stay perfectly constant, so these rows are treated as **held values, not measurements**. Consequences: (1) no live recovery data after the fires; (2) part of the background false alarms coincide with live data resuming; (3) background hours with live data: 52.8 h of 64.2 h. The models were **not** retrained to remove these rows (to avoid tuning to the results); the prototype ignores held rows at inference and in the stabilization check.

## Source verification (second audit)

All DOIs (10.17632/yghykzm4km.1, 10.17632/m85f9h6g9j.1, 10.17632/f3mjnbm9b3.1, 10.17632/m4sbt8hbvk.3, 10.24432/C5VW3R, 10.1038/s41597-022-01877-3) resolved to the stated records. The Mendeley API lists the Industrial Hall and Test Chamber datasets under **Otto von Guericke University Magdeburg** (contributor "Pascal V."), and the Indoor Laboratory dataset under **Amril Nazir, Zayed University**. The DOI 10.3390/fire5010011 resolves to MDPI, whose page refuses automated access (HTTP 403): **not fetched**. The data.gouv.fr ARIA page and the SKAB GitHub repository resolve.

## Remaining data limitations
- No dataset comes from a Tunisian factory. The Protection Civile incident data has been requested.
- Fire experiments are controlled tests; real incipient fires in production may differ.
- The nuisance set is small (15 recordings, 8 types), so nuisance-rejection rates have wide intervals.
