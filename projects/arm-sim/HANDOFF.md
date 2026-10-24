# Claude Code / remote-agent handoff

## User intent and confirmed choices

Build a simulation first because the physical hackathon arm is shared. A breadboard with Arduino power, resistor, LED, and a misplaced positive jumper should be repaired by a robot. The arm picks up a voltage probe, touches an enlarged test region, docks the probe, grips the jumper, places it on a broad copper mesh connected to the correct net, and probes again to verify LED illumination. User confirmed **existing local Gemma 4 E4B**, not cloud Gemini, and **pick up / dock probe**. Exact hackathon arm and SDK are unknown; YAM Ultra is provisional. User authorized us to manage a subproject, iterate through a build/test loop, and provide this handoff for a Claude Code agent controlled from their phone. Keep memory managed. Do not load 12B or duplicate E4B engines.

## Location and launch

Repository: `/Users/michaelli/code.tmp/Hackathons/robot-circuit`
Subproject: `projects/arm-sim/` (ordinary isolated directory with its own pyproject and uv.lock, not nested Git).

```sh
uv sync --project projects/arm-sim
uv run --project projects/arm-sim python projects/arm-sim/run.py
```

Demo: http://127.0.0.1:8000/sim/
Existing webcam app: http://127.0.0.1:8000/
Health / shared engine: http://127.0.0.1:8000/api/health
Simulation state: http://127.0.0.1:8000/sim/api/state
Trace: http://127.0.0.1:8000/sim/api/trace

Only ONE server / ONE worker. Original webcam-only server was replaced with this combined server; its parent source files were not modified. `run.py` imports the parent app and mounts `/sim`. Both apps share `circuit_lab.app.vision` and its inference lock. Do not start a second model process on another port. Use `POST /sim/api/unload` or the UI's Unload model button to release memory when idle. Model is lazy-loaded and otherwise kept warm. No automatic background inference. Each run has at most 16 actions; traces are bounded; one UI request at a time. Browser loop pauses after current action if hidden. Stop is action-boundary pause, not emergency-stop hardware logic.

## Architecture

- `world.py`: guarded task state, ideal electrical circuit, mesh/probe contact, fault scenarios. Supplies observations and atomic simulated actions.
- `kinematics.py`: official YAM Ultra v1 URDF transforms and limits, FK, damped numerical IK, lift/traverse/descend trajectories, basic tabletop joint-origin bound.
- `planner.py`: actual local E4B, short JSON action/reason responses, allowed-action validation, fresh conversation and 180-token output cap. Invalid output stops; no silent scripted fallback.
- `app.py`: state/reset/step/unload/trace APIs, serialization and stale revision check.
- `static/`: self-contained canvas 3D projection (drag orbit, wheel zoom), instruments, controls, trace. No CDN/build tool.
- `hardware_contract.py`: typed future physical adapter boundary, no actual motor or sensor implementation.
- `tests/`: simulation and model-output validation tests.

The model receives structured observations, not rendered images; no new vision-to-pose calibration is implemented. Most action order is constrained by the controller; Gemma chooses the next permitted action and explains it. This is task-level reasoning with nominal kinematics, not general learned robot manipulation. Be candid about this.

Electrical detail: the mesh and test pad are the same input net; a simulated 100k pulldown gives a defined 0V when disconnected; the probe reference is permanently grounded. 5V supply, 330-ohm resistor, 2V LED ideal drop -> 9.09mA. Missed probe contact is null, not 0. A bad placement can finish moving without electrically connecting; post-placement measurement must catch this. A real mesh fixture must retain the released jumper.

## Continuation loop

1. Read current state and this file before changing anything; check for another active agent editing the same files.
2. Run relevant tests after meaningful changes. Use scripted mode for repeated development; use real Gemma sparingly to validate integration.
3. Inspect the UI and one complete model-driven repair; export trace as evidence.
4. Improve concrete deficiencies, record results here, and stop idle inference when done. Do not run an endless model benchmark or repeatedly download models.
5. Hardware port remains pending actual arm identification, calibration, physical probe/LED sensors, gripper fixture, collision/force checks, and primitive validation. Do not claim simulation proves the hardware repair.

## Work status

