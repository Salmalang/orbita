# One-minute demo video script

**Message:** PREVENTIVE INSPECTION → EARLY WARNING → INVESTIGATION → CORRECTIVE ACTION → VERIFICATION → TRACEABILITY.

## Before recording (5 minutes)

1. Start the app: `.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000`, open http://localhost:8000.
2. Browser at 1440×900 or full HD, zoom 100 %. Record with Windows Game Bar (`Win + Alt + R`) or OBS.
3. Prepare the state so the minute is not spent waiting (recommended, because a full replay takes several minutes):
   - **Reset demo** (sidebar).
   - Drone Operations → start **Emergency exits check**; when the East door is inspected, **Record finding** (Obstructed emergency exit, MEDIUM). Do **not** open the case yet.
   - Live Monitoring → **Cable#4** → speed **120×** → Start. Wait until it pauses on CRITICAL (Safety Case opened). Stop here.
4. Have the Overview open when recording starts.

## Timeline (60 s)

| Time | Screen | Action | Narration | On-screen caption |
|---|---|---|---|---|
| 0–6 s | Overview | Hover the hero banner and "What should I do next?" | "AEROGUARD TRUST answers three questions for a factory safety manager: is my facility safe, what needs attention, what should I do next." | Metal-working production hall · prototype |
| 6–15 s | Drone Operations | Show the route on the schematic and the patrol schedule; point at the recorded finding; click **Open Safety Case** | "The drone patrols before any alarm. Here a patrol flagged a blocked emergency exit, and it becomes a Safety Case." | SIMULATED drone · illustrative finding |
| 15–30 s | Live Monitoring | Show the CRITICAL banner, the fire-likelihood chart and the red nodes on the map | "This is a real cable fire recorded in an industrial hall. The AI, tested on events it never saw, raised the alarm earlier than a calibrated smoke-type rule on 14 of 16 fires, by about three minutes." | Real recorded data · held-out model · 14/16 fires earlier, median 195 s |
| 30–42 s | Safety Case (sensor) | Approve the targeted drone flight; switch role to Technician, record action; switch to Verifier, approve | "A case opens automatically, a targeted drone inspection waits for approval, the technician records the fix and a different person verifies it." | Independent verification enforced |
| 42–52 s | Same case | Click **Run closure check** (after resuming the replay off-camera, or show the earlier result) | "AEROGUARD only closes a case on trustworthy live readings. Here the recording repeats old values, so it refuses to close — and says why." | Refuses closure on held data |
| 52–60 s | Black Box, then Passport | Scroll the timeline; show the inspection history | "Every reading, decision and action is recorded in a tamper-evident log. Earlier warning, verified response, full traceability." | AEROGUARD TRUST · ORBITA · INSAT |

If 60 s is too tight, drop the 42–52 s segment and keep the earlier-warning claim and the Black Box.

## Recommended replay speed
120× while preparing; 60× if the fire must appear live on camera. In the Cable#4 window the first abnormal signal appears about 17 minutes into the recording (about 17 s at 60×) and the Safety Case opens about 25 minutes in (about 25 s at 60×).

## What the video may claim (supported by the evidence)

- Detection on real recordings of **staged** fires in an industrial hall: AI 16/17 fires, calibrated particle threshold 17/17.
- Nuisance alarms: AI 4/15, calibrated particle threshold 3/15. **Do not say the AI has fewer false alarms.**
- The AI alarms earlier on **14 of 16** fires detected by both methods, median **195 s**.
- Laboratory electrical fires: warned **3.8–11.9 minutes** before the conventional detector in four experiments.
- The workflow refuses to close a case without trustworthy live measurements.

## What must be presented as simulated or illustrative

- The drone, its movement, schedules, missions and findings (no physical drone, no imagery, no validated vision/thermal model).
- Facility layout, sensor positions, checkpoints, exits and contacts.
- Human roles (demo roles, no real authentication).
- Hedera anchoring is **pending**, not implemented.
- Never claim proven fire prevention or validation in an operating factory.
