# Gemma voice + transcript

One screen: an orb that moves while Gemma talks, Gemma's voice, and a live transcript line by line.
Doesn't modify anything else in the repo.

## Run
```sh
uv run --project projects/arm-sim python projects/arm-sim/run.py   # Michael's server
python ui/serve.py                                                  # this screen
```
Open **http://127.0.0.1:8100** and click once (browsers block audio until a click).
Start the run from Michael's UI at `127.0.0.1:8000/resistor/`; this screen speaks each Gemma decision.

No server? **http://127.0.0.1:8100/?mock=1** replays a recorded Gemma run. **R** restarts it.
Keys: **V** voice on/off. Fullscreen with the browser (Cmd+Ctrl+F).

## How it works
`serve.py` serves this folder and forwards `/api/*` to `127.0.0.1:8000/resistor`.
`app.js` polls `/api/state` every 0.5 s; each new `events[i].decision.reason` is spoken with the
browser's built-in voice (offline on macOS) and typed out word by word as it's spoken.
Near-repeat reasons are replaced with a short action line. Action wording lives in `ACTIONS` at the top of `app.js`.