Implementation and initial 12 tests are complete. Real Gemma UI run is being verified as this file is first written. Further validation results are appended below before handoff. Initial model decisions were valid and took roughly 0.9–1.6 seconds each with this short prompt. These are local integration timings, not physical robot performance. No need for external keys.

The parent repository began with all its files untracked. Do not commit, overwrite, or clean unrelated parent files. The subproject has not been committed. No external messages have been sent.

## Verification update — 2026-10-23

- 15 subproject tests pass: successful repairs across multiple seeds, already-connected circuit, supply-off/reversed-LED/missed-contact failures, invalid actions, FK/limits/velocity checks, API roundtrip/stale-revision checks, invalid model response produces no movement, and input validation.
- Parent regressions: 26 Python tests and 2 JavaScript tests pass. Both Python suites report an existing ecosystem deprecation warning about httpx/TestClient, not a test failure.
- Browser UI was opened and the actual E4B selected all nine repair actions, including probe docking and post-repair measurement. It observed simulated 0V then 5V / LED ON / 9.09mA. Trace saved in `evidence/gemma-success.json`.
- Actual E4B missed-probe test: invalid contact -> null voltage -> dock probe -> abort, with no jumper move and no success claim. Trace saved in `evidence/gemma-probe-miss.json`.
- The first missed-probe test exposed a disallowed model action. Controller rejected it without state mutation. Prompt was clarified and one bounded correction attempt added; the repeated live test passed. There is still no scripted fallback for AI failures.
- Source URDF byte-for-byte verified against the pinned upstream commit; provenance includes SHA-256.
- A browser framing issue (upper arm clipped at home) was fixed by adjusting the default projection scale. Reload restores the previous action explanation and final status. Completed runs require Reset before running again.

`verify_live.py` is an optional bounded real-model missed-contact check using the already-running server. It resets shared state and unloads the model in a finally block. Do not run it while a user is using the demo.

Final state: the updated prompt was re-verified in a complete nine-action browser run. The demo remains open on its successful 5V/LED-ON result; click Reset for a fresh run. E4B was explicitly unloaded after verification, so it will cold-load on the next AI action. The combined server is left running (PID 30425 at handoff; verify before managing it). Screenshot: `evidence/simulator.png`. The simulation is ready for demonstration; the hardware integration described above is intentionally still unimplemented until actual hardware/calibration is available. No unattended inference loop remains.

## MuJoCo physics backend — Claude Code, 2026-10-23 evening

The default simulator is now MuJoCo physics (`arm_sim/physics/`, README section "MuJoCo physics backend"). Same actions, prompt and API. The difference is that grasps, probe contact and circuit closure come from MuJoCo contacts on the official YAM Ultra v2 MJCF + linear_4310 gripper. The UI's Simulator select switches back to the kinematic schematic. Real E4B completed the full nine-action repair in physics (`evidence/mujoco-gemma-success.json`). 8 physics tests: seeds, already-connected, missed mesh (28 mm), missed probe (25 mm), supply off, rendering. Coordination notes between agents are in `COLLAB.md`.

## Current upgrade — camera-guided MuJoCo + continuous playback (Codex)

This section supersedes earlier descriptions of the simulator as receiving only structured/oracle observations.

