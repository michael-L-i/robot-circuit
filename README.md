# Circuit workbench: Jetson + Mac

The current setup uses **Gemma 4 31B on the Jetson**, a phone camera, and the Mac for the dashboard and spoken replies. The task is **probe → replace the faulty resistor module → probe again and verify the LED**. Bluetooth measurement and physical SO101 motion still require hardware commissioning.

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_workbench.py
```

Open http://127.0.0.1:8000. Scan the current QR to pair the phone, or type a question to hear Gemma through the Mac. See [SETUP.md](SETUP.md). This launcher supersedes the older commands below for the Jetson setup. Existing simulators retain their original local model.

---

## Earlier Mac-only prototype

A phone-camera breadboard inspection prototype for the AGI House Gemma hardware hackathon. Gemma 4 E4B repeatedly inspects the latest webcam frame locally through LiteRT-LM. Observations and tentative connection repairs update automatically while the video stays live. Pause analysis when you want to verify or edit lead positions.

## Legacy Mac-only camera mode

```sh
uv sync
brew install cloudflared  # one-time HTTPS helper for Safari camera access
uv run python scripts/run_mac.py --https-phone
```

Open **http://127.0.0.1:8000** on the Mac. Scan its QR using your iPhone/iPad Camera, open the **HTTPS** link in Safari, and tap **Start camera**. Allow camera access. Leave the device pointed at the circuit, Safari open and the device unlocked. A screen wake lock is requested when available.

The rear camera remains live. The phone sends one resized JPEG (longest edge 1280 px) approximately every **10 seconds**; network time is added to that interval. Only the most recent frame is retained. A Mac background worker checks at most once per 10 seconds, reuses local Gemma 4 E4B, prints the finding to the terminal, and speaks it through the Mac speakers with local Kokoro. The dashboard can be closed after pairing: it is only status, pause, mute and the latest finding. The older pin editor is available at `/review`.

Gemma reports LED appearance (`lit`, `unlit`, `uncertain`, `not_visible`), visible wiring issues, uncertainties and a practical next check. A colored LED body alone is not light emission. The checker does not measure voltage or electrical contact. Near-uniform/covered-lens frames are rejected before inference rather than inviting a circuit hallucination. A real board still needs user validation; visual fault hypotheses can be wrong.

**Connection:** `--https-phone` starts a temporary Cloudflare Quick Tunnel, without an account, domain or certificate installation. Frames pass through Cloudflare's HTTPS relay; **Gemma and voice synthesis stay on the Mac**. Only the camera page, its static assets and token-authenticated frame upload route are exposed through the tunnel. The dashboard, pairing secret, model/speech APIs and simulator are blocked. The random pairing token is in the QR fragment and stored for that phone tab. Restarting the server requires rescanning. Stopping the launcher stops the tunnel. This path needs internet access; the phone can use any network that can reach the HTTPS link.

**Strictly local alternative:** omit `--https-phone` and provide `--ssl-certfile PATH --ssl-keyfile PATH` with a certificate trusted by the iPhone. An untrusted certificate warning alone does not establish camera access. Ordinary HTTP LAN links cannot use Safari's live-camera API. Set `CIRCUIT_LAN_IP` if a VPN selects the wrong local interface.

**Voice:** uses the existing local Kokoro service at `http://127.0.0.1:8880/v1/audio/speech`, voice `af_heart`. Override `CIRCUIT_TTS_URL` for another compatible local endpoint. macOS `say` is the fallback, and `afplay` outputs the generated WAV. No microphone access is needed. Identical consecutive spoken findings are not repeated. The live inspector starts automatically through `scripts/run_mac.py`; importing the API directly requires `CIRCUIT_AUTO_INSPECT=1` to enable the worker.

**Preserve the simulator:** use this launcher instead (one process, one shared model):

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_mac.py --with-simulator --https-phone
```

The simulator remains at `/sim/`. Do not launch a second model process on another port. Pause live inspection before using the legacy camera editor to avoid competing for inference. Phone frames stay in memory; the existing model API temporarily writes a JPEG then deletes it. No recording is saved.

## Run on an Apple Silicon Mac

```sh
uv sync
uv run python scripts/download_model.py  # one-time ~3.7 GB download
uv run uvicorn circuit_lab.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in Chrome or Safari. Allow camera access when prompted. If blocked, enable the browser under macOS System Settings → Privacy & Security → Camera. Uploading a photo works without camera access. Dependencies and the model have already been installed on the development Mac.

