"""Start the Mac dashboard, phone pairing, speech, and a private Jetson tunnel."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/workbench.toml')
    parser.add_argument('--ssh-control-path', help='Optional existing authenticated SSH multiplex socket')
    parser.add_argument('--check', action='store_true', help='Check model and list Jetson devices, then exit')
    args = parser.parse_args()
    config = tomllib.loads(args.config.read_text())
    jetson, mac = config['jetson'], config['mac']
    runtime = jetson.get('runtime', 'ollama')
    if runtime not in ('ollama', 'litert'): parser.error('Unknown Jetson runtime')
    remote_port = int(jetson.get('remote_port', 9379 if runtime == 'litert' else 11434))
    if not args.check:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', mac['port'])) == 0:
                parser.error(f"Port {mac['port']} is already running. Stop the existing workbench first; use one server.")
    ssh = ['ssh', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=10',
           '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=10']
    if args.ssh_control_path:
        ssh += ['-S', args.ssh_control_path]
    target = f"{jetson['user']}@{jetson['host']}"
    port = int(jetson['tunnel_port'])
    url = f'http://127.0.0.1:{port}'
    print(f'Connecting to {target}. Enter its SSH password if prompted.', flush=True)
    # A real session keeps multiplexed SSH in the foreground for lifecycle monitoring.
    tunnel = subprocess.Popen(ssh + ['-T', '-L', f'127.0.0.1:{port}:127.0.0.1:{remote_port}', target, 'exec sleep infinity'])
    server = None
    try:
        for _ in range(120):
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited. Check the address, login, and whether the tunnel port is occupied.')
            try:
                with urllib.request.urlopen(url + ('/v1/models' if runtime == 'litert' else '/api/tags'), timeout=1) as response:
                    data = json.load(response)
                    models = [m['id'] for m in data['data']] if runtime == 'litert' else [m['name'] for m in data['models']]
                if jetson['model'] not in models:
                    raise RuntimeError(f"Model {jetson['model']} is not installed on the Jetson.")
                break
            except (OSError, ValueError):
                time.sleep(.5)
        else:
            raise RuntimeError('Jetson did not become ready. Check SSH and the configured inference service.')
        print(f"Ready: {jetson['model']} on Jetson. Speech output: this Mac.", flush=True)
        if args.check:
            subprocess.run(ssh + [target, 'python3 -'], input=(ROOT / 'scripts/jetson_status.py').read_text(),
                           text=True, check=True, timeout=30)
            return
        env = dict(os.environ, CIRCUIT_INFERENCE=runtime, CIRCUIT_REMOTE_RUNTIME=runtime)
        prefix = 'CIRCUIT_LITERT' if runtime == 'litert' else 'CIRCUIT_OLLAMA'
        env[prefix+'_URL'], env[prefix+'_MODEL'] = url, jetson['model']
        command = [sys.executable, str(ROOT / 'scripts/run_mac.py'), '--port', str(mac['port'])]
        if mac.get('with_simulator'):
            command.append('--with-simulator')
        if mac.get('https_phone'):
            command.append('--https-phone')
        server = subprocess.Popen(command, env=env, cwd=ROOT)
        while server.poll() is None:
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel disconnected. Restart this launcher after restoring the Jetson connection.')
            time.sleep(.5)
        if server.returncode:
            raise RuntimeError(f'Dashboard exited with status {server.returncode}.')
    except KeyboardInterrupt:
        pass
    finally:
        for process in (server, tunnel):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if args.ssh_control_path:
            subprocess.run(ssh + ['-O', 'cancel', '-L',
                           f'127.0.0.1:{port}:127.0.0.1:{remote_port}', target],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
