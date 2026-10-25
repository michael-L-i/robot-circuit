---
name: so101-demo
description: Run the full SO101 circuit repair demo with Gemma commentary. The arm probes the circuit (resistor missing, about 0 V), places the resistor in the copper gap (LED lights), then probes again (over 3 V). Gemma on the Jetson commentates each step in the dashboard and on the Mac speaker. Use when the user says run the demo, go, full pipeline, or /so101-demo.
---

# SO101 full demo

Run from the repo root. Keep replies to the user short.

**Before you run, check all of these:**
- The arm is at rest.
- The resistor block is on the tape strip left of the board.
- The red probe lies on the tape strip above the board, needle pointing left.
- The copper gap is empty.
- The phone is streaming. Check that `curl -s http://127.0.0.1:8000/api/live/state` shows `received_at` within the last few seconds.
- The DM40C meter is on and the phone app is disconnected from it.
- The dashboard is http://127.0.0.1:8000 and should be open on the Mac.

**Run:** `.venv-robot/bin/python scripts/so101_pick/demo.py`. It takes about 3–4 minutes.
1. **Probe:** `probe_touch.py --measure` presses once and reports the meter value, about 0 V with no resistor. Gemma comments.
2. **Resistor:** `pickplace.py --verify` places the block, then the camera checks the LED. Gemma comments.
3. **Verify:** `probe_touch.py` presses until the meter reads over 3 V. Gemma confirms the repair.

The skills run unchanged as subprocesses.

**Commentary:** `/api/demo/narrate` in `circuit_lab/live.py`. Gemma streams its text into the dashboard conversation as "Gemma · step" bubbles, then the Mac speaks it. Live frame inspection keeps running but stays silent while `demo` is on.

**Dashboard server:** it must run with live inspection on Gemma on the Jetson:

`CIRCUIT_AUTO_INSPECT=1 CIRCUIT_INFERENCE=ollama CIRCUIT_OLLAMA_URL=http://127.0.0.1:11435 CIRCUIT_OLLAMA_MODEL=gemma4:31b uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_mac.py --port 8000 --https-phone`

This needs the SSH tunnel to the Jetson on 11435. Each restart gives a new phone link from `/api/phone/info`.
