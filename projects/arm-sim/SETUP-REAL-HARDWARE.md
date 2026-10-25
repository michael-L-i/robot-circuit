> For the jumper demo’s current Seeed reBot B601-RS model and hardware commissioning requirements, see [REBOT-B601-RS.md](REBOT-B601-RS.md).

# From this simulation to the hackathon bench

## What this version demonstrates

The default is MuJoCo with camera-based marker localization. Gemma receives a rendered RGB image plus the marker detections and sensor history. OpenCV identifies the taught marker IDs and estimates their poses from pixels; a measured pose is required before an object-directed skill can move. Gemma selects a guarded skill, not joint commands. The explicit oracle baseline is available for isolating physics/controller bugs.

No robot-learning training job is required for this approach. The meanings of the five marker IDs and the marker-to-grasp/target offsets are deliberately taught in `config/objects.json`. This is assisted recognition, not unrestricted object recognition. Markers are rendered in the scene, including occlusion; the detector gets neither simulator segmentation masks nor object coordinates. The physics engine still uses ground truth for rendering, contact sensing and evaluation, as it must.

## Prepare these items

1. **Actual arm information:** exact model/revision, gripper type, SDK setup, host computer, connection method, joint calibration, and available teleoperation/teach mode. Confirm where the arm controller runs; the Mac can run Gemma even if the hardware SDK requires another host.
2. **Stable fixture:** mount the board, probe dock and mesh securely. The simulator assumes a 19 mm diameter probe sleeve, 60 mm handle length, and a 9 × 9 × 24 mm grippable jumper housing. Those are design assumptions, not measurements of your equipment. Match them physically or change the model and reteach the grasps.
3. **Marker mounts:** printable tags are in `config/printable-markers.svg`. Black marker squares are 24 mm. Keep the white border and print at actual size. The simulation uses side-mounted optical flags on the probe/jumper so fingers do not cover the IDs. Physical flag supports, weight, and collision geometry must be modeled after fabrication; the current tags are massless visual geometry.
4. **Camera and lighting:** a rigid camera mount viewing the handle markers, probe dock, pad and mesh. Use sufficient optical detail to resolve marker corners; extra pixels cannot compensate for blur or glare. Start with one fixed camera. If the arm hides targets, reposition it or add a second calibrated view. Do not pretend an occluded object has a fresh measured pose.
5. **Electrical sensing:** a ground-referenced voltage measurement path to the host, with a range appropriate to the actual supply and Arduino board. A probe is not itself a digital sensor. Establish how readings get from the probe/ADC to software, how missing contact is recognized, and how LED illumination is observed independently. The simulated 100k pulldown makes the open input voltage defined; validate the physical circuit before arm use.
6. **Ruler/calipers and a printed calibration board:** measure marker size, fixture surfaces, grasp points and tool tip offsets. These measurements are configuration, not model training.

## Configure in this order

1. Calibrate camera intrinsics and lens distortion with a checkerboard/ChArUco board at the final resolution and focus. Estimate and validate the camera-to-robot-base transform using known target points or a calibration procedure. Camera calibration and robot-base calibration are different steps.
2. Detect the printed IDs on a photograph. `scripts/perception_check.py` accepts real RGB photos, measured calibration JSON and the object registry, and outputs measured targets without moving hardware. Simulator calibration is explicitly rejected by this physical-photo utility. Do not use the simulator's perfect camera transform for the real camera.
3. Teach each grasp relative to its marker: orientation, grasp point, finger opening and approach/retreat clearance. Manually guide the actual arm if its SDK permits. Save the measured marker-to-grasp transform. This prototype's skills assume upright tools; arbitrary orientations require extending the skill, not merely changing a prompt.
4. Calibrate the held tool's tip relative to the gripper. The simulator can estimate this from a visible held marker and then retain it in the gripper frame, or use the explicitly taught geometry when occluded. Physical slippage invalidates that calibration; verify the grip and reacquire after each pickup.
5. Validate each primitive separately at low speed: approach, grasp, lift, dock, probe contact, mesh placement. Implement the hardware adapter using the actual SDK, robot feedback, speed/force limits, and stop controls. This repository has no live hardware implementation.
6. Connect voltage/LED feedback, then run the complete task. Save observations, estimates, robot feedback, action result, and the final electrical verification. A visible LED is not a substitute for a measured voltage.

## What to vary in simulation

Use Layout seed to change the jumper's initial location without editing perception or task code. Test missing markers, wrong calibration, changed illumination, shifted fixtures, failed grasps, supply-off and missed mesh contact. The present automated tests cover selected layout seeds and a blank/missing-camera observation; they are not an exhaustive robustness certificate. Score estimated positions against hidden scene truth only in evaluation. Before claiming transfer, measure repeatability and pose errors on the actual fixtures and tune the physical parameters to observed behavior.

MuJoCo contacts are an approximation. Current simplifications include ideal electronics; simulated voltage/contact/LED sensors; weld retention at the breadboard/mesh; massless marker plates; incomplete self-collision modeling; and nominal actuator/friction parameters. Successful simulated grasping does not establish real force, wire flexibility, or connector retention. The camera setup is ideal and noise-free until perturbation testing is added.

## Relevant references

- OpenCV marker poses and calibration: https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html
- Camera calibration: https://docs.opencv.org/4.12.0/dc/dbb/tutorial_py_calibration.html
- MuJoCo model/contact assumptions: https://mujoco.readthedocs.io/en/stable/modeling.html
- Official arm SDK/models: https://github.com/i2rt-robotics/i2rt
