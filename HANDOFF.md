## First physical movement completed

After user confirmed clear workspace and explicitly requested movement, sent a bounded motor-5 wrist-roll test using Feetech SDK: position mode, torque already enabled, stationary start 207 ticks, goal 218 (+11 ticks, ~1 degree), velocity limit 20 ticks/s. Feedback 208 → 213 → 215, then Moving=0. Measured displacement 8 ticks (~0.7 degree), within 4-tick target tolerance. Other motors were not commanded. Motor 5 Goal_Velocity remains 20 (previously 100); goal remains 218. No torque writes, EEPROM changes, calibration, extension or grasp performed. Evidence .cache/so101-first-motion.json. Do not repeat or enlarge motion without commissioning. Earlier claims below that no physical movement has occurred are superseded by this entry.

## SO101 commissioning update

The arm now connects to the Mac at /dev/cu.usbmodem5AE60583621. Read-only servo queries confirmed IDs 1–6, model 777 (STS3215), no reported errors, about 12.5 V; torque was already enabled. No position or torque-write commands have been sent. User confirms black rectangular pieces are enlarged removable resistor modules, intended to bridge the copper meshes. Immediate goal: pick one up.

Installed isolated .venv-robot with config/robot-requirements.txt. scripts/so101_commission.py status only pings/reads; calibrate requires a physically supported arm and interactive SUPPORTED gate, then uses LeRobot calibration. It releases torque and writes calibration registers. No calibration exists yet and no grasp path is implemented. Never infer target joint positions from the current uncalibrated camera view. Camera uploads resumed; automatic analysis and speech are paused/muted at the user's request. The Mac-to-arm USB data cable works; Jetson USB-C did not enumerate it even after changing usb_role to host and stopping nv-l4t-usb-device-mode.service. Do not move the cable back without reason.

# Current Jetson workbench — 2026-10-24

Use scripts/run_workbench.py with config/workbench.toml; see [SETUP.md](SETUP.md). This supersedes older launch commands below. The Jetson at 192.168.0.169 has Ollama gemma4:31b installed. The Mac launcher owns an SSH tunnel on localhost:11435 and the combined dashboard on port 8000. Do not start duplicate servers.

Task: wiring is intended to be correct. Enlarged rectangular resistor modules support grasping. Probe copper mesh, dock probe, remove circuit power, swap module, restore power, re-probe and verify LED. Bluetooth instrument model/protocol, electrical reference and healthy voltage remain unknown. Physical SO101 motion is disabled; no measurement driver exists yet. Never fabricate readings.

Camera inference uses Ollama; simulator retains local E4B. Chat and image inference share the app lock. Shared Mac playback supports mute and stop. Chat pauses inspection until resumed; camera chat requires a frame under 30 seconds old. HTTPS relay exposes only camera assets and authenticated uploads.

Tests: root Python 40 passed, simulator 60 passed, JavaScript 4 passed. Pre-restart state and trace saved in .cache/sim-before-jetson-workbench.json and .cache/trace-before-jetson-workbench.json. Existing dirty simulator files preserved.

---

# Robot circuit simulation handoff

The current simulation work and Claude Code continuation context are in:
**[projects/arm-sim/HANDOFF.md](projects/arm-sim/HANDOFF.md)**.

Demo: http://127.0.0.1:8000/sim/

Start the combined webcam + simulator server from this directory:

```sh
uv run --project projects/arm-sim python projects/arm-sim/run.py
```

Use one server process only. It shares one local Gemma E4B engine across both apps. The simulation has its own environment and lockfile, and does not issue hardware commands. Read the full handoff before continuing or starting another model process.


## Live iPhone/iPad camera demo — 2026-10-24

