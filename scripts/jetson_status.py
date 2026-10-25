"""Read-only hardware inventory. Does not open serial devices or enable motors."""
import glob
import json
import urllib.request


def main():
    result = dict(serial_devices=sorted(glob.glob('/dev/serial/by-id/*')),
                  serial_ports=sorted(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')),
                  cameras=sorted(glob.glob('/dev/video*')), motion_enabled=False)
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as response:
            result['ollama'] = json.load(response)
    except Exception as exc:
        result['ollama_error'] = str(exc)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
