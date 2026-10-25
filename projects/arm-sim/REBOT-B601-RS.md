# Seeed Studio reBot Arm B601-RS integration

The jumper demo (`/sim/`, MuJoCo mode) now uses Seeed's B601-RS mechanical model: six revolute arm joints and one gripper drive coupled to two sliding fingers. The independent resistor demo and legacy kinematic schematic retain YAM; they are not B601-RS simulations.

## Model source

Official source: https://github.com/Seeed-Projects/reBot-DevArm/tree/main/Rebot_Arm_description/RS

The exact commit is recorded in `arm_sim/assets/rebot_rs/SOURCE.json`. Original MJCF, license and provenance are retained alongside the adapted model. Mesh geometry, joint transforms, joint limits and inertial parameters are from the upstream RS model. Optional wrist-camera meshes are omitted because this demo uses an external calibrated camera.

`physics/rebot.py` configures the task tool frame, collision masks, gravity compensation and bounded position servos. These servos are simulation controllers, not a reproduction of the manufacturer's POS_VEL motor controller. No CAN, motor bridge or hardware commands are sent. Gripper drive force is deliberately limited for this task; it is not a calibrated force sensor.

## Transfer to the physical B601-RS

1. Follow the manufacturer's RS commissioning and zero-position procedure. Verify joint ordering, signs, units, limits and emergency stop with the actual controller.
2. Measure the physical tool centre and gripping surfaces. Confirm the real fingers, sleeves and fixtures match the modeled dimensions; re-teach grasp/contact offsets if they differ.
3. Calibrate the external camera to the robot base. Simulated camera calibration is not usable on a real camera.
4. Implement the same guarded action API using the manufacturer's driver. Validate approach, grasp, lift, dock and contact individually at low speed, using real observations and measured contact/voltage signals.
5. Enable the Gemma action-selection loop only after those routines pass physical tests. Gemma's action vocabulary is reusable; simulated joint trajectories and contact truth are not hardware measurements.

Official setup: https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/

The bench still models rigid tool sleeves, ideal electronics and fixture retention constraints. Flexible wires, physical contact-force reliability and marker mounts need hardware validation.

## Bench adaptation

The RS demo uses a taught fixed jaw orientation (yaw 0), 125 mm home/transit height and smooth cubic motion timing. The 19 mm probe sleeve sits in a 45 mm-high guide with 1 mm radial clearance. Match this holder on hardware or re-teach and revalidate docking. The stock RS finger meshes and collision pieces are retained; no YAM gripper or substitute fingers are attached.

The IK orientation error uses a quaternion logarithm: a 180-degree mismatch cannot be mistaken for success. Reach is checked against RS limits. Large injected placement errors can be unreachable; an IK refusal is not evidence that the circuit was repaired.
