# Live Gemma board voice

Start the existing camera workbench and Jetson Ollama SSH tunnel, then:

```sh
uv run python ui/serve.py
```

Open http://127.0.0.1:8100 and click **Analyze board**. One click freezes the latest paired-phone frame (maximum age 30 seconds), sends that exact image to the configured Jetson Gemma model, displays its answer, and synthesizes speech through the Mac workbench's Kokoro service (macOS voice fallback). The orb animates while browser audio plays. Expand the frame label to inspect the exact source image. Play voice repeats speech only; Analyze board requests a new analysis. There is no automatic analysis loop or robot control.

`--upstream` defaults to the existing camera workbench on http://127.0.0.1:8000. `CIRCUIT_OLLAMA_URL` defaults to http://127.0.0.1:11435 and `CIRCUIT_OLLAMA_MODEL` to gemma4:31b. The connected Jetson is reused; no model is loaded on the Mac by this interface. The old simulator narration, canned action lines and mock trace playback have been removed from this version. `?mock=1` no longer activates any playback.

This uses the latest phone upload, not a remotely triggered camera shutter. The phone must remain open and upload frames. No frames are saved to disk. A visual observation cannot establish voltage, resistance or reliable electrical contact; the Bluetooth reader has not yet been wired into this UI.
