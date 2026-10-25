# Jetson circuit workbench

## Start and use

From the repository on your Mac:

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_workbench.py
```

Enter the Jetson SSH password if asked. Open http://127.0.0.1:8000. Keep the launcher running; Ctrl-C stops its dashboard and tunnels. Run only one server on port 8000. Settings are in `config/workbench.toml`; no password is stored there. Ollama and gemma4:31b are already installed on Jetson.

Scan the dashboard QR using your phone, open Safari, and tap Start camera. Keep Safari visible and the phone unlocked. Re-scan after each restart. The phone sends a resized image approximately every ten seconds. Gemma inspects the latest image and the Mac speaks the finding. This is periodic image analysis, not continuous video inference.

Type a question to stream Gemma's reply and hear it through the Mac. Enable Include the latest camera image to ask about the board; a fresh frame is required. Chat pauses inspection; use Resume inspection afterward. Mute voice stops playback. Voice uses local Kokoro with macOS speech fallback. Voice input is not implemented.

## Component connections

| Component | Connection | Role |
| --- | --- | --- |
| Jetson | Wall power supply; network reachable from Mac | Runs Ollama and Gemma 4 31B |
| Mac | Network route to Jetson 192.168.0.169 | Dashboard, camera receiver, speech and speaker |
| Phone camera | Dashboard HTTPS QR link | Images to Mac, forwarded to Jetson |
| SO101 | Intended: controller USB data to Jetson, separate appropriate arm power supply | Driver integration and calibration pending |
| Bluetooth instrument | Intended: Bluetooth to Jetson | Measurement adapter pending model/protocol |
| Circuit/probe | Copper-mesh test net plus defined reference connection | Before/after electrical evidence |

Mac-to-Jetson USB-C is optional for this network setup. It is not the arm's motor power supply. SSH carries model traffic; Ollama remains on Jetson localhost. The phone HTTPS link uses Cloudflare and needs internet; images pass through that relay. Inference and speech synthesis run on your devices. Trusted local HTTPS can replace the relay using run_mac.py certificate options.

## Hardware work still required

This is an inspection and conversation system; it does not execute physical swaps yet. Existing /sim/ and /resistor/ simulations use other robot models and are not SO101 hardware drivers.

1. Connect SO101 controller USB, verify the exact controller and correct power supply, and record its stable serial path. Install a compatible driver, calibrate joints, establish workspace limits and test low-speed motion and stopping before autonomous actions.
2. Identify the Bluetooth instrument brand/model and BLE or classic Bluetooth protocol. Pair it, implement its reading adapter, and compare readings with its own display. Pairing alone does not provide measurements.
3. Define the voltage reference, supply, healthy voltage and tolerance. Establish valid probe contact. An unverified zero is not reliable failure evidence.
4. Calibrate camera-to-arm geometry and record the mesh target, probe dock, resistor socket, spare and reject locations. Enlarged grips do not establish coordinates.
5. Implement feedback-controlled sequence: baseline reading → dock probe → remove circuit power → replace module → restore power → re-probe → verify voltage and LED. Stop on uncertain contact, grasp or unexpected readings.

Robot and measurement config sections are commissioning placeholders, not active drivers. No live measurements are invented.

## Diagnostics

With the workbench stopped, check the model and enumerate Jetson devices without moving motors:

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_workbench.py --check
```

While running, /api/system reports model and hardware readiness. If SSH drops, restore connectivity and restart. If port 8000 is occupied, use the existing dashboard or stop its launcher first. For stale frames, reopen the current QR link and keep Safari visible. For silent replies, check dashboard mute, Mac volume and audio output.

```sh
uv run pytest -q
uv run --project projects/arm-sim --with qrcode==8.2 pytest projects/arm-sim/tests -q
node --test tests/live-loop.test.mjs tests/ndjson.test.mjs
```


## Current arm connection and commissioning

The arm is now connected to the **Mac**, not the Jetson. All six STS3215 motors responded without reported errors. Use the isolated hardware environment:

```sh
uv venv .venv-robot --python 3.12
uv pip install --python .venv-robot/bin/python -r config/robot-requirements.txt
.venv-robot/bin/python scripts/so101_commission.py status
```

For attended calibration only, with the arm supported and workspace cleared:

```sh
.venv-robot/bin/python scripts/so101_commission.py calibrate
```

The calibration command checks the motors, waits for SUPPORTED, then releases torque and guides manual joint calibration. Do not run it unattended or force joints while torque is enabled. Calibration is saved under .cache/so101-calibration. Calibration alone does not create a pick trajectory: the approach, grasp and lift still need commissioning. No physical pick has been executed.
