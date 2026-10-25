# LiteRT-LM migration — hardware validation pending

The current running Jetson demo still uses Ollama until the new service passes
an actual Jetson image request. Do not describe the migration as complete yet.

The tested client is `circuit_lab/litert_remote.py`. It uses the official
LiteRT-LM 0.18.1 OpenAI-compatible server, including image data URLs and SSE.
A real camera-image request, streaming and JSON output have been checked on the
Mac with Gemma E4B; that does not validate Jetson GPU execution.

## Jetson setup after authenticated SSH access

Inspect exact hardware, RAM, Python version and graphics drivers first. Use an
isolated environment; LiteRT-LM 0.18.1 has Linux aarch64 API wheels. The GPU
backend must be verified on this Jetson, not inferred from CUDA availability.

Install `litert-lm==0.18.1` in that environment. Copy the existing compatible
`models/gemma-4-E4B-it.litertlm` from the Mac or obtain the official model.
Register and start the service inside the environment:

```sh
litert-lm import /absolute/path/gemma-4-E4B-it.litertlm gemma4-e4b
litert-lm serve --host 127.0.0.1 --port 9379 --config /absolute/path/server.json
```

`server.json` requests GPU text/vision with an 8192-token context and thinking
off. Incompatible GPU configurations should fail explicitly. Do not silently
switch to CPU or Ollama and claim GPU LiteRT validation.

Forward Mac port11436 to Jetson localhost9379, verify `/v1/models`, then run a
real image completion with `LiteRTClient`. Stop/unload the Ollama model before
loading the second engine if memory headroom is insufficient.

## Switch only after successful hardware test

The live voice UI can be restarted independently of camera pairing:

```sh
uv run python ui/serve.py --runtime litert
```

For the complete workbench, use:

```sh
uv run --project projects/arm-sim --with qrcode==8.2 python scripts/run_workbench.py --config config/workbench-litert.toml --ssh-control-path /tmp/robot-circuit-jetson-control
```

Restarting the camera workbench changes its phone pairing token; re-pair the
phone. Verify the exact source frame, model answer, voice playback and runtime
status. The profile uses E4B, not the prior Ollama 31B weights. No model download,
installation or remote execution is hidden behind the UI button.

Sources:
- https://developers.google.com/edge/litert-lm/cli/openai_server
- https://developers.google.com/edge/litert-lm/cli/configuration
- https://developers.google.com/edge/litert-lm/python

## Locally staged offline bundle

`.cache/litert-jetson-transfer/` contains the Linux aarch64 LiteRT-LM 0.18.1
wheels and pinned dependencies, `server.json`, SHA-256 checksums, an installer,
and the existing E4B model (hard-linked on Mac to avoid duplicate storage).
This bundle targets Python 3.12 and glibc >= 2.27. Confirm the Jetson's Python
version before installing; regenerate wheels if it differs. Transfer the whole
folder using rsync or USB, then run `bash install.sh` on the Jetson. The installer
verifies checksums and creates an isolated environment, but does not start a
model or change the live demo. Python venv/pip must already be available there.
Authentication is still needed for network transfer. This bundle has not yet
been installed or validated on Jetson.

The installer source is tracked as `config/litert/install-offline.sh`; copy it
into the bundle as `install.sh` when rebuilding the bundle. It is intended to
run beside `wheels/`, `requirements.txt`, `SHA256SUMS` and the model, not directly
from the configuration directory.
