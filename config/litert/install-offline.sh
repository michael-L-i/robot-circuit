#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
[[ "$(uname -s)" == Linux && "$(uname -m)" == aarch64 ]] || { echo 'Requires Linux aarch64'; exit 1; }
python3 -c 'import sys; assert sys.version_info[:2] == (3,12), "This wheel bundle targets Python 3.12; regenerate wheels for other versions"'
sha256sum -c SHA256SUMS
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt
.venv/bin/litert-lm import "$PWD/gemma-4-E4B-it.litertlm" gemma4-e4b
echo 'Installed. Check free memory before starting the model.'
echo 'Start: .venv/bin/litert-lm serve --host 127.0.0.1 --port 9379 --config server.json'
