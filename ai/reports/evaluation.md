# AI evaluation report

All numbers below are **measured** on real public datasets (Industrial Hall, Indoor Laboratory, MetroPT-3, SKAB).
Nothing is synthetic. Rebuild with `.venv/Scripts/python -m ai.train`. Model version 1.0.0.

## 1. Zone model: real fire or industrial nuisance?

Gradient-boosted trees on features relative to each sensor node's recent background (CO, CO₂, H₂, VOC,
particles by size, temperature, humidity). **Leave-one-event-out**: each of the 32 recordings is judged by
a model that never saw it. Welding and abrasive cutting have a single recording each, so they are tested as
**completely unseen** sources.

Decision rule: **coincidence detection** (as in "double-knock" fire systems): the zone alarms when at least
2 sensor nodes are confident (P(fire) ≥ 0.95) for 30 s.

| Result (chosen rule) | AEROGUARD | Single particle threshold |
|---|---|---|
| Real fires detected | 17/17 | 17/17 |
| Nuisances raising a fire alarm | 4/15 | 15/15 |
| Median time from event start to alarm | 371.0 s | – |
| Background alarms in 64.2 h of continuous recording (incl. nights): quiet periods | 1 | – |
| Background alarms: within 70 min after an event (smoke lingering, unventilated hall) | 11 | – |
| Background alarms: sensor warm-up (first 30 min of the recording) | 1 | – |

The particle threshold is set to half of the smallest fire peak, so it catches every fire.

**How the rule was chosen** (criterion fixed before comparing): detect every fire; among those rules, fewest
nuisance alarms; then fewest background alarms. The rule is selected on the same out-of-fold predictions it is
reported on (two parameters only), which slightly flatters it.

**Remaining nuisance alarms**: ethanol, the two fog-machine "smoke" runs and welding. Welding is a single
recording, so here the model had **never seen welding** during training. On a real site, welding recordings
from that site and the platform's hot-work permits (declared welding zones and times) would be used.

![zone](zone_fire_vs_nuisance.png)

All rules tested (trade-off between catching fires and ignoring nuisances):

| p_fire | min_nodes | fires_detected | fire_events | nuisance_false_alarms | nuisance_events | bg_alarms_quiet | bg_alarms_post_event | bg_alarms_warmup | median_time_to_alarm_s |
|---|---|---|---|---|---|---|---|---|---|
| 0.5 | 1 | 17 | 17 | 13 | 15 | 23 | 33 | 1 | 18.0 |
| 0.7 | 1 | 17 | 17 | 12 | 15 | 12 | 33 | 1 | 37.0 |
| 0.8 | 1 | 17 | 17 | 11 | 15 | 8 | 25 | 1 | 60.0 |
| 0.9 | 1 | 17 | 17 | 10 | 15 | 8 | 22 | 1 | 81.0 |
| 0.95 | 1 | 17 | 17 | 5 | 15 | 6 | 18 | 1 | 228.0 |
| 0.5 | 2 | 17 | 17 | 11 | 15 | 7 | 31 | 1 | 23.0 |
| 0.7 | 2 | 17 | 17 | 10 | 15 | 6 | 28 | 1 | 88.0 |
| 0.8 | 2 | 17 | 17 | 8 | 15 | 6 | 22 | 1 | 108.0 |
| 0.9 | 2 | 17 | 17 | 5 | 15 | 4 | 18 | 1 | 203.0 |
| 0.95 | 2 | 17 | 17 | 4 | 15 | 1 | 11 | 1 | 371.0 |
| 0.5 | 3 | 17 | 17 | 11 | 15 | 7 | 27 | 1 | 53.0 |
| 0.7 | 3 | 17 | 17 | 7 | 15 | 5 | 21 | 1 | 111.0 |
| 0.8 | 3 | 17 | 17 | 4 | 15 | 3 | 21 | 1 | 168.0 |
| 0.9 | 3 | 17 | 17 | 4 | 15 | 2 | 14 | 1 | 413.0 |
| 0.95 | 3 | 16 | 17 | 3 | 15 | 2 | 7 | 1 | 527.5 |

