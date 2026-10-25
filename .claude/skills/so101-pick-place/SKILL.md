---
name: so101-pick-place
description: Run the SO101 arm demo that picks the black resistor block off the tape strip and places it across the copper gap, parallel to the strips. Use when the user says pick it up, place the block, run the arm, do it again, or /so101-pick-place.
---

# SO101 pick and place

The tuned pipeline lives in `scripts/so101_pick/`. Run it from the repo root with `.venv-robot/bin/python`. Keep replies to the user short.

1. **Camera:** `curl -s http://127.0.0.1:8000/api/phone/info`.
   - If the connection is refused, start the server in the background:
     `CIRCUIT_AUTO_INSPECT=0 uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_mac.py --port 8000 --https-phone > .cache/camera-server.log 2>&1`.
   - Then read `url` from the info endpoint and send it to the user so they can reopen it on the phone and tap Start camera. Wait until they confirm it is streaming.
2. **Run:** `.venv-robot/bin/python scripts/so101_pick/pickplace.py --verify`. It takes about 20 s. The arm must start at rest, with the block on the tape strip left of the board.
   - "using cached path" means it replays the approved path.
   - If the block moved more than 4 px, it re-plans, which takes about 8 s.
   - `--dry-run` plans without moving. `--slow 1.5` stretches every move.
3. **Check:** view `scripts/so101_pick/last_run.jpg`. Success means the block straddles the gap between the left and middle copper groups, parallel to the strips. Tell the user in one or two lines.

## Errors
- **No block in reach:** ask the user to put the block on the tape strip.
- **MISSED:** the arm has already returned to rest. Offer to retry.
- **No fresh camera frame:** the phone stopped streaming. Ask the user to reopen the camera link.
- If the user's hands are in the frame, wait before running.

## Tuning on request (small steps only)
- **Grip height:** `corr['pick_z'] + 0.009` in `build()` in `pickplace.py`. Change it 1 mm at a time, then run with `--replan`.
- **Drop position:** change `--target U V`. One pixel is about 0.5 mm, and +U moves the block right in the camera image. Or edit `dxy` in `corr.json`. Changing corr.json triggers a re-plan automatically.
- **Drop angle:** `dtheta` in `corr.json`, in degrees.
- **Phone moved:** the view no longer matches `reference_view.jpg`. Recompute `H_new2old.npy` with a SIFT homography from the current frame to `reference_view.jpg`, masking out x > 600.
