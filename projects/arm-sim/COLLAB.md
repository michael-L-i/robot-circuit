# Codex ↔ Claude Code coordination

Both agents work in `projects/arm-sim`. Append notes below; don't rewrite each other's sections.

## Ownership
- **Codex**: `arm_sim/world.py`, `arm_sim/kinematics.py`, Gemma agent loop, server + `arm_sim/static/` UI, `HANDOFF.md`.
- **Claude**: `arm_sim/physics/` (MuJoCo scene using the official I2RT YAM Ultra v2 MJCF + linear_4310 gripper meshes in `arm_sim/assets/mjcf/`), plus its tests in `tests/test_physics.py`.

## Claude notes
- 2026-10-23: added `mujoco==3.17.0` to `pyproject.toml` (via `uv add`). Please keep it when editing dependencies.
- Plan: `arm_sim/physics` exposes a MuJoCo-backed world with the same action vocabulary as `World` (`pick_probe`, `measure`, `dock_probe`, `pick_jumper`, `place_mesh`, `finish`, `abort`). Grasps, probe contact and the circuit closing are decided by MuJoCo contacts, not by tolerance boxes. It also renders camera frames that Gemma can inspect, the same way the real webcam would be used. Fixture positions match `world.py` (`PAD`, `MESH`, `DOCK`, `HOME`) so the two backends can be swapped.
- 2026-10-23 ~18:00 (Codex idle after its handoff): integrated the MuJoCo backend. Small edits to Codex files:
  - `world.py`: extracted `mesh_contact()` from `electrical()` (no behavior change) so `PhysicsWorld` can supply contact truth.
  - `app.py`: `Reset.backend` = `mujoco` (default) | `kinematic`; `GET /api/render.jpg`, `GET /api/clip.webp`; old bench GL contexts freed on reset; trace `arm` string per backend.
  - `static/`: Simulator + Camera selects; `<img id="physics">` replaces the canvas in MuJoCo mode and plays each action's clip; stills are skipped while a run is active (they raced `/api/step` for `world_lock`).
  - Verified: 23 tests pass; real E4B run in the browser completed all nine actions in physics (0 V → seated → 5 V → finish). Evidence: `evidence/mujoco-gemma-success.json`, `evidence/mujoco-final.jpg`.
  - Gotcha: MuJoCo `Renderer` contexts on macOS deadlock when used from several FastAPI worker threads, so everything renders on `bench.GL` (a single-thread executor).
- ~18:20: applied Codex's read-only review (`codex exec -s read-only`): arm hulls + finger pads now collide with bench geometry and trip a collision guard; mesh capture requires sustained pin contact and ≤10° tilt; `held` is set at grasp and re-read from contacts after failures; physics observations report real fixture surfaces; `World.episode` + `Step.episode` reject stale steps across resets; `clip.webp?r=` is bound to its revision; the backend check happens inside `world_lock`. Not changed: Gemma still gets structured observations, not images (documented). 26 tests pass; 30/30 seeds succeed.

## Codex UI diagnosis
- User's existing tab still had the original canvas-only frontend while the server had switched to MuJoCo. Confirmed health loaded=true/busy=false and E4B decisions 0.94–1.22 seconds. The single step API includes physics execution after inference, so its old "Gemma is choosing" message was misleading. Changed the pending label to planning + simulation execution, and added explicit preparation/playback labels for MuJoCo clips. Refreshing the user's tab to load the current frontend. No physics or server changes.

## Codex active upgrade — please coordinate via this file
User authorized a quality/perception upgrade and requests any needed questions be relayed through Claude. I am implementing: (1) bounded-memory 1280x720 MP4 action playback with no repeat/jump-back and accurate phases, (2) calibrated rendered-camera ArUco perception with an explicit marker/object/grasp registry and measured poses used for motion; fail closed on missing detections. Will edit server/UI and narrowly integrate hooks into physics files. Please avoid overlapping edits until the completion note. User does not need to gather training data now; markers and taught grasp offsets are the initial transfer strategy. Please relay this status if they check remotely.

### Upgrade progress for Claude / remote user
- Added camera-only ArUco estimator (`perception.py`), taught registry and printable marker sheet. `VisualWorld` feeds measured poses to grasp/contact skills; missing target detection stops motion. Gemma now receives the rendered camera image as well as detections. This is explicitly marker-assisted, not pretrained free-form object localization.
- Five randomized jumper layouts complete the camera-guided sequence after fixture tuning. Thin 13mm probe handle was sensitive to pose error; a 19mm sleeve is now modeled. Actual fixtures must match or be measured/re-taught. Marker plates are optical-only (massless/no collision), a documented transfer limitation.
- Replacing looping WebP clips with streamed-to-encoder 720p/25fps MP4. Two browser video buffers hold the final frame during model/physics/render stages; camera changes locked during actions. Pending UI verification and full regression check.
- Physical preparation/teaching guide: SETUP-REAL-HARDWARE.md. No hardware commands enabled, no training job or duplicate Gemma process started.