Per event (chosen rule):

| event | truth | fire_alarm | time_to_alarm_s |
|---|---|---|---|
| Abrasive_Cutting#1 | nuisance | False |  |
| CO#1 | nuisance | False |  |
| CO#2 | nuisance | False |  |
| Cable#2 | fire | True | 141.0 |
| Cable#3 | fire | True | 118.0 |
| Cable#4 | fire | True | 240.0 |
| Candles#1 | fire | True | 257.0 |
| Candles#2 | fire | True | 588.0 |
| Candles#3 | fire | True | 1013.0 |
| Candles#4 | fire | True | 443.0 |
| Deodorant#1 | nuisance | False |  |
| Deodorant#2 | nuisance | False |  |
| Deodorant#3 | nuisance | False |  |
| Ethanol#1 | nuisance | True | 131.0 |
| Ethanol#2 | nuisance | False |  |
| Exhaust#1 | nuisance | False |  |
| Exhaust#2 | nuisance | False |  |
| Exhaust#3 | nuisance | False |  |
| Green_Waste#1 | nuisance | False |  |
| Lunts#1 | fire | True | 168.0 |
| Lunts#2 | fire | True | 37.0 |
| Lunts#3 | fire | True | 118.0 |
| Smoke#1 | nuisance | True | 320.0 |
| Smoke#2 | nuisance | True | 103.0 |
| Welding#1 | nuisance | True | 165.0 |
| Wood#1 | fire | True | 337.0 |
| Wood#2 | fire | True | 423.0 |
| Wood#3 | fire | True | 371.0 |
| Wood#4 | fire | True | 815.0 |
| Wood#5 | fire | True | 435.0 |
| Wood#6 | fire | True | 747.0 |
| Wood#7 | fire | True | 437.0 |

## 2. Early warning vs the conventional smoke detector

Unsupervised and **fixed before looking at results**: each recording's first 120 s define normal; a warning
is raised when ≥ 2 gas channels exceed a robust z-score of 8.0 for 10 s.

| experiment | source | detector_min | aeroguard_min | lead_min | warned_before_detector | false_warning_in_stage0 | first_channel |
|---|---|---|---|---|---|---|---|
| electrical_1 | electrical | 37.0 | 32.0 | 5.1 | True | False | tvoc_ppb |
| electrical_2 | electrical | 32.8 | 24.7 | 8.1 | True | False | tvoc_ppb |
| electrical_3 | electrical | 44.1 | 40.3 | 3.8 | True | False | tvoc_ppb |
| electrical_4 | electrical | 48.6 | 36.7 | 11.9 | True | False | tvoc_ppb |
| carton_1 | carton | 3.8 | 2.1 | 1.7 | True | False | tvoc_ppb |
| carton_2 | carton | 6.9 | 2.1 | 4.8 | True | False | mq139_raw |
| clothing_1 | clothing | 6.8 | 8.4 | -1.7 | False | False | eco2_ppm |
| clothing_2 | clothing | 0.3 | 2.6 | -2.3 | False | False | eco2_ppm |

`clothing_2` is excluded from the scores: its conventional detector switched on at 0.3 min, inside the
calibration window.

![lead time](lead_time.png)

Sensitivity to the threshold (shows the result does not depend on one lucky setting):

| z_threshold | min_channels | warned_before_detector | median_lead_time_min | electrical_median_lead_min | false_warnings_stage0 |
|---|---|---|---|---|---|
| 4 | 1 | 7/7 | 27.8 | 32.3 | 2 |
| 6 | 1 | 7/7 | 19.5 | 26.6 | 2 |
| 8 | 1 | 7/7 | 6.0 | 24.0 | 1 |
| 12 | 1 | 6/7 | 9.7 | 17.5 | 0 |
| 16 | 1 | 6/7 | 6.4 | 10.0 | 0 |
| 4 | 2 | 7/7 | 6.0 | 15.3 | 2 |
| 6 | 2 | 7/7 | 4.8 | 7.1 | 0 |
| 8 | 2 | 6/7 | 4.8 | 6.6 | 0 |
| 12 | 2 | 6/7 | 4.3 | 4.9 | 0 |
| 16 | 2 | 6/7 | 3.3 | 4.3 | 0 |

