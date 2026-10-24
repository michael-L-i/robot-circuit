# Arm Circuit Sim

A local Gemma E4B task planner with a MuJoCo YAM Ultra robot, contact-based grasping, camera-measured targets, and electrical verification. Default: **MuJoCo physics + Camera / taught markers**. The older kinematic schematic and oracle-coordinate baseline remain explicit diagnostic options.

## Run

From the repository root:

```sh
uv sync --project projects/arm-sim
uv run --project projects/arm-sim python projects/arm-sim/run.py
```

Open **http://127.0.0.1:8000/sim/**. The existing webcam application remains at `/`. The system `ffmpeg` executable is required for MP4 playback (installed on this Mac). Run one server process/worker without hot reload; both apps share one E4B engine, model file and inference lock. Stop the old webcam-only server before using the combined server on port 8000.

Choose **Run with Gemma**. **Single step** runs one action. **Run scripted rehearsal** exercises the same perception/physics without model inference; it is explicitly labeled and never used as a silent AI fallback. Change a scenario, layout seed or perception mode and click **Reset** to apply it. Export the trace before Reset to retain it.

**Pause after action** stops at an action boundary; it does not interrupt native inference, simulated movement, or video playback already started. A hidden tab pauses further actions at the boundary. **Unload model** releases the shared engine. Model initialization is lazy, conversations are fresh, output is capped, action count is bounded, and no background model loop runs while idle.

## What happens

Camera image → marker ID and estimated pose → taught grasp/target offset → Gemma skill selection → guarded motion → contact/voltage/LED feedback.

1. Detect and pick up the probe.
2. Touch the test pad and read simulated voltage relative to ground.
3. Dock the probe, then pick the misplaced jumper.
4. Put its conductive pin on the copper mesh and release it.
5. Reacquire the probe and measure again, dock, then finish only if voltage and LED agree.

The example circuit is 5V → jumper → mesh → 330Ω → red LED → ground. A 100k pulldown defines the disconnected input at 0V. The probe reference is permanently grounded. An ideal 2V LED drop gives 9.09mA when connected. A missed probe contact is `null`, not 0V. Supply-off, reversed-LED and placement-offset scenarios cannot be declared repaired merely because motion completed.

## Perception and teaching

`arm_sim/perception.py` accepts only RGB pixels, camera calibration and an object registry. It has no simulator imports. OpenCV detects ArUco IDs and solves marker poses; known marker-to-target offsets produce robot-frame coordinates. The camera adapter supplies ideal simulated camera calibration, not object positions. Missing, duplicate, high-reprojection-error, tilted or out-of-workspace detections cannot authorize a target motion.

`config/objects.json` explicitly teaches which ID means probe, jumper, pad, mesh or dock, plus marker size and grasp/contact offsets. These are configuration assumptions, not learned weights. The initial task handles upright tools. Marker IDs are not natural visual recognition; the system does not claim to understand an arbitrary unmarked probe. `config/printable-markers.svg` provides exact-size 24mm tags for a matching physical setup.

`VisualWorld` reacquires targets before each skill. In this mode, no hidden object pose is substituted for a missing detection. Held-tool geometry can be estimated from a visible marker and retained in the gripper frame; if the held marker is occluded, explicitly taught tool geometry is used. Slip invalidates that assumption on real hardware and needs independent detection/recalibration. The physics backend still supplies simulated contact, voltage and LED feedback; these need actual sensors on hardware.

Gemma receives the rendered camera image, calibrated detections, tool state and sensor history. It selects a permitted high-level action, not arbitrary coordinates or joint commands. The deterministic controller guards sequence and success criteria. This is a constrained task planner with taught skills, not a trained general manipulation policy. Visual model explanations may still misdescribe details; motion and success are checked separately.

The **Oracle baseline** supplies exact simulated target geometry for debugging. Do not use its performance as evidence of camera-based transfer. The kinematic schematic uses simplified links and tolerance-based contacts; the default MuJoCo mode uses physical contact pairs instead.

## Physics and playback

