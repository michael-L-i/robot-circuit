# Robot circuit simulation handoff

The current simulation work and Claude Code continuation context are in:
**[projects/arm-sim/HANDOFF.md](projects/arm-sim/HANDOFF.md)**.

Demo: http://127.0.0.1:8000/sim/

Start the combined webcam + simulator server from this directory:

```sh
uv run --project projects/arm-sim python projects/arm-sim/run.py
```

Use one server process only. It shares one local Gemma E4B engine across both apps. The simulation has its own environment and lockfile, and does not issue hardware commands. Read the full handoff before continuing or starting another model process.
