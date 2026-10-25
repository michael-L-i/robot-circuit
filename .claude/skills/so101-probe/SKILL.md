---
name: so101-probe
description: Run the SO101 arm probe routine. It picks the red multimeter probe off the tape strip above the board, softly touches its tip to the middle copper group, holds it there for a reading, then puts the probe back. Use when the user says probe the board, take a reading, touch the copper, or /so101-probe.
---

# SO101 probe touch

Run from the repo root. The arm must start at rest, with the probe lying on the tape strip above the board, needle pointing left in the camera image. Keep replies to the user short.

1. **Camera:** check it the same way as the so101-pick-place skill (`curl -s http://127.0.0.1:8000/api/phone/info`, and restart the server if needed).
2. **Run:** `.venv-robot/bin/python scripts/so101_pick/probe_touch.py --announce`. It takes about 40 s.
   - It picks the probe up using the shared pickup in `probe.py`: wrist roll 1192, the preferred jaw side from `probe.json` (falling back to the other side if the grip is empty), and a fixed grip height `FLOOR_Z` + 3 mm.
   - It uses the calibrated wrist roll as is. Re-aiming the roll changed where the jaws held the probe and caused misses.
   - After pickup it turns the probe round (wrist roll +180°, `FLIP`), so the needle points toward the arm. It then tilts the gripper forward (`TILT` 0.6), which angles the needle about 30° down.
   - It lowers the needle onto the middle copper group, 2 cm further out than the target pixel (`REACH_OUT`), 1 mm at a time from `BOARD_Z` + 12 mm.
   - It reads the DM40C meter over BLE after every step (`meter.py` with the vendored `dm40ble.py`) and stops as soon as the meter reads over 3 V (`VOLT_OK`), or at `BOARD_Z - DEPTH`.
   - If a press gets no voltage, it lifts, shifts 5 mm and then 10 mm (`SEARCH`), and presses again. Each press goes at most `DEPTH` = 8 mm past the board estimate.
   - Every touch pose is planned and checked before the probe is picked up.
   - `--announce`: after parking, Gemma (through the dashboard's `/api/assistant/chat`) phrases the reading and the Mac speaks it (`/api/speaker/play`). This is in `announce.py`, and needs the dashboard running with Gemma reachable.
   - The first good run read 4.99 V at z = 0.0195.
   - `BOARD_Z` is 0.0205 and `DEPTH` is 0.011 (8 mm barely registered a voltage). Before moving, it checks the deepest point is reachable. Each step is logged to `probe_touch_log.json`.
   - It holds for `--hold` seconds (default 3), then lifts, puts the probe back and parks.
   - `--dry-run` plans without moving. `--target U V` sets the touch point as a reference-view pixel; the default `345 470` is the middle copper group, which the user prefers. The narrow right strip is easy to miss.
3. **Report:** tell the user in one line. `scripts/so101_pick/probe_touch_bottom.jpg` is the frame at the lowest point, but the arm usually hides the tip.

## Notes
- The probe pivots in the jaws, so the contact signal is weak. If the user says it presses too hard, or doesn't reach, look at the log and change `DEPTH` or the thresholds a little.
- If the grip misses (for example the probe was put back somewhere else, or the floor height changed), rerun `probe.py` to recalibrate.
- The probe is found by colour, only inside the tape-strip area of the reference view (`find_probe` in `probe.py`). It uses the needle-side red part of the handle, which must be at least 15 px thick, so the red cable (~11 px) is never mistaken for it.
- To recalibrate the grip after a big change: `.venv-robot/bin/python scripts/so101_pick/probe.py` picks the probe, lifts it, puts it back and rewrites `probe.json`.
- **Meter:** AlienTek DM40C over BLE, name `DM40C`. Write `af 05 03 09 00 40` to fff1, and the measurement frame (header `df 05 03 09`) comes back on fff2. The meter only accepts one connection, so the phone app must be disconnected first.
- **Circuit state from camera:** the LED at reference-view (360–400, 440–480) has more than 50 bright-green pixels (hue 25–45, V > 200) when the circuit is closed, and 0 when it is open.