- Official I2RT YAM Ultra v2 MJCF and linear_4310 gripper, retained license/provenance in `arm_sim/assets/mjcf/`. Actual hackathon hardware/revision remains unconfirmed.
- MuJoCo integrates at 2ms; position targets update at 50Hz. Flat finger pads grasp by friction/contact, not welded attachment to the gripper. Contact checks detect failed grasps/lifts, pad touch and pin/mesh closure.
- Link hull and fingertip collisions against bench fixtures stop a skill. Full self-collision and accurate cable dynamics are not implemented.
- Probe sleeve: 19mm diameter / 60mm length. Jumper housing: 9 × 9 × 24mm. The larger sleeve reduces sensitivity to small camera-pose errors; actual hardware must match or be retaught.
- Breadboard and mesh retention use weld constraints; optical marker flags have no mass/contact geometry. Nominal friction, actuator gains, ideal electronics and camera calibration are not physically identified parameters. Real calibration and primitive validation remain necessary.
- Replay is 1280×720 H.264 at 25fps. Frames stream into a two-thread ffmpeg encoder; no full RGB video batch is held in memory. The browser has two video buffers, plays each action once, then holds its final frame while the next action is planned/rendered. Blob URLs are revoked when reused. Camera changes are disabled during a run.
- Progress distinguishes perception, inference, physics and video rendering. Playback is a recording of the completed simulated action, not a live motor-control stream. The last voltage reading stays labeled as a sample until the next measurement.

## Physical transfer

Start with **[SETUP-REAL-HARDWARE.md](SETUP-REAL-HARDWARE.md)**: equipment, camera/base calibration, fixture dimensions, teaching grasps, voltage sensing and validating primitives. There is no enabled hardware driver. `hardware_contract.py` describes the future adapter boundary.

`python projects/arm-sim/scripts/perception_check.py --image ... --calibration ...` inspects a real photograph with measured calibration and produces detections only. It rejects the ideal simulator calibration. `scripts/print_markers.py` regenerates the marker sheet. No large photo dataset or training job is required for this initial marker-assisted approach; arbitrary unmarked objects and learned manipulation are separate future milestones.

## Demo 2 — open resistor (`/resistor/`)
Isolated in `arm_sim/resistor/` with its own scene, skills, task world, Gemma prompt, marker registry (`config/resistor_objects.json`) and UI; it imports demo-1 primitives but changes none of them. Circuit: Arduino 5V → TP1 → resistor socket → TP2 (LED anode) → red LED → GND, 100 kΩ pulldown on TP2.
The arm probes TP1 (5 V proves the supply) and TP2 (0 V with a dark LED ⇒ open resistor), docks the probe, pulls the resistor module (2-pin header on a grip block), drops it in the reject bin, installs the spare from the caddy, re-probes TP2 (≈2.0 V, 9.1 mA, LED on) and finishes. Scenarios: `open_resistor`, `healthy` (no swap), `supply_off` (abort, never blame the resistor), `bad_spare` (abort after one swap).
Motion differs from demo 1: cubic velocity profile, 15 cm transit height and in-place wrist turns, because abrupt starts swing a gripped probe off its calibrated tip offset. Checks: `tests/test_resistor_physics.py`, `tests/test_resistor_api.py`; 20/20 camera-guided layouts with the scripted policy; one live E4B run in `evidence/resistor-gemma-full-run.mp4`.

## Checks and evidence

```sh
uv run --project projects/arm-sim pytest projects/arm-sim/tests -q
uv run pytest -q
node --test tests/live-loop.test.mjs
```

Tests cover camera-guided repairs across selected layout seeds, position-estimate error, an independently moved object, blank camera rejection without motion, calibration resolution mismatch, oracle physics faults, state/API guards and MP4 responses. These tests do not prove real-world reliability. See `HANDOFF.md` and `COLLAB.md` for live validation, agent ownership and current limitations.

Official references: [I2RT SDK/models](https://github.com/i2rt-robotics/i2rt), [OpenCV ArUco pose estimation](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html), [MuJoCo modeling](https://mujoco.readthedocs.io/en/stable/modeling.html).