### Codex handoff / ownership released
Implementation is ready for Claude to continue; no further broad edits planned. Camera-guided default and 720p MP4 pipeline are integrated. Added a sustained-grasp-contact guard and short lock wait so camera rendering cannot spuriously reject Run. Updated README and SETUP-REAL-HARDWARE.md; printable marker IDs and real-photo perception utility are available. Full technical status is appended to HANDOFF.md. Please relay to the user: no training dataset is needed for this first assisted setup; bring a stable camera mount, printed tags/calibration board, fixture dimensions, and actual arm/gripper/SDK details. The physical integration still requires measured calibration and primitive testing. Current live UI validation is running, and final verification will be appended next.
- Final live check exposed a premature safe abort by Gemma (valid 0V confused with failed contact). Preserved failed trace. Simplified model input and removed previous model rationales from its history; added regression coverage. Final run has now passed the earlier failure point and is re-probing the repaired circuit. All physics/perception checks still pass. Please keep this reliability caveat in remote updates; 20/20 layout results use a scripted task policy, not 20 independent Gemma trials.
### Final verification complete — ready for remote handoff
Final real E4B + rendered camera run succeeded in all 9 actions, 0V → 5V/LED ON, 1.39–1.77s per decision, zero formatting retries. 37 unique simulator tests and parent regressions pass. 20/20 camera-layout trials passed under ideal camera conditions with scripted task decisions; do not represent that as a 20-run model reliability benchmark. Server PID 29085, port8000, one warm E4B engine, no loop active, ~1.7GiB RSS. User can Reset then Run with Gemma. Final evidence and physical setup checklist are in HANDOFF.md. Please relay the upgrade summary and checklist to the user when they connect remotely. No outstanding question requires their immediate attention; actual hardware/camera calibration is the next dependency.

## Demo 2 — broken resistor (2026-10-23, user request relayed by Claude)
User wants a second, fully isolated demo: the probe proves the supply is fine (5 V) but the resistor's output node reads 0 V, so the resistor is open; the arm pulls the broken resistor module out, discards it, installs a spare, re-measures (≈2.0 V at the LED anode, LED lit) and finishes. **Demo 1 must not change.** Everything lives in `arm_sim/resistor/` (+ `config/resistor_objects.json`, `tests/test_resistor_*.py`). Demo-1 modules may be *imported* (Bench primitives, MarkerPerception, camera calibration, shared Gemma engine/lock, GL executor) but not edited. Only allowed demo-1 touches: `run.py` import line and one nav link in `static/index.html`.

Ownership: **Claude** — `resistor/{scene,bench,world}.py`, `config/resistor_objects.json`, `tests/test_resistor_physics.py`. **Codex** — `resistor/{app,planner}.py`, `resistor/static/*`, `tests/test_resistor_api.py`, run.py mount, demo selector.

### Contract (`arm_sim.resistor.world`)
- `ResistorConfig(scenario='open_resistor'|'healthy'|'supply_off'|'bad_spare', seed=7, perception='camera_markers'|'oracle')`
- `ResistorWorld(config)`: `.revision .episode .done .success .tool .events .measurements .bench .observer`(None in oracle mode)
  - `events[i] = dict(step, action, note, ok)`; `measurements[i] = dict(point='input'|'output', voltage=float|None, valid_contact, led_on, after_replacement)` (None = no probe contact, never 0 V)
  - `allowed()` → list of actions; `observation()` → JSON for Gemma (no hidden fault truth); `snapshot()` → observation + `electrical`(input_v, output_v, current_ma, led_on) + done/success/events/config/episode/backend/perception_mode
  - `step(action)` → `dict(before, frames, state)`; raises `ValueError` for disallowed actions
  - `refresh_perception()` (camera mode) → detections; `observer.rgb` is the last perception frame, `observer.last` its detections
  - `bench.video(camera, size=(720,1280))` → MP4 bytes of the last action; `bench.render(camera, size=...)` → RGB; `bench.close()`
  - Cameras: `overview`, `bench`, `top`, `perception`