After setup, the app serves all assets locally and performs inference on the Mac. No API key, cloud inference, CDN, telemetry integration, or remote camera upload is used. With the loopback launch below, capture images are sent only to the loopback server, temporarily written for inference, then deleted. The phone launcher above additionally accepts paired camera uploads over the LAN or an explicit HTTPS relay. Browser frames remain in memory until replaced or the tab closes. Model compilation caches remain in `.cache/`. Run with Wi-Fi off after installation to demonstrate offline operation.

## First experiment

Use a standard breadboard with columns A–J, numbered rows 1–63, one resistor, one LED, and two supply jumpers. This version supports the central terminal strips only, not the long power rails. Set up and move parts with power disconnected.

1. Put the positive supply jumper in E5 and ground jumper in E11.
2. Put the LED anode in C10 and cathode in C11; confirm polarity from your actual component.
3. Put the resistor between A5 and A10, then put the positive jumper in E6 instead of E5 (a simulated misplaced jumper).
4. Click **Start live inspection** once and hold the board close enough to read its labels. Video stays live; Gemma analyzes automatically.
5. Watch the explanation, proposed holes, and unverified correction update after each inference. For these sample pins, the shortest preferred repair is positive jumper **E6 → E5**. These example coordinates are not supplied to the model or encoded as a diagnosis.
6. Use **Pause analysis to review** to edit unknown holes and confirm polarity. You can then click **Find the correction** using your reviewed inputs.
7. Move the lead with power off and resume live analysis. New observations automatically update the diagnosis. No repeated capture clicks are needed.

Choose a supply and resistor appropriate for your LED before powering the circuit. The app does not measure or validate these. The simulated example button loads a separate misplaced-resistor example using labeled sample data; it does not run Gemma or claim to observe a physical board.

## What is implemented

- Continuous browser webcam preview and automatic latest-frame analysis; pause/resume, stop camera, and optional JPEG/PNG upload.
- One request in flight, no frame backlog. Pause/stop invalidates late results; analysis continues when switching tabs (the browser may throttle background timers).
- Automatic unverified topology suggestions and a visible source-frame age; manual review remains available.
- Persistent local Gemma engine, fresh conversation for each image, one inference at a time.
- Gemma 4 E4B on the GPU with concise output and optional bounded reasoning, a detailed image-inspection prompt, visual findings, per-endpoint evidence, uncertainties and a targeted next-view suggestion. One formatting retry if JSON cannot be parsed.
- Partial observations survive a malformed endpoint; unsupported coordinates remain unknown. A model-reported absent circuit cannot produce a move plan.
- Human review of exact holes and polarity, plus manual entry when the camera cannot resolve them.
- Breadboard topology: A–E share a row; F–J share a separate row. The checker considers equivalent holes and either orientation of a nonpolar resistor.
- Minimum-move topology search across jumpers, resistor leads and LED leads, allowing the resistor on either side of the LED. Equally short options favor flexible jumpers, then resistor leads, then LED leads. This is a repair preference, not proof of the original mistake.
- Partial connectivity findings remain visible when exact move planning needs more observations. Duplicate-hole checks prevent contradictory observations from producing a repair.
- Local API at `/api/analyze`, `/api/check`, `/api/health`; interactive docs at `/api/docs`.

## Limits

This is a perception and repair-planning prototype, not robot control. There is no arm integration, image-to-robot calibration, or actuation. It handles one resistor and one LED in a series path between positive and ground, with the resistor on either side of the LED. It assumes no extra components, wires, hidden bridges, unusual breadboard internals, or occupied holes beyond the six entered leads. Suggested target holes must be visually checked for availability and physical reach.

A laptop webcam may not resolve breadboard labels or insertion points. A close, well-lit, top-down image is needed; the app deliberately allows unknowns rather than pretending to see exact pins. A macro-capable camera and board calibration are likely next steps for reliable automation. Model confidence is not a measurement. Visual observations do not establish electrical contact, component values, voltage, LED polarity, or whether the LED works.

## Detailed pin review

Select **Detailed pin review** before starting the camera or inspecting an uploaded
photo to allow a bounded 512-token thinking pass on each image. It is slower than
the default fast mode. Both modes ask for lead insertion points grounded in the
printed row labels, grid counting, board orientation and perspective. The model
must describe ambiguities instead of selecting an unsupported neighboring hole.
For a useful comparison, upload the same sharp photo used with another model.
Keep the center gap, row labels and every relevant insertion hole in view.

