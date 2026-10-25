"""Start the Mac/phone demo, optionally preserving the simulator in one process."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-simulator', action='store_true')
    parser.add_argument('--https-phone', action='store_true', help='Temporary HTTPS camera relay through Cloudflare')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--ssl-certfile')
    parser.add_argument('--ssl-keyfile')
    args = parser.parse_args()
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error('Provide both --ssl-certfile and --ssl-keyfile for HTTPS.')
    if args.https_phone and not shutil.which('cloudflared'):
        parser.error('Install the HTTPS helper first: brew install cloudflared')
    os.environ.setdefault('CIRCUIT_AUTO_INSPECT', '1')
    if args.with_simulator:
        sys.path.insert(0, str(ROOT / 'projects/arm-sim'))
        from arm_sim.app import combined_app as app
        import arm_sim.resistor.app  # Register the existing simulator.
    else:
        from circuit_lab.app import app
    from circuit_lab.phone import lan_ip
    import uvicorn
    tunnel = None
    if args.https_phone:
        from circuit_lab import phone
        tunnel = subprocess.Popen(['cloudflared', 'tunnel', '--no-autoupdate', '--protocol', 'http2',
                                   '--url', f'http://127.0.0.1:{args.port}',
                                   '--http-host-header', 'camera-relay.invalid'],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        def read_tunnel():
            for line in tunnel.stdout:
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if match:
                    phone.PUBLIC_URL = match.group(0)
                    print(f'HTTPS camera ready: {phone.PUBLIC_URL}/phone (pair with Mac QR)', flush=True)
                if 'ERR' in line:
                    print('[HTTPS camera] ' + line.strip(), flush=True)
        threading.Thread(target=read_tunnel, daemon=True, name='camera-https').start()
    scheme = 'https' if args.ssl_certfile else 'http'
    print(f'\nMac dashboard: {scheme}://127.0.0.1:{args.port}')
    print(f'iPhone (same Wi-Fi): {scheme}://{lan_ip()}:{args.port}/phone')
    print('Scan the QR on the Mac dashboard to pair. Voice plays automatically on this Mac.\n', flush=True)
    try:
        uvicorn.run(app, host='0.0.0.0', port=args.port, workers=1,
                    ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)
    finally:
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()


if __name__ == '__main__':
    main()