- **Default:** MuJoCo `VisualWorld`, `Camera + taught markers`. `MarkerPerception` takes RGB pixels, calibration, and a taught registry only; it cannot read scene state. Marker poses and known marker-to-grasp offsets drive the skills. `Oracle baseline` remains explicitly selectable for debugging.
- **Gemma now sees the camera:** each decision gets a rendered image plus estimated marker poses and sensor history, sharing the existing E4B engine. Expect ~3–4 seconds per warm image-based decision in the verified run, versus ~1 second for the old text-only prompt. This is not a new model or a training job.
- **Playback:** 720p H.264, 25fps, ffmpeg with two encoder threads, streamed frames, two browser video buffers. No WebP looping. The last frame remains visible during the next decision and rendering phase. Native video `ended`, not a guessed timeout, advances the loop. Progress distinguishes perception/inference/physics/rendering. A small server-lock wait prevents an immediate Run click racing a camera still render.
- **Scene:** proper 2.54mm visual terminal grid, visual marker flags/supports, 19mm-diameter gripper-friendly probe sleeve. The larger sleeve was necessary to tolerate measured pose error; do not assume the user's existing thin probe will behave the same. Reproduce or measure/retune this fixture physically. Marker plates/supports are still massless and non-colliding.
- **No hidden target fallback:** missing required markers stop before motion. Held-tool offsets can be estimated visually and retained in gripper coordinates; when that marker is hidden, explicit taught tool geometry is used, not simulator body pose. Sustained loss of fingertip contact stops motion. Real hardware needs corresponding grip/force feedback and revalidation after slip.
- **Evidence:** `evidence/camera-gemma-success.json` (real local vision+task model, full repair), `camera-layout-evaluation.json` (20 seeded layouts, camera poses and scripted high-level sequence; all succeeded under ideal calibration/lighting), `camera-calibration-and-detections.json`, and final UI evidence. Camera evaluation estimated the initial jumper grasp within approximately 0.4–3.6mm across the 20 layouts. Ground truth is read only by the scoring script.
- **Transfer kit:** `SETUP-REAL-HARDWARE.md`, `config/objects.json`, `config/printable-markers.svg`, `scripts/print_markers.py`, `scripts/perception_check.py`. The real-photo utility requires measured camera calibration and does not issue motor commands. IDs/offsets are taught, not learned semantic recognition. `scripts/evaluate_camera.py` performs a bounded 20-layout check without loading Gemma.
- **Testing:** full camera and baseline regression suites plus a new lost-grasp guard and render/step race test. See final verification appended below.

The exact physical arm, camera, fixtures, camera-to-base transform, sensor wiring and hardware driver remain unconfigured. No real CAN/serial actuation has been enabled. Do not describe sim success as proven physical transfer. Remaining robustness work includes calibration perturbations, lighting/blur/noise, displaced probe/dock/board, marker support mass/collisions, wire flexibility, real friction/force identification and camera/LED/voltage hardware integration. Existing task logic is constrained; it is not a general learned manipulation policy.

### Final reliability correction
A later real-model run safely aborted early after confusing a valid 0V sample with an invalid reading. That trace is retained as `evidence/camera-gemma-premature-abort.json` rather than discarded. Planner input is now compact: visible object names/estimated targets and sensor facts only; previous model-written rationales are not fed back into future prompts. A regression test proves that old explanations and large internal pose matrices are excluded without mutating the original observation. Formatting correction no longer suggests a failed-contact diagnosis when the actual reading is valid zero. This also reduced observed warm image-decision latency in the final check. Deterministic motion/success guards remain authoritative; model prose is not a trusted sensor.

Validation so far: 36 tests in the full simulator suite passed, and the newly added planner-history test passed separately (37 unique simulator tests). Parent 26 Python and 2 JavaScript regressions also pass. Final camera-guided live run and evidence refresh are in progress below.

### Final verification / running state
Final image-based Gemma run completed all nine actions with 0V → 5V and LED ON; all physics skills reported success. Updated input reduced decisions to **1.39–1.77 seconds** in this run, with zero formatting retries. Updated trace is `evidence/camera-gemma-success.json`; the earlier premature-abort trace is retained. Camera evidence: `evidence/camera-detections.jpg`; the corresponding calibration/detection JSON is also saved. Browser playback was verified as 1280×720, loop=false, ending at the final frame. The camera/Run race regression passes.

The live combined server is left running on port 8000 (PID 29085 at handoff; verify before managing processes), with ONE E4B engine warm and no autonomous loop active. RSS was approximately 1.7GiB after the final run, including renderer/model runtime buffers; no model copies or background training were started. Use Unload model if idle memory is preferred; do not start a second engine. The browser is left on the successful result in Bench webcam view; Reset starts a fresh camera-guided run. All 37 unique simulator tests have passed (36 in the full suite plus the final context regression), as have parent 26 Python/2 JS checks.

Ownership is released to Claude. Further improvement should target physical calibration and noisy/occluded perception, not claim that the 20 ideal-camera/scripted trials establish hardware reliability. The user authorized updates/questions through Claude's remote-control connection; read COLLAB.md before concurrent edits.