- Actions: `pick_probe, measure_input, measure_output, dock_probe, remove_resistor, discard_resistor, pick_spare, insert_resistor, finish, abort`
- `scripted_action(world)` → reference policy. Nominal run (12 actions): pick_probe → measure_input 5 V → measure_output 0 V → dock_probe → remove_resistor → discard_resistor → pick_spare → insert_resistor → pick_probe → measure_output ≈2.0 V LED on → dock_probe → finish.
- Circuit: Arduino 5V → TP1 (input pad) → resistor socket → TP2 (output pad / LED anode) → red LED → GND. Open R: TP2 = 0 V (pulldown). Good 330 Ω: TP2 = Vf ≈ 2.0 V, 9.1 mA.

### Codex Demo-2 completion / ownership released
- Added isolated `resistor/app.py`, `planner.py`, and `static/{index.html,app.js,style.css}`: lazy world creation, shared E4B/lock, 20-action limit, episode/revision guards, reset/shutdown GL cleanup, two probe instruments, all four scenarios, camera/oracle selection, and double-buffered 720p MP4 playback. Step requires episode; the UI always supplies it. Planner strips model rationales from history, compacts detections, and permits one formatting retry.
- Only existing-code edits: demo-1 header selector and `run.py` mount import. No Claude-owned physics/config files touched. No server operations, Gemma loads, or commits.
- `tests/test_resistor_api.py` adds fake-world API/lifecycle checks, mocked planner context/retry coverage, and automatic real-world scripted tests for all four scenarios. Final poll: `resistor/world.py` was not yet present, so those four tests skipped.
- Validation: **29 passed, 4 skipped, 1 deselected** across resistor API/planner, existing planner context, kinematic simulation and non-rendering physics tests. JS syntax passes. Full `uv run pytest -q` attempted twice (with `UV_CACHE_DIR=/tmp/robot-circuit-uv-cache` due sandbox filesystem limits); collection fails in unchanged demo-1 `VisualWorld()` with MuJoCo `invalid CoreGraphics connection`. Claude should rerun the full suite outside this sandbox after the world lands, then perform the live Gemma/browser verification using the existing server/model. No full-suite or real-world success claim yet.

### Claude Demo-2 physics complete (2026-10-23 ~20:30)
- `resistor/{scene,bench,world}.py` + `config/resistor_objects.json` (marker IDs 6–11 new; probe 1 / dock 5 reused). `ResistorBench` subclasses demo-1 `Bench`; demo-1 files untouched.
- Findings worth knowing for hardware (and for demo 1): demo-1 `Bench.move` starts/stops at full speed; that jerk swings a gripped probe ~6 mm off its planned tip offset, which is what made docking fail. Demo 2 overrides `move` with a cubic time scaling, lifts to a 15 cm transit height, and turns the wrist in place (~75°/s) before crossing — a straight diagonal dragged the probe over the socketed module. Fixed fixtures keep their last sighting when the arm occludes them; parts must be seen live. Any failed skill leaves only `abort`.
- Verified: 20/20 camera-guided layouts (scripted), all four scenarios behave correctly, 57 tests pass, live E4B run 12/12 actions, 1.6–2.9 s/decision (`evidence/resistor-gemma-full-run.{mp4,json}`). Model rationales sometimes repeat stale facts (step 10 cites "0V" before measuring); allowed_actions keeps actions correct.

## Codex active B601-RS migration (2026-10-24)
User requested Seeed Studio reBot Arm B601-RS (6+1 DOF). Updating demo-1 physics arm with pinned official RS MJCF/meshes and adapter, testing existing repair sequence, updating UI/docs. Preserving demo-2 YAM behavior and original asset files. Please avoid demo-1 physics/UI edits until completion note. No hardware commands.
### B601-RS integration validated
All 60 simulator tests pass. Jumper MuJoCo now uses official RS arm/gripper; resistor remains YAM and passes regression tests. Pin/probe targets still come from rendered-camera markers. Important physical fixture changes and control limitations are in REBOT-B601-RS.md. New probe guide is 45 mm tall / 1 mm radial clearance. New pose solver rejects 180-degree orientation errors. Live E4B validation underway at port8000, PID17174; no overlapping edits needed.

### B601-RS complete / ownership released
Live E4B + camera run passed all 9 actions, 0V → 5V / LED ON, 1.41–1.81s decisions. Evidence and hardware caveats in HANDOFF.md and REBOT-B601-RS.md. Port8000 now serves the new arm for jumper demo; model warm, no loop running. User-facing browser left open at successful result.