## 3. Compressor early warning on 4 real failures (MetroPT-3)

Trained only on February–March 2020 (no failure reported). 30-minute windows; features: duty cycle,
starts, longest run, oil temperature, **physics residual** (measured minus energy-balance prediction), current,
pressures. Alarm = score above the 99.5th percentile of training scores for 1 h. An alarm up to 48 h before a
reported failure counts as an early warning.

| model | failures | detected | detected_before_start | median_lead_time_h | false_alarm_episodes | normal_weeks_evaluated | false_alarms_per_week |
|---|---|---|---|---|---|---|---|
| Autoencoder | 4 | 4 | 2 | 18.0 | 15 | 15.4 | 0.97 |
| Isolation Forest | 4 | 3 | 0 | -17.5 | 3 | 15.4 | 0.19 |

| model | failure | start | detected | first_alarm | lead_time_h |
|---|---|---|---|---|---|
| Autoencoder | 1 | 2020-04-18 00:00:00 | True | 2020-04-18 00:30:00 | -0.5 |
| Autoencoder | 2 | 2020-05-29 23:30:00 | True | 2020-05-29 23:30:00 | 0.0 |
| Autoencoder | 3 | 2020-06-05 10:00:00 | True | 2020-06-03 10:30:00 | 47.5 |
| Autoencoder | 4 | 2020-07-15 14:30:00 | True | 2020-07-14 02:30:00 | 36.0 |
| Isolation Forest | 1 | 2020-04-18 00:00:00 | True | 2020-04-18 17:30:00 | -17.5 |
| Isolation Forest | 2 | 2020-05-29 23:30:00 | False | NaT |  |
| Isolation Forest | 3 | 2020-06-05 10:00:00 | True | 2020-06-06 04:00:00 | -18.0 |
| Isolation Forest | 4 | 2020-07-15 14:30:00 | True | 2020-07-15 15:00:00 | -0.5 |

Reading: the autoencoder detects all 4 failures and warns 36 h and 47.5 h ahead for two of them, at the cost of
about one false alarm per week. The 47.5 h warning is at the edge of the 48 h window and may partly be chance.
Isolation Forest raises fewer false alarms but only detects failures after they start.

## 4. Motor / pump anomalies (SKAB)

First 400 samples of each experiment = normal reference (SKAB convention). Thresholds tuned on the 16
`valve1` experiments, results on the 18 others.

| method | tuned | f1 | false_alarm_rate | missed_alarm_rate | anomalies_detected | median_detection_delay_s |
|---|---|---|---|---|---|---|
| Fixed k-sigma limits | k=2.5 | 0.772 | 0.461 | 0.122 | 17/18 | 3.0 |
| PCA residual (Q statistic) | margin=0.8 | 0.66 | 0.238 | 0.407 | 18/18 | 42.0 |
| MLP autoencoder | margin=0.8 | 0.77 | 0.39 | 0.163 | 18/18 | 7.0 |

Reading: on this bench the autoencoder matches the classic k-sigma limits on F1 while detecting every anomaly and
raising fewer false alarms. The gain is modest; it is reported as such.

## Limitations

- The fire datasets are laboratory and test-hall experiments, not a Tunisian factory. Real deployment needs a
  calibration period on site.
- Welding and abrasive cutting have one recording each; more nuisance data would make the zone model more robust.
- MetroPT-3 has only 4 reported failures: the lead times are evidence, not statistics.
- The Protection Civile incident data, once received, will be used to validate the risk engine's priorities.