The user wants sparse live frames and spoken findings, with minimal UI. The Mac is now running the single combined server through:

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_mac.py --with-simulator --https-phone
```

Mac status / pairing QR: http://127.0.0.1:8000. Scan its current HTTPS URL on the phone and tap Start camera in Safari. Leave the camera page visible and device unlocked. Frames arrive approximately every 10 seconds; a background thread inspects only the latest frame, sharing the E4B engine/lock with the simulator. Kokoro at localhost:8880 generates WAV audio; afplay plays it on this Mac, with macOS say as a synthesis fallback. Closing the dashboard does not stop processing. Root UI is minimal; legacy pin editor is at /review.

Cloudflared provides a temporary public HTTPS camera receiver (frames pass through Cloudflare, inference stays local). Its forced Host header is restricted to camera assets and token-authenticated uploads. Pairing, model/speech APIs and simulators are not exposed via the tunnel. The URL and pairing token change after restart; use the current QR. Stop the launcher to stop the tunnel. Existing simulator files/changes were left as found; its prior trace was saved to .cache/sim-before-phone.json before the server restart.

New code: circuit_lab/phone.py, live.py, speech.py, static/live.html, static/phone.html and phone.js, scripts/run_mac.py. App lifecycle starts the worker only when CIRCUIT_AUTO_INSPECT=1 (the launcher sets it). Live inspection uses a short general visual prompt, avoiding the detailed coordinate prompt's bias toward invented circuits. A near-uniform frame is rejected before inference; malformed model output becomes uncertain rather than a repair.

Verification: 33 parent Python tests and 2 JS loop tests passed; the temporary HTTPS receiver and public-path restrictions were exercised. Real Gemma's short live prompt correctly described a red square and blue circle with no circuit/pins in 3.36 seconds. Kokoro returned playable WAV audio, verified in Chrome. Final HTTPS-upload → background Gemma → Mac speaker integration was exercised with a synthetic frame. No actual phone/physical circuit has been validated until the user starts their camera. Do not describe synthetic checks as real-board accuracy.

## DM40C Bluetooth connection (Codex, 2026-10-24)
User identified Alientek DM40C and enabled Bluetooth. Mac BLE discovery found `DM40C` at CoreBluetooth UUID `FC8016EC-5C57-A4EF-F46C-AE5511E2ED26`, service FFF0. Connected successfully and received checksum-valid 17-byte measurement responses via FFF2 to read-only FFF1 request `af0503090040`. No mode changes or robot actions. Config measurement section now identifies instrument/host/protocol, display_verified=false. Existing live dashboard was not restarted or modified.

Reusable bounded reader: `uv run --with bleak python scripts/instruments/read_dm40.py --seconds 30`. Discovery: `uv run --with bleak python scripts/instruments/scan_dm40.py`. Only observed DCV AUTO+ mode 0x30 decoded; other modes and overload return null volts. Raw packets retained in output, units/sign need comparison with meter screen before task verification. BLE connection alone does not prove probe contact. Reader disconnects at end; no background job left. It can run on the Mac alongside Jetson Gemma. Integrating live readings into Gemma/dashboard still requires a measurement-state adapter; current /api/system remains the old placeholder. Protocol reference: https://github.com/mriscoc/DM40Visor .

## Live voice orb — recorded demo replaced (Codex)
User explicitly requested removing canned narration and adding a one-shot board-analysis button. Current `ui/` in the main workspace replaces PR #1 preview; the temporary `.cache/voice-ui-preview` worktree and its mock trace were removed. Port8100 now runs `uv run python ui/serve.py` (exec session77867). Port8000/Claude camera server was not restarted.

`Analyze board` freezes the latest phone upload (<=30s old), passes exactly that image to the existing Jetson Ollama gemma4:31b through localhost11435, and returns actual model text plus frame/image provenance. No simulator events or canned task lines, no autoplay/mock mode. Local `/api/speak` generates Kokoro audio (existing macOS fallback), the browser plays it on the Mac, and actual audio playing/pause/ended events drive the orb. Stop voice cancels playback; Play voice replays audio without another analysis. One in-flight analysis guarded in UI and server; stale frames/errors show honest messages. No files/images stored by the app and no autonomous loop/motor commands.

Verified browser run: real frame1533, Gemma response displayed, 25.75s audio observed actively playing, body class `speaking`; screenshot `.cache/live-board-voice.png`. Three focused frame-selection/staleness tests pass (`tests/test_voice_ui.py`), JS/Python syntax checks pass, `/mock/trace.json` returns404. This UI currently receives camera images only, not live DM40C readings. The phone upload is periodic, so the click selects latest upload rather than triggering a phone shutter. Run command and prerequisites in `ui/README.md`.