## Configuration

- `MODEL_PATH`: local vision-capable Gemma `.litertlm` file; defaults to `models/gemma-4-E4B-it.litertlm`.
- `LITERT_BACKEND=gpu` (default): language inference uses the Mac GPU through Metal. The vision encoder also uses GPU by default. Override it with `LITERT_VISION_BACKEND=cpu` for comparison. Set `LITERT_BACKEND=cpu` explicitly for CPU-only inference. No silent fallback.
- Context is bounded to 8192 tokens. Thinking is off by default, with a 1500-token output cap. Set `LITERT_THINKING=1` to restore the 1024-token reasoning budget and 3000-token total output cap. Only one model request runs at a time. The E4B model file is checksum-verified by the downloader; the earlier E2B and 12B files can remain on disk as an optional `MODEL_PATH` override.
- Python 3.12 recommended. Dependencies are pinned in `pyproject.toml` and `uv.lock`.
- First inference includes model initialization; subsequent requests reuse the engine. The live loop samples a fresh frame 750 ms after the previous request finishes. Camera frame rate and model inference rate are independent; expect seconds per reasoning update, not video-rate reasoning. Analysis continues when switching tabs; use Pause or Stop to end it. Pausing does not cancel native inference already in progress; its result is discarded and resume waits for it to finish.

## Checks

```sh
uv run pytest -q
node --test tests/live-loop.test.mjs
# With the server running and the model downloaded:
uv run python scripts/smoke_test.py
```

The smoke test sends a blank image to the real Gemma/LiteRT runtime and checks for structured unknowns. It validates runtime integration, not breadboard recognition accuracy. Automated tests cover connectivity, valid moves, invalid inputs, malformed model results, and image API plumbing with a mocked engine. A real breadboard still needs to be tested on camera.

## Verified on this Mac

GPU vision and faster defaults were then enabled for E4B. With an identical
short image-description prompt and thinking disabled, warm CPU-vision and
GPU-vision runs took 1.40 and 0.94 seconds respectively. Both used GPU language
inference. The full application with GPU vision, thinking disabled and concise
output took 4.71 seconds cold and 3.81 seconds warm on the same synthetic shapes
image (previous E4B configuration: 13.48 / 10.55 seconds). Output identified the
shapes without inventing circuit pins. Actual breadboard latency and accuracy
still require a real-board comparison; these numbers are not a real-time guarantee.


The default was subsequently switched to Gemma 4 E4B on the same Metal GPU.
Its pinned model checksum was verified. With the same prompt and reasoning
settings, the red-rectangle/blue-circle image took 13.48 seconds on first load
and 10.55 seconds with the model loaded (12B previously took 39.24 seconds).
Both E4B requests identified the shapes and returned no invented circuit pins.
This comparison uses a synthetic image, not a real breadboard accuracy test.


On 2026-10-23, Gemma 4 12B was loaded on the Apple M5 Pro GPU through Metal
using LiteRT-LM 0.18.1. The model SHA-256 matched the pinned download checksum.
A blank-image API check returned no circuit and no pins (but incorrectly called
the white image black). A second image correctly identified a red rectangle,
blue circle and white background, with no invented circuit. Requests took
36.67 and 39.24 seconds respectively; these are integration checks, not a
breadboard accuracy benchmark. No actual user breadboard image was available
for this validation.

33 Python tests and two live-loop JavaScript tests pass (including phone pairing, latest-frame uploads, LED output validation, blank-frame rejection, local speech and HTTPS gateway restrictions). Browser verification
with explicitly simulated pin data derived a positive-jumper E6 → E5 repair;
location-varied tests cover both supply jumpers and both board halves.

## Layout

- `circuit_lab/app.py`: loopback web server, image validation, inference serialization.
- `circuit_lab/inference.py`: LiteRT-LM engine and visual observation prompt/parser.
- `circuit_lab/circuit.py`: deterministic series-circuit checker and minimum-move lead planner.
- `circuit_lab/static/`: self-contained browser UI.
- `scripts/`: model download and real-runtime smoke check.
- `tests/`: unit and API checks.

## Runtime references

- [Google LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM)
- [Official CLI image input and desktop guidance](https://developers.google.com/edge/litert-lm/cli/usage)
- [Gemma 4 E4B LiteRT model files and model card](https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm)

This uses the installed LiteRT-LM 0.18.1 Python API. Event eligibility and hardware-track judging remain the organizer's decision; this repository is the webcam milestone toward the proposed physical robot.
