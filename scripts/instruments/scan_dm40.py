"""Bounded DM40 BLE discovery. No mode changes, robot actions or GATT writes.
Run: uv run --with bleak python scripts/instruments/scan_dm40.py
"""
import asyncio
import json
import sys

async def main():
    if sys.platform == 'darwin':
        import CoreBluetooth
        auth = CoreBluetooth.CBManager.authorization()
        if auth in (1, 2):
            raise SystemExit('Bluetooth permission denied/restricted. Enable access for the launching app in macOS Privacy & Security > Bluetooth.')
        if auth == 0:
            print('Waiting for macOS Bluetooth permission; allow the launching app when prompted.', flush=True)
    from bleak import BleakScanner
    devices = await BleakScanner.discover(timeout=10, return_adv=True)
    found = []
    for device, adv in devices.values():
        name = adv.local_name or device.name or ''
        if name.upper().startswith('DM40'):
            found.append(dict(name=name,address=device.address,services=adv.service_uuids))
    print(json.dumps({'meters':found},indent=2),flush=True)
    if not found:
        print('No DM40 advertised. Enable Bluetooth on the meter, return to multimeter mode, and disconnect other meter apps.')

if __name__ == '__main__':
    try:
        asyncio.run(asyncio.wait_for(main(),timeout=25))
    except TimeoutError:
        raise SystemExit('Discovery timed out, possibly awaiting macOS Bluetooth permission. Run this command in your interactive terminal and allow Bluetooth.')
